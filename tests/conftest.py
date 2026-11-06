"""Shared test setup.

The app opens its database at import time, so DATABASE_PATH has to point at a throwaway file
before the package is imported -- which is why that happens here, at module level, rather than in
a fixture. Every test then starts from the same small catalogue (see SAMPLE_FIGURES) with no user
data. Nothing in the suite touches the network: fetches go through ophir_figures.fetch.fetch,
which the tests that need it replace (fake_fetch).
"""
import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = Path(tempfile.mkdtemp(prefix="ophir-figures-tests-"))
os.environ["DATABASE_PATH"] = str(DATA_DIR / "ophir-figures.test.db")
atexit.register(shutil.rmtree, DATA_DIR, ignore_errors=True)
os.environ.pop("SECRET_KEY", None)

import ophir_figures  # noqa: E402

DEMO = ("demo", "figuren-1234")
ADMIN = ("admin", "admin")
STAMP = "2026-01-01T00:00:00+00:00"

# Ids of the sample catalogue the tests refer to by name.
MIKU, FRIEREN, REM, MIKASA, TWINS = 1, 2, 3, 4, 5
SAMPLE_FIGURES = (
    (MIKU, "Hatsune Miku: Racing 2024 Ver.", "初音ミク レーシング2024Ver.", "Hatsune Miku", "Vocaloid", "Good Smile Company", "Scale-Figur", "", "1/7",
     "2025-03", 22000, "4580590123456"),
    (FRIEREN, "Nendoroid Frieren", "", "Frieren", "Frieren: Beyond Journey's End", "Good Smile Company", "Nendoroid", "Nendoroid", "Non-Scale",
     "2024-08", 6800, ""),
    (REM, "figma Rem", "", "Rem", "Re:Zero", "Max Factory", "figma", "figma", "Non-Scale", "2023-11", 8800, ""),
    (MIKASA, "POP UP PARADE Mikasa Ackerman", "", "Mikasa Ackerman", "Attack on Titan", "Good Smile Company", "Non-Scale-Figur", "POP UP PARADE",
     "Non-Scale", "2022-05", 3900, ""),
    (TWINS, "Rem & Ram: Twins Ver.", "", "Rem, Ram", "Re:Zero", "Kadokawa", "Scale-Figur", "", "1/7", "2026-12", 39800, ""),
)


def add_users():
    """The suite's accounts: demo (id 1), an ordinary user, and admin (id 2), in place of the
    admin the app seeds."""
    from werkzeug.security import generate_password_hash
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DELETE FROM users")
    connection.executemany("INSERT INTO users(id, username, display_name, password_hash, role, created_at) VALUES(?,?,?,?,?,?)", [
        (1, "demo", "Alex Morgan", generate_password_hash(DEMO[1]), "user", STAMP),
        (2, "admin", "Ophir Figures Admin", generate_password_hash("admin"), "admin", STAMP),
    ])
    connection.commit()
    connection.close()
    ophir_figures.schema.init_database()


def add_figures():
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    connection.executemany(
        """INSERT INTO figures(id,name,original_name,characters,series,manufacturer,category,line,scale,release_date,msrp,jan,
                               msrp_currency,created_by,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'JPY',2,?,?)""",
        [(*figure, STAMP, STAMP) for figure in SAMPLE_FIGURES],
    )
    connection.commit()
    connection.close()


def query(statement, args=()):
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(statement, args)]
        connection.commit()
        return rows
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def fresh_database():
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    connection.execute("PRAGMA foreign_keys=OFF")
    tables = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_migrations'"
    for (table,) in connection.execute(tables).fetchall():
        connection.execute(f"DELETE FROM {table}")
    connection.execute("DELETE FROM sqlite_sequence")
    connection.commit()
    connection.close()
    add_users()
    add_figures()
    yield


def login(credentials=DEMO):
    client = ophir_figures.app.test_client()
    if credentials:
        assert client.post("/login", data={"username": credentials[0], "password": credentials[1]}).status_code == 302
    return client


@pytest.fixture
def client():
    return login()


@pytest.fixture
def admin():
    return login(ADMIN)


@pytest.fixture
def anonymous():
    return login(None)


def default_list(client):
    return next(item["id"] for item in client.get("/api/watchlists").get_json() if item["is_default"])


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replaces every outgoing request: register answers with pages[url] = (content type, bytes)
    or an exception to raise."""
    from ophir_figures import fetch as fetch_module
    pages = {}
    requested = []

    def fetch(url, max_bytes, accept="*/*", session=None):
        requested.append(url)
        answer = pages.get(url)
        if answer is None:
            raise fetch_module.FetchError("Die Seite antwortet mit Fehler 404.")
        if isinstance(answer, Exception):
            raise answer
        content_type, body = answer
        if len(body) > max_bytes:
            raise fetch_module.FetchError("Die Antwort ist zu groß.")
        return url, content_type, body

    for module in (fetch_module, ophir_figures.images, ophir_figures.link_import):
        monkeypatch.setattr(module, "fetch", fetch)
    return type("FakeWeb", (), {"pages": pages, "requested": requested})()


def png_bytes(color=(200, 30, 60), size=(40, 60)):
    return picture_bytes("PNG", color, size)


def avif_bytes(color=(30, 120, 200), size=(40, 60)):
    """Made with Pillow here, so no binary fixture has to live in the repository."""
    return picture_bytes("AVIF", color, size)


def picture_bytes(image_format, color=(200, 30, 60), size=(40, 60)):
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, image_format)
    return buffer.getvalue()
