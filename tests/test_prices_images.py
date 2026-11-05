"""Market values with their history, and figure pictures: upload, download, thumbnails, caching."""
import io

from conftest import FRIEREN, MIKU, png_bytes, query


def test_market_values_are_a_shared_history(client, admin):
    assert client.post(f"/api/figures/{MIKU}/prices", json={"amount": "199,00", "note": "eBay"}).status_code == 201
    history = admin.post(f"/api/figures/{MIKU}/prices", json={"amount": 215}).get_json()
    assert [(row["amount"], row["author"]) for row in history] == [(215, "Ophir Figures Admin"), (199, "Alex Morgan")]
    assert client.get(f"/api/figures/{MIKU}").get_json()["market_value"] == 215
    newest = history[0]["id"]
    assert client.delete(f"/api/figures/{MIKU}/prices/{newest}").get_json()[0]["amount"] == 199
    assert client.delete(f"/api/figures/{FRIEREN}/prices/{history[1]['id']}").status_code == 404, "the value belongs to another figure"


def test_a_market_value_needs_a_sensible_amount(client):
    for amount in ("", "abc", -1, 5_000_000):
        assert client.post(f"/api/figures/{MIKU}/prices", json={"amount": amount}).status_code == 400, amount
    assert client.post("/api/figures/999/prices", json={"amount": 5}).status_code == 404


def upload(client, figure_id, payload, name="bild.png"):
    return client.post(f"/api/figures/{figure_id}/image", data={"file": (io.BytesIO(payload), name)}, content_type="multipart/form-data")


def test_an_uploaded_picture_is_served_with_a_thumbnail(client):
    key = upload(client, MIKU, png_bytes(size=(1200, 1600))).get_json()["image_key"]
    full = client.get(f"/images/figures/{MIKU}?v={key[:12]}")
    assert full.mimetype == "image/png" and "immutable" in full.headers["Cache-Control"]
    thumb = client.get(f"/images/figures/{MIKU}/thumb")
    from PIL import Image
    image = Image.open(io.BytesIO(thumb.data))
    assert thumb.mimetype == "image/webp" and image.width == 480
    assert "immutable" not in thumb.headers.get("Cache-Control", ""), "only a URL with the picture's version is kept for good"


def test_the_same_picture_is_stored_once(client):
    payload = png_bytes()
    assert upload(client, MIKU, payload).get_json()["image_key"] == upload(client, FRIEREN, payload).get_json()["image_key"]
    from ophir_figures.config import IMAGE_DIR
    assert len([path for path in IMAGE_DIR.iterdir() if path.name.startswith(query("SELECT image_key k FROM figures WHERE id=?", (MIKU,))[0]["k"][:12])]) == 1


def test_a_picture_link_is_fetched_on_first_view_and_a_dead_one_not_again_at_once(client, fake_fetch):
    query("UPDATE figures SET image_url='https://cdn.example.com/miku.png' WHERE id=?", (MIKU,))
    query("UPDATE figures SET image_url='https://cdn.example.com/dead.png' WHERE id=?", (FRIEREN,))
    fake_fetch.pages["https://cdn.example.com/miku.png"] = ("image/png", png_bytes())
    assert client.get(f"/images/figures/{MIKU}/thumb").mimetype == "image/webp"
    assert query("SELECT image_key FROM figures WHERE id=?", (MIKU,))[0]["image_key"].endswith(".png")
    for _ in range(3):
        assert client.get(f"/images/figures/{FRIEREN}").mimetype == "image/svg+xml"
    assert fake_fetch.requested.count("https://cdn.example.com/dead.png") == 1


def test_a_picture_can_be_set_by_link_and_removed(client, fake_fetch):
    fake_fetch.pages["https://cdn.example.com/rem.png"] = ("image/png", png_bytes((10, 10, 200)))
    assert client.post(f"/api/figures/{MIKU}/image", json={"url": "https://cdn.example.com/rem.png"}).status_code == 200
    assert client.post(f"/api/figures/{MIKU}/image", json={"url": "https://cdn.example.com/missing.png"}).status_code == 400
    assert client.delete(f"/api/figures/{MIKU}/image").get_json() == {"removed": True}
    assert client.get(f"/api/figures/{MIKU}").get_json()["has_image"] is False


def test_a_new_picture_link_on_save_is_fetched_and_a_failure_reported(client, fake_fetch):
    response = client.patch(f"/api/figures/{MIKU}", json={"image_url": "https://cdn.example.com/kaputt.png"}).get_json()
    assert "404" in response["image_error"] and response["has_image"] is True, "the link is kept to be tried again later"
