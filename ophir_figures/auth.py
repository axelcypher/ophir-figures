"""Signing in: local passwords and the optional OAuth/OIDC provider."""

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from oauth_client import OAuthConfigError, build_authorization_request, exchange_code, extract_identity, fetch_userinfo, id_token_claims

from .config import OAUTH_CONFIG_DEFAULTS, OAUTH_CONFIG_PATH, OAUTH_PROVIDER_KEY, jload, now_iso, slug
from .web import app, db
from .schema import ensure_user_lists


def oauth_config_from_environment():
    """SSO settings from variables named OAUTH_ plus a field of OAUTH_CONFIG_DEFAULTS in capitals:
    OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_DISCOVERY_URL and, if needed, OAUTH_PROVIDER_NAME,
    OAUTH_ACCOUNT_MATCHING and the rest. They switch SSO on. None while OAUTH_CLIENT_ID is unset."""
    values = {}
    for key in OAUTH_CONFIG_DEFAULTS:
        value = os.environ.get(f"OAUTH_{key.upper()}", "").strip()
        if value and key != "enabled":
            values[key] = value
    return {**values, "enabled": True} if values.get("client_id") else None


def resolve_oauth_config():
    # A mounted file wins, then OAUTH_* variables (the homelab renders them from Vault) -- the
    # Admin UI shows the fields read-only in both cases (see admin_get_oauth). Otherwise settings
    # live in app_settings and are read fresh on every call (no in-process caching of this dict)
    # so an Admin UI save takes effect on the very next login click, no restart needed.
    path = Path(OAUTH_CONFIG_PATH)
    if path.is_file():
        try:
            file_config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            file_config = {}
        return {**OAUTH_CONFIG_DEFAULTS, **file_config, "source": "file"}
    environment_config = oauth_config_from_environment()
    if environment_config:
        return {**OAUTH_CONFIG_DEFAULTS, **environment_config, "source": "environment"}
    row = db().execute("SELECT value FROM app_settings WHERE key='oauth_config'").fetchone()
    stored = jload(row["value"], {}) if row else {}
    return {**OAUTH_CONFIG_DEFAULTS, **stored, "source": "database"}


OAUTH_ERROR_MESSAGES = {
    "not_configured": "Single Sign-On ist auf diesem Server nicht aktiviert.",
    "state_mismatch": "Die Anmeldeanfrage ist abgelaufen oder ungültig. Bitte erneut versuchen.",
    "provider_error": "Der Identity Provider hat die Anmeldung abgelehnt oder ist nicht erreichbar.",
    "no_account": "Kein Ophir-Figures-Konto mit dieser Identität verknüpft. Bitte zuerst mit Benutzername/Passwort anmelden und das Konto in den Einstellungen unter „Single Sign-On“ verbinden.",
    "already_linked": "Diese SSO-Identität ist bereits mit einem anderen Konto verknüpft.",
}


def unique_username_from(candidate):
    base = slug(candidate) or "user"
    username, suffix = base, 1
    while db().execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        suffix += 1
        username = f"{base}-{suffix}"
    return username


def email_is_verified(claims):
    """Only a provider that says so has vouched for the address: OIDC's email_verified true, as
    Google sends it (its older endpoints as the string "true"). Authentik sends false from 2025.10
    on unless a scope mapping vouches for it; a provider that sends nothing proves nothing."""
    verified = claims.get("email_verified")
    return verified is True or (isinstance(verified, str) and verified.lower() == "true")


def resolve_oauth_identity(config, subject, email, display_name, email_verified=False):
    """Walks the account-matching chain for a login (not link) OAuth callback and
    returns the matched/created users row, or None if no account could be resolved.
    Order is cumulative: exact identity match always applies; email-matching and
    auto-provisioning are opt-in escalations controlled by account_matching."""
    connection = db()
    matched = connection.execute(
        "SELECT * FROM users WHERE oauth_provider=? AND oauth_subject=?", (OAUTH_PROVIDER_KEY, subject),
    ).fetchone()
    if matched:
        return matched
    mode = config.get("account_matching") or "manual"
    if mode in ("email", "auto_provision") and email:
        candidate = connection.execute(
            "SELECT * FROM users WHERE oauth_subject='' AND lower(email)=lower(?)", (email,),
        ).fetchone()
        if candidate and not email_verified:
            # An address the provider has not verified proves nothing about who is logging in.
            # Neither is the existing account handed over, nor a second account created next to
            # it under the same address.
            return None
        if candidate:
            connection.execute(
                "UPDATE users SET oauth_provider=?, oauth_subject=? WHERE id=?", (OAUTH_PROVIDER_KEY, subject, candidate["id"]),
            )
            connection.commit()
            return connection.execute("SELECT * FROM users WHERE id=?", (candidate["id"],)).fetchone()
    if mode == "auto_provision":
        username = unique_username_from(email.split("@")[0] if email else display_name or subject)
        connection.execute(
            "INSERT INTO users(username,display_name,password_hash,role,created_at,email,oauth_provider,oauth_subject) VALUES(?,?,?,?,?,?,?,?)",
            (username, display_name or username, "", "user", now_iso(), email, OAUTH_PROVIDER_KEY, subject),
        )
        ensure_user_lists(connection, connection.execute("SELECT id FROM users WHERE oauth_provider=? AND oauth_subject=?", (OAUTH_PROVIDER_KEY, subject)).fetchone()["id"])
        connection.commit()
        return connection.execute(
            "SELECT * FROM users WHERE oauth_provider=? AND oauth_subject=?", (OAUTH_PROVIDER_KEY, subject),
        ).fetchone()
    return None


# Password guessing: after this many failed sign-ins within the window, for one username or from
# one address, further attempts are turned away without looking at the password, until the oldest
# of them has left the window. Per username catches guesses spread over many addresses, per address
# one client trying many usernames. Behind a proxy every client has the proxy's address unless
# TRUST_PROXY_HEADERS is set.
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_FAILURES_PER_USERNAME = 10
LOGIN_FAILURES_PER_IP = 30


def login_window_start():
    return (datetime.now(timezone.utc) - LOGIN_FAILURE_WINDOW).replace(microsecond=0).isoformat()


def login_retry_after(connection, ip, username):
    """Seconds until a sign-in from `ip` for `username` is looked at again; 0 = now."""
    since, now = login_window_start(), datetime.now(timezone.utc)
    wait = 0
    for column, value, limit in (("username", username, LOGIN_FAILURES_PER_USERNAME), ("ip", ip, LOGIN_FAILURES_PER_IP)):
        # The limit-th most recent failure: once it has left the window, there is room again.
        row = connection.execute(
            f"SELECT failed_at FROM login_failures WHERE {column}=? AND failed_at>? ORDER BY failed_at DESC LIMIT 1 OFFSET ?",
            (value, since, limit - 1),
        ).fetchone()
        if row:
            free_at = datetime.fromisoformat(row["failed_at"]) + LOGIN_FAILURE_WINDOW
            wait = max(wait, 1, math.ceil((free_at - now).total_seconds()))
    return wait


def record_login_failure(connection, ip, username):
    connection.execute("DELETE FROM login_failures WHERE failed_at<=?", (login_window_start(),))
    connection.execute("INSERT INTO login_failures(ip,username,failed_at) VALUES(?,?,?)", (ip, username, now_iso()))
    connection.commit()


@app.route("/login", methods=["GET", "POST"])
def login():
    oauth_config = resolve_oauth_config()
    oauth_context = {
        "oauth_enabled": oauth_config["enabled"], "oauth_provider_name": oauth_config["provider_name"],
    }
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        connection = db()
        # Counted in lower case ("Admin" is a guess at admin too) and cut short, so a huge field
        # cannot bloat the table.
        ip, counted_name = request.remote_addr or "", username.lower()[:200]
        wait = login_retry_after(connection, ip, counted_name)
        if wait:
            minutes = math.ceil(wait / 60)
            error = f"Zu viele fehlgeschlagene Anmeldeversuche. Bitte in {minutes} {'Minute' if minutes == 1 else 'Minuten'} erneut versuchen."
            return render_template("login.html", error=error, **oauth_context), 429, {"Retry-After": str(wait)}
        row = connection.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            # Only this address's own typos are forgiven: a guesser elsewhere keeps counting.
            connection.execute("DELETE FROM login_failures WHERE ip=? AND username=?", (ip, counted_name))
            connection.commit()
            session.clear()
            session["user_id"] = row["id"]
            return redirect(url_for("index"))
        record_login_failure(connection, ip, counted_name)
        return render_template("login.html", error="Benutzername oder Passwort ist nicht korrekt.", **oauth_context), 401
    if session.get("user_id"):
        return redirect(url_for("index"))
    error = OAUTH_ERROR_MESSAGES.get(request.args.get("error"))
    return render_template("login.html", error=error, **oauth_context)


def oauth_failure_redirect(link_flow, error_code):
    # An already-authenticated user hitting this from the Settings "Verbinden" button never sees
    # /login (it immediately bounces anyone with a session straight to "/") -- routing those
    # failures there would silently swallow the error. Send them to "/" with a query flag the SPA
    # itself reads and toasts (see init() in static/js/main.js) instead. A genuine logged-out login attempt
    # still gets the server-rendered banner on /login as before.
    if link_flow:
        return redirect(url_for("index", oauth_error=error_code))
    return redirect(url_for("login", error=error_code))


@app.get("/oauth/login")
def oauth_login():
    config = resolve_oauth_config()
    link_flow = bool(session.get("user_id"))
    if not config["enabled"]:
        return oauth_failure_redirect(link_flow, "not_configured")
    try:
        auth_url, state, code_verifier = build_authorization_request(config, url_for("oauth_callback", _external=True))
    except OAuthConfigError as error:
        app.logger.warning("SSO login could not be started: %s", error)
        return oauth_failure_redirect(link_flow, "provider_error")
    session["oauth_state"] = state
    session["oauth_code_verifier"] = code_verifier
    # Only set (and only ever trusted) when the browser already carries an authenticated
    # session -- marks this round trip on the callback as "link this identity to my
    # current account" (started from Settings) rather than "log me in as whoever this
    # identity resolves to" (started from the logged-out /login page).
    session["oauth_link_user_id"] = session.get("user_id")
    return redirect(auth_url)


@app.get("/oauth/callback")
def oauth_callback():
    config = resolve_oauth_config()
    link_user_id = session.pop("oauth_link_user_id", None)
    expected_state = session.pop("oauth_state", None)
    code_verifier = session.pop("oauth_code_verifier", None)
    if not config["enabled"] or not expected_state or request.args.get("state") != expected_state:
        return oauth_failure_redirect(link_user_id, "state_mismatch")
    code = request.args.get("code")
    if not code:
        return oauth_failure_redirect(link_user_id, "provider_error")
    # The login page only says "the provider refused or cannot be reached". Which step failed and
    # what the provider answered goes to the log -- without it a wrong client secret, an
    # unreachable token endpoint and a missing claim all look the same.
    step = "token exchange"
    try:
        redirect_uri = url_for("oauth_callback", _external=True)
        token = exchange_code(config, redirect_uri, code, code_verifier)
        step = "userinfo request"
        # An OIDC provider states who signed in twice: in the ID token that comes with the tokens,
        # and at its userinfo endpoint. Either is enough; a provider that refuses the second
        # request (Authentik does for some provider setups) must not make the login fail.
        claims = id_token_claims(config, token)
        try:
            claims = {**claims, **fetch_userinfo(config, token)}
        except OAuthConfigError as error:
            if not claims.get(config.get("subject_claim") or "sub"):
                raise
            app.logger.warning("SSO: the userinfo request failed, using the ID token's claims instead: %s", error)
        step = "reading the identity"
        subject, email, display_name = extract_identity(config, claims)
    except OAuthConfigError as error:
        app.logger.warning("SSO login failed at the %s (redirect URI %s): %s", step, url_for("oauth_callback", _external=True), error)
        return oauth_failure_redirect(link_user_id, "provider_error")

    connection = db()
    if link_user_id:
        conflict = connection.execute(
            "SELECT id FROM users WHERE oauth_provider=? AND oauth_subject=? AND id!=?", (OAUTH_PROVIDER_KEY, subject, link_user_id),
        ).fetchone()
        if conflict:
            return oauth_failure_redirect(link_user_id, "already_linked")
        connection.execute(
            "UPDATE users SET oauth_provider=?, oauth_subject=?, email=CASE WHEN email='' THEN ? ELSE email END WHERE id=?",
            (OAUTH_PROVIDER_KEY, subject, email, link_user_id),
        )
        connection.commit()
        session["user_id"] = link_user_id
        return redirect(url_for("index", linked="1"))

    matched = resolve_oauth_identity(config, subject, email, display_name, email_verified=email_is_verified(claims))
    if not matched:
        return redirect(url_for("login", error="no_account"))
    session.clear()
    session["user_id"] = matched["id"]
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
