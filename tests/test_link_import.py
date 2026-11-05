"""Filling in a figure from a product page: the server reading a page, the bookmarklet's snapshot,
and what is read from JSON-LD, meta tags and label/value tables."""
import pytest

from conftest import MIKU
from ophir_figures.fetch import FetchError

SHOP_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Hatsune Miku: Racing 2024 Ver. 1/7 | Solaris Japan</title>
<meta property="og:site_name" content="Solaris Japan">
<meta property="og:title" content="Hatsune Miku: Racing 2024 Ver. 1/7 | Solaris Japan">
<meta property="og:image" content="//cdn.example.com/files/miku.jpg?v=1">
<link rel="canonical" href="https://solarisjapan.com/products/miku-racing-2024">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Hatsune Miku: Racing 2024 Ver. 1/7 Scale Figure","image":["https://cdn.example.com/files/miku-large.jpg"],
  "brand":{"@type":"Brand","name":"Good Smile Company"},"gtin13":"4580590177777",
  "description":"From the Racing Miku project. Height approx. 255mm.",
  "offers":{"@type":"Offer","price":"189.95","priceCurrency":"EUR"}}]}</script>
</head><body><h1>Hatsune Miku: Racing 2024 Ver.</h1></body></html>"""

DATABASE_PAGE = """<html><head><title>Frieren 1/7 - Figure</title>
<meta property="og:title" content="Frieren: Summer Ver. 1/7">
<meta property="og:image" content="https://static.example.net/upload/items/1/12345.jpg"></head><body>
<div class="data-field"><div class="data-label">Origin</div><div class="data-value"><a>Frieren: Beyond Journey's End</a></div></div>
<div class="data-field"><div class="data-label">Character</div><div class="data-value"><a>Frieren</a></div></div>
<div class="data-field"><div class="data-label">Companies</div><div class="data-value"><a>Good Smile Company</a> <small>(As Distributor)</small>, <a>Max Factory</a> <small>(As Manufacturer)</small></div></div>
<div class="data-field"><div class="data-label">Artists</div><div class="data-value"><a>Taro Sculpt</a> <small>(As Sculptor)</small>, <a>Hana Paint</a> <small>(As Painter)</small></div></div>
<div class="data-field"><div class="data-label">Release date</div><div class="data-value">03/27/2026 as Limited (Japan)</div></div>
<div class="data-field"><div class="data-label">Price</div><div class="data-value">19,800 JPY (Tax included)</div></div>
<div class="data-field"><div class="data-label">Scale &amp; Dimensions</div><div class="data-value">1/7 H=240mm (9.45in)</div></div>
<div class="data-field"><div class="data-label">Materials</div><div class="data-value">ABS, PVC</div></div>
<div class="data-field"><div class="data-label">Barcode</div><div class="data-value">4545784012345</div></div>
<div class="data-field"><div class="data-label">Classification</div><div class="data-value">Prepainted</div></div>
</body></html>"""

MAKER_PAGE = """<html><head><meta charset="utf-8"><title>レム 1/7スケールフィギュア｜コトブキヤ</title></head><body>
<h1>レム 水着Ver. 1/7スケール</h1>
<table><tr><th>作品名</th><td>Re:ゼロから始める異世界生活</td></tr>
<tr><th>価格</th><td>16,500円（税込）</td></tr>
<tr><th>発売時期</th><td>2025年3月</td></tr>
<tr><th>仕様</th><td>塗装済み完成品・1/7スケール・全高約240mm</td></tr>
<tr><th>原型</th><td>山田</td></tr><tr><th>JANコード</th><td>4934054012345</td></tr></table>
<dl><dt>キャラクター</dt><dd>レム</dd></dl></body></html>"""


def test_a_shop_page_is_read_from_its_json_ld(client, fake_fetch):
    fake_fetch.pages["https://solarisjapan.com/products/miku-racing-2024"] = ("text/html", SHOP_PAGE.encode())
    result = client.post("/api/figures/link-import", json={"url": "https://solarisjapan.com/products/miku-racing-2024"}).get_json()
    fields = result["fields"]
    assert fields["name"] == "Hatsune Miku: Racing 2024 Ver. 1/7 Scale Figure"
    assert fields["image_url"] == "https://cdn.example.com/files/miku-large.jpg"
    assert (fields["manufacturer"], fields["jan"], fields["scale"], fields["category"]) == ("Good Smile Company", "4580590177777", "1/7", "Scale-Figur")
    assert fields["height_mm"] == "255" and fields["source_url"] == "https://solarisjapan.com/products/miku-racing-2024"
    assert (fields["msrp"], fields["msrp_currency"]) == (189.95, "EUR") and result["offer"] == {"price": 189.95, "currency": "EUR"}
    assert result["duplicate"] is None


def test_a_database_entry_is_read_from_its_data_fields(client, fake_fetch):
    fake_fetch.pages["https://db.example.net/item/12345"] = ("text/html; charset=utf-8", DATABASE_PAGE.encode())
    fields = client.post("/api/figures/link-import", json={"url": "https://db.example.net/item/12345"}).get_json()["fields"]
    assert fields["name"] == "Frieren: Summer Ver. 1/7"
    assert (fields["series"], fields["characters"]) == ("Frieren: Beyond Journey's End", "Frieren")
    assert fields["manufacturer"] == "Max Factory", "the company in the manufacturer role, not the distributor"
    assert fields["sculptor"] == "Taro Sculpt"
    assert (fields["release_date"], fields["msrp"], fields["msrp_currency"]) == ("2026-03-27", 19800, "JPY")
    assert (fields["scale"], fields["height_mm"], fields["material"], fields["jan"]) == ("1/7", "240", "ABS, PVC", "4545784012345")


def test_a_japanese_maker_page_is_read_from_its_tables(client, fake_fetch):
    fake_fetch.pages["https://maker.example.jp/rem"] = ("text/html", MAKER_PAGE.encode("utf-8"))
    result = client.post("/api/figures/link-import", json={"url": "https://maker.example.jp/rem"}).get_json()
    fields = result["fields"]
    assert fields["name"] == "レム 水着Ver. 1/7スケール", "the heading, not the title with the shop name"
    assert (fields["series"], fields["characters"], fields["sculptor"]) == ("Re:ゼロから始める異世界生活", "レム", "山田")
    assert (fields["msrp"], fields["msrp_currency"], fields["release_date"]) == (16500, "JPY", "2025-03")
    assert (fields["scale"], fields["height_mm"], fields["jan"]) == ("1/7", "240", "4934054012345")


def test_a_page_behind_a_bot_check_says_what_to_do_instead(client, fake_fetch):
    fake_fetch.pages["https://myfigurecollection.net/item/1"] = FetchError("Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots).", blocked=True)
    response = client.post("/api/figures/link-import", json={"url": "https://myfigurecollection.net/item/1"})
    assert response.status_code == 422 and response.get_json()["blocked"] is True
    fake_fetch.pages["https://shop.example/gone"] = FetchError("Die Seite antwortet mit Fehler 404.")
    assert client.post("/api/figures/link-import", json={"url": "https://shop.example/gone"}).get_json()["blocked"] is False


def test_the_bookmarklet_snapshot_takes_the_same_way(client):
    snapshot = {
        "url": "https://myfigurecollection.net/item/777", "title": "Nendoroid Frieren - MyFigureCollection.net",
        "meta": {"og:title": "Nendoroid Frieren", "og:image": "https://static.example.net/777.jpg", "og:site_name": "MyFigureCollection.net"},
        "jsonld": [], "fields": {"Origin": "Frieren: Beyond Journey's End", "Character": "Frieren",
                                 "Companies": "Good Smile Company (As Manufacturer)", "Release date": "08/30/2024 as Standard (Japan)"},
    }
    result = client.post("/api/figures/link-import", json={"snapshot": snapshot}).get_json()
    assert result["fields"]["line"] == "Nendoroid" and result["fields"]["category"] == "Nendoroid"
    assert result["fields"]["release_date"] == "2024-08-30"
    assert result["duplicate"]["reason"] == "gleicher Name, Hersteller und Edition", "the sample catalogue has it already"


def test_an_existing_figure_is_pointed_out(client, fake_fetch):
    page = SHOP_PAGE.replace("4580590177777", "4580590123456")
    fake_fetch.pages["https://shop.example/miku"] = ("text/html", page.encode())
    duplicate = client.post("/api/figures/link-import", json={"url": "https://shop.example/miku"}).get_json()["duplicate"]
    assert duplicate == {"id": MIKU, "name": "Hatsune Miku: Racing 2024 Ver.", "reason": "gleiche JAN"}


@pytest.mark.parametrize("payload, status", [({}, 400), ({"url": ""}, 400), ({"snapshot": "kaputt"}, 400)])
def test_empty_requests_are_refused(client, payload, status):
    assert client.post("/api/figures/link-import", json=payload).status_code == status


def test_a_link_to_something_else_than_a_page_is_refused(client, fake_fetch):
    fake_fetch.pages["https://shop.example/file.zip"] = ("application/zip", b"PK")
    response = client.post("/api/figures/link-import", json={"url": "https://shop.example/file.zip"})
    assert response.status_code == 422 and "keiner Webseite" not in response.get_json()["error"]


def test_the_imported_fields_create_a_figure_with_its_picture_and_value(client, fake_fetch):
    from conftest import png_bytes
    fake_fetch.pages["https://cdn.example.com/files/miku-large.jpg"] = ("image/png", png_bytes())
    created = client.post("/api/figures", json={"name": "Racing Miku 2024", "image_url": "https://cdn.example.com/files/miku-large.jpg",
                                                "market_value": "189,95", "from_import": True}).get_json()
    assert created["has_image"] and created["image_version"] and created["image_error"] is None
    assert created["market_value"] == 189.95 and created["prices"][0]["source"] == "import"
    assert client.get(f"/images/figures/{created['id']}/thumb").mimetype == "image/webp"
