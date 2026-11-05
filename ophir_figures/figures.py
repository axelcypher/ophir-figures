"""The figure catalogue: browsing with filters, details, creating, editing and deleting entries.

The catalogue is shared by every account. Anyone signed in can add a figure (by hand or from a
link, see link_import.py) and correct one; a figure can only be deleted while no account has it
in a collection, preorder or wishlist, and only by whoever created it or an admin.
"""

import json
import re
from datetime import date

from flask import jsonify, request

from . import search
from .config import jload, now_iso
from .images import ImageError, download_image
from .prices import market_value_sql, parse_amount, price_history, record_price
from .web import app, db, login_required, user_id

# Offered in the form; any other text is allowed too.
CATEGORIES = ("Scale-Figur", "Non-Scale-Figur", "Nendoroid", "figma", "Prize-Figur", "Actionfigur",
              "Garage Kit", "Model Kit", "Plüsch", "Sonstiges")
CURRENCIES = ("JPY", "EUR", "USD", "GBP", "CNY", "KRW", "HKD", "TWD", "CAD", "AUD", "CHF")
TEXT_FIELDS = ("name", "original_name", "characters", "series", "manufacturer", "category", "line", "scale",
               "edition", "sculptor", "material")
TEXT_LIMIT, DESCRIPTION_LIMIT = 300, 5000
OPEN_PREORDER = "('ordered','paid','shipped')"
MONTHS = {"jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2, "mar": 3, "mär": 3, "märz": 3, "march": 3,
          "apr": 4, "april": 4, "may": 5, "mai": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7,
          "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "okt": 10, "oktober": 10, "october": 10,
          "nov": 11, "november": 11, "dec": 12, "dez": 12, "dezember": 12, "december": 12}


def normalize_date(value, field="Datum"):
    """'2025', '2025-03', '2025-03-14', '03/2025', '14.03.2025', 'March 2025', '2025年3月' ->
    ISO with as much precision as given. (value, error); empty stays empty."""
    text = str(value or "").strip()
    if not text:
        return "", None
    text = text.replace("年", "-").replace("月", "-").replace("日", "").strip("- ")
    patterns = (
        (r"(\d{4})", lambda m: (int(m[1]), None, None)),
        (r"(\d{4})[-/.](\d{1,2})", lambda m: (int(m[1]), int(m[2]), None)),
        (r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"(\d{1,2})[/.](\d{4})", lambda m: (int(m[2]), int(m[1]), None)),
        (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", lambda m: (int(m[3]), int(m[2]), int(m[1]))),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", lambda m: (int(m[3]), int(m[1]), int(m[2]))),   # US: 03/14/2025
        (r"([A-Za-zäÄ]+)\.?\s+(\d{4})", lambda m: (int(m[2]), MONTHS.get(m[1].lower()), None) if MONTHS.get(m[1].lower()) else None),
    )
    for pattern, build in patterns:
        match = re.fullmatch(pattern, text)
        parts = build(match) if match else None
        if not parts:
            continue
        year, month, day = parts
        try:
            if day:
                return date(year, month, day).isoformat(), None
            if month:
                date(year, month, 1)
                return f"{year:04d}-{month:02d}", None
            if 1900 <= year <= 2200:
                return f"{year:04d}", None
        except ValueError:
            break
    return None, f"{field} „{value}“ ist kein Datum (z. B. 2025-03 oder 14.03.2025)."


def split_list(value):
    """Characters as a list: "Miku, Rin; Len" -> ["Miku", "Rin", "Len"]."""
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = re.split(r"\s*[,;]\s*|\s+/\s+", str(value or ""))
    return list(dict.fromkeys(part.strip() for part in parts if str(part).strip()))


def clean_figure_fields(payload, partial=False):
    """The catalogue fields of a request body, checked and normalized. (fields, error)."""
    fields = {}
    for key in TEXT_FIELDS:
        if key in payload:
            value = ", ".join(split_list(payload[key])) if key == "characters" else re.sub(r"\s+", " ", str(payload[key] or "")).strip()
            if len(value) > TEXT_LIMIT:
                return None, f"„{key}“ ist zu lang (höchstens {TEXT_LIMIT} Zeichen)."
            fields[key] = value
    if "description" in payload:
        fields["description"] = str(payload["description"] or "").strip()[:DESCRIPTION_LIMIT]
    if not partial and not fields.get("name"):
        return None, "Der Name fehlt."
    if partial and "name" in fields and not fields["name"]:
        return None, "Der Name darf nicht leer sein."
    if "release_date" in payload:
        fields["release_date"], error = normalize_date(payload["release_date"], "Erscheinungsdatum")
        if error:
            return None, error
    if "height_mm" in payload:
        raw = str(payload["height_mm"] or "").strip().lower().removesuffix("mm").strip()
        if not raw:
            fields["height_mm"] = None
        elif raw.isdigit() and 1 <= int(raw) <= 5000:
            fields["height_mm"] = int(raw)
        else:
            return None, "Die Höhe bitte in Millimetern (1 bis 5000)."
    if "msrp" in payload:
        fields["msrp"], error = parse_amount(payload["msrp"], "Originalpreis")
        if error:
            return None, error
    if "msrp_currency" in payload:
        currency = str(payload["msrp_currency"] or "JPY").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            return None, "Die Währung bitte als Code mit drei Buchstaben (JPY, EUR, USD …)."
        fields["msrp_currency"] = currency
    if "jan" in payload:
        jan = re.sub(r"[\s-]", "", str(payload["jan"] or ""))
        if jan and not re.fullmatch(r"\d{8,14}", jan):
            return None, "JAN/EAN besteht aus 8 bis 14 Ziffern."
        fields["jan"] = jan
    for key in ("source_url", "image_url"):
        if key in payload:
            url = str(payload[key] or "").strip()
            if url and not re.match(r"https?://", url, re.I):
                return None, "Links müssen mit http:// oder https:// beginnen."
            fields[key] = url[:2000]
    if "attributes" in payload:
        attributes = payload["attributes"] if isinstance(payload["attributes"], dict) else {}
        fields["attributes"] = json.dumps({str(k)[:80]: str(v)[:500] for k, v in list(attributes.items())[:60]}, ensure_ascii=False)
    return fields, None


def fold_key(*parts):
    return "|".join("".join(search.field_words(part or "")[0]) for part in parts)


def find_duplicate(connection, fields, exclude_id=0):
    """An existing figure that is evidently the same product: same JAN, same source link, or same
    name, manufacturer and edition. Returns (id, name, reason) or None."""
    if fields.get("jan"):
        row = connection.execute("SELECT id,name FROM figures WHERE jan=? AND id!=?", (fields["jan"], exclude_id)).fetchone()
        if row:
            return row["id"], row["name"], "gleiche JAN"
    if fields.get("source_url"):
        row = connection.execute("SELECT id,name FROM figures WHERE source_url=? AND id!=?", (fields["source_url"], exclude_id)).fetchone()
        if row:
            return row["id"], row["name"], "gleicher Link"
    key = fold_key(fields.get("name"), fields.get("manufacturer"), fields.get("edition"))
    for row in connection.execute("SELECT id,name,manufacturer,edition FROM figures WHERE id!=?", (exclude_id,)):
        if fold_key(row["name"], row["manufacturer"], row["edition"]) == key:
            return row["id"], row["name"], "gleicher Name, Hersteller und Edition"
    return None


def image_fields(row):
    return {"has_image": bool(row["image_key"] or row["image_url"]), "image_version": (row["image_key"] or "")[:12]}


LIST_COLUMNS = ("id", "name", "original_name", "characters", "series", "manufacturer", "category", "line", "scale",
                "edition", "release_date", "msrp", "msrp_currency", "jan", "created_at")


def figure_list_sql(where="1=1"):
    return f"""SELECT f.*, COALESCE(own.quantity,0) owned, COALESCE(pre.count,0) preordered,
                 EXISTS(SELECT 1 FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id
                        WHERE we.figure_id=f.id AND w.user_id=?1) wished,
                 {market_value_sql('f.id')} market_value
               FROM figures f
               LEFT JOIN (SELECT figure_id, SUM(quantity) quantity FROM collection_entries WHERE user_id=?1 GROUP BY figure_id) own
                 ON own.figure_id=f.id
               LEFT JOIN (SELECT figure_id, SUM(quantity) count FROM preorders WHERE user_id=?1 AND status IN {OPEN_PREORDER} GROUP BY figure_id) pre
                 ON pre.figure_id=f.id
               WHERE {where}"""


def list_item(row):
    item = {key: row[key] for key in LIST_COLUMNS}
    item.update(image_fields(row))
    item.update({"owned": row["owned"], "preordered": row["preordered"], "wished": bool(row["wished"]), "market_value": row["market_value"]})
    return item


SORTS = {
    "release": lambda item: (item["release_date"] or "0000", item["id"]),
    "name": lambda item: (search.fold(item["name"]), item["id"]),
    "added": lambda item: (item["created_at"], item["id"]),
    "value": lambda item: (item["market_value"] if item["market_value"] is not None else -1, item["id"]),
    "manufacturer": lambda item: (search.fold(item["manufacturer"]), search.fold(item["name"])),
}
DESCENDING = {"release", "added", "value"}


def apply_filters(items, args):
    """The filters every figure grid shares (catalogue, collection, wishlist), on list items."""
    for key in ("category", "manufacturer", "series", "line", "scale"):
        wanted = str(args.get(key) or "").strip()
        if wanted:
            items = [item for item in items if (item.get(key) or "") == wanted]
    character = str(args.get("character") or "").strip()
    if character:
        items = [item for item in items if character in split_list(item.get("characters"))]
    year = str(args.get("year") or "").strip()
    if year:
        items = [item for item in items if (item.get("release_date") or "").startswith(year) or (year == "none" and not item.get("release_date"))]
    query = str(args.get("q") or "").strip()
    if query:
        scored = [(search.query(query).score(search.figure_fields(item)), item) for item in items]
        items = [item for score, item in scored if score > 0]
    return items


def sort_items(items, sort, direction=None):
    sort = sort if sort in SORTS else "release"
    descending = (direction or ("desc" if sort in DESCENDING else "asc")) == "desc"
    return sorted(items, key=SORTS[sort], reverse=descending)


def facets(items):
    """For the filter menus: every value of the grid's figures with how often it occurs."""
    result = {key: {} for key in ("category", "manufacturer", "series", "line", "scale", "character", "year")}
    for item in items:
        for key in ("category", "manufacturer", "series", "line", "scale"):
            if item.get(key):
                result[key][item[key]] = result[key].get(item[key], 0) + 1
        for character in split_list(item.get("characters")):
            result["character"][character] = result["character"].get(character, 0) + 1
        year = (item.get("release_date") or "")[:4]
        if year:
            result["year"][year] = result["year"].get(year, 0) + 1
    def ordered(key, counts):
        pairs = [[value, count] for value, count in counts.items()]
        if key == "year":
            return sorted(pairs, reverse=True)
        return sorted(pairs, key=lambda pair: (-pair[1], search.fold(pair[0])))
    return {key: ordered(key, counts) for key, counts in result.items()}


@app.get("/api/figures")
@login_required
def list_figures():
    args = request.args
    items = [list_item(row) for row in db().execute(figure_list_sql(), (user_id(),))]
    all_items = items
    mode = args.get("mode", "all")
    if mode == "owned":
        items = [item for item in items if item["owned"]]
    elif mode == "missing":
        items = [item for item in items if not item["owned"]]
    elif mode == "wished":
        items = [item for item in items if item["wished"]]
    elif mode == "preordered":
        items = [item for item in items if item["preordered"]]
    items = sort_items(apply_filters(items, args), args.get("sort", "release"), args.get("direction"))
    return jsonify({"figures": items, "total": len(all_items), "facets": facets(all_items)})


@app.get("/api/figures/suggestions")
@login_required
def figure_suggestions():
    """Values for the form's autocomplete: what the catalogue already uses, and the account's own
    shops and storage places."""
    uid = user_id()
    connection = db()

    def distinct(column):
        return [row[0] for row in connection.execute(
            f"SELECT {column} FROM figures WHERE {column}!='' GROUP BY {column} ORDER BY COUNT(*) DESC, {column} LIMIT 400")]
    characters = {}
    for (value,) in connection.execute("SELECT characters FROM figures WHERE characters!=''"):
        for character in split_list(value):
            characters[character] = characters.get(character, 0) + 1
    shops = [row[0] for row in connection.execute(
        """SELECT shop FROM (SELECT shop FROM collection_entries WHERE user_id=?1 UNION ALL SELECT shop FROM preorders WHERE user_id=?1)
           WHERE shop!='' GROUP BY shop ORDER BY COUNT(*) DESC LIMIT 100""", (uid,))]
    locations = [row[0] for row in connection.execute(
        "SELECT location FROM collection_entries WHERE user_id=? AND location!='' GROUP BY location ORDER BY COUNT(*) DESC LIMIT 100", (uid,))]
    categories = list(dict.fromkeys([*CATEGORIES, *distinct("category")]))
    return jsonify({
        "category": categories, "manufacturer": distinct("manufacturer"), "series": distinct("series"), "line": distinct("line"),
        "scale": list(dict.fromkeys(["1/4", "1/6", "1/7", "1/8", "Non-Scale", *distinct("scale")])), "sculptor": distinct("sculptor"),
        "material": distinct("material"), "edition": distinct("edition"),
        "character": sorted(characters, key=lambda name: (-characters[name], search.fold(name)))[:600],
        "shop": shops, "location": locations, "currencies": list(CURRENCIES),
    })


def figure_detail(figure_id, uid):
    connection = db()
    row = connection.execute(figure_list_sql("f.id=?2"), (uid, figure_id)).fetchone()
    if not row:
        return None
    figure = {key: row[key] for key in row.keys() if key not in ("image_key", "attributes", "created_by")}
    figure.update(image_fields(row))
    figure["wished"] = bool(row["wished"])
    figure["attributes"] = jload(row["attributes"], {}) or {}
    creator = connection.execute("SELECT display_name FROM users WHERE id=?", (row["created_by"],)).fetchone() if row["created_by"] else None
    figure["created_by_name"] = creator["display_name"] if creator else ""
    figure["can_delete"] = can_delete(connection, row, uid)
    figure["entries"] = [dict(entry) for entry in connection.execute(
        "SELECT * FROM collection_entries WHERE user_id=? AND figure_id=? ORDER BY purchased_at DESC, id DESC", (uid, figure_id))]
    from .preorders import preorder_rows
    figure["preorders"] = preorder_rows(uid, "p.figure_id=?", (figure_id,))
    figure["lists"] = [dict(entry) for entry in connection.execute(
        """SELECT w.id list_id, w.name, w.is_default, we.target_price, we.note, we.created_at FROM watchlist_entries we
           JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? AND we.figure_id=? ORDER BY w.is_default DESC, w.name""", (uid, figure_id))]
    figure["prices"] = price_history(figure_id)
    figure["owners"] = connection.execute("SELECT COUNT(DISTINCT user_id) FROM collection_entries WHERE figure_id=?", (figure_id,)).fetchone()[0]
    return figure


def in_use(connection, figure_id):
    return any(connection.execute(sql, (figure_id,)).fetchone() for sql in (
        "SELECT 1 FROM collection_entries WHERE figure_id=? LIMIT 1",
        "SELECT 1 FROM preorders WHERE figure_id=? LIMIT 1",
        "SELECT 1 FROM watchlist_entries WHERE figure_id=? LIMIT 1",
    ))


def can_delete(connection, row, uid):
    role = connection.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    allowed = (role and role["role"] == "admin") or row["created_by"] == uid
    return bool(allowed) and not in_use(connection, row["id"])


@app.get("/api/figures/<int:figure_id>")
@login_required
def get_figure(figure_id):
    figure = figure_detail(figure_id, user_id())
    if not figure:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    return jsonify(figure)


def try_image(connection, figure_id, url):
    """Fetches the picture of a newly given image link; a failure is reported, not fatal."""
    if not url:
        return None
    try:
        key = download_image(url)
    except ImageError as error:
        return str(error)
    connection.execute("UPDATE figures SET image_key=? WHERE id=?", (key, figure_id))
    return None


@app.post("/api/figures")
@login_required
def create_figure():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    fields, error = clean_figure_fields(payload)
    if error:
        return jsonify({"error": error}), 400
    connection = db()
    duplicate = find_duplicate(connection, fields)
    if duplicate and not payload.get("force"):
        return jsonify({"error": f"„{duplicate[1]}“ ist schon im Katalog ({duplicate[2]}).", "duplicate_id": duplicate[0]}), 409
    market_value, error = parse_amount(payload.get("market_value"), "Marktwert")
    if error:
        return jsonify({"error": error}), 400
    stamp, uid = now_iso(), user_id()
    columns = ["created_by", "created_at", "updated_at", *fields]
    cursor = connection.execute(
        f"INSERT INTO figures({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", (uid, stamp, stamp, *fields.values()),
    )
    figure_id = cursor.lastrowid
    image_error = try_image(connection, figure_id, fields.get("image_url"))
    if market_value is not None:
        record_price(connection, figure_id, market_value, "import" if payload.get("from_import") else "manual", "", uid, stamp)
    connection.commit()
    return jsonify({**figure_detail(figure_id, uid), "image_error": image_error}), 201


@app.patch("/api/figures/<int:figure_id>")
@login_required
def update_figure(figure_id):
    connection = db()
    current = connection.execute("SELECT * FROM figures WHERE id=?", (figure_id,)).fetchone()
    if not current:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    fields, error = clean_figure_fields(payload, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    merged = {**dict(current), **fields}
    duplicate = find_duplicate(connection, merged, exclude_id=figure_id)
    if duplicate and not payload.get("force"):
        return jsonify({"error": f"„{duplicate[1]}“ ist schon im Katalog ({duplicate[2]}).", "duplicate_id": duplicate[0]}), 409
    connection.execute(f"UPDATE figures SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?",
                       (*fields.values(), now_iso(), figure_id))
    image_error = None
    if "image_url" in fields and fields["image_url"] != current["image_url"]:
        connection.execute("UPDATE figures SET image_key='' WHERE id=?", (figure_id,))
        image_error = try_image(connection, figure_id, fields["image_url"])
    connection.commit()
    return jsonify({**figure_detail(figure_id, user_id()), "image_error": image_error})


@app.delete("/api/figures/<int:figure_id>")
@login_required
def delete_figure(figure_id):
    connection = db()
    row = connection.execute("SELECT * FROM figures WHERE id=?", (figure_id,)).fetchone()
    if not row:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    if in_use(connection, figure_id):
        return jsonify({"error": "Die Figur steht noch in einer Sammlung, Vorbestellung oder Wunschliste und kann nicht gelöscht werden."}), 409
    if not can_delete(connection, row, user_id()):
        return jsonify({"error": "Nur wer die Figur angelegt hat oder ein Admin kann sie löschen."}), 403
    connection.execute("DELETE FROM figures WHERE id=?", (figure_id,))
    connection.commit()
    return jsonify({"deleted": True})


@app.get("/api/search")
@login_required
def global_search():
    """The quick search (Ctrl+K): the best-matching figures of the whole catalogue."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    limit = min(80, max(1, request.args.get("limit", 24, type=int)))
    rows = db().execute(
        f"""SELECT * FROM ({figure_list_sql()}) found
            JOIN (SELECT f.id found_id, {search.figure_score_sql('?2')} score FROM figures f) scored ON scored.found_id=found.id
            WHERE scored.score>0 ORDER BY scored.score DESC, found.name LIMIT ?3""", (user_id(), q, limit),
    ).fetchall()
    return jsonify([list_item(row) for row in rows])
