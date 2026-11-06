# Architecture

Ophir Figures is one Flask application with one SQLite database, served by gunicorn in a single container. There are no background jobs: everything happens inside requests. It was built from DeckLedger's code base (commit 1646923); the core (app, migrations, sign-in, admin, look and feel) is DeckLedger's, the domain (figures instead of cards) is new.

## Processes

```
browser (templates/index.html + static/js, plain scripts)
   |  JSON under /api/, pictures under /images/, static files
   v
gunicorn app:app (2 workers x 4 threads, port 8080)
   |  ophir_figures package: one Flask app, routes from every module
   |------> product pages and pictures on the internet (fetch.py, only on a user's request)
   v
SQLite  <DATA>/ophir-figures.db (WAL)  +  figure-images/  figure-thumbnails/
```

- `docker-entrypoint.sh` runs `python -c "import app"` first, so the migrations finish before gunicorn serves anything. Importing the package anywhere migrates and seeds the database (`schema.init_database`).
- Every connection uses `busy_timeout` 10 s; requests share the one writer of the WAL database.

## Package layout

`app.py` is only the entry point. `ophir_figures/__init__.py` imports `config, web, schema` first, then the feature modules, then runs `schema.init_database()`.

| Area | Source | Doc |
| --- | --- | --- |
| Core: paths, the Flask app, request guards, schema and migrations | `app.py`, `config.py`, `web.py`, `schema.py`, `migrations/` | [database.md](database.md) |
| Catalogue, search, pictures, market values | `figures.py`, `search.py`, `images.py`, `prices.py`, `fetch.py` | [catalog.md](catalog.md) |
| Filling in a figure from a product page | `link_import.py`, `fetch.py`, bookmarklet in `static/js/figures-ui.js` | [link-import.md](link-import.md) |
| Collection and wishlists | `collection.py`, `watchlists.py` | [collection.md](collection.md) |
| Preorders | `preorders.py` | [preorders.md](preorders.md) |
| Export, backup, restore | `backup.py` | [backup.md](backup.md) |
| Sign-in, SSO, own account, admin API | `auth.py`, `oauth_client.py` (repo root), `account.py`, `admin.py` | [auth.md](auth.md) |
| Shared sign-in of the Ophir apps on one host (master/slave) | `shared_auth.py`, `ophir_auth.py` (repo root) | [shared-auth.md](shared-auth.md) |
| Page shell, bootstrap, dashboard, public profile | `pages.py`, `public_profile.py`, `templates/` | [pages.md](pages.md) |
| Browser frontend and its tests | `templates/index.html`, `static/` | [frontend.md](frontend.md) |

## Request flow

- Every route module registers on the one `web.app`. `web.db()` gives one connection per request (`sqlite3.Row`, foreign keys on, the SQL function `search_score`); writing views commit themselves.
- `@login_required` re-reads the session's user on every request; `@admin_required` adds the admin role. `/api/...` answers 401/403 JSON, pages redirect.
- A `before_request` hook refuses cross-site writes (Fetch Metadata / `Origin`); it is the app's only CSRF protection.
- With `OPHIR_AUTH_MODE` `master` or `slave`, a second `before_request` hook (`shared_auth.py`) sets the session's user from the host-wide `ophir_auth` cookie on every request, and the master's `after_request` renews or clears that cookie ([shared-auth.md](shared-auth.md)).
- Unauthenticated routes: `/login`, the OAuth callback, `/health`, and the public profile (`/u/<slug>`, `/u/<slug>/images/<id>`, `/api/public/<slug>`).

## Where state lives

All state is in the directory of `DATABASE_PATH` (`/data` in the container, the `ophir_figures_data` volume):

- `ophir-figures.db` - users and settings (`users`, `login_failures` for the login throttle, `user_settings`, `app_settings`), the catalogue (`figures`, `price_observations`), account data (`collection_entries`, `watchlists`, `watchlist_entries`, `preorders`, `preorder_events`, `import_operations`) and `schema_migrations`.
- `ophir-figures.db.before-migration-NNNN` - copies taken before a migration (two kept).
- `figure-images/` - every picture once, named by the SHA-256 of its bytes (uploads cannot be fetched again: back this up); `figure-thumbnails/` - WebP thumbnails, rebuildable.
- In the browser: only the theme cookie and nothing else (besides the session cookie and, with the shared sign-in, the host-wide `ophir_auth` cookie); there is no offline mode.

## External services

- Product pages and pictures named by users' links, fetched only on request ([link-import.md](link-import.md), [catalog.md](catalog.md)).
- One OAuth2/OIDC identity provider, optional ([auth.md](auth.md)).
- Google Fonts for the web fonts (decorative; the page renders without them).

## Tests

- `python -m pytest` (`tests/`): a throwaway database with five sample figures (`tests/conftest.py`), no network; `fake_fetch` replaces every outgoing request.
- `node --test "tests/frontend/*.test.mjs"`: frontend unit tests in a bare JavaScript context (`scripts.mjs`), including the bookmarklet run against a fake page, and smoke tests in headless Chrome against `tests/frontend/serve.py`.
- CI (`.github/workflows/container-image.yml`) runs both before an image is built.
