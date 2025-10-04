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

    lemma_details: dict[str, dict[str, dict[str, int] | int | None]] = {}

    for key, priority in priority_map.items():
        if key in exact_keys:
            continue

        lemma, _, reading = key
        if not reading and lemma in lemma_only:
            continue

        info = lemma_details.setdefault(
            lemma,
            {"readings": {}, "fallback": None},
        )

        readings = info["readings"]
        assert isinstance(readings, dict)

        display_reading = reading if reading and reading != lemma else ""

        if display_reading:
            existing_priority = readings.get(display_reading)
            if existing_priority is None or priority < existing_priority:
                readings[display_reading] = priority
        else:
            fallback_priority = info["fallback"]
            if not isinstance(fallback_priority, int) or priority < fallback_priority:
                info["fallback"] = priority

    missing_entries: list[tuple[str, str, int]] = []

    for lemma, info in lemma_details.items():
        readings = info["readings"]
        fallback_priority = info["fallback"]

        if isinstance(readings, dict):
            for reading, priority in readings.items():
                missing_entries.append((lemma, reading, priority))

        if isinstance(fallback_priority, int) and (
            not isinstance(readings, dict) or not readings
        ):
            missing_entries.append((lemma, "", fallback_priority))

    missing_entries.sort(key=lambda entry: (entry[2], entry[0], entry[1]))

    lemmas_with_readings = {lemma for lemma, reading, _ in missing_entries if reading}

    deduped: list[tuple[str, str, int]] = []
    for lemma, reading, priority in missing_entries:
        if reading:
            deduped.append((lemma, reading, priority))
            continue

        if lemma not in lemmas_with_readings:
            deduped.append((lemma, reading, priority))

    return deduped
