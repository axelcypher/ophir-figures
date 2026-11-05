"""The public profile: off by default, a unique address, and only catalogue facts leave the server."""
import io

from conftest import FRIEREN, MIKU, REM, default_list, login, png_bytes, query, ADMIN


def switch_on(client, **changes):
    return client.put("/api/account/public-profile", json={"enabled": True, "slug": "alex", **changes})


def test_a_profile_is_off_until_switched_on(client, anonymous):
    assert client.get("/api/account/public-profile").get_json()["enabled"] is False
    assert anonymous.get("/u/alex").status_code == 404
    assert anonymous.get("/api/public/alex").status_code == 404


def test_the_address_is_checked_and_unique(client):
    for slug in ("A", "ab", "-alex", "alex-", "alex alex", "älex"):
        assert switch_on(client, slug=slug).status_code == 400, slug
    assert client.put("/api/account/public-profile", json={"enabled": True, "slug": ""}).status_code == 400
    assert switch_on(client).status_code == 200
    other = login(ADMIN)
    assert switch_on(other).status_code == 400
    assert switch_on(other, slug="admin-figuren").status_code == 200


def test_visitors_see_the_collection_without_prices_or_private_data(client, anonymous):
    client.post("/api/collection", json={"figure_id": MIKU, "quantity": 2, "purchase_price": "199,90", "shop": "AmiAmi",
                                         "location": "Vitrine 2", "notes": "Geschenk von Oma"})
    client.post(f"/api/figures/{MIKU}/prices", json={"amount": 250})
    client.post("/api/preorders", json={"figure_id": REM, "price": 99})
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": FRIEREN, "target_price": 40})
    switch_on(client, name="Alex' Vitrine")
    page = anonymous.get("/u/alex")
    assert page.status_code == 200 and "Alex&#39; Vitrine" in page.get_data(as_text=True)
    data = anonymous.get("/api/public/alex").get_json()
    assert data["name"] == "Alex' Vitrine" and data["stats"] == {"figures": 1, "copies": 2}
    assert [(item["id"], item["owned"]) for item in data["collection"]] == [(MIKU, 2)]
    assert "wishlist" not in data, "the wishlist is only shown when chosen"
    text = str(data)
    for secret in ("199", "250", "AmiAmi", "Vitrine 2", "Oma", "market_value", "purchase", "99"):
        assert secret not in text, secret


def test_the_wishlist_can_be_shared_too(client, anonymous):
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": FRIEREN, "target_price": 40})
    switch_on(client, show_wishlist=True)
    data = anonymous.get("/api/public/alex").get_json()
    assert [item["id"] for item in data["wishlist"]] == [FRIEREN] and "40" not in str(data["wishlist"])


def test_pictures_are_public_only_for_shared_figures(client, anonymous):
    client.post(f"/api/figures/{MIKU}/image", data={"file": (io.BytesIO(png_bytes()), "miku.png")}, content_type="multipart/form-data")
    client.post("/api/collection", json={"figure_id": MIKU})
    switch_on(client)
    picture = anonymous.get(f"/u/alex/images/{MIKU}")
    assert picture.status_code == 200 and picture.mimetype == "image/webp"
    assert anonymous.get(f"/u/alex/images/{REM}").status_code == 404
    switch_on(client, enabled=False)
    assert anonymous.get(f"/u/alex/images/{MIKU}").status_code == 404
    assert query("SELECT COUNT(*) n FROM user_settings WHERE key='publicProfile'")[0]["n"] == 1
