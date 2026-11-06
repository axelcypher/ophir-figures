"""Presets per product line: what a line fixes -- manufacturer, brand, category, scale, material --
so that choosing the line fills those fields of a figure instead of typing them for every figure
of a line that comes from one company.

Shared by every account, like the catalogue: one preset per line, the line's name matched without
regard to case (line_key). Anyone signed in can add and correct a preset; only whoever made it or
an admin can delete it. A preset only ever fills fields and never takes a value away: the form
keeps them editable, the link import fills what the page did not say (or only guessed), and
applying a preset to the catalogue fills empty fields only.
"""

from flask import jsonify, request

from . import search
from .config import now_iso
from .figures import TEXT_LIMIT
from .web import app, db, login_required, user_id

PRESET_FIELDS = ("manufacturer", "brand", "category", "scale", "material")
FIELD_NAMES = {"line": "Linie", "manufacturer": "Hersteller", "brand": "Marke", "category": "Kategorie", "scale": "Maßstab", "material": "Material"}


def line_key(text):
    """How two lines' names are compared: spacing and case aside ("figma" is "FIGMA ")."""
    return " ".join(str(text or "").split()).casefold()


def clean_preset(payload, partial=False):
    """The preset fields of a request body, checked: (fields, error)."""
    fields = {}
    for key in ("line", *PRESET_FIELDS):
        if key in payload or (key == "line" and not partial):
            value = " ".join(str(payload.get(key) or "").split())
            if len(value) > TEXT_LIMIT:
                return None, f"„{FIELD_NAMES[key]}“ ist zu lang (höchstens {TEXT_LIMIT} Zeichen)."
            fields[key] = value
    if "line" in fields and not fields["line"]:
        return None, "Die Linie fehlt."
    return fields, None


def all_presets(connection):
    return [dict(row) for row in connection.execute("SELECT * FROM line_presets ORDER BY line COLLATE NOCASE")]


def preset_for(connection, line, exclude_id=0):
    """The preset of a line, or None."""
    key = line_key(line)
    if not key:
        return None
    return next((preset for preset in all_presets(connection) if line_key(preset["line"]) == key and preset["id"] != exclude_id), None)


def fill_from_preset(connection, fields, guessed=()):
    """Fills a figure's fields (a dict, changed in place) from its line's preset: the empty ones and
    those named in `guessed` (a value the link import only inferred). Returns {id, line, applied}
    or None without a preset."""
    preset = preset_for(connection, fields.get("line"))
    if not preset:
        return None
    applied = []
    for key in PRESET_FIELDS:
        if preset[key] and (not fields.get(key) or key in guessed) and fields.get(key) != preset[key]:
            fields[key] = preset[key]
            applied.append(key)
    return {"id": preset["id"], "line": preset["line"], "applied": applied}


def is_admin(connection, uid):
    row = connection.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row and row["role"] == "admin")


def preset_item(preset, figures_by_line, names, uid, admin):
    """A preset as the API shows it: with how many catalogue figures have its line and how many of
    them it would complete (an empty field the preset fills)."""
    figures = figures_by_line.get(line_key(preset["line"]), [])
    return {
        **{key: preset[key] for key in ("id", "line", *PRESET_FIELDS, "created_at", "updated_at")},
        "figures": len(figures),
        "incomplete": sum(1 for figure in figures if any(preset[key] and not figure[key] for key in PRESET_FIELDS)),
        "created_by_name": names.get(preset["created_by"], ""),
        "can_delete": admin or preset["created_by"] == uid,
    }


def catalogue_lines(connection):
    """The catalogue's figures that have a line, by line_key."""
    by_line = {}
    for row in connection.execute(f"SELECT id, line, {', '.join(PRESET_FIELDS)} FROM figures WHERE line!=''"):
        by_line.setdefault(line_key(row["line"]), []).append(dict(row))
    return by_line


def common_values(figures):
    """What a line's figures mostly say per preset field: the start of a preset for it."""
    common = {}
    for key in PRESET_FIELDS:
        counts = {}
        for figure in figures:
            if figure[key]:
                counts[figure[key]] = counts.get(figure[key], 0) + 1
        common[key] = max(counts, key=lambda value: (counts[value], value)) if counts else ""
    return common


def detail(connection, preset_id, uid):
    preset = connection.execute("SELECT * FROM line_presets WHERE id=?", (preset_id,)).fetchone()
    if not preset:
        return None
    names = {row["id"]: row["display_name"] for row in connection.execute("SELECT id, display_name FROM users")}
    return preset_item(dict(preset), catalogue_lines(connection), names, uid, is_admin(connection, uid))


@app.get("/api/line-presets")
@login_required
def list_line_presets():
    """Every preset, and the catalogue's lines that have none yet, each with what its figures mostly
    say -- so a preset for a line already in use starts filled in."""
    connection, uid = db(), user_id()
    by_line = catalogue_lines(connection)
    names = {row["id"]: row["display_name"] for row in connection.execute("SELECT id, display_name FROM users")}
    admin = is_admin(connection, uid)
    presets = all_presets(connection)
    covered = {line_key(preset["line"]) for preset in presets}
    lines = []
    for key, figures in by_line.items():
        if key in covered:
            continue
        spellings = {}
        for figure in figures:
            spellings[figure["line"]] = spellings.get(figure["line"], 0) + 1
        lines.append({"line": max(spellings, key=lambda value: (spellings[value], value)), "figures": len(figures), "common": common_values(figures)})
    lines.sort(key=lambda item: (-item["figures"], search.fold(item["line"])))
    return jsonify({"presets": [preset_item(preset, by_line, names, uid, admin) for preset in presets], "lines": lines,
                    "fields": list(PRESET_FIELDS)})


def refuse_empty(fields):
    if not any(fields.get(key) for key in PRESET_FIELDS):
        return jsonify({"error": "Die Vorlage legt noch nichts fest: trag mindestens Hersteller, Marke, Kategorie, Maßstab oder Material ein."}), 400
    return None


def refuse_taken(connection, line, exclude_id=0):
    taken = preset_for(connection, line, exclude_id)
    if taken:
        return jsonify({"error": f"Für die Linie „{taken['line']}“ gibt es schon eine Vorlage.", "preset_id": taken["id"]}), 409
    return None


@app.post("/api/line-presets")
@login_required
def create_line_preset():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    fields, error = clean_preset(payload)
    if error:
        return jsonify({"error": error}), 400
    connection = db()
    if refused := refuse_empty(fields) or refuse_taken(connection, fields["line"]):
        return refused
    stamp, uid = now_iso(), user_id()
    columns = ["created_by", "created_at", "updated_at", *fields]
    cursor = connection.execute(f"INSERT INTO line_presets({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                (uid, stamp, stamp, *fields.values()))
    connection.commit()
    return jsonify(detail(connection, cursor.lastrowid, uid)), 201


@app.patch("/api/line-presets/<int:preset_id>")
@login_required
def update_line_preset(preset_id):
    connection, uid = db(), user_id()
    current = connection.execute("SELECT * FROM line_presets WHERE id=?", (preset_id,)).fetchone()
    if not current:
        return jsonify({"error": "Vorlage nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    fields, error = clean_preset(payload, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    if refused := refuse_empty({**dict(current), **fields}) or ("line" in fields and refuse_taken(connection, fields["line"], preset_id)):
        return refused
    connection.execute(f"UPDATE line_presets SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?",
                       (*fields.values(), now_iso(), preset_id))
    connection.commit()
    return jsonify(detail(connection, preset_id, uid))


@app.delete("/api/line-presets/<int:preset_id>")
@login_required
def delete_line_preset(preset_id):
    connection, uid = db(), user_id()
    preset = connection.execute("SELECT * FROM line_presets WHERE id=?", (preset_id,)).fetchone()
    if not preset:
        return jsonify({"error": "Vorlage nicht gefunden."}), 404
    if preset["created_by"] != uid and not is_admin(connection, uid):
        return jsonify({"error": "Nur wer die Vorlage angelegt hat oder ein Admin kann sie löschen."}), 403
    connection.execute("DELETE FROM line_presets WHERE id=?", (preset_id,))
    connection.commit()
    return jsonify({"deleted": True})


@app.post("/api/line-presets/<int:preset_id>/apply")
@login_required
def apply_line_preset(preset_id):
    """Completes the catalogue's figures of the preset's line: fills their empty fields from it.
    A field that has a value keeps it. Returns how many figures changed and which fields."""
    connection = db()
    preset = connection.execute("SELECT * FROM line_presets WHERE id=?", (preset_id,)).fetchone()
    if not preset:
        return jsonify({"error": "Vorlage nicht gefunden."}), 404
    stamp, filled, updated = now_iso(), {}, 0
    for figure in catalogue_lines(connection).get(line_key(preset["line"]), []):
        changes = {key: preset[key] for key in PRESET_FIELDS if preset[key] and not figure[key]}
        if not changes:
            continue
        connection.execute(f"UPDATE figures SET {','.join(f'{key}=?' for key in changes)}, updated_at=? WHERE id=?",
                           (*changes.values(), stamp, figure["id"]))
        updated += 1
        for key in changes:
            filled[key] = filled.get(key, 0) + 1
    connection.commit()
    return jsonify({"updated": updated, "filled": filled})
