"""Wishlists: named lists of figures a user wants, each entry with an optional target price and a
note. Every account has a default list ("Wunschliste", schema.ensure_user_lists) that cannot be
deleted; further lists are the user's own.

An entry whose figure's market value has fallen to its target price or below is marked
(target_reached), so the list shows what is worth buying now.
"""

from flask import jsonify, request

from .config import now_iso
from .figures import apply_filters, facets, figure_list_sql, list_item, sort_items
from .prices import parse_amount
from .web import app, db, login_required, user_id

NAME_LIMIT = 60


def own_list(list_id, uid):
    return db().execute("SELECT * FROM watchlists WHERE id=? AND user_id=?", (list_id, uid)).fetchone()


def lists_of(uid):
    return [dict(row) for row in db().execute(
        """SELECT w.id, w.name, w.is_default, w.created_at, COUNT(we.id) count
           FROM watchlists w LEFT JOIN watchlist_entries we ON we.list_id=w.id
           WHERE w.user_id=? GROUP BY w.id ORDER BY w.is_default DESC, lower(w.name)""", (uid,))]


@app.get("/api/watchlists")
@login_required
def get_watchlists():
    return jsonify(lists_of(user_id()))


def clean_name(payload, uid, list_id=0):
    name = " ".join(str(payload.get("name") or "").split())[:NAME_LIMIT]
    if not name:
        return None, "Der Name fehlt."
    if db().execute("SELECT 1 FROM watchlists WHERE user_id=? AND lower(name)=lower(?) AND id!=?", (uid, name, list_id)).fetchone():
        return None, "Eine Liste mit diesem Namen gibt es schon."
    return name, None


@app.post("/api/watchlists")
@login_required
def create_watchlist():
    uid = user_id()
    name, error = clean_name(request.get_json(force=True) or {}, uid)
    if error:
        return jsonify({"error": error}), 400
    cursor = db().execute("INSERT INTO watchlists(user_id,name,is_default,created_at) VALUES(?,?,0,?)", (uid, name, now_iso()))
    db().commit()
    return jsonify({"id": cursor.lastrowid, "name": name, "is_default": 0, "count": 0}), 201


@app.patch("/api/watchlists/<int:list_id>")
@login_required
def rename_watchlist(list_id):
    uid = user_id()
    if not own_list(list_id, uid):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    name, error = clean_name(request.get_json(force=True) or {}, uid, list_id)
    if error:
        return jsonify({"error": error}), 400
    db().execute("UPDATE watchlists SET name=? WHERE id=?", (name, list_id))
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/watchlists/<int:list_id>")
@login_required
def delete_watchlist(list_id):
    row = own_list(list_id, user_id())
    if not row:
        return jsonify({"error": "Liste nicht gefunden."}), 404
    if row["is_default"]:
        return jsonify({"error": "Die Standardliste kann nicht gelöscht werden."}), 400
    db().execute("DELETE FROM watchlists WHERE id=?", (list_id,))  # its entries go with it (ON DELETE CASCADE)
    db().commit()
    return jsonify({"deleted": True})


def watchlist_items(list_id, uid):
    entries = {row["figure_id"]: row for row in db().execute("SELECT * FROM watchlist_entries WHERE list_id=?", (list_id,))}
    items = []
    for row in db().execute(figure_list_sql("f.id IN (SELECT figure_id FROM watchlist_entries WHERE list_id=?2)"), (uid, list_id)):
        item = list_item(row)
        entry = entries[row["id"]]
        item.update({"target_price": entry["target_price"], "note": entry["note"], "wished_at": entry["created_at"],
                     "target_reached": entry["target_price"] is not None and item["market_value"] is not None
                     and item["market_value"] <= entry["target_price"]})
        items.append(item)
    return items


@app.get("/api/watchlists/<int:list_id>/figures")
@login_required
def watchlist_figures(list_id):
    uid = user_id()
    row = own_list(list_id, uid)
    if not row:
        return jsonify({"error": "Liste nicht gefunden."}), 404
    all_items = watchlist_items(list_id, uid)
    items = apply_filters(all_items, request.args)
    if request.args.get("mode") == "missing":
        items = [item for item in items if not item["owned"]]
    sort = request.args.get("sort", "wished")
    if sort == "wished":
        items = sorted(items, key=lambda item: (item["wished_at"], item["id"]), reverse=request.args.get("direction", "desc") == "desc")
    else:
        items = sort_items(items, sort, request.args.get("direction"))
    estimate = sum(item["market_value"] if item["market_value"] is not None else (item["target_price"] or 0) for item in all_items)
    return jsonify({"list": dict(row), "figures": items, "facets": facets(all_items),
                    "stats": {"count": len(all_items), "owned": sum(1 for item in all_items if item["owned"]),
                              "target_reached": sum(1 for item in all_items if item["target_reached"]), "estimate": round(estimate, 2)}})


def clean_entry(payload):
    fields = {}
    if "target_price" in payload:
        fields["target_price"], error = parse_amount(payload["target_price"], "Zielpreis")
        if error:
            return None, error
    if "note" in payload:
        fields["note"] = str(payload["note"] or "").strip()[:500]
    return fields, None


@app.post("/api/watchlists/<int:list_id>/figures")
@login_required
def add_to_watchlist(list_id):
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    try:
        figure_id = int(payload.get("figure_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Keine Figur angegeben."}), 400
    if not db().execute("SELECT 1 FROM figures WHERE id=?", (figure_id,)).fetchone():
        return jsonify({"error": "Figur nicht gefunden."}), 404
    fields, error = clean_entry(payload)
    if error:
        return jsonify({"error": error}), 400
    db().execute("INSERT OR IGNORE INTO watchlist_entries(list_id,figure_id,created_at) VALUES(?,?,?)", (list_id, figure_id, now_iso()))
    if fields:
        db().execute(f"UPDATE watchlist_entries SET {','.join(f'{key}=?' for key in fields)} WHERE list_id=? AND figure_id=?",
                     (*fields.values(), list_id, figure_id))
    db().commit()
    return jsonify({"added": True, "lists": lists_of(user_id())}), 201


@app.patch("/api/watchlists/<int:list_id>/figures/<int:figure_id>")
@login_required
def update_watchlist_entry(list_id, figure_id):
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    fields, error = clean_entry(request.get_json(force=True) or {})
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    updated = db().execute(f"UPDATE watchlist_entries SET {','.join(f'{key}=?' for key in fields)} WHERE list_id=? AND figure_id=?",
                           (*fields.values(), list_id, figure_id)).rowcount
    if not updated:
        return jsonify({"error": "Die Figur steht nicht auf dieser Liste."}), 404
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/watchlists/<int:list_id>/figures/<int:figure_id>")
@login_required
def remove_from_watchlist(list_id, figure_id):
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    entry = db().execute("SELECT figure_id,target_price,note FROM watchlist_entries WHERE list_id=? AND figure_id=?", (list_id, figure_id)).fetchone()
    if not entry:
        return jsonify({"error": "Die Figur steht nicht auf dieser Liste."}), 404
    db().execute("DELETE FROM watchlist_entries WHERE list_id=? AND figure_id=?", (list_id, figure_id))
    db().commit()
    return jsonify({"removed": dict(entry), "lists": lists_of(user_id())})
