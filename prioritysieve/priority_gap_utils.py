from __future__ import annotations

from collections.abc import Iterable

from .entry import Entry
from .reading_utils import normalize_reading


def _load_priority_map(priority_files: Iterable[str] | str) -> dict[tuple[str, str], int]:
    from .priority_files import load_priority_map as loader

    return loader(priority_files)


load_priority_map = _load_priority_map


def find_missing_priority_entries(
    entries: Iterable[Entry],
    priority_files: Iterable[str] | str,
) -> list[tuple[str, str, int]]:
    """Return priority list entries that have no matching cards."""

    if isinstance(priority_files, str):
        priority_candidates = [priority_files]
    else:
        priority_candidates = list(priority_files)

    priority_map = load_priority_map(priority_candidates)
    if not priority_map:
        return []

    existing_keys = {
        (entry.text, normalize_reading(entry.reading))
        for entry in entries
    }
    existing_texts = {text for text, _ in existing_keys}

    details: dict[str, dict[str, dict[str, int] | int | None]] = {}

    for (text, reading), priority in sorted(
        priority_map.items(),
        key=lambda item: (item[1], item[0][0], item[0][1]),
    ):
        normalized_reading = normalize_reading(reading)

        if normalized_reading:
            if (text, normalized_reading) in existing_keys:
                continue
        else:
            if text in existing_texts:
                continue

        info = details.setdefault(
            text,
            {"readings": {}, "fallback": None},
        )

        readings = info["readings"]
        assert isinstance(readings, dict)

        if normalized_reading:
            existing_priority = readings.get(normalized_reading)
            if existing_priority is None or priority < existing_priority:
                readings[normalized_reading] = priority
        else:
            fallback_priority = info["fallback"]
            if not isinstance(fallback_priority, int) or priority < fallback_priority:
                info["fallback"] = priority

    missing_entries: list[tuple[str, str, int]] = []

    for text, info in details.items():
        readings = info["readings"]
        fallback_priority = info["fallback"]

        if isinstance(readings, dict) and readings:
            reading_priorities = list(readings.values())
            best_reading_priority = min(reading_priorities)

            if isinstance(fallback_priority, int) and fallback_priority <= best_reading_priority:
                missing_entries.append((text, "", fallback_priority))
                continue

            for reading, priority in readings.items():
                missing_entries.append((text, reading, priority))
            continue

        if isinstance(fallback_priority, int):
            missing_entries.append((text, "", fallback_priority))

    missing_entries.sort(key=lambda entry: (entry[2], entry[0], entry[1]))
    return missing_entries
