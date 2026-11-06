"""Export, backup and restore of what an account entered.

- GET /api/export.json: a backup of the account -- collection, preorders (with their history),
  wishlists -- carrying every figure it refers to, so it can be restored on another instance
  whose catalogue does not have them yet. Pictures are not part of it; their links are.
- GET /api/export.csv and /api/export/preorders.csv: tables for spreadsheets.
- POST /api/import/json/preview and /apply: restore such a backup. Figures are matched to the
  catalogue (same JAN, same link, or same name/manufacturer/edition) and created where missing.
  "add" adds the collection rows to the current ones, "replace" replaces the collection.
  Preorders already present (same figure, shop, order date and order number) are skipped;
  wishlists are merged by name.
- POST /api/import/<id>/undo takes the latest restore back: what it added goes, a replaced
  collection comes back, figures it created go when nothing uses them any more.
"""

import csv
import io
import json

from flask import Response, jsonify, request

from .collection import CONDITIONS, clean_entry_fields
from .config import APP_NAME, jload, now_iso
from .figures import TEXT_FIELDS, clean_figure_fields, find_duplicate, in_use
from .preorders import STATUSES, clean_preorder_fields
from .prices import market_value_sql
from .schema import ensure_user_lists
from .web import app, db, login_required, user_id

FORMAT = "ophir-figures-backup"
FIGURE_EXPORT_FIELDS = (*TEXT_FIELDS, "description", "release_date", "height_mm", "msrp", "msrp_currency", "jan", "source_url", "image_url")
ENTRY_FIELDS = ("quantity", "condition", "purchase_price", "purchased_at", "shop", "location", "notes")
PREORDER_FIELDS = ("status", "shop", "order_number", "ordered_at", "quantity", "price", "shipping", "paid", "expected_release",
                   "tracking", "notes", "delivered_at")


def build_backup(uid):
    connection = db()
    user = connection.execute("SELECT username,display_name FROM users WHERE id=?", (uid,)).fetchone()
    entries = [dict(row) for row in connection.execute("SELECT * FROM collection_entries WHERE user_id=? ORDER BY id", (uid,))]
    preorders = [dict(row) for row in connection.execute("SELECT * FROM preorders WHERE user_id=? ORDER BY id", (uid,))]
    lists = [dict(row) for row in connection.execute("SELECT * FROM watchlists WHERE user_id=? ORDER BY is_default DESC, id", (uid,))]
    list_entries = {}
    for row in connection.execute(
            "SELECT we.* FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? ORDER BY we.id", (uid,)):
        list_entries.setdefault(row["list_id"], []).append(dict(row))
    figure_ids = sorted({row["figure_id"] for row in entries} | {row["figure_id"] for row in preorders}
                        | {entry["figure_id"] for rows in list_entries.values() for entry in rows})
    figures = []
    for figure_id in figure_ids:
        row = connection.execute(f"SELECT f.*, {market_value_sql('f.id')} market_value FROM figures f WHERE f.id=?", (figure_id,)).fetchone()
        figure = {key: row[key] for key in FIGURE_EXPORT_FIELDS}
        figure.update({"ref": row["id"], "attributes": jload(row["attributes"], {}) or {}, "market_value": row["market_value"]})
        figures.append(figure)
    preorder_index = {row["id"]: index for index, row in enumerate(preorders)}
    events = {}
    if preorders:
        placeholders = ",".join("?" for _ in preorders)
        for event in connection.execute(f"SELECT * FROM preorder_events WHERE preorder_id IN ({placeholders}) ORDER BY id", [row["id"] for row in preorders]):
            events.setdefault(event["preorder_id"], []).append({key: event[key] for key in ("kind", "old_value", "new_value", "created_at")})
    return {
        "format": FORMAT, "version": 1, "app": APP_NAME, "exported_at": now_iso(),
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "figures": figures,
        "collection": [{"figure_ref": row["figure_id"], **{key: row[key] for key in ENTRY_FIELDS},
                        "preorder_index": preorder_index.get(row["preorder_id"]), "created_at": row["created_at"]} for row in entries],
        "preorders": [{"figure_ref": row["figure_id"], **{key: row[key] for key in PREORDER_FIELDS}, "created_at": row["created_at"],
                       "events": events.get(row["id"], [])} for row in preorders],
        "watchlists": [{"name": row["name"], "is_default": bool(row["is_default"]),
                        "entries": [{"figure_ref": entry["figure_id"], "target_price": entry["target_price"], "note": entry["note"],
                                     "created_at": entry["created_at"]} for entry in list_entries.get(row["id"], [])]} for row in lists],
    }


@app.get("/api/export.json")
@login_required
def export_json():
    payload = json.dumps(build_backup(user_id()), ensure_ascii=False, indent=1)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=ophir-figures-backup-{now_iso()[:10]}.json"})


def csv_response(rows, header, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    # A BOM, so Excel reads the umlauts as UTF-8.
    return Response("﻿" + buffer.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def money_cell(value):
    return "" if value is None else f"{value:.2f}".replace(".", ",")


@app.get("/api/export.csv")
@login_required
def export_csv():
    rows = db().execute(
        f"""SELECT f.*, c.quantity, c.condition, c.purchase_price, c.purchased_at, c.shop, c.location, c.notes, {market_value_sql('f.id')} market_value
            FROM collection_entries c JOIN figures f ON f.id=c.figure_id WHERE c.user_id=? ORDER BY f.name, c.id""", (user_id(),))
    header = ["Name", "Originalname", "Charaktere", "Franchise", "Hersteller", "Marke", "Kategorie", "Linie", "Maßstab", "Edition", "Erscheinung",
              "JAN", "Anzahl", "Zustand", "Kaufpreis (EUR)", "Kaufdatum", "Shop", "Aufbewahrung", "Notizen", "Marktwert (EUR)", "Link"]
    return csv_response(
        ([row["name"], row["original_name"], row["characters"], row["series"], row["manufacturer"], row["brand"], row["category"], row["line"], row["scale"],
          row["edition"], row["release_date"], row["jan"], row["quantity"], CONDITIONS.get(row["condition"], row["condition"]),
          money_cell(row["purchase_price"]), row["purchased_at"], row["shop"], row["location"], row["notes"], money_cell(row["market_value"]),
          row["source_url"]] for row in rows),
        header, f"ophir-figures-sammlung-{now_iso()[:10]}.csv")


@app.get("/api/export/preorders.csv")
@login_required
def export_preorders_csv():
    rows = db().execute(
        """SELECT f.name, f.manufacturer, p.* FROM preorders p JOIN figures f ON f.id=p.figure_id WHERE p.user_id=?
           ORDER BY COALESCE(NULLIF(p.expected_release,''),'9999'), p.id""", (user_id(),))
    header = ["Name", "Hersteller", "Status", "Shop", "Bestellnummer", "Bestellt am", "Anzahl", "Preis (EUR)", "Versand (EUR)",
              "Bezahlt (EUR)", "Erwartet", "Angekommen", "Sendungsnummer", "Notizen"]
    return csv_response(
        ([row["name"], row["manufacturer"], STATUSES.get(row["status"], row["status"]), row["shop"], row["order_number"], row["ordered_at"],
          row["quantity"], money_cell(row["price"]), money_cell(row["shipping"]), money_cell(row["paid"]), row["expected_release"],
          row["delivered_at"] or "", row["tracking"], row["notes"]] for row in rows),
        header, f"ophir-figures-vorbestellungen-{now_iso()[:10]}.csv")


class BackupError(Exception):
    pass


def read_backup(payload):
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("Das ist keine Sicherung von Ophir Figures.")
    if not isinstance(data.get("figures"), list):
        raise BackupError("Die Sicherung enthält keine Figurenliste.")
    figures = {}
    for raw in data["figures"]:
        if not isinstance(raw, dict) or "ref" not in raw:
            raise BackupError("Eine Figur der Sicherung hat keine Kennung.")
        fields, error = clean_figure_fields({key: raw.get(key) for key in (*FIGURE_EXPORT_FIELDS, "attributes") if key in raw})
        if error:
            raise BackupError(f"Figur „{raw.get('name') or raw['ref']}“: {error}")
        figures[raw["ref"]] = fields
    return data, figures


def match_figures(connection, figures):
    """{ref: existing figure id or None (to be created)}."""
    return {ref: (duplicate[0] if (duplicate := find_duplicate(connection, fields)) else None) for ref, fields in figures.items()}


@app.post("/api/import/json/preview")
@login_required
def preview_backup():
    try:
        data, figures = read_backup(request.get_json(force=True) or {})
    except BackupError as error:
        return jsonify({"error": str(error)}), 400
    matches = match_figures(db(), figures)
    return jsonify({
        "figures": len(figures), "figures_new": sum(1 for value in matches.values() if value is None),
        "collection": len(data.get("collection") or []), "preorders": len(data.get("preorders") or []),
        "watchlists": len(data.get("watchlists") or []),
        "watchlist_entries": sum(len(item.get("entries") or []) for item in data.get("watchlists") or [] if isinstance(item, dict)),
        "exported_at": data.get("exported_at"), "user": (data.get("user") or {}).get("display_name"),
    })


@app.post("/api/import/json/apply")
@login_required
def apply_backup():
    payload = request.get_json(force=True) or {}
    strategy = payload.get("strategy") if payload.get("strategy") in ("add", "replace") else "add"
    uid, connection = user_id(), db()
    try:
        data, figures = read_backup(payload)
        changes = restore(connection, uid, data, figures, strategy)
    except BackupError as error:
        connection.rollback()
        return jsonify({"error": str(error)}), 400
    cursor = connection.execute("INSERT INTO import_operations(user_id,created_at,changes) VALUES(?,?,?)", (uid, now_iso(), json.dumps(changes)))
    connection.commit()
    return jsonify({"operation_id": cursor.lastrowid, "figures_created": len(changes["figures"]), "collection": len(changes["entries"]),
                    "preorders": len(changes["preorders"]), "preorders_skipped": changes["preorders_skipped"],
                    "watchlist_entries": len(changes["watchlist_entries"]), "replaced": len(changes["replaced"])})


def restore(connection, uid, data, figures, strategy):
    stamp = now_iso()
    changes = {"figures": [], "entries": [], "preorders": [], "preorders_skipped": 0, "watchlists": [], "watchlist_entries": [], "replaced": []}
    ids = match_figures(connection, figures)
    for ref, fields in figures.items():
        if ids[ref] is None:
            columns = ["created_by", "created_at", "updated_at", *fields]
            ids[ref] = connection.execute(f"INSERT INTO figures({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                          (uid, stamp, stamp, *fields.values())).lastrowid
            changes["figures"].append(ids[ref])

    def figure_of(item, what):
        if not isinstance(item, dict) or item.get("figure_ref") not in ids:
            raise BackupError(f"{what} verweist auf eine Figur, die nicht in der Sicherung steht.")
        return ids[item["figure_ref"]]

    preorder_ids = []
    for item in data.get("preorders") or []:
        figure_id = figure_of(item, "Eine Vorbestellung")
        fields, error = clean_preorder_fields({key: item.get(key) for key in PREORDER_FIELDS if key in item})
        if error:
            raise BackupError(f"Vorbestellung: {error}")
        existing = connection.execute(
            "SELECT id FROM preorders WHERE user_id=? AND figure_id=? AND shop=? AND ordered_at=? AND order_number=?",
            (uid, figure_id, fields.get("shop", ""), fields.get("ordered_at", ""), fields.get("order_number", ""))).fetchone()
        if existing:
            preorder_ids.append(existing["id"])
            changes["preorders_skipped"] += 1
            continue
        columns = ["user_id", "figure_id", "created_at", "updated_at", *fields]
        preorder_id = connection.execute(f"INSERT INTO preorders({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                         (uid, figure_id, item.get("created_at") or stamp, stamp, *fields.values())).lastrowid
        for event in item.get("events") or []:
            if isinstance(event, dict) and event.get("kind"):
                connection.execute("INSERT INTO preorder_events(preorder_id,kind,old_value,new_value,created_at) VALUES(?,?,?,?,?)",
                                   (preorder_id, str(event["kind"])[:20], str(event.get("old_value") or "")[:40],
                                    str(event.get("new_value") or "")[:40], str(event.get("created_at") or stamp)[:40]))
        preorder_ids.append(preorder_id)
        changes["preorders"].append(preorder_id)

    if strategy == "replace":
        for row in connection.execute("SELECT * FROM collection_entries WHERE user_id=?", (uid,)):
            changes["replaced"].append(dict(row))
        connection.execute("DELETE FROM collection_entries WHERE user_id=?", (uid,))
    for item in data.get("collection") or []:
        figure_id = figure_of(item, "Ein Sammlungseintrag")
        fields, error = clean_entry_fields({key: item.get(key) for key in ENTRY_FIELDS if key in item})
        if error:
            raise BackupError(f"Sammlungseintrag: {error}")
        index = item.get("preorder_index")
        preorder_id = preorder_ids[index] if isinstance(index, int) and 0 <= index < len(preorder_ids) else None
        columns = ["user_id", "figure_id", "preorder_id", "created_at", "updated_at", *fields]
        changes["entries"].append(connection.execute(
            f"INSERT INTO collection_entries({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            (uid, figure_id, preorder_id, item.get("created_at") or stamp, stamp, *fields.values())).lastrowid)

    ensure_user_lists(connection, uid)
    for item in data.get("watchlists") or []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())[:60]
        if item.get("is_default"):
            row = connection.execute("SELECT id FROM watchlists WHERE user_id=? AND is_default=1", (uid,)).fetchone()
        else:
            row = connection.execute("SELECT id FROM watchlists WHERE user_id=? AND lower(name)=lower(?)", (uid, name)).fetchone() if name else None
        if row:
            list_id = row["id"]
        elif name:
            list_id = connection.execute("INSERT INTO watchlists(user_id,name,is_default,created_at) VALUES(?,?,0,?)", (uid, name, stamp)).lastrowid
            changes["watchlists"].append(list_id)
        else:
            continue
        for entry in item.get("entries") or []:
            figure_id = figure_of(entry, "Ein Wunschlisteneintrag")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO watchlist_entries(list_id,figure_id,target_price,note,created_at) VALUES(?,?,?,?,?)",
                (list_id, figure_id, entry.get("target_price") if isinstance(entry.get("target_price"), (int, float)) else None,
                 str(entry.get("note") or "")[:500], entry.get("created_at") or stamp))
            if cursor.rowcount:
                changes["watchlist_entries"].append(cursor.lastrowid)
    return changes


@app.post("/api/import/<int:operation_id>/undo")
@login_required
def undo_import(operation_id):
    uid, connection = user_id(), db()
    operation = connection.execute("SELECT * FROM import_operations WHERE id=? AND user_id=?", (operation_id, uid)).fetchone()
    if not operation:
        return jsonify({"error": "Diesen Import gibt es nicht."}), 404
    if operation["undone_at"]:
        return jsonify({"error": "Der Import wurde schon rückgängig gemacht."}), 400
    latest = connection.execute("SELECT MAX(id) FROM import_operations WHERE user_id=? AND undone_at IS NULL", (uid,)).fetchone()[0]
    if latest != operation_id:
        return jsonify({"error": "Nur der letzte Import kann rückgängig gemacht werden."}), 400
    changes = jload(operation["changes"], {}) or {}

    def delete(table, row_ids, owner_check):
        for row_id in row_ids or []:
            connection.execute(f"DELETE FROM {table} WHERE id=? AND {owner_check}", (row_id, uid))

    delete("watchlist_entries", changes.get("watchlist_entries"), "list_id IN (SELECT id FROM watchlists WHERE user_id=?)")
    delete("watchlists", changes.get("watchlists"), "user_id=? AND is_default=0")
    delete("collection_entries", changes.get("entries"), "user_id=?")
    delete("preorders", changes.get("preorders"), "user_id=?")
    for row in changes.get("replaced") or []:
        if row.get("preorder_id") and not connection.execute("SELECT 1 FROM preorders WHERE id=?", (row["preorder_id"],)).fetchone():
            row["preorder_id"] = None   # deleted since; the copies stay
        columns = [key for key in row if key != "id"]
        connection.execute(f"INSERT INTO collection_entries({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                           [row[key] for key in columns])
    for figure_id in changes.get("figures") or []:
        if not in_use(connection, figure_id):
            connection.execute("DELETE FROM figures WHERE id=? AND created_by=?", (figure_id, uid))
    connection.execute("UPDATE import_operations SET undone_at=? WHERE id=?", (now_iso(), operation_id))
    connection.commit()
    return jsonify({"undone": True})
