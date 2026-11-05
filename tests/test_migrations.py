"""Numbered schema migrations: each runs once, completely or not at all, and the app only ever
changes its schema through them."""
import re
import sqlite3
import threading
import types
from pathlib import Path

import pytest

from conftest import ophir_figures
from ophir_figures import migrations

ROOT = Path(ophir_figures.__file__).parent.parent


def connect(path):
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def run(path, **options):
    connection = connect(path)
    try:
        return migrations.migrate(connection, path, log=lambda message: None, **options)
    finally:
        connection.close()


def step(name, statement=None, fail=False):
    def apply(connection, context):
        if statement:
            connection.execute(statement)
        if fail:
            raise RuntimeError("boom")
    return types.SimpleNamespace(NAME=name, apply=apply)


@pytest.fixture
def fresh(tmp_path):
    path = tmp_path / "fresh.db"
    run(path)
    return path


# ---- the migrations themselves -------------------------------------------------------------------

def test_a_new_database_gets_every_migration_once(fresh):
    connection = connect(fresh)
    recorded = [(row["version"], row["name"]) for row in connection.execute("SELECT version,name FROM schema_migrations ORDER BY version")]
    connection.close()
    assert recorded == [(index + 1, module.NAME) for index, module in enumerate(migrations.MIGRATIONS)]
    assert run(fresh) == []


def test_start_up_switches_the_database_to_wal_and_seeds_the_first_admin(tmp_path, monkeypatch):
    path = tmp_path / "start.db"
    monkeypatch.setattr(ophir_figures.schema, "DB_PATH", str(path))
    ophir_figures.schema.init_database()
    ophir_figures.schema.init_database()
    connection = connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert [tuple(row) for row in connection.execute("SELECT username, role FROM users")] == [("admin", "admin")]
        assert [tuple(row) for row in connection.execute("SELECT name, is_default FROM watchlists")] == [("Wunschliste", 1)]
    finally:
        connection.close()


def test_the_database_is_copied_before_it_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    run(path)
    connection = connect(path)
    connection.execute("INSERT INTO users(username,display_name,password_hash,created_at) VALUES('tobi','Tobi','x','t')")
    connection.commit()
    connection.close()
    run(path, migrations=[*migrations.MIGRATIONS, step("later", "ALTER TABLE users ADD COLUMN later TEXT")])
    backup = tmp_path / f"old.db.before-migration-{len(migrations.MIGRATIONS) + 1:04d}"
    assert backup.is_file()
    connection = connect(backup)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    connection.close()
    assert "later" not in columns, "the copy is the database as it was"


# ---- the runner --------------------------------------------------------------------------------

def test_a_failing_migration_leaves_no_trace_and_is_not_recorded(tmp_path):
    path = tmp_path / "db.sqlite"
    steps = [
        step("one", "CREATE TABLE one (id INTEGER)"),
        step("two", "CREATE TABLE two (id INTEGER)", fail=True),
        step("three", "CREATE TABLE three (id INTEGER)"),
    ]
    with pytest.raises(RuntimeError, match="boom"):
        run(path, migrations=steps)
    connection = connect(path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
    connection.close()
    assert tables == {"schema_migrations", "one"} and versions == [1]

    steps[1] = step("two", "CREATE TABLE two (id INTEGER)")
    assert run(path, migrations=steps) == [2, 3], "the next start picks up where it stopped"


def test_only_what_is_new_runs(tmp_path):
    path = tmp_path / "db.sqlite"
    first = [step("one", "CREATE TABLE log (entry TEXT)"), step("two", "INSERT INTO log VALUES('two')")]
    assert run(path, migrations=first) == [1, 2]
    assert run(path, migrations=first + [step("three", "INSERT INTO log VALUES('three')")]) == [3]
    connection = connect(path)
    assert [row[0] for row in connection.execute("SELECT entry FROM log")] == ["two", "three"]
    connection.close()


def test_processes_starting_together_apply_each_migration_once(tmp_path):
    path = tmp_path / "db.sqlite"
    steps = [step("one", "CREATE TABLE log (entry TEXT)")] + [step(f"step {number}", f"INSERT INTO log VALUES('{number}')") for number in range(2, 8)]
    barrier, results, errors = threading.Barrier(4), [], []

    def worker():
        try:
            barrier.wait()
            results.append(run(path, migrations=steps))
        except Exception as error:  # noqa: BLE001 -- reported below
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert sorted(version for applied in results for version in applied) == list(range(1, 8))
    connection = connect(path)
    assert [row[0] for row in connection.execute("SELECT entry FROM log ORDER BY entry")] == [str(number) for number in range(2, 8)]
    connection.close()


def test_a_database_from_a_newer_version_is_refused(fresh):
    connection = connect(fresh)
    connection.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(99,'from the future','2027-01-01T00:00:00+00:00')")
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="Schema-Version 99"):
        run(fresh)


def test_a_new_database_is_not_copied_and_old_copies_are_cleared(tmp_path):
    path = tmp_path / "db.sqlite"
    steps = [step("one", "CREATE TABLE users (id INTEGER)")]
    run(path, migrations=steps)
    assert list(tmp_path.glob("*.before-migration-*")) == []
    for number in range(2, 6):
        steps.append(step(f"step {number}"))
        run(path, migrations=steps)
    assert sorted(item.name for item in tmp_path.glob("*.before-migration-*")) == ["db.sqlite.before-migration-0004", "db.sqlite.before-migration-0005"]


def test_scripts_run_inside_the_migrations_transaction(tmp_path):
    path = tmp_path / "db.sqlite"

    def apply(connection, context):
        context.run_script("""
          -- a comment; with a semicolon
          CREATE TABLE a (id INTEGER, note TEXT DEFAULT 'x;y');
          CREATE TABLE b (id INTEGER);
        """)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run(path, migrations=[types.SimpleNamespace(NAME="script", apply=apply)])
    connection = connect(path)
    assert {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"schema_migrations"}
    with pytest.raises(ValueError, match="incomplete"):
        migrations.Context(connection, "now").run_script("CREATE TABLE c (id INTEGER")
    connection.close()


# ---- how the app uses them -----------------------------------------------------------------------

def test_health_reports_the_schema_version(anonymous):
    health = anonymous.get("/health").get_json()
    assert health["schema_version"] == health["schema_expected"] == len(migrations.MIGRATIONS)


def test_migrations_are_numbered_without_gaps():
    numbers = [int(re.match(r"m(\d{4})_", module.__name__.rsplit(".", 1)[1]).group(1)) for module in migrations.MIGRATIONS]
    assert numbers == list(range(1, len(numbers) + 1))
    files = sorted(path.stem for path in (ROOT / "ophir_figures" / "migrations").glob("m[0-9]*.py"))
    assert files == [module.__name__.rsplit(".", 1)[1] for module in migrations.MIGRATIONS], "a migration file is not listed in MIGRATIONS"


def test_nothing_but_a_migration_changes_the_schema():
    pattern = re.compile(r"\b(CREATE\s+(UNIQUE\s+)?(TABLE|INDEX)|ALTER\s+TABLE|DROP\s+(TABLE|INDEX|COLUMN))\b", re.I)
    sources = [*(ROOT / "ophir_figures").glob("*.py")]
    offenders = [
        f"{path.name}:{number}" for path in sources
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line) and "TEMP TABLE" not in line and "schema_migrations" not in line
    ]
    assert offenders == []


@pytest.mark.parametrize("statement, index", [
    ("SELECT amount FROM price_observations WHERE figure_id=1 ORDER BY observed_at DESC, id DESC LIMIT 1", "idx_prices_figure"),
    ("SELECT * FROM collection_entries WHERE user_id=1 AND figure_id=2", "idx_collection_user"),
    ("SELECT * FROM collection_entries WHERE preorder_id=3", "idx_collection_preorder"),
    ("SELECT * FROM preorder_events WHERE preorder_id=1 ORDER BY id", "idx_preorder_events"),
    ("SELECT * FROM watchlist_entries WHERE figure_id=1", "idx_watchlist_entries_figure"),
    ("SELECT id FROM figures WHERE jan='4580590123456'", "idx_figures_jan"),
])
def test_frequent_lookups_use_an_index(statement, index):
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    try:
        plan = " ".join(row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}"))
    finally:
        connection.close()
    assert index in plan, plan
