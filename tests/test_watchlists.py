"""Wishlists: a default list per account, further named lists, target prices."""
from conftest import ADMIN, FRIEREN, MIKU, REM, TWINS, default_list, login


def test_every_account_has_a_default_list_that_stays(client):
    lists = client.get("/api/watchlists").get_json()
    assert [(item["name"], item["is_default"], item["count"]) for item in lists] == [("Wunschliste", 1, 0)]
    assert client.delete(f"/api/watchlists/{lists[0]['id']}").status_code == 400


def test_named_lists_are_created_renamed_and_deleted(client):
    created = client.post("/api/watchlists", json={"name": "  Geburtstag  "}).get_json()
    assert created["name"] == "Geburtstag"
    assert client.post("/api/watchlists", json={"name": "geburtstag"}).status_code == 400
    assert client.post("/api/watchlists", json={"name": ""}).status_code == 400
    assert client.patch(f"/api/watchlists/{created['id']}", json={"name": "Weihnachten"}).status_code == 200
    client.post(f"/api/watchlists/{created['id']}/figures", json={"figure_id": MIKU})
    assert client.delete(f"/api/watchlists/{created['id']}").get_json() == {"deleted": True}
    assert [item["name"] for item in client.get("/api/watchlists").get_json()] == ["Wunschliste"]
    assert login(ADMIN).delete(f"/api/watchlists/{default_list(client)}").status_code == 404, "lists are the account's own"


def test_entries_carry_target_price_and_note(client):
    list_id = default_list(client)
    assert client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": MIKU, "target_price": "180", "note": "nur neu"}).status_code == 201
    client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": TWINS})
    client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": MIKU})          # adding again changes nothing
    client.post(f"/api/figures/{MIKU}/prices", json={"amount": 175})
    data = client.get(f"/api/watchlists/{list_id}/figures").get_json()
    rows = {row["id"]: row for row in data["figures"]}
    assert (rows[MIKU]["target_price"], rows[MIKU]["note"], rows[MIKU]["target_reached"]) == (180, "nur neu", True)
    assert rows[TWINS]["target_reached"] is False
    assert data["stats"] == {"count": 2, "owned": 0, "target_reached": 1, "estimate": 175}
    assert client.patch(f"/api/watchlists/{list_id}/figures/{MIKU}", json={"target_price": ""}).status_code == 200
    assert client.get(f"/api/watchlists/{list_id}/figures").get_json()["stats"]["target_reached"] == 0
    assert client.patch(f"/api/watchlists/{list_id}/figures/{REM}", json={"note": "x"}).status_code == 404


def test_removing_returns_what_is_needed_to_put_it_back(client):
    list_id = default_list(client)
    client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": FRIEREN, "target_price": 30})
    removed = client.delete(f"/api/watchlists/{list_id}/figures/{FRIEREN}").get_json()
    assert removed["removed"] == {"figure_id": FRIEREN, "target_price": 30, "note": ""} and removed["lists"][0]["count"] == 0
    assert client.delete(f"/api/watchlists/{list_id}/figures/{FRIEREN}").status_code == 404


def test_the_list_marks_what_is_already_owned(client):
    list_id = default_list(client)
    for figure_id in (MIKU, REM):
        client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": figure_id})
    client.post("/api/collection", json={"figure_id": REM})
    data = client.get(f"/api/watchlists/{list_id}/figures", query_string={"mode": "missing"}).get_json()
    assert [row["id"] for row in data["figures"]] == [MIKU] and data["stats"]["owned"] == 1
