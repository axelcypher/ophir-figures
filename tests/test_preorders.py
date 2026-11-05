"""Preorders: payments, postponed releases, and arrival booked into the collection."""
import pytest

from conftest import ADMIN, MIKU, REM, TWINS, default_list, login, query


def order(client, figure_id=TWINS, **fields):
    response = client.post("/api/preorders", json={"figure_id": figure_id, "shop": "AmiAmi", "price": "240,00", "shipping": 20, **fields})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_a_preorder_starts_with_the_figures_release_and_today(client):
    preorder = order(client)
    assert (preorder["status"], preorder["expected_release"], preorder["total"], preorder["outstanding"]) == ("ordered", "2026-12", 260, 260)
    assert preorder["ordered_at"] and preorder["figure_name"] == "Rem & Ram: Twins Ver."
    assert [event["kind"] for event in preorder["events"]] == ["created"]


@pytest.mark.parametrize("fields, message", [
    ({"status": "lost"}, "Status"), ({"quantity": 0}, "zwischen 1"), ({"price": "viel"}, "keine Zahl"),
    ({"expected_release": "bald"}, "kein Datum"),
])
def test_wrong_input_is_refused(client, fields, message):
    response = client.post("/api/preorders", json={"figure_id": TWINS, **fields})
    assert response.status_code == 400 and message in response.get_json()["error"]


def test_postponements_are_counted(client):
    preorder = order(client, expected_release="2026-03")
    for month in ("2026-05", "2026-05-20", "2026-08", "2026-07"):
        updated = client.patch(f"/api/preorders/{preorder['id']}", json={"expected_release": month}).get_json()
    assert updated["expected_release"] == "2026-07"
    # March -> May and May -> August are delays; a day within May and the move back to July are not.
    assert updated["delays"] == 2
    assert [(event["old_value"], event["new_value"]) for event in updated["events"] if event["kind"] == "release"][0] == ("2026-03", "2026-05")


def test_marking_paid_settles_the_amount(client):
    preorder = order(client, paid=50)
    assert preorder["outstanding"] == 210
    paid = client.patch(f"/api/preorders/{preorder['id']}", json={"status": "paid"}).get_json()
    assert (paid["paid"], paid["outstanding"]) == (260, 0)
    assert {event["kind"] for event in paid["events"]} == {"created", "status", "paid"}


def test_arrival_books_the_copies_into_the_collection_and_back_out(client):
    preorder = order(client, quantity=2, order_number="A-123", ordered_at="2025-10-01")
    delivered = client.patch(f"/api/preorders/{preorder['id']}", json={"status": "delivered"}).get_json()
    assert delivered["delivered_at"] and len(delivered["booked_entry_ids"]) == 1
    entry = query("SELECT * FROM collection_entries")[0]
    assert (entry["figure_id"], entry["quantity"], entry["condition"], entry["purchase_price"]) == (TWINS, 2, "sealed", 130)
    assert (entry["purchased_at"], entry["shop"], entry["notes"]) == ("2025-10-01", "AmiAmi", "Vorbestellung A-123")
    # Correcting the arrived order corrects what it booked.
    client.patch(f"/api/preorders/{preorder['id']}", json={"shipping": 40})
    assert query("SELECT purchase_price p FROM collection_entries")[0]["p"] == 140
    # Taking the arrival back takes the copies out again.
    back = client.patch(f"/api/preorders/{preorder['id']}", json={"status": "shipped"}).get_json()
    assert back["delivered_at"] is None and query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 0


def test_deleting_an_arrived_preorder_keeps_the_copies(client):
    preorder = order(client)
    client.patch(f"/api/preorders/{preorder['id']}", json={"status": "delivered"})
    assert client.delete(f"/api/preorders/{preorder['id']}").get_json() == {"deleted": True}
    assert query("SELECT preorder_id FROM collection_entries") == [{"preorder_id": None}]


def test_a_preorder_entered_as_arrived_is_booked_at_once(client):
    order(client, status="delivered")
    assert query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 1


def test_ordering_can_take_the_figure_off_the_wishlists(client):
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": TWINS})
    order(client, remove_from_wishlists=True)
    assert query("SELECT COUNT(*) n FROM watchlist_entries")[0]["n"] == 0


def test_the_overview_counts_and_filters(client):
    order(client, TWINS, expected_release="2026-12", paid=20)
    old = order(client, MIKU, expected_release="2025-01")
    gone = order(client, REM)
    client.patch(f"/api/preorders/{gone['id']}", json={"status": "cancelled"})
    data = client.get("/api/preorders").get_json()
    assert [row["figure_id"] for row in data["preorders"]] == [MIKU, TWINS], "open ones, by expected release"
    assert data["stats"]["open"] == 2 and data["stats"]["outstanding"] == 500 and data["stats"]["cancelled"] == 1
    assert data["stats"]["overdue"] >= 1, "a release month in the past is overdue"
    assert [row["id"] for row in client.get("/api/preorders?status=cancelled").get_json()["preorders"]] == [gone["id"]]
    assert len(client.get("/api/preorders?status=all").get_json()["preorders"]) == 3
    assert old["id"] in [row["id"] for row in client.get("/api/preorders").get_json()["preorders"]]


def test_preorders_are_private(client):
    preorder = order(client)
    other = login(ADMIN)
    assert other.get("/api/preorders").get_json()["preorders"] == []
    assert other.patch(f"/api/preorders/{preorder['id']}", json={"status": "cancelled"}).status_code == 404
    assert other.delete(f"/api/preorders/{preorder['id']}").status_code == 404
