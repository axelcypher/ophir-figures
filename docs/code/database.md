# Database and application core

`config.py`, `web.py`, `schema.py`, `migrations/` and the entry point `app.py`: where state lives, the one Flask app every module registers routes on, the per-request database connection with its guards, and bringing the database to the current schema at start-up.

## Public interface

### app.py

- `gunicorn app:app` in the container (2 workers, 4 threads, port 8080); `python app.py` starts Flask's debug server on 0.0.0.0:8080. It only re-exports `ophir_figures.app`.
- Importing `ophir_figures` (or any submodule) imports every route module and calls `schema.init_database()`.

### config.py

Imports nothing from the package.

- `ROOT` - repository root; `DB_PATH` - env `DATABASE_PATH`, default `<ROOT>/ophir-figures.db`; `DATA_DIR` - its directory; `IMAGE_DIR` (`figure-images/`) and `THUMB_DIR` (`figure-thumbnails/`) next to it.
- `OAUTH_CONFIG_PATH`, `OAUTH_PROVIDER_KEY = "generic"`, `OAUTH_CONFIG_DEFAULTS` (see auth.md); `APP_NAME`; `CURRENCY = "EUR"` (every amount a user enters).
- `now_iso()` (UTC, whole seconds, ISO 8601 with offset: the format of every `*_at` column), `today_iso()`, `jload(value, default)`, `slug(text)`.

### web.py

- `app` - the single Flask app (`OphirFigures`, `root_path=ROOT`). `db()` - one connection per app context: `sqlite3.Row`, `PRAGMA foreign_keys = ON`, `busy_timeout` 10 s, SQL function `search_score`. Nothing auto-commits.
- `login_required`, `admin_required`, `user_id()` - as in DeckLedger: a stale session is cleared; `/api/...` gets 401/403 JSON.
- `asset_url(filename)` (Jinja global) - static URL with `?v=<12 hex of the content hash>`; such a URL is cached for a year. Text files and JSON/HTML answers are gzipped.
- Hooks: `reject_cross_site_writes` (403 for a write whose `Sec-Fetch-Site` is not `same-origin`/`none`, or whose `Origin` is another host), `compress_answer`, `IntegrityError` -> 400 JSON on `/api/...`.
- `GET /health` (no auth) - `{"status", "database", "schema_version", "schema_expected"}`.

### schema.py

- `init_database()` - WAL mode, `migrations.migrate()`, then under `BEGIN IMMEDIATE`: `seed_database()` (the account `admin`/`admin` on an empty database, nothing else) and `ensure_user_lists()`.
- `ensure_user_lists(connection, user_id=None)` - gives every account (or one) its default wishlist `Wunschliste` if it has none. Called after an account is created (admin, SSO auto-provisioning, restore).

### migrations/

- `MIGRATIONS` - the ordered list; `m0001_baseline` creates every table. `migrate(connection, path)` applies each missing one in its own transaction and records it in `schema_migrations`; safe with several processes starting together; refuses a database with a version it does not know; copies an existing database first (`<db>.before-migration-NNNN`, two kept). `status(connection)` - (version, expected).

## Tables (m0001)

| Table | Holds | Notes |
| --- | --- | --- |
| `users`, `user_settings`, `app_settings` | accounts, per-account JSON settings, app-wide settings (`oauth_config`) | `(oauth_provider, oauth_subject)` unique when linked |
| `figures` | the shared catalogue | `created_by` SET NULL when the account goes; `attributes` JSON of extra imported fields |
| `price_observations` | market values per figure, newest = current | CASCADE with the figure; `user_id` SET NULL |
| `collection_entries` | copies: quantity (>0), condition (`sealed`/`boxed`/`loose`/`damaged`), purchase data, location, notes, `preorder_id` | CASCADE with the user; `preorder_id` SET NULL |
| `watchlists`, `watchlist_entries` | wishlists (one `is_default` per account), entries with `target_price`, `note` | entries CASCADE with their list |
| `preorders`, `preorder_events` | preorders (status CHECK), their history (`created`/`status`/`release`/`paid`) | CASCADE with the user / the preorder |
| `import_operations` | restores with the ids they added, for undo | CASCADE with the user |

Deleting an account therefore needs no code beyond `DELETE FROM users` (foreign keys are on in every request connection).

## Dependencies

- `ophir_figures.search` - `score` registered as `search_score`
- Flask, orjson, werkzeug (password hashes, ProxyFix)

## Decisions and assumptions

- A fresh baseline instead of DeckLedger's sixteen migrations: there is no older Ophir Figures database to upgrade.
- Every user-entered amount is in EUR; only the retail price (MSRP) keeps its own currency, as catalogue data.
- No background jobs: catalogue data comes from users, not from feeds, so nothing needs refreshing on a schedule.
