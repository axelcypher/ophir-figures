"""Shared sign-in of the Ophir apps on one host (OPHIR_AUTH_MODE, ophir_figures/shared_auth.py): the
master signs people in under /auth and hands the sign-in to the slaves in the cookie ophir_auth.
Ophir Cards has the same tests (tests/test_shared_auth.py there)."""

import os
import subprocess
import sys

import pytest

import ophir_auth
import ophir_figures
from conftest import DEMO, ROOT, query

AUTH = "http://localhost/auth"
FIGURES = "http://localhost/figures"
SSO_CONFIG = {"enabled": True, "client_id": "ophir", "client_secret": "secret", "account_matching": "email"}


@pytest.fixture
def mode(monkeypatch):
    def switch(value):
        monkeypatch.setattr(ophir_figures.config, "AUTH_MODE", value)
        monkeypatch.setattr(ophir_figures.config, "AUTH_PATH", "/auth")
        monkeypatch.setattr(ophir_figures.config, "AUTH_HOME", "/figures/")
    return switch


@pytest.fixture
def sso(monkeypatch):
    """SSO switched on, with a provider that answers the round trip with `sso.claims` (demo by
    email unless a test changes them)."""
    claims = {"sub": "idp-1", "email": "demo@example.com", "email_verified": True}
    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    monkeypatch.setattr(ophir_figures.auth, "resolve_oauth_config", lambda: {**ophir_figures.config.OAUTH_CONFIG_DEFAULTS, **SSO_CONFIG})
    monkeypatch.setattr(ophir_figures.auth, "build_authorization_request", lambda config, redirect_uri: (f"https://idp.example/authorize?redirect_uri={redirect_uri}", "state-1", "verifier"))
    monkeypatch.setattr(ophir_figures.auth, "exchange_code", lambda *args: {"access_token": "at"})
    monkeypatch.setattr(ophir_figures.auth, "fetch_userinfo", lambda config, token: claims)
    return type("FakeProvider", (), {"claims": claims})()


def shared_cookie(response):
    """The value the response sets for ophir_auth ('' when it clears it), None when untouched."""
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith(f"{ophir_auth.COOKIE}="):
            assert "Path=/;" in header and "HttpOnly" in header
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


def token(**identity):
    return ophir_auth.sign(ophir_figures.app.config["SECRET_KEY"], {"sub": "7", "username": "kim", "name": "Kim", "email": "kim@example.org", "role": "user", **identity})


def read_token(value):
    identity, _ = ophir_auth.read(ophir_figures.app.config["SECRET_KEY"], value, 60)
    return identity


def demo_id():
    return query("SELECT id FROM users WHERE username='demo'")[0]["id"]


# ---- master ------------------------------------------------------------------------------------

def test_the_master_signs_in_under_the_auth_path_for_every_app(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    signed_in = client.post("/login?next=/cards/", data={"username": DEMO[0], "password": DEMO[1]}, base_url=AUTH)
    assert signed_in.status_code == 302 and signed_in.headers["Location"] == "/cards/"
    identity = read_token(shared_cookie(signed_in))
    assert identity["sub"] == str(demo_id()) and identity["username"] == "demo" and identity["name"] == "Alex Morgan" and identity["role"] == "user"

    # The app itself (under /figures) takes the same sign-in: a browser with only the shared cookie.
    other = ophir_figures.app.test_client()
    other.set_cookie(ophir_auth.COOKIE, shared_cookie(signed_in))
    assert other.get("/api/bootstrap", base_url=FIGURES).get_json()["auth"] == {"mode": "master", "base": "/auth"}


def test_a_sign_in_at_the_auth_path_without_a_destination_ends_at_the_home(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    signed_in = client.post("/login", data={"username": DEMO[0], "password": DEMO[1]}, base_url=AUTH)
    assert signed_in.headers["Location"] == "/figures/"
    # Signed in already: the sign-in page sends people on at once, with the token renewed if need be.
    assert client.get("/login?next=/cards/", base_url=AUTH).headers["Location"] == "/cards/"


def test_the_master_takes_identity_from_the_shared_cookie_only(mode, client):
    """The client fixture signed in before the app became a master: a session, no token."""
    mode("master")
    assert client.get("/api/bootstrap").status_code == 401


def test_the_auth_path_serves_sign_in_only(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    assert client.get("/login", base_url=AUTH).status_code == 200
    assert client.get("/static/login.css", base_url=AUTH).status_code == 200
    assert client.get("/health", base_url=AUTH).status_code == 200
    assert client.get("/", base_url=AUTH).status_code == 404
    assert client.get("/api/bootstrap", base_url=AUTH).status_code == 404
    assert client.get("/u/someone", base_url=AUTH).status_code == 404


def test_on_the_shared_host_the_master_sends_sign_in_and_sso_to_the_auth_path(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    assert client.get("/login", base_url=FIGURES).headers["Location"] == "/auth/login?next=/figures/"
    assert client.get("/oauth/login", base_url=FIGURES).headers["Location"] == "/auth/oauth/login?next=/figures/"
    # On a host of its own (no path) it signs people in itself, as before.
    assert client.get("/login").status_code == 200


def test_the_auth_path_keeps_guessing_passwords_throttled(mode, monkeypatch):
    mode("master")
    monkeypatch.setattr(ophir_figures.auth, "LOGIN_FAILURES_PER_USERNAME", 2)
    client = ophir_figures.app.test_client()
    for _ in range(2):
        assert client.post("/login?next=/cards/", data={"username": "demo", "password": "wrong"}, base_url=AUTH).status_code == 401
    turned_away = client.post("/login?next=/cards/", data={"username": DEMO[0], "password": DEMO[1]}, base_url=AUTH)
    assert turned_away.status_code == 429 and shared_cookie(turned_away) is None


def test_signing_out_at_the_master_signs_out_everywhere(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    signed_in = client.post("/login", data={"username": DEMO[0], "password": DEMO[1]}, base_url=AUTH)
    assert shared_cookie(signed_in)
    signed_out = client.post("/logout", base_url=AUTH)
    assert shared_cookie(signed_out) == "" and signed_out.headers["Location"] == "/auth/login"
    assert client.get("/api/bootstrap", base_url=FIGURES).status_code == 401


def test_signing_out_at_the_auth_path_ends_where_the_slave_asked(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    client.post("/login", data={"username": DEMO[0], "password": DEMO[1]}, base_url=AUTH)
    signed_out = client.post("/logout?next=/cards/", base_url=AUTH)
    assert shared_cookie(signed_out) == "" and signed_out.headers["Location"] == "/cards/"


def test_a_deleted_account_loses_the_shared_sign_in(mode):
    mode("master")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(sub="999999"))
    answer = client.get("/api/bootstrap", base_url=FIGURES)
    assert answer.status_code == 401 and shared_cookie(answer) == ""


def test_the_master_renews_an_older_sign_in(mode, monkeypatch):
    mode("master")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(sub=str(demo_id()), username="demo"))
    assert shared_cookie(client.get("/api/bootstrap", base_url=FIGURES)) is None, "a recent token stays as it is"
    monkeypatch.setattr(ophir_auth, "RENEW_AFTER_SECONDS", -1)
    identity = read_token(shared_cookie(client.get("/api/bootstrap", base_url=FIGURES)))
    assert identity["username"] == "demo" and identity["name"] == "Alex Morgan"


def test_sso_at_the_auth_path_ends_where_the_sign_in_started(mode, sso):
    mode("master")
    client = ophir_figures.app.test_client()
    page = client.get("/login?next=/cards/", base_url=AUTH).get_data(as_text=True)
    assert 'href="/auth/oauth/login?next=/cards/"' in page, "the SSO button keeps the destination"
    started = client.get("/oauth/login?next=/cards/", base_url=AUTH)
    assert started.headers["Location"].startswith("https://idp.example/authorize?redirect_uri=http://localhost/auth/oauth/callback")
    finished = client.get("/oauth/callback?code=abc&state=state-1", base_url=AUTH)
    assert finished.headers["Location"] == "/cards/"
    assert read_token(shared_cookie(finished))["sub"] == str(demo_id())


def test_a_failed_sso_sign_in_keeps_the_destination(mode, sso):
    mode("master")
    sso.claims.update(sub="stranger", email="stranger@example.com")
    client = ophir_figures.app.test_client()
    client.get("/oauth/login?next=/cards/", base_url=AUTH)
    refused = client.get("/oauth/callback?code=abc&state=state-1", base_url=AUTH)
    assert refused.headers["Location"] == "/auth/login?error=no_account&next=/cards/"
    assert shared_cookie(refused) is None


def test_linking_sso_from_an_app_on_the_shared_host_comes_back_there(mode, sso):
    mode("master")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(sub=str(demo_id()), username="demo"))
    # Settings' "Verbinden" under /figures goes to the auth path, which links and sends people back.
    assert client.get("/oauth/login", base_url=FIGURES).headers["Location"] == "/auth/oauth/login?next=/figures/"
    client.get("/oauth/login?next=/figures/", base_url=AUTH)
    linked = client.get("/oauth/callback?code=abc&state=state-1", base_url=AUTH)
    assert linked.headers["Location"] == "/figures/?linked=1"
    assert query("SELECT oauth_subject FROM users WHERE username='demo'")[0]["oauth_subject"] == "idp-1"

    client.get("/oauth/login?next=/figures/", base_url=AUTH)
    failed = client.get("/oauth/callback?code=abc&state=another-state", base_url=AUTH)
    assert failed.headers["Location"] == "/figures/?oauth_error=state_mismatch"


# ---- slave -------------------------------------------------------------------------------------

def test_a_slave_sends_whoever_is_not_signed_in_to_the_master(mode):
    mode("slave")
    client = ophir_figures.app.test_client()
    assert client.get("/", base_url=FIGURES).headers["Location"] == "/figures/login"
    assert client.get("/login", base_url=FIGURES).headers["Location"] == "/auth/login?next=/figures/"
    assert client.get("/login?next=/figures/?route=settings", base_url=FIGURES).headers["Location"] == "/auth/login?next=/figures/%3Froute%3Dsettings"
    assert client.get("/login?next=https://evil.example/", base_url=FIGURES).headers["Location"] == "/auth/login?next=/figures/"
    assert client.get("/oauth/login", base_url=FIGURES).headers["Location"] == "/auth/oauth/login?next=/figures/"
    posted = client.post("/login", data={"username": DEMO[0], "password": DEMO[1]}, base_url=FIGURES)
    assert posted.status_code == 307 and posted.headers["Location"].startswith("/auth/login")
    assert client.get("/api/bootstrap", base_url=FIGURES).status_code == 401
    signed_out = client.post("/logout", base_url=FIGURES)
    assert signed_out.status_code == 307 and signed_out.headers["Location"] == "/auth/logout?next=/figures/"


def test_a_slave_takes_the_masters_sign_in_and_account(mode):
    mode("slave")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(role="admin"))
    boot = client.get("/api/bootstrap", base_url=FIGURES).get_json()
    assert boot["auth"] == {"mode": "slave", "base": "/auth"}
    assert (boot["user"]["username"], boot["user"]["display_name"], boot["user"]["role"], boot["user"]["email"]) == ("kim", "Kim", "admin", "kim@example.org")
    assert query("SELECT auth_subject, password_hash FROM users WHERE username='kim'") == [{"auth_subject": "7", "password_hash": ""}]
    assert [item["name"] for item in boot["watchlists"] if item["is_default"]] == ["Wunschliste"], "a new account has its default wishlist"

    # Name and role follow the master.
    client.set_cookie(ophir_auth.COOKIE, token(role="user", name="Kim K."))
    boot = client.get("/api/bootstrap", base_url=FIGURES).get_json()
    assert (boot["user"]["display_name"], boot["user"]["role"]) == ("Kim K.", "user")
    assert query("SELECT COUNT(*) n FROM users WHERE auth_subject='7'")[0]["n"] == 1


def test_a_slave_gives_a_new_account_a_username_of_its_own(mode):
    mode("slave")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(sub="8", username="demo", email="other@example.org"))
    query("UPDATE users SET auth_subject='3' WHERE username='demo'")
    assert client.get("/api/bootstrap", base_url=FIGURES).get_json()["user"]["username"] == "demo-2"


def test_a_slave_links_an_account_it_already_has(mode):
    mode("slave")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(sub="42", username="DEMO", email=""))
    assert client.get("/api/bootstrap", base_url=FIGURES).get_json()["user"]["id"] == demo_id()
    assert query("SELECT auth_subject FROM users WHERE username='demo'")[0]["auth_subject"] == "42"

    # By email before the username.
    query("UPDATE users SET email='Chief@Example.org' WHERE username='admin'")
    other = ophir_figures.app.test_client()
    other.set_cookie(ophir_auth.COOKIE, token(sub="43", username="chief", email="chief@example.org", role="admin"))
    assert other.get("/api/bootstrap", base_url=FIGURES).get_json()["user"]["username"] == "admin"
    assert query("SELECT auth_subject FROM users WHERE username='admin'")[0]["auth_subject"] == "43"


def test_a_slave_refuses_outdated_and_foreign_sign_ins(mode, monkeypatch):
    mode("slave")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, ophir_auth.sign("another-key", {"sub": "7", "username": "kim", "role": "admin"}))
    assert client.get("/api/bootstrap", base_url=FIGURES).status_code == 401
    monkeypatch.setattr(ophir_auth, "FRESH_SECONDS", -1)
    client.set_cookie(ophir_auth.COOKIE, token())
    assert client.get("/api/bootstrap", base_url=FIGURES).status_code == 401, "back to the master to have it renewed"


def test_a_slave_leaves_account_changes_to_the_master(mode):
    mode("slave")
    client = ophir_figures.app.test_client()
    client.set_cookie(ophir_auth.COOKIE, token(role="admin"))
    assert client.patch("/api/account", json={"display_name": "Other"}, base_url=FIGURES).status_code == 409
    assert client.post("/api/account/password", json={"new_password": "a-new-password"}, base_url=FIGURES).status_code == 409
    assert client.post("/api/account/oauth/unlink", json={}, base_url=FIGURES).status_code == 409
    assert client.post("/api/admin/users", json={"username": "new-one", "password": "a-new-password", "role": "user"}, base_url=FIGURES).status_code == 409
    assert client.patch(f"/api/admin/users/{demo_id()}", json={"role": "admin"}, base_url=FIGURES).status_code == 409
    assert client.delete(f"/api/admin/users/{demo_id()}", base_url=FIGURES).status_code == 409
    # Everything else is the app's own, as before.
    assert client.post("/api/settings", json={"mobileThemeAppearance": "dark"}, base_url=FIGURES).status_code == 200
    assert client.get("/api/admin/users", base_url=FIGURES).status_code == 200


# ---- standalone and start-up -------------------------------------------------------------------

def test_standalone_signs_people_in_itself(client):
    assert client.get("/api/bootstrap").get_json()["auth"] == {"mode": "standalone", "base": ""}
    assert shared_cookie(client.post("/logout")) is None


def test_an_unknown_mode_stops_the_app_at_start_up(tmp_path):
    environment = {**os.environ, "OPHIR_AUTH_MODE": "primary", "DATABASE_PATH": str(tmp_path / "x.db")}
    started = subprocess.run([sys.executable, "-c", "import ophir_figures"], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
    assert started.returncode != 0 and "OPHIR_AUTH_MODE must be one of standalone, master, slave" in started.stderr


def test_where_to_go_after_signing_in_stays_on_this_host():
    for value in ("https://evil.example/", "//evil.example/x", "/\\evil.example", "javascript:alert(1)", "/ok\nSet-Cookie: x=y", ""):
        assert ophir_auth.safe_next(value, "/figures/") == "/figures/"
    assert ophir_auth.safe_next("/cards/?linked=1", "/figures/") == "/cards/?linked=1"
