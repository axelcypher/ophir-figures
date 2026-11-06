"""How every search box matches: forgiving about spacing, case, accents and small typos.

A query is split into words, and each word has to turn up in one of the figure's fields -- name,
original (Japanese) name, characters, franchise (series), manufacturer, brand, line, category, scale, edition, JAN,
sculptor, description -- in any order. Inside a field spaces and punctuation do not count, so
"Hatsune Miku", "HatsuneMiku" and "hatsune-miku 1/7" all find "Hatsune Miku" (1/7). A word of
four letters or more (without digits) may be one letter off (two from eight letters on) from a word
in the field or its start: "Hatsnue" finds "Hatsune".

A query with the syntax only a regular expression uses -- | ^ $ \\ [ ] * + ? { } -- is matched as
typed, or read as that expression ("Miku|Rin", "^Nendoroid"), in any one field. Brackets and dots
alone do not count, so "Miku (Racing)" and "Ver. 2" are words.

Matches are scored -- the name counts for more than the description, the whole name for most --
so searches that show a few results list the best ones first.
"""

import re
import unicodedata
from functools import lru_cache

WORD = re.compile(r"\w+")
REGEX_SYNTAX = re.compile(r"[|^$\\\[\]*+?{}]")
QUERY_MAX = 200

# The weight a field's hit adds to the score.
NAME, NUMBER, SET, DETAIL, TEXT = 4.0, 3.0, 2.0, 1.0, 0.4
FUZZY = 0.6


@lru_cache(maxsize=200_000)
def fold(text):
    """Lower case without accents: "Pokémon" -> "pokemon"."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


@lru_cache(maxsize=200_000)
def field_words(text):
    """The field's words and the field without spaces/punctuation."""
    words = tuple(WORD.findall(fold(text)))
    return words, "".join(words)


def within_prefixes(token, word, lengths, limit):
    """Whether `token` is at most `limit` edits (Levenshtein) from word[:n] for any n in `lengths`.

    One table for all of them: row i, column j of the table between the token and the longest
    prefix is the distance from token[:i] to word[:j], so its last row holds the distance to every
    prefix at once. Only cells within `limit` of the diagonal can end up within `limit`; the others
    are capped at limit + 1 and not computed, and a row with nothing left within `limit` ends it.
    A table per prefix length (and one for the whole word), as before, cost four times the work
    on every new word typed into a search box."""
    top, cap = max(lengths), limit + 1
    previous = [j if j <= limit else cap for j in range(top + 1)]
    for i, char in enumerate(token, 1):
        current = [cap] * (top + 1)
        current[0] = best = i if i <= limit else cap
        for j in range(max(1, i - limit), min(top, i + limit) + 1):
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char != word[j - 1]), cap)
            current[j] = value
            best = min(best, value)
        if best > limit:
            return False
        previous = current
    return any(previous[length] <= limit for length in lengths)


@lru_cache(maxsize=4096)
def typo_tolerant(token):
    """Whether a token may be a letter off: four letters or more, no digits (1/7 is no typo of 1/8).
    Cached because a search asks it for every field of every figure it scores."""
    return len(token) >= 4 and not any(char.isdigit() for char in token)


def near_miss(token, text):
    """Whether the field has a word (or two run together) one letter off the token, two from eight
    letters on -- whole, or as much of its start as was typed. Not for numbers: 1/7 is no typo of
    1/8."""
    # Tested ahead of the cache of matches: short words and numbers never match, and would fill it.
    return typo_tolerant(token) and fuzzy_match(token, text)


@lru_cache(maxsize=400_000)
def fuzzy_match(token, text):
    words = field_words(text)[0]
    limit = 1 if len(token) < 8 else 2
    for word in list(words) + [a + b for a, b in zip(words, words[1:])]:
        lengths = [size for size in (len(token) - 1, len(token), len(token) + 1) if 0 < size < len(word)]
        if abs(len(word) - len(token)) <= limit:
            lengths.append(len(word))
        if lengths and within_prefixes(token, word, lengths, limit):
            return True
    return False


def token_score(token, fields):
    """The weight of the best field the token is in; a near miss counts 0.6 of it. Rules text is
    only searched for the word itself -- long texts have a near miss for almost anything."""
    best = max((weight for text, weight in fields if token in field_words(text)[1]), default=0.0)
    if not typo_tolerant(token):
        return best
    for text, weight in fields:
        if weight > TEXT and weight * FUZZY > best and fuzzy_match(token, text):
            best = weight * FUZZY
    return best


class Query:
    def __init__(self, text):
        self.text = text.strip()
        self.tokens = tuple(dict.fromkeys(WORD.findall(fold(self.text))))
        self.compact = "".join(self.tokens)
        self.pattern = None
        if REGEX_SYNTAX.search(self.text):
            literal = re.escape(self.text)
            try:
                self.pattern = re.compile(f"{literal}|(?:{self.text})" if len(self.text) <= QUERY_MAX else literal, re.I)
            except re.error:
                self.pattern = re.compile(literal, re.I)

    def __bool__(self):
        return bool(self.tokens or self.pattern)

    def score(self, fields):
        """fields: (text, weight) pairs; empty ones are skipped. 0 means no match."""
        fields = [(str(text), weight) for text, weight in fields if text not in (None, "")]
        if self.pattern:
            return max((weight for text, weight in fields if self.pattern.search(text)), default=0.0)
        total = 0.0
        for token in self.tokens:
            best = token_score(token, fields)
            if not best:
                return 0.0
            total += best
        # The whole query as (the start of) the name puts that figure first.
        names = [field_words(text)[1] for text, weight in fields if weight == NAME]
        if self.compact in names:
            total += 10
        elif any(name.startswith(self.compact) for name in names):
            total += 5
        return total


@lru_cache(maxsize=256)
def query(text):
    return Query(text)


def score(text, *fields):
    """SQL: search_score(?, text1, weight1, text2, weight2, ...)."""
    return query(text).score(zip(fields[::2], fields[1::2]))


def matches(text, fields):
    return query(text).score(fields) > 0


FIGURE_FIELDS = (
    ("name", NAME), ("original_name", NAME), ("characters", NUMBER), ("jan", NUMBER),
    ("series", SET), ("manufacturer", SET), ("brand", SET), ("line", DETAIL), ("category", DETAIL), ("scale", DETAIL),
    ("edition", DETAIL), ("sculptor", DETAIL), ("description", TEXT),
)


def figure_fields(row):
    """A figure row's searchable fields."""
    return tuple((row.get(column), weight) for column, weight in FIGURE_FIELDS)


def figure_score_sql(parameter="?", alias="f"):
    """figure_fields in SQL for a query over `figures {alias}`; `parameter` is the query's placeholder."""
    return f"search_score({parameter}," + ",".join(f"{alias}.{column},{weight}" for column, weight in FIGURE_FIELDS) + ")"
