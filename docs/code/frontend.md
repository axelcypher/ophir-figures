# Browser frontend

`templates/index.html` plus plain scripts in `static/js/` that share one global scope (no build step, no framework), in this order: `core.js`, `figures-ui.js`, `views.js`, `dashboard.js`, `settings.js`, `admin.js`, `import.js`, `main.js`. `filter-panel.js` and `stat-pill.js` define the custom elements `ophir-filter-panel` (a collapsible filter area on small screens) and `ophir-stat-pill`. The public profile has its own `static/public.js`.

## Public interface

### core.js

- `state` - `boot` (the bootstrap answer), `route`, `edit` (quick edit: ＋ on tiles), filters per view (`catalogFilters`, `collectionFilters`, `watchFilters` with `default…Filters()`, all with the value filters of `FIGURE_FACETS()`), `grouping` per grid (`catalog`, `collection`, `watch`: `{by, sort, open}`, `defaultGrouping()`; the kind each grid shows comes back from the setting `groupings`), `watchlistId`, `preorderStatus`, `modalFigure`, `modalTab`, `suggestions`, `linePresets` (the answer of `/api/line-presets`, `loadLinePresets(force)`), `gridFigures`.
- `APP_ROOT` - the path the app is served under, from `<html data-root>` (the request's script root: `''` at the root, `/figures` behind a proxy that strips it); `appUrl(path)` puts it in front of a path starting with `/`. Every address of the app goes through it: `api` does it for every call, and `figureThumb`/`figureImage`, the CSV and SSO links and the bookmarklet use it. `public.js` reads the same attribute.
- `api(url, options)`, `post`, `patch`, `del` - JSON; 401 goes to `/login`; errors carry `status` and `data`.
- `routeTo(route, data)` - `dashboard`, `catalog`, `collection`, `watchlist`, `preorders`, `settings`, `admin`; `renderGuard()` lets a late answer drop itself; `refreshCurrentView()`, `refreshCounts()`, `paintCounts()` (`[data-count]` badges).
- `openDialog({id, eyebrow, title, intro, body, stack, wide})` / `closeDialog()` - dialogs (`.dl-modal`); `fieldValues(root)` reads `[data-field]`.
- Helpers: `escapeHtml`, `money`, `currencyMoney`, `amountValue` (German form value), `partialDate` (`2026-03` -> `März 2026`), `plural`, `figureThumb`, `figureImage`, `searchMatcher` (as search.py), `statPill`, `mountFilterPanel`, `toast(message, actionLabel, action, key)`, `applyAppearance()` (cookie `ophir_figures_theme`).

### figures-ui.js

- `figureTile(figure, {note, value, badge})`, `renderFigureGrid(container, figures, {tile, empty})` (pages of 180, the next loads on scroll), `toggleWish`, `quickAddCopy`.
- `filterBar({...})` / `wireFilterBar(root, filters, render, reset)`, `filterQuery(filters)`. With `grouping`, the bar sorts the groups (`data-group-sort`) and leaves out the filter of the grouped field; in an open group that filter is the group and does not count for "Filter zurücksetzen".
- Groups (catalogue, collection, wishlist alike): `groupSwitch(view)` (Figuren · Franchise · Marke · Hersteller · Linie), `wireGroups(root, view, filters, render)`, `gridQuery(filters, grouping)`, `syncOpenGroup` (the filter select of the grouped field picks another group, "Alle" goes back), `openGroup(view, filters, name, render)`, `groupHead(view, {count, owned, actions})`, `groupTile(by, group, stats)` (a mosaic of up to four figures), `renderGroupGrid(container, view, groups, {stats, empty, onOpen})`, `restoreGroupings`, `GROUPINGS`, `NONE_VALUE`.
- `openFigure(id, tab)` - the figure dialog (`#figure-modal`) with tabs `copies`, `preorders`, `value`, `lists`, `info`; `afterChange()` reloads it, the counts and the view.
- `openEntryDialog(figure, entry)`, `openPreorderDialog(figure, preorder, prefill)`, `openWishDialog(id)`, `openImageDialog(figure)`, `openFigureForm(prefill, {figureId, importResult})` (create/edit with link import; "Danach" opens the copy or preorder dialog or wishes). Both picture file fields offer `PICTURE_TYPES` (JPEG, PNG, WebP, GIF, AVIF, as images.py takes them); the server checks the file itself.
- The figure form is in sections (`FIGURE_SECTIONS`: Figur; Linie & Hersteller with the line first; Details; Preis & Bild; Quelle & Beschreibung).
- Line presets: `wireLinePreset(form, {applyNow})` - choosing a line with a preset fills its fields that are empty or still hold what a preset put there; a typed value stays and the hint (`#preset-hint`) offers "Vorlage übernehmen"; without a preset it offers "Als Vorlage speichern". An existing figure's form only says what the preset would change until the line is chosen again. `openLinePresets()` (catalogue: "Linien-Vorlagen") lists the presets with "Ergänzen" (apply) and the catalogue's lines without one; `openPresetForm(preset, prefill, {onSaved})`; `presetForLine`, `presetBadge` ("Vorlage" on a line group's tile), `PRESET_FIELDS`. An open line group's head shows its preset and "Vorlage anlegen/bearbeiten".
- `bookmarkletHref()` - the `javascript:` link; `handleImportFragment()` - reads `#import=<snapshot>` at start-up and opens the form.

### views.js, dashboard.js, settings.js, admin.js, import.js, main.js

- `renderCatalog`, `renderCollection`, `renderWatchlist(listId)`, `renderPreorders` (grouped: overdue, by month, without date, closed), `pickFigure(title, onPick)`; `renderDashboard`; `renderSettings` (account, appearance, bookmarklet, public profile); `renderAdmin` (SSO, accounts, catalogue duplicates); `openImportExport`; `init()` and the fixed controls.

## Tests

- `tests/frontend/unit.test.mjs` - loads the scripts into a vm context (`scripts.mjs`): formatting, search matching, tiles, filter URLs, preorder grouping, the bookmarklet run against a fake page, and `appUrl`/`api`/the bookmarklet under a root (`loadScripts(..., {root})`).
- `tests/frontend/smoke.test.mjs` - headless Chrome over the DevTools protocol (`harness.mjs`) against `serve.py`: every view, catalogue filters and dialog tabs, a figure from a link into the collection, wish -> preorder -> arrival, settings, admin, and the app under `/figures` (`startServer({prefix})`; every request the page makes has to carry the prefix, `page.requests`). Skipped locally without Chrome.
- `tests/frontend/serve.py <port> [<prefix>]` - with a prefix it stands in for Traefik's StripPrefix: a 404 outside the prefix, otherwise the path without it and the prefix in `X-Forwarded-Prefix`, read by `web.behind_proxy`.

## Decisions and assumptions

- The look is DeckLedger's (its stylesheets unchanged); `figures.css` adds the figure components on top of the design tokens in `design-system.css`.
- No service worker and no offline mode (left out on purpose).
