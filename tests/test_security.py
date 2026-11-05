"""Session handling, cross-site writes, access to images, fetching only public addresses and SSO
account matching."""
import io
import json
import runpy

import pytest

from conftest import DEMO, MIKU, ROOT, ophir_figures, png_bytes, query

WRITE = json.dumps({"figure_id": MIKU, "quantity": 1})


def test_a_server_does_not_start_with_the_public_development_key(monkeypatch):
    """Without SECRET_KEY, gunicorn would sign the session cookies with a key anyone can read in
    the repository, so anyone could forge a session for any account. gunicorn and
    docker-entrypoint.sh import app.py; only the local debug server may go on with that key."""
    monkeypatch.setitem(ophir_figures.app.config, "SECRET_KEY", ophir_figures.web.DEVELOPMENT_SECRET_KEY)
    with pytest.raises(SystemExit, match="SECRET_KEY"):
        runpy.run_path(str(ROOT / "app.py"), run_name="app")
    ophir_figures.web.require_secret_key(debug=True)

    monkeypatch.setitem(ophir_figures.app.config, "SECRET_KEY", "a-long-random-key-of-its-own")
    runpy.run_path(str(ROOT / "app.py"), run_name="app")


def test_session_cookie_is_samesite_lax(anonymous):
    response = anonymous.post("/login", data={"username": DEMO[0], "password": DEMO[1]})
    cookie = response.headers["Set-Cookie"]
    assert "SameSite=Lax" in cookie and "HttpOnly" in cookie


def test_cross_site_writes_are_rejected(client):
    # What a <form> on another website can send: no JSON content type, cookies attached.
    for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}, {"Origin": "https://evil.example"}):
        response = client.post("/api/collection", data=WRITE, content_type="text/plain", headers=headers)
        assert response.status_code == 403, headers
    assert query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 0


def test_own_and_non_browser_writes_pass(client):
    for headers in ({"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {"Origin": "http://localhost"}, {}):
        assert client.post("/api/collection", data=WRITE, content_type="application/json", headers=headers).status_code == 201, headers


def test_api_requires_a_session(anonymous):
    assert anonymous.get("/api/bootstrap").status_code == 401
    assert anonymous.post("/api/collection", json={"figure_id": MIKU}).status_code == 401
    assert anonymous.get("/api/figures").status_code == 401
    assert anonymous.post("/api/figures/link-import", json={"url": "https://example.com"}).status_code == 401
    assert anonymous.get("/api/admin/users").status_code == 401


def test_admin_api_is_closed_to_normal_users(client):
    for url in ("/api/admin/users", "/api/admin/catalog", "/api/admin/oauth"):
        assert client.get(url).status_code == 403, url


def test_figure_images_need_a_login(anonymous, client):
    for url in (f"/images/figures/{MIKU}", f"/images/figures/{MIKU}/thumb"):
        assert anonymous.get(url).status_code == 302, url
        assert client.get(url).status_code == 200, url


def test_public_endpoints_stay_public(anonymous):
    for url in ("/health", "/login", "/static/manifest.json"):
        assert anonymous.get(url).status_code == 200, url


def test_a_figure_without_picture_gets_a_placeholder_that_is_not_kept_for_long(client):
    response = client.get(f"/images/figures/{MIKU}")
    assert response.mimetype == "image/svg+xml"
    assert "immutable" not in response.headers.get("Cache-Control", "")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://localhost:8080/", "http://10.0.0.5/x", "http://192.168.1.10/", "http://[::1]/",
    "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)",
])
def test_links_into_the_local_network_or_other_schemes_are_never_fetched(url):
    with pytest.raises(ophir_figures.fetch.FetchError):
        ophir_figures.fetch.check_url(url)


def test_a_redirect_into_the_local_network_is_refused(monkeypatch):
    """The first address may be public; where it redirects to is checked again."""
    class Answer:
        status_code, is_redirect, headers = 302, True, {"Location": "http://127.0.0.1/secret"}

        def close(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            assert "127.0.0.1" not in url
            return Answer()

    monkeypatch.setattr(ophir_figures.fetch, "public_address", lambda host: host != "127.0.0.1")
    with pytest.raises(ophir_figures.fetch.FetchError, match="lokalen Netz"):
        ophir_figures.fetch.fetch("https://shop.example/item", 1000, session=Session())


def test_uploads_must_be_real_pictures(client):
    response = client.post(f"/api/figures/{MIKU}/image", data={"file": (io.BytesIO(b"<svg onload=alert(1)>"), "x.png")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    ok = client.post(f"/api/figures/{MIKU}/image", data={"file": (io.BytesIO(png_bytes()), "x.png")}, content_type="multipart/form-data")
    assert ok.status_code == 200 and ok.get_json()["image_key"].endswith(".png")


def resolve(mode, email, verified=True):
    with ophir_figures.app.app_context():
        row = ophir_figures.auth.resolve_oauth_identity({"account_matching": mode}, "subject-1", email, "Name", email_verified=verified)
        return dict(row) if row else None


def test_sso_links_a_user_by_verified_email():
    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    assert resolve("email", "demo@example.com")["username"] == "demo"
    assert query("SELECT oauth_subject s FROM users WHERE username='demo'")[0]["s"] == "subject-1"


def test_sso_does_not_hand_over_or_duplicate_an_account_for_an_unverified_email():
    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    for mode in ("email", "auto_provision"):
        assert resolve(mode, "demo@example.com", verified=False) is None, mode
    assert query("SELECT COUNT(*) n FROM users")[0]["n"] == 2
    assert query("SELECT oauth_subject s FROM users WHERE username='demo'")[0]["s"] == ""


def test_sso_links_an_admin_by_email_like_any_other_account():
    query("UPDATE users SET email='admin@example.com' WHERE username='admin'")
    assert resolve("auto_provision", "admin@example.com")["username"] == "admin"
    assert query("SELECT COUNT(*) n FROM users")[0]["n"] == 2, "no second account next to the admin"


def test_sso_auto_provision_creates_a_ready_to_use_account_for_an_unknown_identity():
    created = resolve("auto_provision", "neu@example.com")
    assert (created["username"], created["role"], created["email"]) == ("neu", "user", "neu@example.com")
    lists = query("SELECT name FROM watchlists WHERE user_id=? AND is_default=1", (created["id"],))
    assert [row["name"] for row in lists] == ["Wunschliste"], "a default wishlist right away"


def test_sso_email_mode_links_but_never_creates():
    assert resolve("email", "ganz-neu@example.com") is None
    assert query("SELECT COUNT(*) n FROM users")[0]["n"] == 2


def test_sso_manual_mode_only_accepts_linked_identities():
    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    assert resolve("manual", "demo@example.com") is None
    query("UPDATE users SET oauth_provider='generic', oauth_subject='subject-1' WHERE username='demo'")
    assert resolve("manual", "")["username"] == "demo"


def test_a_failed_sso_login_says_why_in_the_log(anonymous, monkeypatch, caplog):
    """Regression: every failure after the return from the provider ended in the same message on
    the login page and nothing in the log, so a wrong secret could not be told from a network problem."""
    config = {**ophir_figures.config.OAUTH_CONFIG_DEFAULTS, "enabled": True, "client_id": "id", "client_secret": "secret"}
    monkeypatch.setattr(ophir_figures.auth, "resolve_oauth_config", lambda: config)

    def refuse(*args):
        raise ophir_figures.auth.OAuthConfigError("invalid_client: Client authentication failed")

    monkeypatch.setattr(ophir_figures.auth, "exchange_code", refuse)
    with anonymous.session_transaction() as session:
        session["oauth_state"], session["oauth_code_verifier"] = "state-1", "verifier"
    with caplog.at_level("WARNING"):
        response = anonymous.get("/oauth/callback?code=abc&state=state-1")
    assert response.status_code == 302 and response.headers["Location"].endswith("/login?error=provider_error")
    assert "token exchange" in caplog.text and "invalid_client" in caplog.text and "/oauth/callback" in caplog.text
    assert "secret" not in caplog.text.replace("invalid_client", "") and "abc" not in caplog.text


def id_token(claims):
    import base64
    part = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    return f'{part({"alg": "RS256"})}.{part(claims)}.signature'


SSO_CONFIG = {"enabled": True, "client_id": "ophir-figures", "client_secret": "secret", "account_matching": "email"}


def sso_callback(anonymous, monkeypatch, token, userinfo):
    import oauth_client

    monkeypatch.setattr(ophir_figures.auth, "resolve_oauth_config", lambda: {**ophir_figures.config.OAUTH_CONFIG_DEFAULTS, **SSO_CONFIG})
    monkeypatch.setattr(ophir_figures.auth, "exchange_code", lambda *args: token)

    def fetch(config, token):
        if isinstance(userinfo, Exception):
            raise userinfo
        return userinfo

    monkeypatch.setattr(ophir_figures.auth, "fetch_userinfo", fetch)
    with anonymous.session_transaction() as session:
        session["oauth_state"], session["oauth_code_verifier"] = "state-1", "verifier"
    return anonymous.get("/oauth/callback?code=abc&state=state-1"), oauth_client


def test_sso_login_works_when_the_provider_refuses_the_userinfo_request(anonymous, monkeypatch, caplog):
    """Regression: Authentik answered the userinfo request with 403 although the token exchange
    had succeeded; the ID token that came with the tokens already says who signed in."""
    import time

    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    token = {"access_token": "at", "id_token": id_token({"sub": "abc-123", "email": "demo@example.com", "email_verified": True, "aud": "ophir-figures", "exp": time.time() + 300})}
    refusal = ophir_figures.auth.OAuthConfigError("Userinfo-Endpunkt antwortet mit 403: Forbidden")
    with caplog.at_level("WARNING"):
        response, _ = sso_callback(anonymous, monkeypatch, token, refusal)
    assert response.status_code == 302 and response.headers["Location"].endswith("/")
    assert anonymous.get("/api/bootstrap").get_json()["user"]["username"] == "demo"
    assert query("SELECT oauth_subject s FROM users WHERE username='demo'")[0]["s"] == "abc-123"
    assert "userinfo request failed" in caplog.text and "403" in caplog.text


def test_sso_userinfo_wins_over_the_id_token_and_no_claims_at_all_fail(anonymous, monkeypatch):
    import time

    query("UPDATE users SET email='demo@example.com' WHERE username='demo'")
    token = {"access_token": "at", "id_token": id_token({"sub": "from-id-token", "aud": "ophir-figures", "exp": time.time() + 300})}
    response, _ = sso_callback(anonymous, monkeypatch, token, {"sub": "from-userinfo", "email": "demo@example.com", "email_verified": True})
    assert response.headers["Location"].endswith("/")
    assert query("SELECT oauth_subject s FROM users WHERE username='demo'")[0]["s"] == "from-userinfo"

    fresh = ophir_figures.app.test_client()
    refused, _ = sso_callback(fresh, monkeypatch, {"access_token": "at"}, ophir_figures.auth.OAuthConfigError("403"))
    assert refused.headers["Location"].endswith("/login?error=provider_error")


def test_sso_only_counts_an_email_the_provider_says_it_verified():
    """Google sends email_verified true (its older endpoints the string "true"); Authentik from
    2025.10 on sends false unless a scope mapping vouches for the address."""
    verified = ophir_figures.auth.email_is_verified
    assert verified({"email_verified": True}) and verified({"email_verified": "true"}) and verified({"email_verified": "True"})
    for claims in ({}, {"email_verified": None}, {"email_verified": False}, {"email_verified": "false"}, {"email_verified": 1}, {"email_verified": "yes"}):
        assert not verified(claims), claims


def test_sso_without_email_verified_does_not_take_over_an_account(anonymous, monkeypatch):
    """A provider that sends no email_verified claim at all must not count as having verified the
    address, or anyone who could set that address at the provider would get the matching account."""
    query("UPDATE users SET email='admin@example.com' WHERE username='admin'")
    response, _ = sso_callback(anonymous, monkeypatch, {"access_token": "at"}, {"sub": "attacker", "email": "admin@example.com"})
    assert response.headers["Location"].endswith("/login?error=no_account")
    assert query("SELECT oauth_subject s FROM users WHERE username='admin'")[0]["s"] == ""
    assert anonymous.get("/api/bootstrap").status_code == 401


def test_an_id_token_for_someone_else_or_out_of_date_is_not_used():
    import time

    import oauth_client

    config, soon = {"client_id": "ophir-figures"}, time.time() + 300
    claims = lambda **changes: oauth_client.id_token_claims(config, {"id_token": id_token({"sub": "s", "aud": "ophir-figures", "exp": soon, **changes})})
    assert claims()["sub"] == "s"
    assert claims(aud=["other", "ophir-figures"])["sub"] == "s"
    assert claims(aud="another-client") == {} and claims(exp=time.time() - 5) == {} and claims(exp="never") == {}
    assert oauth_client.id_token_claims(config, {"id_token": "not.a-token"}) == {}
    assert oauth_client.id_token_claims(config, {"id_token": "a.%%%.c"}) == {}
    assert oauth_client.id_token_claims(config, {"access_token": "only"}) == {} and oauth_client.id_token_claims(config, "plain") == {}
