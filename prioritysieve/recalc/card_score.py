from __future__ import annotations

from ..prioritysieve_globals import DEFAULT_REVIEW_DUE
from ..reading_utils import normalize_reading
from ..morpheme import Morpheme

# Anki stores the 'due' value of cards as a 32-bit integer.
# We keep the original ceiling for reuse in other modules (e.g., offset logic).
_MAX_SCORE: int = 2_047_483_647


def compute_due_from_priorities(
    morphs: list[Morpheme],
    morph_priorities: dict[tuple[str, str, str], int],
) -> int:
    """Return the minimum priority value found for the card's morphs."""

    priorities: list[int] = []
    for morph in morphs:
        lemma = morph.lemma
        reading = normalize_reading(morph.reading)

        key = (lemma, lemma, reading)
        value = morph_priorities.get(key)

        if value is not None:
            priorities.append(value)

    if priorities:
        return min(priorities)

    return DEFAULT_REVIEW_DUE
