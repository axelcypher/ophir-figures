# Preorders

`preorders.py` tracks figures ordered before their release: payment, the expected release and how often it moved, status until arrival, and booking the arrived copies into the collection.

## Public interface

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/preorders?status=` | `open` (default: ordered, paid, shipped), one status, or `all`. Returns `{preorders, stats, statuses}`; `stats` always over all of the account's preorders: `open`, `open_copies`, `outstanding`, `open_total`, `paid`, `due_this_month`, `overdue` (expected month before this one), `next_month`, `delivered`, `cancelled`, `postponed`. |
| POST | `/api/preorders` | `{figure_id, status, shop, order_number, ordered_at (default today), quantity (1-99), price, shipping, paid, expected_release (default the figure's release date), tracking, notes, delivered_at, remove_from_wishlists}`. 201 with the row. |
| PATCH | `/api/preorders/<id>` | Any subset; only the owner's (404 otherwise). |
| DELETE | `/api/preorders/<id>` | Booked copies stay (their `preorder_id` becomes NULL). |

A row (`preorder_rows(uid, where, params)`, also used by the figure detail): the table's columns plus `figure_name`, `manufacturer`, `series`, `category`, `figure_release`, `has_image`, `image_version`, `total` (price + shipping, None when both are empty), `outstanding` (open ones only), `events`, `delays`, `booked_entry_ids`. Order: open first, then by expected release.

Status effects (`apply_status_side_effects`):

- to `paid`: `paid` is raised to the total if it was lower (logged as a `paid` event);
- to `delivered`: `delivered_at` = today unless set; the copies are booked once (`book_delivery`): condition `sealed`, purchase price = total / quantity, date = `ordered_at`, shop, note `Vorbestellung <order number>`;
- from `delivered` to anything else: `delivered_at` cleared, booked rows deleted;
- while `delivered`, changing quantity, price, shipping, shop or order date rebooks.

Events: `created`, `status`, `release`, `paid` with old and new value. `delays` counts `release` events whose new month is later than the old one.

## Dependencies

- `figures.normalize_date`, `prices.parse_amount`, `collection_entries` (booking)

## Decisions and assumptions

- Statuses are a fixed list (CHECK constraint) so the overview can count and group them.
- The expected release is the shop's, kept per preorder: the catalogue's release date is a fact about the product, the preorder's is what a shop currently promises.
