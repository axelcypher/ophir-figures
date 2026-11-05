# Browser frontend

`templates/index.html` plus plain scripts in `static/js/` that share one global scope (no build step, no framework), in this order: `core.js`, `figures-ui.js`, `views.js`, `dashboard.js`, `settings.js`, `admin.js`, `import.js`, `main.js`. `filter-panel.js` and `stat-pill.js` define the custom elements `ophir-filter-panel` (a collapsible filter area on small screens) and `ophir-stat-pill`. The public profile has its own `static/public.js`.

## Public interface

### core.js

- `state` - `boot` (the bootstrap answer), `route`, `edit` (quick edit: ＋ on tiles), filters per view (`catalogFilters`, `collectionFilters`, `watchFilters` with `default…Filters()`), `watchlistId`, `preorderStatus`, `modalFigure`, `modalTab`, `suggestions`, `gridFigures`.
- `api(url, options)`, `post`, `patch`, `del` - JSON; 401 goes to `/login`; errors carry `status` and `data`.
- `routeTo(route, data)` - `dashboard`, `catalog`, `collection`, `watchlist`, `preorders`, `settings`, `admin`; `renderGuard()` lets a late answer drop itself; `refreshCurrentView()`, `refreshCounts()`, `paintCounts()` (`[data-count]` badges).
- `openDialog({id, eyebrow, title, intro, body, stack, wide})` / `closeDialog()` - dialogs (`.dl-modal`); `fieldValues(root)` reads `[data-field]`.
- Helpers: `escapeHtml`, `money`, `currencyMoney`, `amountValue` (German form value), `partialDate` (`2026-03` -> `März 2026`), `plural`, `figureThumb`, `figureImage`, `searchMatcher` (as search.py), `statPill`, `mountFilterPanel`, `toast(message, actionLabel, action, key)`, `applyAppearance()` (cookie `ophir_figures_theme`).

### figures-ui.js

- `figureTile(figure, {note, value, badge})`, `renderFigureGrid(container, figures, {tile, empty})` (pages of 180, the next loads on scroll), `toggleWish`, `quickAddCopy`.
- `filterBar({...})` / `wireFilterBar(root, filters, render, reset)`, `filterQuery(filters)`.
- `openFigure(id, tab)` - the figure dialog (`#figure-modal`) with tabs `copies`, `preorders`, `value`, `lists`, `info`; `afterChange()` reloads it, the counts and the view.
- `openEntryDialog(figure, entry)`, `openPreorderDialog(figure, preorder, prefill)`, `openWishDialog(id)`, `openImageDialog(figure)`, `openFigureForm(prefill, {figureId, importResult})` (create/edit with link import; "Danach" opens the copy or preorder dialog or wishes).
- `bookmarkletHref()` - the `javascript:` link; `handleImportFragment()` - reads `#import=<snapshot>` at start-up and opens the form.

### views.js, dashboard.js, settings.js, admin.js, import.js, main.js

- `renderCatalog`, `renderCollection`, `renderWatchlist(listId)`, `renderPreorders` (grouped: overdue, by month, without date, closed), `pickFigure(title, onPick)`; `renderDashboard`; `renderSettings` (account, appearance, bookmarklet, public profile); `renderAdmin` (SSO, accounts, catalogue duplicates); `openImportExport`; `init()` and the fixed controls.

## Tests

- `tests/frontend/unit.test.mjs` - loads the scripts into a vm context (`scripts.mjs`): formatting, search matching, tiles, filter URLs, preorder grouping, and the bookmarklet run against a fake page.
- `tests/frontend/smoke.test.mjs` - headless Chrome over the DevTools protocol (`harness.mjs`) against `serve.py`: every view, catalogue filters and dialog tabs, a figure from a link into the collection, wish -> preorder -> arrival, settings, admin. Skipped locally without Chrome.

## Decisions and assumptions

- The look is DeckLedger's (its stylesheets unchanged); `figures.css` adds the figure components on top of the design tokens in `design-system.css`.
- No service worker and no offline mode (left out on purpose).
