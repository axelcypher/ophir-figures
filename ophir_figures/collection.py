"""A user's collection: the copies they own, each row a group of copies of one figure with the
same condition and purchase (price, date, shop), where they are kept and notes.

A copy is worth the figure's current market value, or else what was paid for it (prices.py).
"""

from flask import jsonify, request

from .config import now_iso
from .figures import apply_filters, facets, figure_list_sql, list_item, normalize_date, sort_items
from .prices import collection_value_sql, market_value_sql, parse_amount
from .web import app, db, login_required, user_id

CONDITIONS = {"sealed": "Neu, versiegelt", "boxed": "Geöffnet, mit Karton", "loose": "Ohne Karton", "damaged": "Beschädigt"}
ENTRY_TEXT = {"shop": 120, "location": 120, "notes": 2000}
QUANTITY_LIMIT = 999


def clean_entry_fields(payload, partial=False):
    """(fields, error) for a collection row from a request body."""
    fields = {}
    if "quantity" in payload or not partial:
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            return None, "Die Anzahl ist keine Zahl."
        if not 1 <= quantity <= QUANTITY_LIMIT:
            return None, f"Die Anzahl muss zwischen 1 und {QUANTITY_LIMIT} liegen."
        fields["quantity"] = quantity
    if "condition" in payload or not partial:
        condition = payload.get("condition") or "boxed"
        if condition not in CONDITIONS:
            return None, "Unbekannter Zustand."
        fields["condition"] = condition
    if "purchase_price" in payload:
        fields["purchase_price"], error = parse_amount(payload["purchase_price"], "Kaufpreis")
        if error:
            return None, error
    if "purchased_at" in payload:
        fields["purchased_at"], error = normalize_date(payload["purchased_at"], "Kaufdatum")
        if error:
            return None, error
    for key, limit in ENTRY_TEXT.items():
        if key in payload:
            fields[key] = str(payload[key] or "").strip()[:limit]
    return fields, None


def owned_figures(uid):
    """List items of every figure the user owns, with what their copies cost and are worth."""
    items = {row["id"]: list_item(row) for row in db().execute(figure_list_sql("own.quantity>0"), (uid,))}
    for row in db().execute(
        f"""SELECT c.figure_id, SUM(c.quantity*COALESCE(c.purchase_price,0)) spent,
              SUM(CASE WHEN c.purchase_price IS NULL AND {market_value_sql('c.figure_id')} IS NULL THEN c.quantity ELSE 0 END) unpriced,
              SUM({collection_value_sql()}) value, GROUP_CONCAT(DISTINCT c.condition) conditions,
              GROUP_CONCAT(DISTINCT NULLIF(c.location,'')) locations, MAX(c.created_at) added_at,
              MAX(NULLIF(c.purchased_at,'')) purchased_at
            FROM collection_entries c WHERE c.user_id=? GROUP BY c.figure_id""", (uid,)):
        item = items.get(row["figure_id"])
        if item:
            item.update({
                "spent": round(row["spent"] or 0, 2), "unpriced": row["unpriced"], "value": round(row["value"] or 0, 2),
                "conditions": (row["conditions"] or "").split(",") if row["conditions"] else [],
                "locations": (row["locations"] or "").split(",") if row["locations"] else [],
                "added_at": row["added_at"], "purchased_at": row["purchased_at"] or "",
            })
    return list(items.values())


def collection_stats(items):
    return {
        "figures": len(items),
        "copies": sum(item["owned"] for item in items),
        "value": round(sum(item.get("value", 0) for item in items), 2),
        "spent": round(sum(item.get("spent", 0) for item in items), 2),
        "unpriced": sum(item.get("unpriced", 0) for item in items),
        "with_market_value": sum(1 for item in items if item.get("market_value") is not None),
    }


COLLECTION_SORTS = {
    "added": lambda item: (item.get("added_at") or "", item["id"]),
    "purchased": lambda item: (item.get("purchased_at") or "", item["id"]),
    "spent": lambda item: (item.get("spent", 0), item["id"]),
    "collection_value": lambda item: (item.get("value", 0), item["id"]),
}


@app.get("/api/collection")
@login_required
def get_collection():
    args = request.args
    all_items = owned_figures(user_id())
    items = apply_filters(all_items, args)
    location = str(args.get("location") or "").strip()
    if location:
        items = [item for item in items if location in item.get("locations", [])]
    condition = str(args.get("condition") or "").strip()
    if condition:
        items = [item for item in items if condition in item.get("conditions", [])]
    sort = args.get("sort", "added")
    if sort in COLLECTION_SORTS:
        items = sorted(items, key=COLLECTION_SORTS[sort], reverse=args.get("direction", "desc") == "desc")
    else:
        items = sort_items(items, sort, args.get("direction"))
    result_facets = facets(all_items)
    locations = {}
    for item in all_items:
        for place in item.get("locations", []):
            locations[place] = locations.get(place, 0) + 1
    result_facets["location"] = sorted(([place, count] for place, count in locations.items()), key=lambda pair: (-pair[1], pair[0]))
    return jsonify({"figures": items, "stats": collection_stats(all_items), "shown": collection_stats(items),
                    "facets": result_facets, "conditions": CONDITIONS})


def entry_row(entry_id, uid):
    row = db().execute("SELECT * FROM collection_entries WHERE id=? AND user_id=?", (entry_id, uid)).fetchone()
    return dict(row) if row else None


@app.post("/api/collection")
@login_required
def add_collection_entry():
    payload = request.get_json(force=True) or {}
    uid = user_id()
    try:
        figure_id = int(payload.get("figure_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Keine Figur angegeben."}), 400
    if not db().execute("SELECT 1 FROM figures WHERE id=?", (figure_id,)).fetchone():
        return jsonify({"error": "Figur nicht gefunden."}), 404
    fields, error = clean_entry_fields(payload)
    if error:
        return jsonify({"error": error}), 400
    stamp = now_iso()
    columns = ["user_id", "figure_id", "created_at", "updated_at", *fields]
    cursor = db().execute(f"INSERT INTO collection_entries({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                          (uid, figure_id, stamp, stamp, *fields.values()))
    db().commit()
    return jsonify(entry_row(cursor.lastrowid, uid)), 201


@app.patch("/api/collection/<int:entry_id>")
@login_required
def update_collection_entry(entry_id):
    uid = user_id()
    if not entry_row(entry_id, uid):
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    fields, error = clean_entry_fields(request.get_json(force=True) or {}, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    db().execute(f"UPDATE collection_entries SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=? AND user_id=?",
                 (*fields.values(), now_iso(), entry_id, uid))
    db().commit()
    return jsonify(entry_row(entry_id, uid))


@app.delete("/api/collection/<int:entry_id>")
@login_required
def delete_collection_entry(entry_id):
    """Removes the row and returns it, so the client can offer to put it back (POST it again)."""
    uid = user_id()
    entry = entry_row(entry_id, uid)
    if not entry:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    db().execute("DELETE FROM collection_entries WHERE id=? AND user_id=?", (entry_id, uid))
    db().commit()
    return jsonify({"deleted": entry})


def dashboard_collection(uid):
    """Totals and the latest additions for the dashboard."""
    connection = db()
    totals = connection.execute(
        f"""SELECT COUNT(DISTINCT c.figure_id) figures, COALESCE(SUM(c.quantity),0) copies,
              COALESCE(SUM(c.quantity*COALESCE(c.purchase_price,0)),0) spent, COALESCE(SUM({collection_value_sql()}),0) value
            FROM collection_entries c WHERE c.user_id=?""", (uid,)).fetchone()
    recent = []
    for row in connection.execute(
        f"""SELECT f.id, f.name, f.manufacturer, f.series, f.category, f.image_key, f.image_url, MAX(c.created_at) added_at,
              SUM(c.quantity) quantity, {market_value_sql('f.id')} market_value
            FROM collection_entries c JOIN figures f ON f.id=c.figure_id WHERE c.user_id=?
            GROUP BY f.id ORDER BY MAX(c.created_at) DESC, MAX(c.id) DESC LIMIT 12""", (uid,)):
        item = {key: row[key] for key in ("id", "name", "manufacturer", "series", "category", "added_at", "quantity", "market_value")}
        item.update({"has_image": bool(row["image_key"] or row["image_url"]), "image_version": (row["image_key"] or "")[:12]})
        recent.append(item)
    by_category = [dict(row) for row in connection.execute(
        """SELECT COALESCE(NULLIF(f.category,''),'Ohne Kategorie') category, SUM(c.quantity) copies
           FROM collection_entries c JOIN figures f ON f.id=c.figure_id WHERE c.user_id=?
           GROUP BY 1 ORDER BY copies DESC LIMIT 8""", (uid,))]
    return {"figures": totals["figures"], "copies": totals["copies"], "spent": round(totals["spent"], 2),
            "value": round(totals["value"], 2), "recent": recent, "by_category": by_category}
