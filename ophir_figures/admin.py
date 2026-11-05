"""Admin API: accounts, SSO settings and a look over the shared catalogue."""

import json
import re
from pathlib import Path

from flask import jsonify, request
from werkzeug.security import generate_password_hash

from .config import OAUTH_CONFIG_DEFAULTS, OAUTH_CONFIG_PATH, jload, now_iso
from .web import admin_required, app, db, user_id
from .schema import ensure_user_lists
from .auth import resolve_oauth_config


# ---- User management (admin) -------------------------------------------------------------------
USERNAME_PATTERN = r"[a-zA-Z0-9._-]{3,32}"
EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"
USER_ROLES = ("user", "admin")


def user_fields_error(connection, payload, user_id_to_skip=0, require=()):
    """Validates the account fields present in `payload`; returns an error text or None."""
    for field in require:
        if not str(payload.get(field) or "").strip():
            return {"username": "Benutzername ist erforderlich.", "password": "Passwort ist erforderlich."}[field]
    if "username" in payload:
        username = str(payload["username"] or "").strip()
        if not re.fullmatch(USERNAME_PATTERN, username):
            return "Benutzername muss 3-32 Zeichen lang sein (Buchstaben, Zahlen, . _ -)."
        if connection.execute("SELECT 1 FROM users WHERE lower(username)=lower(?) AND id!=?", (username, user_id_to_skip)).fetchone():
            return "Benutzername ist bereits vergeben."
    if payload.get("email"):
        email = str(payload["email"]).strip()
        if not re.fullmatch(EMAIL_PATTERN, email):
            return "E-Mail-Adresse ist ungültig."
        if connection.execute("SELECT 1 FROM users WHERE email!='' AND lower(email)=lower(?) AND id!=?", (email, user_id_to_skip)).fetchone():
            return "E-Mail-Adresse wird bereits von einem anderen Konto verwendet."
    if payload.get("password") and len(str(payload["password"])) < 8:
        return "Das Passwort muss mindestens 8 Zeichen lang sein."
    if "role" in payload and payload["role"] not in USER_ROLES:
        return "Unbekannte Rolle."
    return None


def other_admins(connection, uid):
    return connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND id!=?", (uid,)).fetchone()[0]


@app.get("/api/admin/users")
@admin_required
def admin_list_users():
    rows = db().execute(
        """SELECT u.id,u.username,u.display_name,u.email,u.role,u.created_at,
                  u.oauth_subject!='' oauth_linked, u.password_hash!='' password_set,
                  (SELECT COALESCE(SUM(quantity),0) FROM collection_entries c WHERE c.user_id=u.id) copies,
                  (SELECT COUNT(*) FROM preorders p WHERE p.user_id=u.id AND p.status IN ('ordered','paid','shipped')) preorders
           FROM users u ORDER BY lower(u.username)"""
    ).fetchall()
    return jsonify([{**dict(row), "is_self": row["id"] == user_id()} for row in rows])


@app.post("/api/admin/users")
@admin_required
def admin_create_user():
    p = request.get_json(force=True)
    if not isinstance(p, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    error = user_fields_error(db(), p, require=("username", "password"))
    if error:
        return jsonify({"error": error}), 400
    username = str(p["username"]).strip()
    cur = db().execute(
        "INSERT INTO users(username,display_name,password_hash,role,created_at,email) VALUES(?,?,?,?,?,?)",
        (username, str(p.get("display_name") or "").strip() or username, generate_password_hash(str(p["password"])),
         p.get("role") or "user", now_iso(), str(p.get("email") or "").strip()),
    )
    ensure_user_lists(db(), cur.lastrowid)
    db().commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.patch("/api/admin/users/<int:target_id>")
@admin_required
def admin_update_user(target_id):
    target = db().execute("SELECT * FROM users WHERE id=?", (target_id,)).fetchone()
    if not target:
        return jsonify({"error": "Konto nicht gefunden."}), 404
    p = request.get_json(force=True)
    if not isinstance(p, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    error = user_fields_error(db(), p, user_id_to_skip=target_id)
    if error:
        return jsonify({"error": error}), 400
    if p.get("role") == "user" and target["role"] == "admin" and not other_admins(db(), target_id):
        return jsonify({"error": "Das letzte Admin-Konto kann nicht herabgestuft werden."}), 400
    fields, values = [], []
    for key in ("username", "display_name", "email", "role"):
        if key in p:
            value = str(p[key] or "").strip()
            if key == "display_name" and not value:
                continue
            fields.append(f"{key}=?")
            values.append(value)
    if p.get("password"):
        fields.append("password_hash=?")
        values.append(generate_password_hash(str(p["password"])))
    if p.get("unlink_oauth"):
        fields += ["oauth_provider=''", "oauth_subject=''"]
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    db().execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", (*values, target_id))
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/admin/users/<int:target_id>")
@admin_required
def admin_delete_user(target_id):
    target = db().execute("SELECT role FROM users WHERE id=?", (target_id,)).fetchone()
    if not target:
        return jsonify({"error": "Konto nicht gefunden."}), 404
    if target_id == user_id():
        return jsonify({"error": "Das eigene Konto kann hier nicht gelöscht werden."}), 400
    if target["role"] == "admin" and not other_admins(db(), target_id):
        return jsonify({"error": "Das letzte Admin-Konto kann nicht gelöscht werden."}), 400
    # Everything the account entered goes with it (ON DELETE CASCADE on user_id); the catalogue
    # and market values are shared and stay, only no longer credited to the account.
    db().execute("DELETE FROM users WHERE id=?", (target_id,))
    db().commit()
    return jsonify({"deleted": True})


# ---- Catalogue overview (admin) ----------------------------------------------------------------

@app.get("/api/admin/catalog")
@admin_required
def admin_catalog_overview():
    """Every figure with how many accounts use it, and groups of figures that look like the same
    product (same JAN, or same name and manufacturer), so duplicates can be merged."""
    rows = [dict(row) for row in db().execute(
        """SELECT f.id,f.name,f.manufacturer,f.edition,f.jan,f.release_date,f.created_at,u.display_name created_by_name,
                  (SELECT COUNT(DISTINCT user_id) FROM collection_entries c WHERE c.figure_id=f.id) owners,
                  (SELECT COUNT(*) FROM preorders p WHERE p.figure_id=f.id) preorders,
                  (SELECT COUNT(*) FROM watchlist_entries w WHERE w.figure_id=f.id) wished
           FROM figures f LEFT JOIN users u ON u.id=f.created_by ORDER BY lower(f.name)""")]
    groups = {}
    for row in rows:
        keys = [f"jan:{row['jan']}"] if row["jan"] else []
        keys.append("name:" + re.sub(r"\W+", "", f"{row['name']}|{row['manufacturer']}".lower()))
        for key in keys:
            groups.setdefault(key, []).append(row["id"])
    duplicates = [ids for ids in {tuple(ids) for ids in groups.values() if len(ids) > 1}]
    return jsonify({"figures": rows, "duplicates": sorted(duplicates), "unused": [row["id"] for row in rows if not (row["owners"] or row["preorders"] or row["wished"])]})


@app.post("/api/admin/catalog/merge")
@admin_required
def admin_merge_figures():
    """Moves everything that refers to `source` over to `target` and deletes `source`."""
    payload = request.get_json(force=True) or {}
    try:
        source, target = int(payload.get("source")), int(payload.get("target"))
    except (TypeError, ValueError):
        return jsonify({"error": "Quelle und Ziel fehlen."}), 400
    if source == target:
        return jsonify({"error": "Quelle und Ziel sind dieselbe Figur."}), 400
    connection = db()
    if connection.execute("SELECT COUNT(*) FROM figures WHERE id IN (?,?)", (source, target)).fetchone()[0] != 2:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    for table in ("collection_entries", "preorders", "price_observations"):
        connection.execute(f"UPDATE {table} SET figure_id=? WHERE figure_id=?", (target, source))
    # A list that has both keeps the target's entry.
    connection.execute("""DELETE FROM watchlist_entries WHERE figure_id=?1
                          AND list_id IN (SELECT list_id FROM watchlist_entries WHERE figure_id=?2)""", (source, target))
    connection.execute("UPDATE watchlist_entries SET figure_id=? WHERE figure_id=?", (target, source))
    connection.execute("DELETE FROM figures WHERE id=?", (source,))
    connection.commit()
    return jsonify({"merged": True})


@app.delete("/api/admin/catalog/<int:figure_id>")
@admin_required
def admin_delete_figure(figure_id):
    from .figures import in_use
    if in_use(db(), figure_id):
        return jsonify({"error": "Die Figur wird noch verwendet; erst zusammenführen."}), 409
    if not db().execute("DELETE FROM figures WHERE id=?", (figure_id,)).rowcount:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    db().commit()
    return jsonify({"deleted": True})


@app.get("/api/admin/oauth")
@admin_required
def admin_get_oauth():
    config = resolve_oauth_config()
    response = {key: value for key, value in config.items() if key != "client_secret"}
    response["client_secret_set"] = bool(config.get("client_secret"))
    response["config_path"] = OAUTH_CONFIG_PATH
    return jsonify(response)


@app.post("/api/admin/oauth")
@admin_required
def admin_save_oauth():
    if Path(OAUTH_CONFIG_PATH).is_file():
        return jsonify({"error": f"OAuth wird über die Config-Datei {OAUTH_CONFIG_PATH} verwaltet und kann hier nicht bearbeitet werden."}), 400
    if resolve_oauth_config()["source"] == "environment":
        return jsonify({"error": "OAuth wird über die Umgebungsvariablen OAUTH_* verwaltet und kann hier nicht bearbeitet werden."}), 400
    p = request.get_json(force=True) or {}
    if p.get("account_matching") not in ("manual", "email", "auto_provision"):
        return jsonify({"error": "Ungültiger Wert für account_matching."}), 400
    row = db().execute("SELECT value FROM app_settings WHERE key='oauth_config'").fetchone()
    current = jload(row["value"], {}) if row else {}
    config = {**OAUTH_CONFIG_DEFAULTS, **current}
    for key in ("enabled",):
        config[key] = bool(p.get(key))
    for key in ("provider_name", "client_id", "discovery_url", "authorize_url", "token_url", "userinfo_url",
                "scopes", "username_claim", "email_claim", "subject_claim", "account_matching"):
        if key in p:
            config[key] = str(p[key] or "").strip()
    # Blank client_secret in the payload means "leave the stored secret unchanged" -- the GET
    # response above never sends the real secret back, so the form field is blank by default
    # and a save that doesn't touch it must not wipe it out.
    if p.get("client_secret"):
        config["client_secret"] = p["client_secret"]
    db().execute(
        "INSERT INTO app_settings(key,value) VALUES('oauth_config',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (json.dumps(config),),
    )
    db().commit()
    return jsonify({"saved": True})
