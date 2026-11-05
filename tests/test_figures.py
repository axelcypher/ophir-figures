"""The shared figure catalogue: browsing, filters, creating and correcting entries, duplicates and
who may delete what."""
import pytest

from conftest import FRIEREN, MIKASA, MIKU, REM, TWINS, ADMIN, default_list, login, query
from ophir_figures.figures import normalize_date


def names(rows):
    return [row["name"] for row in rows]


def test_the_catalogue_lists_every_figure_newest_release_first(client):
    data = client.get("/api/figures").get_json()
    assert [row["id"] for row in data["figures"]] == [TWINS, MIKU, FRIEREN, REM, MIKASA]
    assert data["total"] == 5
    assert data["facets"]["manufacturer"][0] == ["Good Smile Company", 3]
    assert data["facets"]["year"][0] == ["2026", 1], "years newest first"
    assert ["Rem", 2] in data["facets"]["character"], "a figure with two characters counts for each"


@pytest.mark.parametrize("args, expected", [
    ({"manufacturer": "Good Smile Company"}, [MIKU, FRIEREN, MIKASA]),
    ({"category": "Scale-Figur"}, [TWINS, MIKU]),
    ({"series": "Re:Zero"}, [TWINS, REM]),
    ({"character": "Ram"}, [TWINS]),
    ({"year": "2024"}, [FRIEREN]),
    ({"line": "figma"}, [REM]),
    ({"sort": "name"}, [REM, MIKU, FRIEREN, MIKASA, TWINS]),        # case and accents aside
    ({"sort": "release", "direction": "asc"}, [MIKASA, REM, FRIEREN, MIKU, TWINS]),
])
def test_filters_and_sorting(client, args, expected):
    assert [row["id"] for row in client.get("/api/figures", query_string=args).get_json()["figures"]] == expected


def test_each_figure_says_what_the_account_has_of_it(client):
    client.post("/api/collection", json={"figure_id": MIKU, "quantity": 2})
    client.post("/api/collection", json={"figure_id": MIKU, "quantity": 1, "condition": "loose"})
    client.post("/api/preorders", json={"figure_id": TWINS})
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": FRIEREN})
    rows = {row["id"]: row for row in client.get("/api/figures").get_json()["figures"]}
    assert (rows[MIKU]["owned"], rows[TWINS]["preordered"], rows[FRIEREN]["wished"], rows[REM]["owned"]) == (3, 1, True, 0)
    for mode, expected in (("owned", [MIKU]), ("missing", [TWINS, FRIEREN, REM, MIKASA]), ("wished", [FRIEREN]), ("preordered", [TWINS])):
        assert [row["id"] for row in client.get("/api/figures", query_string={"mode": mode}).get_json()["figures"]] == expected, mode
    # Another account sees none of it.
    assert not any(row["owned"] or row["wished"] or row["preordered"] for row in login(ADMIN).get("/api/figures").get_json()["figures"])


def test_creating_a_figure_cleans_up_what_was_typed(client):
    response = client.post("/api/figures", json={
        "name": "  Saber   Alter ", "characters": "Saber Alter; Artoria Pendragon , Saber Alter", "manufacturer": "Alter",
        "release_date": "03/2026", "height_mm": "250 mm", "msrp": "19.800", "msrp_currency": "jpy", "jan": "4560228 2012 34",
        "scale": "1/7", "category": "Scale-Figur", "source_url": "https://example.com/saber",
    })
    assert response.status_code == 201, response.get_json()
    figure = response.get_json()
    assert figure["name"] == "Saber Alter" and figure["characters"] == "Saber Alter, Artoria Pendragon"
    assert (figure["release_date"], figure["height_mm"], figure["msrp_currency"], figure["jan"]) == ("2026-03", 250, "JPY", "4560228201234")
    assert figure["created_by_name"] == "Alex Morgan" and figure["can_delete"] is True
    assert query("SELECT msrp FROM figures WHERE id=?", (figure["id"],))[0]["msrp"] == 19800, "groups of three digits are thousands, as yen prices are written"


@pytest.mark.parametrize("payload, message", [
    ({}, "Name fehlt"), ({"name": "X", "release_date": "irgendwann"}, "kein Datum"), ({"name": "X", "height_mm": "riesig"}, "Millimetern"),
    ({"name": "X", "jan": "12ab"}, "8 bis 14 Ziffern"), ({"name": "X", "source_url": "javascript:alert(1)"}, "http"),
    ({"name": "X", "msrp_currency": "Euro"}, "drei Buchstaben"), ({"name": "X", "msrp": "-5"}, "außerhalb"),
    ({"name": "x" * 301}, "zu lang"),
])
def test_creation_refuses_what_cannot_be_right(client, payload, message):
    response = client.post("/api/figures", json=payload)
    assert response.status_code == 400 and message in response.get_json()["error"]


@pytest.mark.parametrize("text, expected", [
    ("2025", "2025"), ("2025-3", "2025-03"), ("2025/03/14", "2025-03-14"), ("03/2025", "2025-03"), ("14.03.2025", "2025-03-14"),
    ("03/14/2025", "2025-03-14"), ("March 2025", "2025-03"), ("Mär 2025", "2025-03"), ("2025年3月", "2025-03"), ("2025年3月14日", "2025-03-14"),
    ("", ""),
])
def test_dates_are_read_in_the_usual_spellings(text, expected):
    assert normalize_date(text) == (expected, None)


def test_the_same_product_is_not_entered_twice(client):
    by_jan = client.post("/api/figures", json={"name": "Miku anders geschrieben", "jan": "4580590123456"})
    assert by_jan.status_code == 409 and by_jan.get_json()["duplicate_id"] == MIKU
    by_name = client.post("/api/figures", json={"name": "figma  rem", "manufacturer": "Max Factory"})
    assert by_name.status_code == 409 and "Name, Hersteller und Edition" in by_name.get_json()["error"]
    other_edition = client.post("/api/figures", json={"name": "figma Rem", "manufacturer": "Max Factory", "edition": "Limited"})
    assert other_edition.status_code == 201, "another edition is another product"
    forced = client.post("/api/figures", json={"name": "figma Rem", "manufacturer": "Max Factory", "force": True})
    assert forced.status_code == 201


def test_anyone_can_correct_an_entry_but_not_into_a_duplicate(client):
    response = client.patch(f"/api/figures/{MIKASA}", json={"edition": "Re-release", "release_date": "2025-01-31"})
    assert response.status_code == 200 and response.get_json()["release_date"] == "2025-01-31"
    clash = client.patch(f"/api/figures/{REM}", json={"jan": "4580590123456"})
    assert clash.status_code == 409
    assert client.patch(f"/api/figures/{REM}", json={"name": ""}).status_code == 400
    assert client.patch("/api/figures/999", json={"name": "Weg"}).status_code == 404


def test_deleting_needs_the_creator_or_an_admin_and_an_unused_figure(client):
    own = client.post("/api/figures", json={"name": "Testfigur"}).get_json()["id"]
    assert client.delete(f"/api/figures/{MIKU}").status_code == 403, "the sample figures were made by the admin"
    client.post("/api/collection", json={"figure_id": own})
    assert client.delete(f"/api/figures/{own}").status_code == 409
    entry = query("SELECT id FROM collection_entries WHERE figure_id=?", (own,))[0]["id"]
    client.delete(f"/api/collection/{entry}")
    assert client.delete(f"/api/figures/{own}").get_json() == {"deleted": True}
    assert login(ADMIN).delete(f"/api/figures/{MIKU}").get_json() == {"deleted": True}


def test_a_figure_detail_has_everything_of_the_account_around_it(client):
    client.post("/api/collection", json={"figure_id": TWINS, "purchase_price": 180})
    client.post("/api/preorders", json={"figure_id": TWINS, "price": 200})
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": TWINS, "target_price": 150})
    client.post(f"/api/figures/{TWINS}/prices", json={"amount": 230})
    detail = client.get(f"/api/figures/{TWINS}").get_json()
    assert len(detail["entries"]) == 1 and detail["entries"][0]["purchase_price"] == 180
    assert detail["preorders"][0]["price"] == 200 and detail["preorders"][0]["expected_release"] == "2026-12"
    assert detail["lists"][0]["target_price"] == 150 and detail["market_value"] == 230
    assert [price["amount"] for price in detail["prices"]] == [230] and detail["owners"] == 1


def test_suggestions_offer_what_the_catalogue_and_the_account_use(client):
    client.post("/api/collection", json={"figure_id": MIKU, "shop": "AmiAmi", "location": "Vitrine"})
    suggestions = client.get("/api/figures/suggestions").get_json()
    assert suggestions["manufacturer"][0] == "Good Smile Company"
    assert {"Rem", "Ram", "Hatsune Miku"} <= set(suggestions["character"])
    assert suggestions["shop"] == ["AmiAmi"] and suggestions["location"] == ["Vitrine"]
    assert "Nendoroid" in suggestions["category"] and "1/7" in suggestions["scale"]
    assert login(ADMIN).get("/api/figures/suggestions").get_json()["shop"] == [], "shops are the account's own"
