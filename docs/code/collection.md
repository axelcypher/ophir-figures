# Collection and wishlists

`collection.py` holds an account's copies; `watchlists.py` its wishlists. Both list figures with the catalogue's list items, filters and facets (figures.py).

## Public interface

### collection.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/collection` | Owned figures as list items plus `spent`, `unpriced`, `value`, `conditions`, `locations`, `added_at`, `purchased_at`. Filters as the catalogue plus `location` and `condition`; sorts as the catalogue plus `added`, `purchased`, `spent`, `collection_value`. Returns `{figures, stats, shown, facets (with location), conditions}`; `stats` over the whole collection, `shown` over the filtered one. |
| POST | `/api/collection` | `{figure_id, quantity (1-999, default 1), condition (default boxed), purchase_price, purchased_at, shop, location, notes}`. 201 with the row. |
| PATCH | `/api/collection/<id>` | Any subset; only the owner's rows (404 otherwise). |
| DELETE | `/api/collection/<id>` | Returns `{deleted: row}`, enough to post it back (undo in the UI). |

- `CONDITIONS` - `sealed` Neu, versiegelt · `boxed` Geöffnet, mit Karton · `loose` Ohne Karton · `damaged` Beschädigt.
- `clean_entry_fields(payload, partial)`, `owned_figures(uid)`, `collection_stats(items)`, `dashboard_collection(uid)` (totals, 12 latest additions, copies per category).
- A copy's value: market value, else its purchase price, else 0 (`prices.collection_value_sql`); `unpriced` counts copies with neither a market value nor a purchase price.

### watchlists.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/watchlists` | The account's lists with `count`, default first. |
| POST | `/api/watchlists` | `{name}` (60 characters, unique per account ignoring case). |
| PATCH | `/api/watchlists/<id>` | Rename. |
| DELETE | `/api/watchlists/<id>` | Not the default list (400). |
| GET | `/api/watchlists/<id>/figures` | List items plus `target_price`, `note`, `wished_at`, `target_reached` (market value <= target). Filters as the catalogue; `mode=missing` hides owned ones; sorts `wished` (default) or the catalogue's. `stats`: `count`, `owned`, `target_reached`, `estimate` (market values, else target prices). |
| POST | `/api/watchlists/<id>/figures` | `{figure_id, target_price, note}`; adding again only updates the given fields. Returns `{added, lists}`. |
| PATCH | `/api/watchlists/<id>/figures/<figure_id>` | `target_price`, `note`. |
| DELETE | `/api/watchlists/<id>/figures/<figure_id>` | Returns `{removed: {figure_id, target_price, note}, lists}`. |

- `lists_of(uid)` (also in bootstrap).

## Dependencies

- `figures` (list query, filters, facets, `normalize_date`), `prices` (`parse_amount`, value SQL), `schema.ensure_user_lists` (default list)

## Decisions and assumptions

- A collection row groups copies with the same condition and purchase; several rows per figure are normal (two copies bought at different times).
- The heart on a tile always means the default list; other lists are chosen in the figure dialog.
