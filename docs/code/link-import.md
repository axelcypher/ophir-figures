# Link import

`link_import.py` turns a product page into figure fields for the form. Nothing is saved there; the user checks the form and saves through `POST /api/figures`.

## Public interface

| Method | Path | Body | What it does |
| --- | --- | --- | --- |
| POST | `/api/figures/link-import` | `{url}` | The server fetches the page (fetch.py, 4 MB) and reads it. 422 `{error, blocked}` when the fetch fails (`blocked` from `FetchError.blocked`) or the link is no HTML page. |
| POST | `/api/figures/link-import` | `{snapshot}` | A snapshot the browser made (bookmarklet), cut down by `sanitize_snapshot`. |

Answer: `{fields, offer, warnings, unmapped, duplicate}` - `fields` in the form's names (`name`, `original_name`, `characters`, `series`, `manufacturer`, `category`, `line`, `scale`, `height_mm`, `edition`, `release_date`, `msrp`, `msrp_currency`, `jan`, `sculptor`, `material`, `description`, `image_url`, `source_url`), only those found; `offer` the page's price `{price, currency}`; `unmapped` up to 30 label/value pairs nothing understood; `duplicate` `{id, name, reason}` from `figures.find_duplicate`.

### The snapshot

`{url, canonical, title, heading (first h1), meta {property|name|itemprop: content}, jsonld [parsed blocks], fields {label: value}}`. `snapshot_from_html(html, url)` builds it on the server with a forgiving tree (`TreeBuilder` on `html.parser`); the bookmarklet (`bookmarkletHref()` in static/js/figures-ui.js) builds the same in the page. Label/value pairs come from MyFigureCollection-style `.data-field` (`.data-label` / `.data-value`), `<dt>`/`<dd>` and two-cell table rows; first label wins, 200 at most.

### extract(snapshot)

- Name: JSON-LD Product `name`, else `og:title`, else the h1, else the title; the site name and "Buy"/"Pre-order" prefixes are cut.
- Picture, description, canonical link: JSON-LD, then OpenGraph/Twitter tags.
- Labels in English, German and Japanese (`LABELS`): series/origin/作品名, character/キャラクター, manufacturer/company/メーカー (the company in the manufacturer role), release date/発売日 (first date in the text), price/価格 (with currency hints ¥/円/€/$), scale and dimensions/仕様 (`1/7`, `H=240mm`, `全高約240mm`, cm), sculptor/原型 (or an artist "as Sculptor"), material/素材, JAN/barcode/gtin.
- Line and category from known product lines (`LINES`: Nendoroid, figma, POP UP PARADE, ARTFX J, Luminasta, …), else from the page's category, else Scale/Non-Scale from the scale.
- The retail price is the labelled price, else the JSON-LD offer, else `product:price:amount`.

## Dependencies

- `fetch.fetch`, `figures.find_duplicate`, `figures.normalize_date`, `figures.split_list`

## Decisions and assumptions

- MyFigureCollection, AmiAmi, Kotobukiya and HobbySearch answered server requests with a Cloudflare check when this was built (2026-11-05), and Solaris Japan (Shopify) answered requests from Python with 429 after a few tries while curl got through; the app sends an honest user agent and does not try to get around either. The bookmarklet reads the page the user has open in their own browser and hands it over in the URL fragment (never logged by a server, and a same-origin POST from the app page).
- The MyFigureCollection labels (`.data-field`, `Origin`, `Companies … (As Manufacturer)`, `Release date 03/27/2026 as …`) follow its known page structure; they could not be checked against the live site because of the bot check. Unknown labels end up in `unmapped`, so a changed page degrades to fewer filled fields, not to wrong ones.
- A US-style `03/27/2026` is read month first; `27.03.2026` day first.
