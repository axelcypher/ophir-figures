"""Market values of figures: entered by hand (or brought along by a link import), shared by every
account, kept as a history. The newest value is the current one.

A copy in a collection is worth the figure's current market value; without one, what was paid
for it (collection_value_sql). Retail prices (MSRP) are catalogue data, not market values.
"""

import re

from flask import jsonify, request

from .config import CURRENCY, now_iso
from .web import app, db, login_required, user_id

PRICE_LIMIT = 1_000_000


def market_value_sql(figure_column="f.id"):
    """The current market value of the figure in `figure_column`, as a correlated subquery."""
    return (f"(SELECT po.amount FROM price_observations po WHERE po.figure_id={figure_column} "
            "ORDER BY po.observed_at DESC, po.id DESC LIMIT 1)")


def collection_value_sql(entry="c", figure_column="c.figure_id"):
    """What one collection row is worth: copies times market value, else times purchase price."""
    return f"({entry}.quantity * COALESCE({market_value_sql(figure_column)}, {entry}.purchase_price, 0))"


def parse_amount(value, field="Betrag", allow_none=True):
    """A money amount from a form, typed as Germans and others do: 189,90 / 189.90 / 1.299,00 /
    1,299.00 / 19.800 (thousands, as yen prices are written). (value, error)."""
    if value in (None, ""):
        return (None, None) if allow_none else (None, f"{field} fehlt.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = repr(float(value))
    else:
        text = re.sub(r"[\s€¥$£]|EUR|JPY|USD", "", str(value), flags=re.I)
        if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", text):                  # 19.800 / 1,299: groups of thousands
            text = re.sub(r"[.,]", "", text)
        elif "," in text and "." in text:                                   # the last mark is the decimal one
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        else:
            text = text.replace(",", ".")
    try:
        amount = round(float(text), 2)
    except ValueError:
        return None, f"{field} ist keine Zahl."
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None, f"{field} ist keine Zahl."
    if amount < 0 or amount > PRICE_LIMIT:
        return None, f"{field} liegt außerhalb des erlaubten Bereichs."
    return amount, None


def price_history(figure_id):
    return [dict(row) for row in db().execute(
        """SELECT po.id,po.amount,po.currency,po.source,po.note,po.observed_at,u.display_name author
           FROM price_observations po LEFT JOIN users u ON u.id=po.user_id
           WHERE po.figure_id=? ORDER BY po.observed_at DESC, po.id DESC""", (figure_id,))]


def record_price(connection, figure_id, amount, source="manual", note="", uid=None, observed_at=None):
    connection.execute(
        "INSERT INTO price_observations(figure_id,amount,currency,source,note,user_id,observed_at) VALUES(?,?,?,?,?,?,?)",
        (figure_id, amount, CURRENCY, source, note, uid, observed_at or now_iso()),
    )


@app.get("/api/figures/<int:figure_id>/prices")
@login_required
def figure_prices(figure_id):
    if not db().execute("SELECT 1 FROM figures WHERE id=?", (figure_id,)).fetchone():
        return jsonify({"error": "Figur nicht gefunden."}), 404
    return jsonify(price_history(figure_id))


@app.post("/api/figures/<int:figure_id>/prices")
@login_required
def add_figure_price(figure_id):
    if not db().execute("SELECT 1 FROM figures WHERE id=?", (figure_id,)).fetchone():
        return jsonify({"error": "Figur nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    amount, error = parse_amount(payload.get("amount"), "Marktwert", allow_none=False)
    if error:
        return jsonify({"error": error}), 400
    note = str(payload.get("note") or "").strip()[:200]
    record_price(db(), figure_id, amount, "manual", note, user_id())
    db().commit()
    return jsonify(price_history(figure_id)), 201


@app.delete("/api/figures/<int:figure_id>/prices/<int:price_id>")
@login_required
def delete_figure_price(figure_id, price_id):
    deleted = db().execute("DELETE FROM price_observations WHERE id=? AND figure_id=?", (price_id, figure_id)).rowcount
    if not deleted:
        return jsonify({"error": "Wert nicht gefunden."}), 404
    db().commit()
    return jsonify(price_history(figure_id))
