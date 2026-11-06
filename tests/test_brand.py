"""A figure's brand beside its manufacturer: stored, filtered, sorted, searched, read from product
pages and carried through export and restore. (Migration 0004 adds the column.)"""
import pytest

from conftest import FRIEREN, MIKASA, MIKU, REM, TWINS, query


def set_brands(**brands):
    for figure_id, brand in brands.items():
        query("UPDATE figures SET brand=? WHERE id=?", (brand, int(figure_id.removeprefix("f"))))


@pytest.fixture
def branded():
    # Twins and Rem keep no brand.
    set_brands(**{f"f{MIKU}": "Good Smile Company", f"f{FRIEREN}": "Good Smile Company", f"f{MIKASA}": "Good Smile Arts"})


def ids(client, **args):
    return [row["id"] for row in client.get("/api/figures", query_string=args).get_json()["figures"]]


def test_a_figure_keeps_its_brand_apart_from_its_manufacturer(client):
    created = client.post("/api/figures", json={"name": "S.H.Figuarts Goku", "manufacturer": "Bandai Spirits", "brand": "  Tamashii   Nations "}).get_json()
    assert (created["manufacturer"], created["brand"]) == ("Bandai Spirits", "Tamashii Nations")
    changed = client.patch(f"/api/figures/{created['id']}", json={"brand": ""}).get_json()
    assert (changed["manufacturer"], changed["brand"]) == ("Bandai Spirits", "")
    assert client.post("/api/figures", json={"name": "Long", "brand": "x" * 301}).status_code == 400


def test_the_grid_filters_by_brand_and_by_having_none(client, branded):
    assert ids(client, brand="Good Smile Company") == [MIKU, FRIEREN]
    assert ids(client, brand="__none__") == [TWINS, REM]
    assert ids(client, series="__none__") == [], "every sample figure has a franchise"
    facets = client.get("/api/figures").get_json()["facets"]
    assert facets["brand"] == [["Good Smile Company", 2], ["Good Smile Arts", 1]]


@pytest.mark.parametrize("sort, direction, expected", [
    ("brand", None, [MIKASA, MIKU, FRIEREN, REM, TWINS]),           # A-Z, then by name; without a brand last, by name
    ("brand", "desc", [FRIEREN, MIKU, MIKASA, REM, TWINS]),         # still last when reversed
    ("series", None, [MIKASA, FRIEREN, REM, TWINS, MIKU]),
    ("line", None, [REM, FRIEREN, MIKASA, MIKU, TWINS]),
    ("manufacturer", None, [MIKU, FRIEREN, MIKASA, TWINS, REM]),
])
def test_text_sorts_put_figures_without_a_value_last(client, branded, sort, direction, expected):
    assert ids(client, sort=sort, **({"direction": direction} if direction else {})) == expected


def test_the_collection_and_wishlists_filter_by_brand_too(client, branded):
    for figure_id in (MIKU, REM):
        client.post("/api/collection", json={"figure_id": figure_id})
    collection = client.get("/api/collection", query_string={"brand": "Good Smile Company"}).get_json()
    assert [row["id"] for row in collection["figures"]] == [MIKU]
    assert collection["facets"]["brand"] == [["Good Smile Company", 1]]


def test_search_and_suggestions_know_the_brand(client, branded):
    assert [row["id"] for row in client.get("/api/search", query_string={"q": "Good Smile Arts"}).get_json()][0] == MIKASA
    assert client.get("/api/figures/suggestions").get_json()["brand"] == ["Good Smile Company", "Good Smile Arts"]


SHOP_PAGE = """<html><head><script type="application/ld+json">{"@type":"Product","name":"Goku 1/8",
"brand":{"@type":"Brand","name":"Tamashii Nations"},"manufacturer":{"@type":"Organization","name":"Bandai Spirits"}}</script>
</head><body></body></html>"""
BRAND_ONLY_PAGE = """<html><head><script type="application/ld+json">{"@type":"Product","name":"Miku 1/7","brand":"Good Smile Company"}</script>
</head><body></body></html>"""
TABLE_PAGE = """<html><head><title>Rem</title></head><body><table>
<tr><th>Manufacturer</th><td>FuRyu</td></tr><tr><th>Brand</th><td>F:NEX</td></tr></table></body></html>"""


@pytest.mark.parametrize("page, brand, manufacturer", [
    (SHOP_PAGE, "Tamashii Nations", "Bandai Spirits"),
    (BRAND_ONLY_PAGE, "Good Smile Company", "Good Smile Company"),   # shops name the maker as the brand
    (TABLE_PAGE, "F:NEX", "FuRyu"),
])
def test_the_link_import_reads_brand_and_manufacturer_apart(client, fake_fetch, page, brand, manufacturer):
    fake_fetch.pages["https://shop.example/item"] = ("text/html", page.encode())
    fields = client.post("/api/figures/link-import", json={"url": "https://shop.example/item"}).get_json()["fields"]
    assert (fields["brand"], fields["manufacturer"]) == (brand, manufacturer)


def test_export_and_restore_carry_the_brand(client, branded):
    client.post("/api/collection", json={"figure_id": MIKU})
    csv = client.get("/api/export.csv").get_data().decode("utf-8-sig")
    header, row = csv.splitlines()[:2]
    assert header.split(";")[3:6] == ["Franchise", "Hersteller", "Marke"]
    assert row.split(";")[5] == "Good Smile Company"
    backup = client.get("/api/export.json").get_json()
    assert backup["figures"][0]["brand"] == "Good Smile Company"
    backup["figures"][0].update({"ref": 999, "jan": "", "name": "Miku, restored", "source_url": ""})
    for entry in backup["collection"]:
        entry["figure_ref"] = 999
    assert client.post("/api/import/json/apply", json={"data": backup, "strategy": "add"}).status_code == 200
    assert query("SELECT brand FROM figures WHERE name='Miku, restored'") == [{"brand": "Good Smile Company"}]
