# Authentication, accounts and admin

`auth.py` signs users in with a local password or the one optional OAuth2/OIDC provider (protocol mechanics in `oauth_client.py`, repository root). `account.py` holds a user's own settings, account data and password; `admin.py` the admin API for accounts, SSO settings and tidying the catalogue. `auth.py`, `oauth_client.py` and `account.py` are DeckLedger's unchanged apart from names.

## Public interface

### auth.py

| Method | Path | What it does |
| --- | --- | --- |
| GET/POST | `/login` | Login page / form (`username`, `password`); success clears the session and sets `user_id`. 401 on failure. Throttled (see below): the page with 429 and `Retry-After`, the password is not checked. |
| GET | `/oauth/login` | Authorization code flow with PKCE; with a signed-in session it is a link flow. |
| GET | `/oauth/callback` | Checks `state`, exchanges the code, then links (link flow) or signs in. Errors: `not_configured`, `state_mismatch`, `provider_error`, `no_account`, `already_linked`. |
| POST | `/logout` | Clears the session. |

- Login throttle (table `login_failures`, migration 0002): every failed `POST /login` stores the client address (`request.remote_addr`, the proxy's unless `TRUST_PROXY_HEADERS`), the username in lower case (cut to 200 characters, unknown names too) and the time, and deletes rows older than `LOGIN_FAILURE_WINDOW` (15 min). `login_retry_after(connection, ip, username)` returns the seconds until an attempt is looked at again: with `LOGIN_FAILURES_PER_USERNAME` (10) failures for the username or `LOGIN_FAILURES_PER_IP` (30) from the address inside the window, until the oldest of the counted ones leaves it. A turned-away attempt is not recorded. A successful sign-in deletes only the failures of its own address for that username.
- `resolve_oauth_config()` - defaults overlaid by the file at `OAUTH_CONFIG_PATH` (`source: file`) or `app_settings.oauth_config`; read on every call.
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
| GET/POST | `/api/admin/oauth` | SSO settings without the secret / save (refused while a config file is mounted; a blank secret keeps the stored one). |

- The last admin can be neither demoted nor deleted; nobody deletes their own account here.

## Dependencies

- `web`, `config` (OAuth constants, `slug`, `now_iso`), `schema.ensure_user_lists`, Authlib and requests (oauth_client), werkzeug.security
- External: the configured identity provider

## Decisions and assumptions

- Exactly one SSO provider; `users.oauth_provider` is always `generic`.
- Matching by email includes admin accounts, so it needs the provider's word that it verified the address: only an explicit `email_verified: true` counts (DeckLedger 369946e). A missing claim used to count as verified, which let anyone who could set that address at the provider take over the account. Google sends the claim; Authentik sends `false` from 2025.10 on unless a scope mapping says otherwise; Entra ID and plain OAuth2 providers send none and so never match by email.
- No CSRF tokens: forms and API writes rely on `web.reject_cross_site_writes`.
- The login throttle (DeckLedger 9ead237) keeps its count in SQLite, not in memory, so both gunicorn workers count together and a restart forgives nothing. Counting per username also stops guesses spread over many addresses, at a price: someone who keeps failing for a username keeps its password sign-in blocked (SSO still works). A success forgets only its own address's failures, so a guesser elsewhere gets no fresh allowance from the owner signing in.
- The seeded `admin`/`admin` account is not forced to change its password; the README says to change it right away.
