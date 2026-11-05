"""What a database is seeded with, and bringing it up to date at start-up. The schema itself
is defined by the migrations in ophir_figures/migrations."""

import os
import sqlite3

from werkzeug.security import generate_password_hash

from .config import APP_NAME, DB_PATH, now_iso
from .migrations import migrate

DEFAULT_WATCHLIST = "Wunschliste"


def seed_database(connection):
    """The first account, admin/admin, on an empty database. There is no demo data."""
    if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    connection.execute(
        "INSERT INTO users(username, display_name, password_hash, role, created_at) VALUES(?,?,?,?,?)",
        ("admin", f"{APP_NAME} Admin", generate_password_hash("admin"), "admin", now_iso()),
    )


def ensure_user_lists(connection, user_id=None):
    """Every account has a default wishlist. Idempotent; runs for all accounts at start-up and for
    one account right after it is created (admin, SSO auto-provisioning), so its first "add to
    wishlist" never finds no list."""
    connection.execute(
        """INSERT OR IGNORE INTO watchlists(user_id,name,is_default,created_at)
           SELECT u.id,?1,1,?2 FROM users u
           WHERE (?3 IS NULL OR u.id=?3)
             AND NOT EXISTS(SELECT 1 FROM watchlists w WHERE w.user_id=u.id AND w.is_default=1)""",
        (DEFAULT_WATCHLIST, now_iso(), user_id),
    )


def init_database():
    """Brings the database to the current schema, then makes sure the first account and every
    account's default list are there. Runs at import, in every process that loads the app."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        # WAL lets readers and the one writer work side by side. The mode is stored in the
        # database file itself, so setting it once here covers every later connection.
        connection.execute("PRAGMA journal_mode = WAL")
        migrate(connection, DB_PATH)
        # Gunicorn workers can import the app concurrently on a fresh volume.
        # Serialize the one-time seed so both workers never insert the first admin.
        connection.execute("BEGIN IMMEDIATE")
        seed_database(connection)
        ensure_user_lists(connection)
        connection.commit()
    finally:
        connection.close()
