# Catalogue, search, pictures and market values

`figures.py` is the shared figure catalogue: listing with filters, details, create, update, delete, duplicate detection. `search.py` is how every search box matches; `images.py` stores and serves pictures; `prices.py` keeps market values; `fetch.py` is the guarded HTTP client for user-given links.

## Public interface

### figures.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/figures` | Every figure as a list item (catalogue fields, `has_image`, `image_version`, and for the signed-in account `owned`, `preordered` (open), `wished`, plus `market_value`). Args: `mode` (`all`/`owned`/`missing`/`wished`/`preordered`), `q`, `category`, `manufacturer`, `series`, `line`, `scale`, `character`, `year` (or `none`), `sort` (`release`/`name`/`added`/`value`/`manufacturer`), `direction`. Returns `{figures, total, facets}`; facets are over the whole catalogue. |
| GET | `/api/figures/suggestions` | Autocomplete values: catalogue columns by frequency, characters, the account's own shops and storage places, `currencies`. |
| GET | `/api/figures/<id>` | Detail: all columns, `attributes`, `created_by_name`, `can_delete`, and the account's `entries`, `preorders` (preorders.preorder_rows), `lists`, plus `prices` and `owners`. 404 when unknown. |
| POST | `/api/figures` | Create. Fields as `clean_figure_fields` reads them; `market_value` adds a first price observation (`source` `import` with `from_import`); `force` skips the duplicate check. 409 `{error, duplicate_id}` for a duplicate. Fetches `image_url` at once; a failure comes back as `image_error`, the link is kept. 201 with the detail. |
| PATCH | `/api/figures/<id>` | Update any subset; duplicate check against the merged row; a changed `image_url` is fetched again. |
| DELETE | `/api/figures/<id>` | Only while no account uses it (409) and only by its creator or an admin (403). |
| GET | `/api/search?q=&limit=` | Quick search: best-scored list items, at least two characters. |

Helpers used by other modules: `normalize_date` (`2025`, `2025-03`, `14.03.2025`, `03/2025`, `03/14/2025`, `March 2025`, `2025年3月` -> ISO with the given precision; returns `(value, error)`), `split_list` (characters), `clean_figure_fields`, `find_duplicate` (same JAN, same `source_url`, or same folded name+manufacturer+edition), `figure_list_sql(where)` (the list query; `?1` is the user id), `list_item`, `apply_filters`, `sort_items`, `facets`, `in_use`, `CATEGORIES`.

### search.py

- `score(query, text1, weight1, ...)` (SQL `search_score`), `matches`, `query(text)`; `figure_fields(row)` and `figure_score_sql(param, alias)` with the weights: name and original name 4, characters and JAN 3, series and manufacturer 2, line/category/scale/edition/sculptor 1, description 0.4.
- Every word must be in some field (spaces and punctuation inside a field ignored); words of 4+ letters without digits may be one edit off (two from 8 letters). Text with `| ^ $ \ [ ] * + ? { }` is matched literally or as a regular expression.

### images.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET | `/images/figures/<id>` | login | The picture (original bytes, with the content type of its format, e.g. `image/avif`); a placeholder SVG (5 min cache) without one. |
| GET | `/images/figures/<id>/thumb` | login | WebP, 480 px wide, made on first use (from any of the formats below). |
| POST | `/api/figures/<id>/image` | login | Multipart `file`, or JSON `{url}` to download. 400 for anything Pillow cannot read as JPEG/PNG/WebP/GIF/AVIF or above 15 MB. |
| DELETE | `/api/figures/<id>/image` | login | Clears `image_key` and `image_url`; the file stays (it may be shared). |

- `store_image(bytes)` -> key `<sha256>.<ext>`, the bytes kept as they came; `FORMATS` maps Pillow's format (`JPEG`, `PNG`, `WEBP`, `GIF`, `AVIF`) to extension and content type. AVIF needs a Pillow built with libavif: the PyPI wheels of the pinned Pillow (Windows and the manylinux ones the image installs) bundle it. `download_image(url)` (also the picture an `image_url` on create/update or from the link import names); `ensure_image(connection, figure)` fetches a pending `image_url` on first view, a failed URL not again for 600 s (per process); `serve_figure_image(id, size)` (also used by the public profile). A request with `?v=<first 12 of the key>` is cached for a year.

### prices.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/figures/<id>/prices` | History, newest first, with the author's name. |
| POST | `/api/figures/<id>/prices` | `{amount, note}`; amount required. |
| DELETE | `/api/figures/<id>/prices/<price_id>` | Removes one value of that figure. |

- `market_value_sql(column)`, `collection_value_sql()` (copies x market value, else x purchase price, else 0), `parse_amount(value, field)` (`189,90`, `1.299,00`, `1,299.00`, `19.800` = 19800; 0 to 1,000,000; returns `(value, error)`), `record_price`, `price_history`.

### fetch.py

- `fetch(url, max_bytes, accept)` -> `(final url, content type, bytes)`; raises `FetchError` with a German message and `blocked` (True for 401/403/429/503: the site refuses automatic requests, the message points to the bookmarklet). Only http(s), only hosts whose every address is global (no loopback, private, link-local, multicast), redirects followed by hand (5) and each checked, 15 s timeout, size limit. User agent `Mozilla/5.0 (compatible; OphirFigures/1.0; +…)`.

## Dependencies

- `web` (app, db, guards), `config`, `prices` <-> `figures`, `preorders.preorder_rows` (figure detail), Pillow (images), requests (fetch)

## Decisions and assumptions

- One shared catalogue that everyone may correct, like a small wiki; deleting is restricted to unused entries and their creator or an admin. Duplicates are prevented on entry and merged by admins (admin.md in auth.md).
- An edition (Limited, bonus part, re-release) is a figure of its own, so the duplicate key includes the edition.
- Pictures are content-addressed and never deleted automatically: two figures may share one, and an upload cannot be fetched again.
- The DNS check and the connection are separate lookups, so DNS rebinding is not prevented; acceptable for an app whose users are signed in.
