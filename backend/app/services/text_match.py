"""Trigram similarity compatible with PostgreSQL pg_trgm, for reference resolution.

Computed in Python so the same scores apply in tests (SQLite) and production; the
per-user list of open titles is small.
"""
from __future__ import annotations

import re

STOPWORDS = {'the', 'a', 'an', 'my', 'that', 'this', 'thing', 'task', 'for', 'to', 'of', 'with', 'about'}
PRONOUNS = {'it', 'that', 'this', 'that one', 'this one', 'the last one'}


def _words(text: str) -> list[str]:
    return re.findall(r'[^\W_]+', text.lower())


def trigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for word in _words(text):
        padded = f'  {word} '
        grams.update(padded[index:index + 3] for index in range(len(padded) - 2))
    return grams


def similarity(left: str, right: str) -> float:
    a, b = trigrams(left), trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def reference_score(reference: str, title: str) -> float:
    """Similarity of a spoken reference ("the report") to a stored title."""
    core = ' '.join(word for word in _words(reference) if word not in STOPWORDS) or reference
    score = similarity(core, title)
    title_words = set(_words(title))
    core_words = set(_words(core))
    if core_words and core_words <= title_words:
        # Every meaningful word of the reference appears in the title.
        score = max(score, 0.6 + 0.4 * len(core_words) / max(len(title_words), 1))
    return round(min(score, 1.0), 3)


def is_pronoun(reference: str) -> bool:
    return ' '.join(_words(reference)) in PRONOUNS


def rank(reference: str, candidates: list[tuple[str, str]]) -> list[tuple[str, str, float]]:
    """Rank (id, title) pairs for a reference, best first."""
    scored = [(identity, title, reference_score(reference, title)) for identity, title in candidates]
    return sorted(scored, key=lambda item: -item[2])
