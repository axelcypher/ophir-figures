"""Paths, constants and the helpers everything else leans on. Imports nothing from the package."""

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


# The repository root: templates and static files live there.
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("DATABASE_PATH", str(ROOT / "ophir-figures.db"))
DATA_DIR = Path(os.path.dirname(os.path.abspath(DB_PATH)))
# Figure pictures: the original of every picture (downloaded from a source or uploaded) and the
# thumbnails made from it. Uploads cannot be fetched again, so the folder belongs in the backup.
IMAGE_DIR = DATA_DIR / "figure-images"
THUMB_DIR = DATA_DIR / "figure-thumbnails"
# Optional SSO config file mounted into the container. When present it is the sole source of
# truth for OAuth settings and the Admin UI renders it read-only; when absent, OAuth settings live
# in the app_settings table and are fully editable from Admin.
OAUTH_CONFIG_PATH = os.environ.get("OAUTH_CONFIG_PATH", "/config/oauth.json")
# Shared sign-in with the other Ophir apps on one host (ophir_auth.py, docs/code/shared-auth.md):
# standalone (default), master (signs people in for all of them under AUTH_PATH) or slave (takes
# the master's sign-in). Read through the module (config.AUTH_MODE) so tests can switch it.
AUTH_MODE = os.environ.get("OPHIR_AUTH_MODE", "standalone").strip().lower() or "standalone"
# Where the master serves sign-in on the shared host, and where it sends people after a sign-in
# there that did not say where to go (OPHIR_AUTH_HOME, e.g. /figures/).
AUTH_PATH = "/" + os.environ.get("OPHIR_AUTH_PATH", "/auth").strip().strip("/")
AUTH_HOME = os.environ.get("OPHIR_AUTH_HOME", "/").strip() or "/"
# Fixed since there's only ever one configured provider -- kept as a named constant so
# users.oauth_provider reads as "which identity system", not a magic string at every call site.
OAUTH_PROVIDER_KEY = "generic"
OAUTH_CONFIG_DEFAULTS = {
    "enabled": False, "provider_name": "SSO", "client_id": "", "client_secret": "",
    "discovery_url": "", "authorize_url": "", "token_url": "", "userinfo_url": "",
    "scopes": "openid email profile", "username_claim": "preferred_username",
    "email_claim": "email", "subject_claim": "sub", "account_matching": "auto_provision",
}
APP_NAME = "Ophir Figures"
# Every amount a user enters (purchase price, preorder price, market value) is in this currency;
# a retail price (MSRP) keeps the currency it was announced in.
CURRENCY = "EUR"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def jload(value, default=None):
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def slug(value):
    """'Hatsune Miku: Racing 2024 (1/7)' -> 'hatsune-miku-racing-2024-1-7'."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
