"""The page shell, what the app loads first (bootstrap) and the dashboard's data."""

from flask import jsonify, render_template

from .auth import resolve_oauth_config
from .collection import CONDITIONS, dashboard_collection
from .config import CURRENCY, jload
from .figures import CATEGORIES
from .preorders import STATUSES, dashboard_preorders
from .watchlists import lists_of
from .web import app, db, login_required, user_id


@app.get("/")
@login_required
def index():
    return render_template("index.html")


def counts(uid):
    connection = db()
    return {
        "collection": connection.execute("SELECT COUNT(DISTINCT figure_id) FROM collection_entries WHERE user_id=?", (uid,)).fetchone()[0],
        "wished": connection.execute(
            "SELECT COUNT(DISTINCT we.figure_id) FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=?", (uid,)).fetchone()[0],
        "preorders": connection.execute(
            "SELECT COUNT(*) FROM preorders WHERE user_id=? AND status IN ('ordered','paid','shipped')", (uid,)).fetchone()[0],
        "catalog": connection.execute("SELECT COUNT(*) FROM figures").fetchone()[0],
    }


@app.get("/api/bootstrap")
@login_required
def bootstrap():
    uid = user_id()
    current = db().execute("SELECT id,username,display_name,role,email,oauth_subject,password_hash FROM users WHERE id=?", (uid,)).fetchone()
    settings = {row["key"]: jload(row["value"], row["value"]) for row in db().execute("SELECT key,value FROM user_settings WHERE user_id=?", (uid,))}
    user_payload = {key: current[key] for key in ("id", "username", "display_name", "role", "email")}
    user_payload["oauth_linked"] = bool(current["oauth_subject"])
    user_payload["password_set"] = bool(current["password_hash"])
    oauth_config = resolve_oauth_config()
    imports = [dict(row) for row in db().execute("SELECT id,created_at,undone_at FROM import_operations WHERE user_id=? ORDER BY id DESC LIMIT 4", (uid,))]
    return jsonify({
        "user": user_payload, "settings": settings, "counts": counts(uid), "watchlists": lists_of(uid), "imports": imports,
        "oauth": {"enabled": oauth_config["enabled"], "provider_name": oauth_config["provider_name"]},
        "conditions": CONDITIONS, "statuses": STATUSES, "categories": list(CATEGORIES), "currency": CURRENCY,
    })


@app.get("/api/dashboard")
@login_required
def dashboard():
    uid = user_id()
    return jsonify({"collection": dashboard_collection(uid), "preorders": dashboard_preorders(uid), "counts": counts(uid)})
