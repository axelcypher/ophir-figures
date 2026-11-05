"""The page shell, the login page and what the app loads first."""
import re

from conftest import ROOT, MIKU, default_list


def test_the_shell_renders_and_every_asset_it_names_exists(client):
    page = client.get("/").get_data(as_text=True)
    assets = re.findall(r'/static/([\w./-]+)\?v=[0-9a-f]{12}', page)
    assert {"js/core.js", "js/figures-ui.js", "js/views.js", "js/main.js", "figures.css"} <= set(assets)
    for asset in assets:
        assert (ROOT / "static" / asset).is_file(), asset
    assert "Ophir Figures" in page and "DeckLedger" not in page


def test_static_files_are_kept_for_good_only_with_their_version(client):
    page = client.get("/").get_data(as_text=True)
    url = re.search(r'/static/js/core\.js\?v=[0-9a-f]{12}', page).group(0)
    assert "immutable" in client.get(url).headers["Cache-Control"]
    assert "immutable" not in client.get("/static/js/core.js?v=old").headers.get("Cache-Control", "")


def test_the_login_page_carries_the_new_name(anonymous):
    page = anonymous.get("/login").get_data(as_text=True)
    assert "Ophir Figures" in page and "OPHIR" in page and "DeckLedger" not in page


def test_bootstrap_has_what_the_app_needs_to_start(client):
    client.post("/api/collection", json={"figure_id": MIKU})
    client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": MIKU})
    boot = client.get("/api/bootstrap").get_json()
    assert boot["user"]["username"] == "demo" and boot["user"]["password_set"] is True
    assert boot["counts"] == {"collection": 1, "wished": 1, "preorders": 0, "catalog": 5}
    assert [item["name"] for item in boot["watchlists"]] == ["Wunschliste"]
    assert set(boot["conditions"]) == {"sealed", "boxed", "loose", "damaged"}
    assert set(boot["statuses"]) == {"ordered", "paid", "shipped", "delivered", "cancelled"}
    assert "Nendoroid" in boot["categories"] and boot["currency"] == "EUR"


def test_settings_are_saved_per_account(client, admin):
    client.post("/api/settings", json={"mobileThemeAppearance": "light", "publicProfile": {"enabled": True, "slug": "hack"}})
    assert client.get("/api/bootstrap").get_json()["settings"] == {"mobileThemeAppearance": "light"}, "the profile only through its own endpoint"
    assert admin.get("/api/bootstrap").get_json()["settings"] == {}
