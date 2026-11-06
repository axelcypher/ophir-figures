# Catalogue, search, pictures and market values

`figures.py` is the shared figure catalogue: listing with filters, details, create, update, delete, duplicate detection. `line_presets.py` keeps what a product line fixes, so choosing the line fills it in. `search.py` is how every search box matches; `images.py` stores and serves pictures; `prices.py` keeps market values; `fetch.py` is the guarded HTTP client for user-given links.

## Public interface

### figures.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/figures` | Every figure as a list item (catalogue fields, `has_image`, `image_version`, and for the signed-in account `owned`, `preordered` (open), `wished`, plus `market_value`). Args: `mode` (`all`/`owned`/`missing`/`wished`/`preordered`), `q`, the value filters `series` (franchise), `brand`, `manufacturer`, `line`, `category`, `scale` (each also `__none__`: figures without a value), `character`, `year` (or `none`), `sort` (`release`/`name`/`added`/`value`, or the text sorts `series`/`brand`/`manufacturer`/`line`), `direction`, and `group` / `group_sort` (below). Returns `{figures, total, shown, facets}`; facets are over the whole catalogue. |
| GET | `/api/figures/suggestions` | Autocomplete values: catalogue columns by frequency, characters, the account's own shops and storage places, `currencies`. |
| GET | `/api/figures/<id>` | Detail: all columns, `attributes`, `created_by_name`, `can_delete`, and the account's `entries`, `preorders` (preorders.preorder_rows), `lists`, plus `prices` and `owners`. 404 when unknown. |
| POST | `/api/figures` | Create. Fields as `clean_figure_fields` reads them; `market_value` adds a first price observation (`source` `import` with `from_import`); `force` skips the duplicate check. 409 `{error, duplicate_id}` for a duplicate. Fetches `image_url` at once; a failure comes back as `image_error`, the link is kept. 201 with the detail. |
| PATCH | `/api/figures/<id>` | Update any subset; duplicate check against the merged row; a changed `image_url` is fetched again. |
| DELETE | `/api/figures/<id>` | Only while no account uses it (409) and only by its creator or an admin (403). |
| GET | `/api/search?q=&limit=` | Quick search: best-scored list items, at least two characters. |

### Groups

The catalogue, the collection and a wishlist can answer with their figures in groups instead (`?group=<kind>`): `series` (Franchise), `brand` (Marke), `manufacturer` (Hersteller) or `line` (Linie) - kinds side by side, none above another. The grid's filters, mode and sort apply first; the answer then has `group` and `groups` in place of `figures`, the rest stays (`total`, `shown`, `facets`, `stats` ...).

- A group: `name` (`""` for the figures without a value, always last), `count`, `owned` (figures in the collection), `copies`, `preordered`, `wished`, `target_reached` (wishlist entries), `value` (the sum of the market values; in the collection what the copies are worth), `spent` (collection), `latest_release`, `samples` (up to four `{id, name, has_image, image_version}`, those with a picture first, in the grid's order).
- `group_sort`: `name` (default, A-Z), `count`, `owned` (share of the group in the collection), `value`, `release` (latest release first). Equal groups stay A-Z.
- Opening a group is filtering by it: `series=Re:Zero`, or `series=__none__` for the group without a value.
- `group_items(items, by, sort, value_key)`, `grouped(args, items, value_key)` (None when no valid `group` was asked for), `GROUPINGS`, `GROUP_SORTS`.

Helpers used by other modules: `normalize_date` (`2025`, `2025-03`, `14.03.2025`, `03/2025`, `03/14/2025`, `March 2025`, `2025年3月` -> ISO with the given precision; returns `(value, error)`), `split_list` (characters), `clean_figure_fields`, `find_duplicate` (same JAN, same `source_url`, or same folded name+manufacturer+edition), `figure_list_sql(where)` (the list query; `?1` is the user id), `list_item`, `apply_filters`, `sort_items`, `facets`, `in_use`, `CATEGORIES`, `FACET_FIELDS` (the value filters, in the order the facets list them), `NONE_VALUE` (`__none__`), `TEXT_SORTS`.

- Text sorts go A-Z, then by name; figures without a value come last in either direction, by name.
- `series` is shown as **Franchise** in the interface (the work a figure comes from); `brand` (**Marke**, migration 0004) is the label a figure is sold under (Tamashii Nations, F:NEX), `manufacturer` (**Hersteller**) the company that makes it (Bandai Spirits, FuRyu).

### line_presets.py

A preset per product line (`line_presets`, migration 0005) holds what the line usually fixes: `manufacturer`, `brand`, `category`, `scale`, `material` (`PRESET_FIELDS`). Shared like the catalogue: anyone signed in creates and corrects presets, only the creator or an admin deletes one. Lines are matched by `line_key` (spacing and case aside), one preset per line.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/line-presets` | `{presets, lines, fields}`: every preset with `figures` (catalogue figures of the line), `incomplete` (of those, how many have an empty field the preset fills), `created_by_name`, `can_delete`; `lines` are the catalogue's lines without a preset, most figures first, each with `figures` and `common` (per field the value its figures mostly have) to start a preset from. |
| POST | `/api/line-presets` | `{line, manufacturer, brand, category, scale, material}`; spacing tidied. 400 without a line, when no field is set or one is longer than 300 characters; 409 `{error, preset_id}` when the line has a preset. 201 with the preset. |
| PATCH | `/api/line-presets/<id>` | Any subset; the result must still set a field; renaming onto another preset's line is 409. |
| DELETE | `/api/line-presets/<id>` | Creator or admin (403 otherwise). The figures stay as they are. |
| POST | `/api/line-presets/<id>/apply` | Fills the empty preset fields of every catalogue figure of the line; a field with a value keeps it. `{updated, filled: {field: count}}`. |

- `fill_from_preset(connection, fields, guessed)` - fills a figure's fields in place from its line's preset: the empty ones and those in `guessed`; returns `{id, line, applied}` or None. Used by the link import (link-import.md).
- `preset_for(connection, line)`, `line_key(text)`, `clean_preset(payload, partial)`.
- A preset only ever fills fields, it never empties one: in the form the filled fields stay editable, the link import keeps what the page says, and applying keeps every value a figure has.
- Presets are not part of an account's backup: like figures they are shared catalogue data.

### search.py

- `score(query, text1, weight1, ...)` (SQL `search_score`), `matches`, `query(text)`; `figure_fields(row)` and `figure_score_sql(param, alias)` with the weights: name and original name 4, characters and JAN 3, series, manufacturer and brand 2, line/category/scale/edition/sculptor 1, description 0.4.
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
