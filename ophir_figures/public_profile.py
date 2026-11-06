"""A public, shareable view of a user's collection: /u/<slug>, readable without signing in.

The user switches it on in Settings and decides whether the wishlist is shown too. A visitor sees
the figures of the collection (and, if shared, of the default wishlist) with their pictures and
catalogue facts -- no prices or values, no purchase data, conditions, storage places, notes or
preorders, nothing else of the app. Everything public goes through this module, so what leaves
the server is decided here (public_figure); a profile that is off or unknown is a 404, the same
answer either way.

The setting lives in user_settings under PROFILE_KEY and is only written through
/api/account/public-profile, which checks the address (slug) and keeps it unique.
"""
import json
import os
import re

from flask import Response, jsonify, render_template, request

from .config import jload
from .figures import facets, figure_list_sql, list_item, sort_items
from .web import app, db, login_required, user_id

PROFILE_KEY = "publicProfile"
THEMES = ("auto", "light", "dark")   # auto: as the visitor's system asks
SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])")
NAME_LIMIT = 60
# Where profiles are shared from, e.g. https://figures.example.org (with the path the app is served
# under, if any: https://example.org/figures) -- the app itself may run under
# a private address. Without it the link uses the address the settings were opened on.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_PROFILE_URL", "").strip().rstrip("/")
PUBLIC_FIELDS = ("id", "name", "original_name", "characters", "series", "manufacturer", "brand", "category", "line", "scale", "edition",
                 "release_date", "has_image", "image_version")


def load_profile(connection, uid):
    row = connection.execute("SELECT value FROM user_settings WHERE user_id=? AND key=?", (uid, PROFILE_KEY)).fetchone()
    stored = jload(row["value"], {}) if row else {}
    stored = stored if isinstance(stored, dict) else {}
    return {"enabled": bool(stored.get("enabled")), "slug": str(stored.get("slug") or ""), "name": str(stored.get("name") or ""),
            "show_wishlist": bool(stored.get("show_wishlist")),
            "theme": stored.get("theme") if stored.get("theme") in THEMES else "auto"}


def profile_url(slug):
    return f"{PUBLIC_BASE_URL or request.url_root.rstrip('/')}/u/{slug}" if slug else ""


def public_owner(slug):
    """(user id, profile, display name) of the switched-on profile at this address, else None."""
    row = db().execute(
        "SELECT s.user_id,u.display_name FROM user_settings s JOIN users u ON u.id=s.user_id WHERE s.key=? AND json_extract(s.value,'$.slug')=?",
        (PROFILE_KEY, slug.lower())).fetchone()
    if not row:
        return None
    profile = load_profile(db(), row["user_id"])
    if not profile["enabled"]:
        return None
    return row["user_id"], profile, profile["name"] or row["display_name"]


def not_found():
    return jsonify({"error": "Dieses Profil gibt es nicht oder es ist nicht öffentlich."}), 404


def public_figure(item):
    """What a visitor may see of a figure: catalogue facts and how many copies, nothing else."""
    return {**{key: item.get(key) for key in PUBLIC_FIELDS}, "owned": item.get("owned", 0)}


def shared_figure_ids(uid, profile):
    ids = {row[0] for row in db().execute("SELECT DISTINCT figure_id FROM collection_entries WHERE user_id=?", (uid,))}
    if profile["show_wishlist"]:
        ids |= {row[0] for row in db().execute(
            "SELECT we.figure_id FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? AND w.is_default=1", (uid,))}
    return ids


# ---- The owner's setting ------------------------------------------------------------------------

@app.get("/api/account/public-profile")
@login_required
def get_public_profile():
    profile = load_profile(db(), user_id())
    return jsonify({**profile, "url": profile_url(profile["slug"])})


@app.put("/api/account/public-profile")
@login_required
def save_public_profile():
    uid, payload = user_id(), request.get_json(force=True) or {}
    profile = load_profile(db(), uid)
    if "slug" in payload:
        slug = str(payload["slug"] or "").strip().lower()
        if slug and not SLUG.fullmatch(slug):
            return jsonify({"error": "Die Adresse darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten (3 bis 32 Zeichen, kein Bindestrich am Anfang oder Ende)."}), 400
        taken = db().execute("SELECT 1 FROM user_settings WHERE key=? AND user_id!=? AND json_extract(value,'$.slug')=?", (PROFILE_KEY, uid, slug)).fetchone()
        if slug and taken:
            return jsonify({"error": "Diese Adresse ist schon vergeben."}), 400
        profile["slug"] = slug
    if "name" in payload:
        profile["name"] = str(payload["name"] or "").strip()[:NAME_LIMIT]
    if "show_wishlist" in payload:
        profile["show_wishlist"] = bool(payload["show_wishlist"])
    if payload.get("theme") in THEMES:
        profile["theme"] = payload["theme"]
    if "enabled" in payload:
        profile["enabled"] = bool(payload["enabled"])
    if profile["enabled"] and not profile["slug"]:
        return jsonify({"error": "Wähle eine Adresse für dein Profil."}), 400
    db().execute("INSERT INTO user_settings(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
                 (uid, PROFILE_KEY, json.dumps(profile)))
    db().commit()
    return jsonify({**profile, "url": profile_url(profile["slug"])})


# ---- What visitors see --------------------------------------------------------------------------

@app.get("/u/<slug>")
def public_profile_page(slug):
    owner = public_owner(slug)
    if not owner:
        return render_template("public.html", slug=slug, name="", missing=True, theme="auto"), 404
    return render_template("public.html", slug=slug.lower(), name=owner[2], missing=False, theme=owner[1]["theme"])


@app.get("/api/public/<slug>")
def public_profile_data(slug):
    owner = public_owner(slug)
    if not owner:
        return not_found()
    uid, profile, name = owner
    collection = [list_item(row) for row in db().execute(figure_list_sql("own.quantity>0"), (uid,))]
    collection = sort_items(collection, request.args.get("sort", "release"))
    result = {"name": name, "slug": profile["slug"], "collection": [public_figure(item) for item in collection],
              "facets": {key: value for key, value in facets(collection).items() if key in ("category", "manufacturer", "series")},
              "stats": {"figures": len(collection), "copies": sum(item["owned"] for item in collection)}}
    if profile["show_wishlist"]:
        wished = [list_item(row) for row in db().execute(figure_list_sql(
            "f.id IN (SELECT we.figure_id FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=?1 AND w.is_default=1)"), (uid,))]
        result["wishlist"] = [public_figure(item) for item in sort_items(wished, "release")]
    return jsonify(result)


@app.get("/u/<slug>/images/<int:figure_id>")
def public_figure_image(slug, figure_id):
    from .images import serve_figure_image
    owner = public_owner(slug)
    if not owner or figure_id not in shared_figure_ids(owner[0], owner[1]):
        return Response(status=404)
    return serve_figure_image(figure_id, "full" if request.args.get("size") == "full" else "thumb")
