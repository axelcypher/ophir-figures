"""Serves the app for the browser tests (tests/frontend/*.test.mjs): the working tree, a throwaway
database and the same small catalogue the Python tests use. Nothing reaches the internet: product
pages and pictures come from fakes.

    python tests/frontend/serve.py <port> [<path prefix, e.g. /figures>]

With a prefix it stands in for the homelab's Traefik: only requests under the prefix reach the app,
with the prefix stripped and named in X-Forwarded-Prefix.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conftest  # noqa: E402  -- points DATABASE_PATH at a temp file before the app is imported

conftest.add_users()
conftest.add_figures()

SHOP_PAGE = b"""<html><head><meta property="og:title" content="Saber Alter 1/7 | Test Shop"><meta property="og:site_name" content="Test Shop">
<script type="application/ld+json">{"@type":"Product","name":"Saber Alter 1/7","brand":{"name":"Alter"},"gtin13":"4560228200001",
"offers":{"price":"159.90","priceCurrency":"EUR"}}</script></head><body></body></html>"""


def fake_fetch(url, max_bytes, accept="*/*", session=None):
    if url.startswith("https://shop.test/"):
        return url, "text/html", SHOP_PAGE
    raise conftest.ophir_figures.fetch.FetchError("Die Seite antwortet mit Fehler 404.")


def strip_prefix(wsgi_app, prefix):
    """What Traefik's StripPrefix middleware does in front of the app: a 404 outside the prefix,
    otherwise the path without it and the prefix in X-Forwarded-Prefix."""
    from werkzeug.exceptions import NotFound

    def strip(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path != prefix and not path.startswith(prefix + "/"):
            return NotFound()(environ, start_response)
        environ["PATH_INFO"] = path[len(prefix):] or "/"
        environ["HTTP_X_FORWARDED_PREFIX"] = prefix
        return wsgi_app(environ, start_response)
    return strip


for module in (conftest.ophir_figures.fetch, conftest.ophir_figures.images, conftest.ophir_figures.link_import):
    module.fetch = fake_fetch
app = conftest.ophir_figures.app
if len(sys.argv) > 2:
    app.wsgi_app = strip_prefix(conftest.ophir_figures.web.behind_proxy(app.wsgi_app), sys.argv[2].rstrip("/"))
app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, threaded=True)
