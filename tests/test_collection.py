"""The collection: copies with condition and purchase, what they cost and are worth."""
import pytest

from conftest import ADMIN, FRIEREN, MIKU, REM, TWINS, login, query


def add(client, figure_id, **fields):
    response = client.post("/api/collection", json={"figure_id": figure_id, **fields})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_copies_are_added_with_their_purchase(client):
    entry = add(client, MIKU, quantity=2, condition="sealed", purchase_price="189,90", purchased_at="14.03.2025", shop="AmiAmi",
                location="Vitrine 1", notes="mit Bonusteil")
    assert (entry["quantity"], entry["condition"], entry["purchase_price"], entry["purchased_at"]) == (2, "sealed", 189.9, "2025-03-14")
    assert (entry["shop"], entry["location"], entry["notes"]) == ("AmiAmi", "Vitrine 1", "mit Bonusteil")


@pytest.mark.parametrize("fields, message", [
    ({"quantity": 0}, "zwischen 1"), ({"quantity": "viele"}, "keine Zahl"), ({"condition": "mint"}, "Zustand"),
    ({"purchase_price": "teuer"}, "keine Zahl"), ({"purchased_at": "gestern"}, "kein Datum"),
])
def test_wrong_input_is_refused(client, fields, message):
    response = client.post("/api/collection", json={"figure_id": MIKU, **fields})
    assert response.status_code == 400 and message in response.get_json()["error"]
    assert client.post("/api/collection", json={"figure_id": 999}).status_code == 404


def test_the_collection_adds_up_cost_and_value(client):
    add(client, MIKU, quantity=2, purchase_price=150)
    add(client, MIKU, quantity=1, purchase_price=100, condition="loose", location="Regal")
    add(client, FRIEREN, purchase_price=45)
    add(client, REM)                                      # no price known at all
    add(client, TWINS)                                    # no purchase price, but a market value
    client.post(f"/api/figures/{FRIEREN}/prices", json={"amount": 60})
    client.post(f"/api/figures/{TWINS}/prices", json={"amount": 200})
    data = client.get("/api/collection").get_json()
    rows = {row["id"]: row for row in data["figures"]}
    assert data["stats"] == {"figures": 4, "copies": 6, "value": 660.0, "spent": 445.0, "unpriced": 1, "with_market_value": 2}
    assert (rows[MIKU]["spent"], rows[MIKU]["value"], sorted(rows[MIKU]["conditions"]), rows[MIKU]["locations"]) == (400, 400, ["boxed", "loose"], ["Regal"])
    assert rows[FRIEREN]["value"] == 60, "the market value wins over what was paid"
    assert rows[REM]["value"] == 0 and rows[REM]["unpriced"] == 1


def test_collection_filters(client):
    add(client, MIKU, location="Vitrine", condition="sealed")
    add(client, FRIEREN, location="Regal")
    add(client, TWINS, location="Vitrine")
    ids = lambda **args: [row["id"] for row in client.get("/api/collection", query_string=args).get_json()["figures"]]
    assert ids(location="Vitrine", sort="name") == [MIKU, TWINS]
    assert ids(condition="sealed") == [MIKU]
    assert ids(manufacturer="Good Smile Company", sort="name") == [MIKU, FRIEREN]
    assert ids(sort="added", direction="asc") == [MIKU, FRIEREN, TWINS]
    facets = client.get("/api/collection").get_json()["facets"]
    assert facets["location"] == [["Vitrine", 2], ["Regal", 1]]


def test_rows_are_edited_and_deleted_by_their_owner_only(client):
    entry = add(client, MIKU, quantity=1)
    assert client.patch(f"/api/collection/{entry['id']}", json={"quantity": 3, "shop": "Solaris"}).get_json()["quantity"] == 3
    other = login(ADMIN)
    assert other.patch(f"/api/collection/{entry['id']}", json={"quantity": 9}).status_code == 404
    assert other.delete(f"/api/collection/{entry['id']}").status_code == 404
    deleted = client.delete(f"/api/collection/{entry['id']}").get_json()["deleted"]
    assert deleted["shop"] == "Solaris" and query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 0
    # What came back is enough to put the row back (the "undo" of the toast).
    restored = client.post("/api/collection", json={key: deleted[key] for key in ("figure_id", "quantity", "condition", "shop")})
    assert restored.status_code == 201


def test_the_dashboard_sums_up(client):
    add(client, MIKU, quantity=2, purchase_price=100)
    add(client, FRIEREN, purchase_price=40)
    client.post("/api/preorders", json={"figure_id": TWINS, "price": 250, "shipping": 15, "paid": 50, "expected_release": "2026-12"})
    data = client.get("/api/dashboard").get_json()
    assert (data["collection"]["figures"], data["collection"]["copies"], data["collection"]["spent"]) == (2, 3, 240)
    assert [item["id"] for item in data["collection"]["recent"]] == [FRIEREN, MIKU]
    assert data["preorders"]["stats"]["outstanding"] == 215 and data["preorders"]["upcoming"][0]["figure_id"] == TWINS
    assert data["counts"] == {"collection": 2, "wished": 0, "preorders": 1, "catalog": 5}
