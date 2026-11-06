# Page shell, bootstrap, dashboard and public profile

`pages.py` serves the page shell and what the app loads first; `public_profile.py` the shared view of a collection for visitors without an account.

## Public interface

### pages.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET | `/` | login | `templates/index.html`. |
| GET | `/api/bootstrap` | login | `user` (with `oauth_linked`, `password_set`), `settings`, `counts` (`collection` figures, `wished` figures, open `preorders`, `catalog`), `watchlists`, last 4 `imports`, `oauth` (enabled, name), `auth` (`mode` of the shared sign-in, `base` where sign-in is: `/auth` on the shared host, else the app's root; [shared-auth.md](shared-auth.md)), `conditions`, `statuses`, `categories`, `currency`. |
| GET | `/api/dashboard` | login | `collection` (collection.dashboard_collection), `preorders` (`stats`, `upcoming`: 8 open ones by expected release), `counts`. |

### public_profile.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET/PUT | `/api/account/public-profile` | login | The owner's setting: `enabled`, `slug` (3-32 of `a-z0-9-`, no hyphen at either end, unique), `name` (60), `show_wishlist`, `theme` (`auto`/`light`/`dark`); `url` built on `PUBLIC_PROFILE_URL` or the request's root URL (host plus the path the app is served under). Enabling needs a slug. |
| GET | `/u/<slug>` | none | `templates/public.html`; 404 page when off or unknown. |
| GET | `/api/public/<slug>` | none | `{name, slug, collection, facets (category, manufacturer, series), stats (figures, copies), wishlist?}`; figures through `public_figure` only. |
| GET | `/u/<slug>/images/<id>` | none | Thumbnail, or the full picture with `?size=full`, only for figures in the shared collection or shared default wishlist; 404 otherwise. |

- `public_figure(item)` is the only shape that leaves the server for visitors: `id, name, original_name, characters, series, manufacturer, category, line, scale, edition, release_date, has_image, image_version, owned`. No prices, values, purchase data, conditions, storage places, notes, preorders or target prices.

## Dependencies

- `collection`, `preorders`, `watchlists`, `figures`, `images.serve_figure_image`, `auth.resolve_oauth_config`

## Decisions and assumptions

- An off and an unknown profile answer the same 404, so addresses cannot be probed.
- The setting is only written through its own endpoint, which checks the slug; `/api/settings` skips the key.
