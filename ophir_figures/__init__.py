"""Ophir Figures: a self-hosted collection manager for anime figures.

Importing the package builds the whole application: every module registers its routes on the one
Flask app, then the database is created or migrated. `app.py` in the repository root is the entry
point servers and scripts import.
"""
from . import config, web, schema  # noqa: F401  -- the order is the dependency order
from . import prices, images, figures, link_import, collection, watchlists, preorders, backup, auth, account, admin, pages, public_profile  # noqa: F401
from .web import app

schema.init_database()

__all__ = ["app"]
