"""Backups: export, restore into the same or another catalogue, undo, CSV."""
import sqlite3

from conftest import ADMIN, FRIEREN, MIKU, TWINS, default_list, login, ophir_figures, query


def fill(client):
    client.post("/api/collection", json={"figure_id": MIKU, "quantity": 2, "purchase_price": 150, "shop": "AmiAmi", "location": "Vitrine"})
    preorder = client.post("/api/preorders", json={"figure_id": TWINS, "price": 250, "shipping": 15, "expected_release": "2026-10"}).get_json()
    client.patch(f"/api/preorders/{preorder['id']}", json={"expected_release": "2026-12"})
    arrived = client.post("/api/preorders", json={"figure_id": FRIEREN, "price": 45, "ordered_at": "2024-03-01"}).get_json()
    client.patch(f"/api/preorders/{arrived['id']}", json={"status": "delivered"})
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": FRIEREN, "target_price": 30, "note": "zweites Exemplar"})
    extra = client.post("/api/watchlists", json={"name": "Grails"}).get_json()
    client.post(f"/api/watchlists/{extra['id']}/figures", json={"figure_id": TWINS})
    client.post(f"/api/figures/{MIKU}/prices", json={"amount": 199})


def test_the_backup_carries_the_figures_it_refers_to(client):
    fill(client)
    backup = client.get("/api/export.json").get_json()
    assert backup["format"] == "ophir-figures-backup" and backup["user"]["username"] == "demo"
    assert sorted(figure["ref"] for figure in backup["figures"]) == [MIKU, FRIEREN, TWINS]
    assert next(figure for figure in backup["figures"] if figure["ref"] == MIKU)["market_value"] == 199
    assert len(backup["collection"]) == 2 and len(backup["preorders"]) == 2
    twins = next(item for item in backup["preorders"] if item["figure_ref"] == TWINS)
    assert [event["kind"] for event in twins["events"]] == ["created", "release"]
    booked = next(item for item in backup["collection"] if item["figure_ref"] == FRIEREN)
    assert backup["preorders"][booked["preorder_index"]]["figure_ref"] == FRIEREN
    assert [(item["name"], len(item["entries"])) for item in backup["watchlists"]] == [("Wunschliste", 1), ("Grails", 1)]


def test_restoring_into_an_empty_account_and_undoing_it(client):
    fill(client)
    backup = client.get("/api/export.json").get_json()
    other = login(ADMIN)
    preview = other.post("/api/import/json/preview", json={"data": backup}).get_json()
    assert (preview["figures"], preview["figures_new"], preview["collection"], preview["preorders"]) == (3, 0, 2, 2)
    result = other.post("/api/import/json/apply", json={"data": backup}).get_json()
    assert (result["figures_created"], result["collection"], result["preorders"], result["watchlist_entries"]) == (0, 2, 2, 2)
    assert other.get("/api/collection").get_json()["stats"]["copies"] == 3
    preorders = other.get("/api/preorders?status=all").get_json()["preorders"]
    assert {row["figure_id"]: row["delays"] for row in preorders} == {TWINS: 1, FRIEREN: 0}
    assert any(row["booked_entry_ids"] for row in preorders if row["figure_id"] == FRIEREN), "the booked copies stay linked"
    assert [item["name"] for item in other.get("/api/watchlists").get_json()] == ["Wunschliste", "Grails"]
    # Restoring again adds the collection again but not the preorders.
    again = other.post("/api/import/json/apply", json={"data": backup}).get_json()
    assert again["preorders"] == 0 and again["preorders_skipped"] == 2
    assert other.post(f"/api/import/{result['operation_id']}/undo", json={}).status_code == 400, "only the latest one"
    assert other.post(f"/api/import/{again['operation_id']}/undo", json={}).get_json() == {"undone": True}
    assert other.post(f"/api/import/{result['operation_id']}/undo", json={}).get_json() == {"undone": True}
    assert other.get("/api/collection").get_json()["stats"]["copies"] == 0
    assert other.get("/api/preorders?status=all").get_json()["preorders"] == []
    assert [item["name"] for item in other.get("/api/watchlists").get_json()] == ["Wunschliste"]


def test_replacing_the_collection_can_be_taken_back(client):
    client.post("/api/collection", json={"figure_id": TWINS, "quantity": 4})
    backup = client.get("/api/export.json").get_json()
    client.post("/api/collection", json={"figure_id": MIKU})
    result = client.post("/api/import/json/apply", json={"data": backup, "strategy": "replace"}).get_json()
    assert result["replaced"] == 2
    assert [(row["id"], row["owned"]) for row in client.get("/api/collection").get_json()["figures"]] == [(TWINS, 4)]
    client.post(f"/api/import/{result['operation_id']}/undo", json={})
    assert sorted((row["id"], row["owned"]) for row in client.get("/api/collection").get_json()["figures"]) == [(MIKU, 1), (TWINS, 4)]


def test_a_backup_from_another_instance_creates_the_missing_figures(client):
    backup = {"format": "ophir-figures-backup", "version": 1, "figures": [
        {"ref": 900, "name": "Saber Alter 1/7", "manufacturer": "Alter", "release_date": "2026-05", "jan": "4560228209999"},
        {"ref": 901, "name": "Hatsune Miku: Racing 2024 Ver.", "jan": "4580590123456"},
    ], "collection": [{"figure_ref": 900, "quantity": 1, "condition": "sealed"}, {"figure_ref": 901, "quantity": 1}],
        "preorders": [], "watchlists": []}
    result = client.post("/api/import/json/apply", json={"data": backup}).get_json()
    assert result["figures_created"] == 1
    owned = {row["name"] for row in client.get("/api/collection").get_json()["figures"]}
    assert owned == {"Saber Alter 1/7", "Hatsune Miku: Racing 2024 Ver."}
    client.post(f"/api/import/{result['operation_id']}/undo", json={})
    assert not query("SELECT 1 FROM figures WHERE name='Saber Alter 1/7'"), "a figure the restore created goes with it"


def test_broken_backups_are_refused_without_a_trace(client):
    for data in (None, {"format": "deckledger"}, {"format": "ophir-figures-backup"},
                 {"format": "ophir-figures-backup", "figures": [{"ref": 1, "name": ""}]},
                 {"format": "ophir-figures-backup", "figures": [], "collection": [{"figure_ref": 5}]}):
        response = client.post("/api/import/json/apply", json={"data": data})
        assert response.status_code == 400, data
    assert query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 0
    assert query("SELECT COUNT(*) n FROM import_operations")[0]["n"] == 0


def test_csv_exports_are_readable_by_spreadsheets(client):
    fill(client)
    collection = client.get("/api/export.csv")
    text = collection.data.decode("utf-8")
    assert text.startswith("﻿Name;") and "Hatsune Miku: Racing 2024 Ver." in text and "150,00" in text and "Geöffnet, mit Karton" in text
    preorders = client.get("/api/export/preorders.csv").data.decode("utf-8")
    assert "Rem & Ram: Twins Ver." in preorders and "Angekommen" in preorders


def test_the_database_keeps_its_foreign_keys_after_a_restore(client):
    fill(client)
    login(ADMIN).post("/api/import/json/apply", json={"data": client.get("/api/export.json").get_json()})
    connection = sqlite3.connect(ophir_figures.config.DB_PATH)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
