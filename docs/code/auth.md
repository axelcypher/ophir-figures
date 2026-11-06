# Authentication, accounts and admin

`auth.py` signs users in with a local password or the one optional OAuth2/OIDC provider (protocol mechanics in `oauth_client.py`, repository root). `account.py` holds a user's own settings, account data and password; `admin.py` the admin API for accounts, SSO settings and tidying the catalogue. `auth.py`, `oauth_client.py` and `account.py` are DeckLedger's (Ophir Cards') unchanged apart from names. `shared_auth.py` (with `ophir_auth.py`, repository root) adds the shared sign-in of the Ophir apps; see the section below and [shared-auth.md](shared-auth.md).

## Public interface

### auth.py

| Method | Path | What it does |
| --- | --- | --- |
| GET/POST | `/login` | Login page / form (`username`, `password`, optional `next`); success clears the session, sets `user_id` and goes to `next_target()`. 401 on failure. Throttled (see below): the page with 429 and `Retry-After`, the password is not checked. |
| GET | `/oauth/login` | Authorization code flow with PKCE; with a signed-in session it is a link flow. Keeps `next` for the callback in `session["oauth_next"]`. |
| GET | `/oauth/callback` | Checks `state`, exchanges the code, then links (link flow) or signs in, ending at the kept `next`. Errors: `not_configured`, `state_mismatch`, `provider_error`, `no_account`, `already_linked`. |
| POST | `/logout` | Clears the session; goes to `next` when given, else to `/login`. |

- Login throttle (table `login_failures`, migration 0002): every failed `POST /login` stores the client address (`request.remote_addr`, the proxy's unless `TRUST_PROXY_HEADERS`), the username in lower case (cut to 200 characters, unknown names too) and the time, and deletes rows older than `LOGIN_FAILURE_WINDOW` (15 min). `login_retry_after(connection, ip, username)` returns the seconds until an attempt is looked at again: with `LOGIN_FAILURES_PER_USERNAME` (10) failures for the username or `LOGIN_FAILURES_PER_IP` (30) from the address inside the window, until the oldest of the counted ones leaves it. A turned-away attempt is not recorded. A successful sign-in deletes only the failures of its own address for that username.
- `resolve_oauth_config()` - defaults overlaid by the file at `OAUTH_CONFIG_PATH` (`source: file`), else by `oauth_config_from_environment()` (`source: environment`), else by `app_settings.oauth_config` (`source: database`); read on every call.
- `oauth_config_from_environment()` - `OAUTH_<FIELD>` for every field of `OAUTH_CONFIG_DEFAULTS` except `enabled` (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_DISCOVERY_URL`, `OAUTH_PROVIDER_NAME`, `OAUTH_ACCOUNT_MATCHING`, ...); a set `OAUTH_CLIENT_ID` switches SSO on, without it the variables are ignored.
- `email_is_verified(claims)` - True only for an `email_verified` claim of `true` or the string `"true"` (any case); missing, `false`, `null` or anything else is False. The callback passes this to `resolve_oauth_identity`.
- `resolve_oauth_identity(config, subject, email, name, email_verified=False)` - linked account; with `email`/`auto_provision` the unlinked account with that verified email (an unverified one that matches gives None); with `auto_provision` a new `user` account plus its default wishlist.

### oauth_client.py

`build_authorization_request`, `exchange_code`, `fetch_userinfo`, `id_token_claims` (no signature check; `aud` and `exp` checked), `extract_identity`, `resolved_endpoints`. Only `OAuthConfigError` escapes. 10 s timeout, User-Agent `Ophir Figures (OAuth client)`.

### account.py

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/settings` | Upserts each key into `user_settings` (JSON); `publicProfile` is ignored here. |
| PATCH | `/api/account` | `display_name`, `username` (3-32 of `a-zA-Z0-9._-`, unique), `email` (unique). |
| POST | `/api/account/password` | `new_password` (8+); `current_password` unless no local password yet. |
| POST | `/api/account/oauth/unlink` | Refused while there is no local password. |

### admin.py (every route `@admin_required`)

| Method | Path | What it does |
| --- | --- | --- |
| GET/POST | `/api/admin/users` | List (with `copies`, open `preorders`, `oauth_linked`, `password_set`, `is_self`) / create (also creates the default wishlist). |
| PATCH/DELETE | `/api/admin/users/<id>` | Edit fields, role, password, `unlink_oauth` / delete the account with all its data (foreign keys cascade; created figures and entered market values stay, uncredited). |
| GET | `/api/admin/catalog` | Every figure with `owners`, `preorders`, `wished`; `duplicates` (groups with the same JAN or the same name+manufacturer); `unused` ids. |
| POST | `/api/admin/catalog/merge` | `{source, target}`: collection rows, preorders and market values move to `target`, wishlist entries too (a list that has both keeps one), `source` is deleted. |
| DELETE | `/api/admin/catalog/<id>` | Only an unused figure (409). |
| GET/POST | `/api/admin/oauth` | SSO settings without the secret, with their `source` / save (refused while they come from a config file or `OAUTH_*` variables; a blank secret keeps the stored one). |

- The last admin can be neither demoted nor deleted; nobody deletes their own account here.

### Shared sign-in (shared_auth.py, ophir_auth.py)

With `OPHIR_AUTH_MODE` `master` or `slave` (`config.AUTH_MODE`, with `AUTH_PATH` and `AUTH_HOME`; any other value stops the app when `shared_auth` is imported) the routes above follow [shared-auth.md](shared-auth.md):

- `sign_in_from_shared_cookie` (`before_request`) sets `session["user_id"]` from the `ophir_auth` cookie on every request, or drops it: master, `sub` is the account id; slave, `local_account(identity)` finds the account by `users.auth_subject`, else links an unlinked one by email, then username (case-insensitive), else creates one without a password plus its default wishlist; display name, email (when the token has one) and role follow the token. Under the auth path the master answers 404 for every endpoint but `login`, `logout`, `oauth_login`, `oauth_callback`, `static` and `health`.
- `renew_shared_cookie` (`after_request`, master only) signs a new token after a sign-in, when the token is older than an hour or names another account, and clears it once the session has no account or the account is gone.
- `signs_in_elsewhere()` (a slave, or the master served under a path of the shared host): `/login`, `/oauth/login` and `/logout` redirect to the same routes under `OPHIR_AUTH_PATH` (`to_auth_path()`), keeping `next` (`/logout` and `POST /login` as 307).
- Sign-ins end at `next_target()` (validated `next`, else `start_page()`: the app's start page, or `OPHIR_AUTH_HOME` under the auth path). The SSO round trip keeps it in `session["oauth_next"]`; link-flow results go there with `linked=1` or `oauth_error=<code>`; login-flow failures go to `/login?error=<code>` with `next` unless it is the start page. The sign-in page's SSO button passes its `next` on.
- `refuse_when_slave()` answers 409 for changes of the own account (`PATCH /api/account`, password, SSO unlink) and of accounts in the admin area (create, change, delete) in slave mode.
- The bootstrap carries `auth: {mode, base}` (`auth_base()`); the Settings and Admin views show accounts as managed by the master in slave mode (no account editing, no SSO card).

## Dependencies

- `web`, `config` (OAuth constants, `AUTH_*`, `slug`, `now_iso`), `schema.ensure_user_lists`, `ophir_auth` (repository root, itsdangerous), Authlib and requests (oauth_client), werkzeug.security
- External: the configured identity provider; in slave mode the master Ophir app on the same host

## Decisions and assumptions

- Exactly one SSO provider; `users.oauth_provider` is always `generic`.
- SSO settings from `OAUTH_*` variables as well as from a file: the homelab renders secrets from Vault into an env file for the container, while a rendered file would belong to the render agent's user (mode `0400`) and be unreadable for the app's.
- Matching by email includes admin accounts, so it needs the provider's word that it verified the address: only an explicit `email_verified: true` counts (DeckLedger 369946e). A missing claim used to count as verified, which let anyone who could set that address at the provider take over the account. Google sends the claim; Authentik sends `false` from 2025.10 on unless a scope mapping says otherwise; Entra ID and plain OAuth2 providers send none and so never match by email.
- No CSRF tokens: forms and API writes rely on `web.reject_cross_site_writes`.
- The login throttle (DeckLedger 9ead237) keeps its count in SQLite, not in memory, so both gunicorn workers count together and a restart forgives nothing. Counting per username also stops guesses spread over many addresses, at a price: someone who keeps failing for a username keeps its password sign-in blocked (SSO still works). A success forgets only its own address's failures, so a guesser elsewhere gets no fresh allowance from the owner signing in.
- The seeded `admin`/`admin` account is not forced to change its password; the README says to change it right away.
- The session cookie has its own name (`ophir_figures_session`) and its own signing salt, because the homelab keeps one `SECRET_KEY` for the Ophir apps (Vault `docker-secrets/ophir`) and may serve Ophir Cards on the same host: with Flask's defaults a session cookie signed by Ophir Cards would be valid here and open the account with the same id, and the two apps would overwrite each other's cookie.
- Shared sign-in: `ophir_auth.py` is the same file in every Ophir app and is never edited here alone; `shared_auth.py` is a port of Ophir Cards' `ophir_cards/shared_auth.py` and should stay alike. A new slave account gets its default wishlist like every other new account. The link to the master is a column of its own (`users.auth_subject`, migration 0003), not the SSO columns, so going back to `standalone` keeps SSO links.
