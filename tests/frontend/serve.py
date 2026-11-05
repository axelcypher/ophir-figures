"""Serves the app for the browser tests (tests/frontend/*.test.mjs): the working tree, a throwaway
database and the same small catalogue the Python tests use. Nothing reaches the internet: product
pages and pictures come from fakes.

    python tests/frontend/serve.py <port>
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


for module in (conftest.ophir_figures.fetch, conftest.ophir_figures.images, conftest.ophir_figures.link_import):
    module.fetch = fake_fetch
conftest.ophir_figures.app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, threaded=True)
