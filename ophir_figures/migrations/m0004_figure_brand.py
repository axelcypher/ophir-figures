"""The brand a figure is sold under (Tamashii Nations, F:NEX, Banpresto), beside the company that
makes it (manufacturer: Bandai Spirits, FuRyu). Existing figures start without one: copying the
manufacturer over would only be a guess.
"""

NAME = "figure brand"


def apply(connection, context):
    context.run_script("""
ALTER TABLE figures ADD COLUMN brand TEXT NOT NULL DEFAULT '';
""")
