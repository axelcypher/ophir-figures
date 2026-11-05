"""The first schema of Ophir Figures.

Frozen: a later change to the schema is a new migration, never an edit here.
"""

NAME = "baseline"

TABLES = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '', oauth_provider TEXT NOT NULL DEFAULT '', oauth_subject TEXT NOT NULL DEFAULT ''
);
-- Only rows linked to an identity of the SSO provider.
CREATE UNIQUE INDEX idx_users_oauth_identity ON users(oauth_provider,oauth_subject) WHERE oauth_subject != '';

CREATE TABLE user_settings (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, key TEXT NOT NULL, value TEXT NOT NULL,
  PRIMARY KEY(user_id, key)
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- The catalogue, shared by every account. A row is one product: an edition with its own bonus
-- part or release (Standard / Limited) is a row of its own.
CREATE TABLE figures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  original_name TEXT NOT NULL DEFAULT '',
  characters TEXT NOT NULL DEFAULT '',
  series TEXT NOT NULL DEFAULT '',
  manufacturer TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  line TEXT NOT NULL DEFAULT '',
  scale TEXT NOT NULL DEFAULT '',
  height_mm INTEGER,
  edition TEXT NOT NULL DEFAULT '',
  release_date TEXT NOT NULL DEFAULT '',
  msrp REAL,
  msrp_currency TEXT NOT NULL DEFAULT 'JPY',
  jan TEXT NOT NULL DEFAULT '',
  sculptor TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  image_key TEXT NOT NULL DEFAULT '',
  attributes TEXT NOT NULL DEFAULT '{}',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_figures_jan ON figures(jan);
CREATE INDEX idx_figures_release ON figures(release_date);

-- Market values: one row per value someone entered (or a link import brought along); the newest
-- is the current one, the rest is the history.
CREATE TABLE price_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  figure_id INTEGER NOT NULL REFERENCES figures(id) ON DELETE CASCADE,
  amount REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
  source TEXT NOT NULL DEFAULT 'manual', note TEXT NOT NULL DEFAULT '',
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX idx_prices_figure ON price_observations(figure_id, observed_at DESC, id DESC);

CREATE TABLE preorders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  figure_id INTEGER NOT NULL REFERENCES figures(id),
  status TEXT NOT NULL DEFAULT 'ordered' CHECK(status IN ('ordered','paid','shipped','delivered','cancelled')),
  shop TEXT NOT NULL DEFAULT '',
  order_number TEXT NOT NULL DEFAULT '',
  ordered_at TEXT NOT NULL DEFAULT '',
  quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
  price REAL,
  shipping REAL,
  paid REAL NOT NULL DEFAULT 0,
  expected_release TEXT NOT NULL DEFAULT '',
  tracking TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  delivered_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_preorders_user ON preorders(user_id, status);
CREATE INDEX idx_preorders_figure ON preorders(figure_id);
-- What happened to a preorder: status changes, payments and above all moved release dates.
CREATE TABLE preorder_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  preorder_id INTEGER NOT NULL REFERENCES preorders(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, old_value TEXT NOT NULL DEFAULT '', new_value TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_preorder_events ON preorder_events(preorder_id, id);

-- One row per copy group of the same figure, condition and purchase.
CREATE TABLE collection_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  figure_id INTEGER NOT NULL REFERENCES figures(id),
  quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
  condition TEXT NOT NULL DEFAULT 'boxed' CHECK(condition IN ('sealed','boxed','loose','damaged')),
  purchase_price REAL,
  purchased_at TEXT NOT NULL DEFAULT '',
  shop TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  preorder_id INTEGER REFERENCES preorders(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_collection_user ON collection_entries(user_id, figure_id);
CREATE INDEX idx_collection_figure ON collection_entries(figure_id);
CREATE INDEX idx_collection_preorder ON collection_entries(preorder_id) WHERE preorder_id IS NOT NULL;

CREATE TABLE watchlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  UNIQUE(user_id, name)
);
CREATE TABLE watchlist_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  figure_id INTEGER NOT NULL REFERENCES figures(id),
  target_price REAL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  UNIQUE(list_id, figure_id)
);
CREATE INDEX idx_watchlist_entries_figure ON watchlist_entries(figure_id);

-- Restores of a JSON backup, so the latest can be taken back.
CREATE TABLE import_operations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, changes TEXT NOT NULL, undone_at TEXT
);
"""


def apply(connection, context):
    context.run_script(TABLES)
