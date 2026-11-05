"""User management by an admin, and what happens to a session once its account is gone."""
from conftest import MIKU, default_list, login, ophir_figures, query

NEW = {"username": "mia", "display_name": "Mia", "email": "mia@example.com", "password": "geheim-1234", "role": "user"}


def create(admin, **overrides):
    return admin.post("/api/admin/users", json={**NEW, **overrides})


def test_listing_shows_accounts_without_password_hashes(admin):
    users = admin.get("/api/admin/users").get_json()
    assert [(user["username"], user["role"], user["is_self"]) for user in users] == [("admin", "admin", True), ("demo", "user", False)]
    assert all("password_hash" not in user for user in users)


def test_user_management_is_admin_only(client, anonymous):
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/users", json=NEW).status_code == 403
    assert anonymous.get("/api/admin/users").status_code == 401


def test_created_account_can_sign_in_and_use_the_app(admin):
    assert create(admin).status_code == 201
    mia = login(("mia", "geheim-1234"))
    games = mia.get("/api/bootstrap").get_json()
    assert games["user"]["display_name"] == "Mia" and games["user"]["role"] == "user"
    # Accounts made while the app runs have their default list at once, not after the next restart.
    assert mia.post(f"/api/watchlists/{default_list(mia)}/figures", json={"figure_id": MIKU}).status_code == 201
    assert {item["name"] for item in mia.get("/api/watchlists").get_json()} == {"Wunschliste"}


def test_creation_validates_its_input(admin):
    for overrides, text in (
        ({"username": "x"}, "3-32 Zeichen"), ({"username": "DEMO"}, "bereits vergeben"), ({"password": "kurz"}, "mindestens 8"),
        ({"email": "keine-mail"}, "ungültig"), ({"role": "root"}, "Rolle"), ({"password": ""}, "erforderlich"),
    ):
        response = create(admin, **overrides)
        assert response.status_code == 400 and text in response.get_json()["error"], overrides
    assert query("SELECT COUNT(*) n FROM users")[0]["n"] == 2


def test_edit_role_and_reset_password(admin):
    user_id = create(admin).get_json()["id"]
    assert admin.patch(f"/api/admin/users/{user_id}", json={"role": "admin", "display_name": "Mia M.", "password": "neues-passwort"}).status_code == 200
    mia = login(("mia", "neues-passwort"))
    assert mia.get("/api/admin/users").status_code == 200
    assert ophir_figures.app.test_client().post("/login", data={"username": "mia", "password": "geheim-1234"}).status_code == 401


def test_the_last_admin_cannot_be_removed_or_demoted(admin):
    admin_id = query("SELECT id FROM users WHERE username='admin'")[0]["id"]
    assert admin.patch(f"/api/admin/users/{admin_id}", json={"role": "user"}).status_code == 400
    assert admin.delete(f"/api/admin/users/{admin_id}").status_code == 400
    # With a second admin the first one may step down, but still not delete itself here.
    create(admin, role="admin")
    assert admin.delete(f"/api/admin/users/{admin_id}").status_code == 400
    assert admin.patch(f"/api/admin/users/{admin_id}", json={"role": "user"}).status_code == 200


def test_deleting_an_account_removes_its_data_and_ends_its_session(admin):
    demo = login()
    demo.post("/api/collection", json={"figure_id": MIKU, "quantity": 2})
    demo.post(f"/api/watchlists/{default_list(demo)}/figures", json={"figure_id": MIKU})
    preorder = demo.post("/api/preorders", json={"figure_id": MIKU, "price": 150}).get_json()
    demo.patch(f"/api/preorders/{preorder['id']}", json={"expected_release": "2026-02"})
    demo.post(f"/api/figures/{MIKU}/prices", json={"amount": 180})
    demo.post("/api/settings", json={"catalogSort": "name"})
    created = demo.post("/api/figures", json={"name": "Eigene Figur"}).get_json()
    admin.post("/api/collection", json={"figure_id": MIKU, "quantity": 5})
    demo_id = query("SELECT id FROM users WHERE username='demo'")[0]["id"]

    assert admin.delete(f"/api/admin/users/{demo_id}").get_json() == {"deleted": True}

    for table in ("collection_entries", "watchlists", "preorders", "user_settings"):
        assert query(f"SELECT COUNT(*) n FROM {table} WHERE user_id=?", (demo_id,))[0]["n"] == 0, table
    assert query("SELECT COUNT(*) n FROM watchlist_entries")[0]["n"] == 0 and query("SELECT COUNT(*) n FROM preorder_events")[0]["n"] == 0
    assert query("SELECT SUM(quantity) q FROM collection_entries")[0]["q"] == 5, "other accounts keep their data"
    # The shared catalogue and market values stay, no longer credited to the account.
    assert query("SELECT created_by FROM figures WHERE id=?", (created["id"],)) == [{"created_by": None}]
    assert query("SELECT user_id FROM price_observations") == [{"user_id": None}]
    # The deleted account's cookie is still in its browser; it must not work any more.
    assert demo.get("/api/bootstrap").status_code == 401
    assert demo.get("/").status_code == 302


def test_the_login_page_offers_no_demo_account(anonymous):
    page = anonymous.get("/login").get_data(as_text=True)
    assert "Demo-Zugang" not in page and "figuren-1234" not in page
