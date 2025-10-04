from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .morph_priority_utils import get_morph_priority
from .reading_utils import normalize_reading

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers only
    from .morpheme import Morpheme
    from .prioritysieve_db import PrioritySieveDB


def _build_existing_priority_keys(
    card_morph_map_cache: dict[int, list[Morpheme]],
) -> tuple[set[tuple[str, str, str]], set[str]]:
    """Return the exact morph keys and lemma-only lookup for existing cards."""

    exact_keys: set[tuple[str, str, str]] = set()
    lemma_only: set[str] = set()

    for morphs in card_morph_map_cache.values():
        for morph in morphs:
            reading = normalize_reading(morph.reading)
            exact_keys.add((morph.lemma, morph.lemma, reading))
            lemma_only.add(morph.lemma)

    return exact_keys, lemma_only


def find_missing_priority_entries(
    am_db: PrioritySieveDB,
    morph_priority_selection: Iterable[str] | str,
) -> list[tuple[str, str, int]]:
    """Return priority entries without matching cards, ordered by priority."""

    priority_map = get_morph_priority(am_db, morph_priority_selection)
    if not priority_map:
        return []

    card_morph_map_cache = am_db.get_card_morph_map_cache()
    exact_keys, lemma_only = _build_existing_priority_keys(card_morph_map_cache)

    missing_entries: list[tuple[str, str, int]] = []

    for key, priority in priority_map.items():
        if key in exact_keys:
            continue

        lemma, _, reading = key
        if not reading and lemma in lemma_only:
            continue

        missing_entries.append((lemma, reading, priority))

    missing_entries.sort(key=lambda entry: (entry[2], entry[0], entry[1]))
    return missing_entries
