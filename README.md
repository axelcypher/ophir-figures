# Ophir Figures

Self-hosted, multi-user collection manager for anime figures (scale figures, Nendoroids, figma, prize figures and the like): a shared figure catalogue, each account's collection with purchase data, wishlists, preorders from order to arrival, market values and a public profile. One Flask app with an SQLite database, shipped as a single container image. The figures counterpart of [DeckLedger](https://github.com/axelcypher/deckledger) (future Ophir Cards), built from its code base. Prototype: complete and tested, not yet deployed.

## Features

- Local accounts with user and admin roles; optional sign-in through one OAuth2/OIDC provider
- Shared catalogue: name, original name, characters, series, manufacturer, category, line, scale, height, edition, release date, retail price with currency, JAN, sculptor, material, source link, picture; filters, sorting and a forgiving search (`Rem|Ram` for alternatives, a letter off is fine)
- Figures from a link: paste a product page and the form fills itself from its JSON-LD, meta tags and spec tables; for pages that refuse automatic requests (MyFigureCollection, AmiAmi, Kotobukiya, HobbySearch …) the bookmarklet "Zu Ophir Figures" reads the page in your own browser
- Duplicate check (same JAN, same link, or same name, manufacturer and edition) and, for admins, merging duplicates
- Collection: copies with condition (sealed, opened with box, loose, damaged), purchase price, date, shop, storage place and notes; totals for value and money spent
- Wishlists: a default list plus named lists, target price per entry, marked when the market value has fallen to it
- Preorders: shop, order number, price, shipping, what has been paid, expected release, status (ordered, paid, shipped, arrived, cancelled), tracking number; every postponed release is logged; arrival books the copies into the collection
- Market values per figure as a shared history with a chart; without one a copy counts with its purchase price
- Pictures: downloaded from a link or uploaded, thumbnails made on the server
- Public profile at `/u/<address>`: the collection (optionally the wishlist) with pictures, readable without signing in, without prices or private data
- JSON backup and restore (also onto another instance, with undo), CSV export of collection and preorders
- Dark and light appearance, works on phones

## Requirements

- Docker with Compose - runs the container ([compose.yaml](compose.yaml))
- Python 3.13 - development and the test suite (the image is `python:3.13-slim`)
- Node.js 22 or newer - the frontend tests use Node's own test runner (CI uses Node 24)
- Chrome or Chromium - the browser smoke tests; without it they are skipped locally

## Setup

1. Clone the repository:

    ```bash
    git clone https://github.com/axelcypher/ophir-figures.git
    cd ophir-figures
    ```

2. Set a strong `SECRET_KEY` in the environment or in a `.env` file next to `compose.yaml` (Compose falls back to a fixed development key otherwise):

    ```dotenv
    SECRET_KEY=<long random string>
    ```

3. Build and start:

    ```bash
    docker compose up --build -d
    ```

4. Open <http://localhost:18082> and sign in as `admin` / `admin`. Change that password under **Admin → Benutzer** right away and create the other accounts there.

The first start creates the database in the `ophir_figures_data` volume. There is no demo data: the catalogue starts empty and grows with the figures you add.

## Configuration

| Setting | Where | Description | Default | Required |
| --- | --- | --- | --- | --- |
| `SECRET_KEY` | env | Signs the session cookies | a fixed development key | yes, outside a local test |
| `DATABASE_PATH` | env | SQLite file; pictures and thumbnails live in `figure-images/` and `figure-thumbnails/` next to it | `ophir-figures.db` in the repo root; `/data/ophir-figures.db` in the image | no |
| `TRUST_PROXY_HEADERS` | env | `true`, `1` or `yes`: honour `X-Forwarded-Proto` / `X-Forwarded-Host` | off | behind a TLS-terminating proxy |
| `OAUTH_CONFIG_PATH` | env | SSO config file that replaces the Admin UI settings | `/config/oauth.json` | no |
| `PUBLIC_PROFILE_URL` | env | Base URL public profile links are built on, e.g. `https://ophirfigures.example.org` | the address the settings page was opened on | no |
| SSO settings | **Admin → Single Sign-On** or `oauth.json` | One OAuth2/OIDC provider, shape as in [oauth.json.example](oauth.json.example) | off | no |

### Single sign-on (OAuth2 / OIDC)

Works as in DeckLedger: configured under **Admin → Single Sign-On** (stored in the database) or with a config file mounted read-only at `/config/oauth.json`, which then wins and makes the Admin UI read-only. Required are `client_id`, `client_secret` and either `discovery_url` or all of `authorize_url`, `token_url` and `userinfo_url`. `account_matching` is `manual` (an identity must be linked under **Einstellungen → Konto**), `email` (an unlinked account with the provider-verified email is linked) or `auto_provision` (default: also creates a `user` account for an unknown identity). The redirect URI is `https://<host>/oauth/callback`; behind a TLS-terminating reverse proxy set `TRUST_PROXY_HEADERS=true`, and only when the proxy is the sole way to reach the container.

## Usage

### Adding figures

**＋ Figur** opens the form. A link pasted at the top is read by the server: shop pages with JSON-LD (Shopify shops, many manufacturer pages) fill name, picture, manufacturer, JAN, price and, where the page has them as label/value pairs, series, characters, release date, scale, height, sculptor and material. Requests go only to public addresses (no local network), with a 15 s timeout and size limits.

Many figure sites answer server requests with a bot check. For those, drag **★ Zu Ophir Figures** from **Einstellungen** (or from the form) into the bookmarks bar and click it on the product page: it reads the page you have open and opens Ophir Figures with the form filled in. The data travels in the address's fragment (`#import=…`), which never reaches a server log.

### Preorders

A preorder starts with the figure's release date as the expected release. Changing the expected release logs the move; a later month counts as a postponement. Marking it **Bezahlt** sets the paid amount to price plus shipping; **Angekommen** adds the copies to the collection as sealed, at the order's price per copy including shipping, with its date and shop. Setting it back takes those copies out again; deleting a preorder keeps them.

### Backup

**Import / Export** in the user menu downloads a JSON backup (collection, preorders with their history, wishlists, and every figure they refer to) or CSV tables. Restoring a backup matches its figures to the catalogue and creates missing ones; **Rückgängig** takes the latest restore back. Pictures are not in the backup; their links are, and the `ophir_figures_data` volume holds the uploaded ones.

### Operations

```bash
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` keeps the `ophir_figures_data` volume; it holds the database and every picture, so it is what to back up. `GET /health` answers with the database name, `schema_version` and `schema_expected`. Before an existing database is migrated, a copy is written next to it (`ophir-figures.db.before-migration-NNNN`, the two newest kept); a database written by a newer version is refused at start-up.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python app.py
```

`python app.py` starts Flask's debug server on port 8080 with `ophir-figures.db` in the repo root. `python tests/frontend/serve.py <port>` serves the app with a throwaway database and the small test catalogue (account `demo` / `figuren-1234`), the link import answering only from fakes.

- Code layout: `app.py` is only the entry point; the application is the `ophir_figures` package. Module docs: [docs/code/](docs/code/architecture.md).
- Schema changes: add `ophir_figures/migrations/mNNNN_<what>.py` with `NAME` and `apply(connection, context)` and list it in `MIGRATIONS`. A released migration is never edited; nothing else creates or alters tables (a test enforces it).
- Python tests: `python -m pytest` - every API against a throwaway database with a small built-in catalogue; outgoing requests are replaced by fakes.
- Frontend tests: `node --test "tests/frontend/*.test.mjs"` - script logic and the bookmarklet in a bare JavaScript context, and smoke tests that drive the real app in headless Chrome (`CHROME_BIN` sets the browser, `OPHIR_PYTHON` the interpreter that starts the app).
- Lint / format: none configured.

## Release

[.github/workflows/container-image.yml](.github/workflows/container-image.yml) runs on every push to `main`, on `v*` tags, on pull requests and by hand. It runs both test suites, then builds the image and, except for pull requests, pushes it to `ghcr.io/<owner>/<repository>` with the tags `main`, `latest`, `sha-<commit>` and, for a `v*` tag, the semver tags, and attests it. There is no version number in the code; images are identified by their `sha-<commit>` tag.

After a published build, the job `update-deployment-repository` writes that tag into an env file of another repository. It stays off until the repository variable `OPHIR_FIGURES_DEPLOY_REPOSITORY` is set:

| Variable / secret | Description | Default |
| --- | --- | --- |
| `OPHIR_FIGURES_DEPLOY_REPOSITORY` | Target repository, `owner/repository` | none (job disabled) |
| `OPHIR_FIGURES_DEPLOY_BRANCH` | Branch to commit to | `main` |
| `OPHIR_FIGURES_DEPLOY_ENV_FILE` | Env file in the target repository | `.env` |
| `OPHIR_FIGURES_DEPLOY_IMAGE_KEY` | Variable that receives the tag | `OPHIR_FIGURES_IMAGE_VERSION` |
| `OPHIR_FIGURES_DEPLOY_TOKEN` (secret) | Fine-grained token with read/write access to the target's contents | none |

## Documentation

- Module docs for agents: [docs/code/](docs/code/architecture.md)
- Detailed docs: vault note `homelab-docs/projects/ophir-figures.md`
