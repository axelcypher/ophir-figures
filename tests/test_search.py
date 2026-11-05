"""What the search boxes match: every word somewhere in the figure, forgiving about spacing, case and
small typos -- or, with regular-expression syntax, the text as typed or read as an expression."""
import pytest

from conftest import FRIEREN, MIKASA, MIKU, REM, TWINS, default_list
from ophir_figures import search


def names(rows):
    return {row["name"] for row in rows}


@pytest.mark.parametrize("query, expected", [
    ("rem", {"figma Rem", "Rem & Ram: Twins Ver."}),
    ("Frieren|Mikasa", {"Nendoroid Frieren", "POP UP PARADE Mikasa Ackerman"}),
    ("^(figma|nendoroid) ", {"figma Rem", "Nendoroid Frieren"}),
    ("Hatsune Miku: Racing", {"Hatsune Miku: Racing 2024 Ver."}),
    ("hatsunemiku", {"Hatsune Miku: Racing 2024 Ver."}),
    ("Hatsume", {"Hatsune Miku: Racing 2024 Ver."}),           # a letter off
    ("good smile 1/7", {"Hatsune Miku: Racing 2024 Ver."}),     # manufacturer and scale
    ("re zero kadokawa", {"Rem & Ram: Twins Ver."}),
    ("4580590123456", {"Hatsune Miku: Racing 2024 Ver."}),      # the JAN
    ("初音ミク", {"Hatsune Miku: Racing 2024 Ver."}),             # the original name
    ("(Twins", {"Rem & Ram: Twins Ver."}),                      # no valid expression: taken literally
])
def test_every_search_box_reads_the_text_the_same_way(client, query, expected):
    for figure_id in (MIKU, FRIEREN, REM, MIKASA, TWINS):
        client.post("/api/collection", json={"figure_id": figure_id})
        client.post(f"/api/watchlists/{default_list(client)}/figures", json={"figure_id": figure_id})
    everywhere = client.get("/api/search", query_string={"q": query, "limit": 80}).get_json()
    catalogue = client.get("/api/figures", query_string={"q": query}).get_json()["figures"]
    collection = client.get("/api/collection", query_string={"q": query}).get_json()["figures"]
    wished = client.get(f"/api/watchlists/{default_list(client)}/figures", query_string={"q": query}).get_json()["figures"]
    assert names(everywhere) == names(catalogue) == names(collection) == names(wished) == expected


def test_the_quick_search_ranks_names_starting_with_the_query_first(client):
    found = client.get("/api/search", query_string={"q": "rem"}).get_json()
    assert [row["name"] for row in found] == ["Rem & Ram: Twins Ver.", "figma Rem"]
    assert [row["name"] for row in client.get("/api/search", query_string={"q": "figma rem"}).get_json()] == ["figma Rem"]
    assert client.get("/api/search", query_string={"q": "r"}).get_json() == [], "one letter is no search yet"


SMUG_ALANA = (("Smug Alana (PL9)", search.NAME), ("PL9", search.NUMBER), ("Fractured Paradox", search.SET), ("FP", search.SET),
              ("1st Edition Holo", search.DETAIL), ("Rare", search.DETAIL), ("Gains 2 power when attacking.", search.TEXT))


@pytest.mark.parametrize("query", [
    "Smug Alana", "smug alana", "Smugalana", "SmugAlana PL9", "SmugAlana Fractured Paradox 1st Ed", "alana smug",
    "Smug Alana (PL9)", "Smug Allana", "smgu alana", "Smug Alana Holo", "PL9 Paradox", "Smúg Alana",
])
def test_a_name_is_found_however_it_is_typed(query):
    assert search.score(query, *[value for field in SMUG_ALANA for value in field]) > 0


@pytest.mark.parametrize("query", ["Smug Alana PL8", "Smug Bob", "Alana Shattered", "Smug Alana 2nd"])
def test_every_word_has_to_fit(query):
    assert search.score(query, *[value for field in SMUG_ALANA for value in field]) == 0


def test_rules_text_is_searched_but_not_for_typos():
    assert search.matches("attacking", SMUG_ALANA) and not search.matches("atacking", SMUG_ALANA)


def test_the_closest_name_ranks_first():
    exact = search.query("Goddess").score((("Goddess", search.NAME),))
    longer = search.query("Goddess").score((("Goddess Sansindra", search.NAME),))
    in_text = search.query("Goddess").score((("Ember", search.NAME), ("Pray to the goddess.", search.TEXT)))
    assert exact > longer > in_text > 0


def test_expressions_still_work():
    fields = (("Monarch (PL10)", search.NAME),)
    assert search.matches("PL9|10", fields), "an alternative stands on its own"
    assert not search.matches("PL9|PL10", (("Monarch (PL8) 010", search.NAME),))
    assert search.matches("C++", (("c++", search.NAME),)) and search.matches("mr. mime", (("MR. MIME", search.NAME),))
    assert search.matches(r"\d{3}", (("No. 204", search.NAME),)) and not search.matches(r"\D", (("204", search.NAME),))
    assert not search.matches("a" * 300 + "|b", (("b", search.NAME),)), "a very long text is not compiled as an expression"


def reference_near_miss(token, text):
    """near_miss as it was first written: a full edit-distance table per word and per prefix
    length. The faster version (one banded table per word) has to agree with it everywhere."""
    def within(word, other, limit):
        if abs(len(word) - len(other)) > limit:
            return False
        previous = list(range(len(other) + 1))
        for i, char in enumerate(word, 1):
            current = [i]
            for j, other_char in enumerate(other, 1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char != other_char)))
            previous = current
        return previous[-1] <= limit

    if len(token) < 4 or any(char.isdigit() for char in token):
        return False
    words = search.field_words(text)[0]
    limit = 1 if len(token) < 8 else 2
    return any(
        within(token, word, limit) or any(within(token, word[:size], limit) for size in (len(token) - 1, len(token), len(token) + 1) if 0 < size < len(word))
        for word in list(words) + [a + b for a, b in zip(words, words[1:])]
    )


def test_typo_tolerance_agrees_with_the_plain_edit_distance():
    import random
    generator = random.Random(7)
    # A small alphabet makes near misses common; lengths around 4 and 8 cover both limits.
    alphabet = "abcde"
    texts = ["Mickey Mouse - Detective", "Smug Alana PL9", "Goddess of the Sea", "Ember (PL8)", "Maleficent", "a", ""]
    texts += [" ".join("".join(generator.choice(alphabet) for _ in range(generator.randint(1, 11))) for _ in range(generator.randint(1, 3))) for _ in range(400)]
    tokens = ["mickey", "mikey", "mickeymouse", "godess", "goddes", "smugalana", "malefiscent", "embr", "ember", "pl8"]
    tokens += ["".join(generator.choice(alphabet) for _ in range(generator.randint(3, 10))) for _ in range(150)]
    disagreements = [(token, text) for token in tokens for text in texts if search.near_miss(token, text) != reference_near_miss(token, text)]
    assert not disagreements
    matches = sum(reference_near_miss(token, text) for token in tokens for text in texts)
    assert matches > 500, "the sample has to contain plenty of near misses to mean anything"


def test_short_words_and_numbers_stay_out_of_the_typo_cache():
    search.fuzzy_match.cache_clear()
    assert not search.near_miss("els", "Elsa - Snow Queen") and not search.near_miss("pl10", "Smug Alana PL9")
    assert search.fuzzy_match.cache_info().currsize == 0
