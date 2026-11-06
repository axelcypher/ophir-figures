# Export, backup and restore

`backup.py` writes an account's data out (JSON backup, CSV tables) and restores a backup, with undo.

## Public interface

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/export.json` | Download `ophir-figures-backup-<date>.json`. |
| GET | `/api/export.csv` | The collection, one row per collection row, `;`-separated, UTF-8 with BOM, decimal comma. |
| GET | `/api/export/preorders.csv` | The preorders, same format. |
| POST | `/api/import/json/preview` | `{data}` -> counts: `figures`, `figures_new`, `collection`, `preorders`, `watchlists`, `watchlist_entries`, `exported_at`, `user`. 400 for anything that is not a backup. |
| POST | `/api/import/json/apply` | `{data, strategy: add|replace}` -> `operation_id` and counts. All or nothing: an invalid item rolls everything back (400). |
| POST | `/api/import/<id>/undo` | Only the account's latest restore that is not undone yet. |

Backup format (`format: "ophir-figures-backup"`, `version: 1`): `figures` (catalogue fields, `ref` = id on the source instance, `attributes`, `market_value` for information), `collection` (`figure_ref`, entry fields, `preorder_index` into `preorders`), `preorders` (`figure_ref`, fields, `events`), `watchlists` (`name`, `is_default`, `entries` with `figure_ref`, `target_price`, `note`).

Restore:

- Each figure is matched with `figures.find_duplicate`; missing ones are created (credited to the restoring account).
- Preorders already present (same figure, shop, order date and order number) are skipped; new ones get their events back. Booked collection rows keep their link through `preorder_index`.
- `replace` deletes the collection first and remembers the rows; `add` appends.
- Wishlists are merged: the default list into the default list, others by name (created when missing).
- `import_operations.changes` records created figures, rows, preorders, lists, list entries and replaced rows. Undo deletes what was added, puts replaced rows back (dropping a `preorder_id` whose preorder is gone) and deletes created figures nothing uses any more.

## Dependencies

- `figures` (`clean_figure_fields`, `find_duplicate`, `in_use`), `collection.clean_entry_fields`, `preorders.clean_preorder_fields`, `schema.ensure_user_lists`, `prices.market_value_sql`

## Decisions and assumptions

- Market values in a backup are informational and not restored: they are shared catalogue data, not the account's. Line presets are not in it for the same reason.
- Pictures are not included (size); `image_url` is, and an instance re-downloads it on first view. Uploaded pictures are only in the data volume.
