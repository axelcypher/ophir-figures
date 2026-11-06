"""Presets per product line: what a line fixes (manufacturer, brand, category, scale, material), so
choosing the line fills those fields of a figure (line_presets.py). Shared by every account, like
the catalogue; one preset per line, the line's name matched without regard to case.
"""

NAME = "line presets"


def apply(connection, context):
    context.run_script("""
CREATE TABLE line_presets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  line TEXT NOT NULL,
  manufacturer TEXT NOT NULL DEFAULT '',
  brand TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  scale TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_line_presets_line ON line_presets(line COLLATE NOCASE);
""")
