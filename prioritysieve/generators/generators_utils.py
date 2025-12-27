from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from aqt import mw  # pylint:disable=unused-import
from ..entry_db import EntryDB
from ..exceptions import UnicodeException
from ..priority_files import ENTRY_HEADERS, READING_HEADERS
from ..reading_utils import normalize_reading

OCCURRENCE_HEADERS = ("Occurrences", "Occurrence", "Count", "Frequency")


class CountColumn(Enum):
    FILE_NAME = 0
    UNIQUE_ENTRIES = 1
    UNIQUE_REVIEWED = 2
    UNIQUE_UNREVIEWED = 3
    TOTAL_OCCURRENCES = 4
    REVIEWED_OCCURRENCES = 5
    UNREVIEWED_OCCURRENCES = 6
    NUMBER_OF_COLUMNS = 7


class PercentColumn(Enum):
    FILE_NAME = 0
    REVIEWED_ENTRIES = 1
    UNREVIEWED_ENTRIES = 2
    REVIEWED_OCCURRENCES = 3
    UNREVIEWED_OCCURRENCES = 4
    NUMBER_OF_COLUMNS = 5


@dataclass
class EntryAggregate:
    text: str
    reading: str
    occurrences: int

    def key(self) -> tuple[str, str]:
        return (self.text, self.reading)


@dataclass
class FileEntryStats:
    unique_entries: int = 0
    unique_reviewed: int = 0
    unique_unreviewed: int = 0
    total_occurrences: int = 0
    reviewed_occurrences: int = 0
    unreviewed_occurrences: int = 0

    def __iadd__(self, other: FileEntryStats) -> FileEntryStats:
        self.unique_entries += other.unique_entries
        self.unique_reviewed += other.unique_reviewed
        self.unique_unreviewed += other.unique_unreviewed
        self.total_occurrences += other.total_occurrences
        self.reviewed_occurrences += other.reviewed_occurrences
        self.unreviewed_occurrences += other.unreviewed_occurrences
        return self


def read_entry_occurrences(path: Path) -> dict[tuple[str, str], EntryAggregate]:
    try:
        with path.open(encoding="utf-8") as handle:
            reader = csv.reader(handle)
            headers = next(reader, [])
            entry_index = _find_header(headers, ENTRY_HEADERS)
            if entry_index is None:
                raise ValueError(f"{path} is missing an entry column")
            reading_index = _find_header(headers, READING_HEADERS)
            occurrence_index = _find_header(headers, OCCURRENCE_HEADERS)

            aggregates: dict[tuple[str, str], EntryAggregate] = {}

            for row in reader:
                if entry_index >= len(row):
                    continue
                text = row[entry_index].strip()
                if not text:
                    continue

                reading = ""
                if reading_index is not None and reading_index < len(row):
                    reading = normalize_reading(row[reading_index].strip())

                occurrences = 1
                if occurrence_index is not None and occurrence_index < len(row):
                    occurrences_str = row[occurrence_index].strip()
                    try:
                        occurrences = int(occurrences_str)
                    except ValueError:
                        occurrences = 1
                if occurrences <= 0:
                    occurrences = 1

                key = (text, reading)
                aggregate = aggregates.get(key)
                if aggregate is None:
                    aggregates[key] = EntryAggregate(
                        text=text,
                        reading=reading,
                        occurrences=occurrences,
                    )
                else:
                    aggregate.occurrences += occurrences
                    if not aggregate.reading and reading:
                        aggregate.reading = reading

            return aggregates
    except UnicodeDecodeError as exc:
        raise UnicodeException(path) from exc


def read_entries_for_files(
    input_files: Iterable[Path],
) -> dict[Path, dict[tuple[str, str], EntryAggregate]]:
    return {path: read_entry_occurrences(path) for path in input_files}


def build_reviewed_lookup() -> dict[tuple[str, str], bool]:
    """Build a lookup mapping (text, reading) to whether it's reviewed.

    Since entries are now language-specific, we aggregate across languages:
    if an entry is reviewed in ANY language, we consider it reviewed.
    """
    with EntryDB() as entry_db:
        stored = entry_db.get_entries()
    # Aggregate reviewed status across languages - if reviewed in any, mark as reviewed
    lookup: dict[tuple[str, str], bool] = {}
    for entry in stored:
        key = (entry.text, entry.reading)
        if entry.reviewed:
            lookup[key] = True
        elif key not in lookup:
            lookup[key] = False
    return lookup


def compute_file_stats(
    file_entries: dict[tuple[str, str], EntryAggregate],
    reviewed_lookup: dict[tuple[str, str], bool],
) -> FileEntryStats:
    stats = FileEntryStats()
    for aggregate in file_entries.values():
        stats.unique_entries += 1
        stats.total_occurrences += aggregate.occurrences

        reviewed = reviewed_lookup.get(aggregate.key(), False)
        if reviewed:
            stats.unique_reviewed += 1
            stats.reviewed_occurrences += aggregate.occurrences
        else:
            stats.unique_unreviewed += 1
            stats.unreviewed_occurrences += aggregate.occurrences

    return stats


def combine_totals(
    entries_by_file: dict[Path, dict[tuple[str, str], EntryAggregate]],
    reviewed_lookup: dict[tuple[str, str], bool],
) -> FileEntryStats:
    total = FileEntryStats()
    for file_entries in entries_by_file.values():
        total += compute_file_stats(file_entries, reviewed_lookup)
    return total


def build_global_aggregates(
    entries_by_file: dict[Path, dict[tuple[str, str], EntryAggregate]]
) -> dict[tuple[str, str], EntryAggregate]:
    combined: dict[tuple[str, str], EntryAggregate] = {}
    for file_entries in entries_by_file.values():
        for key, aggregate in file_entries.items():
            existing = combined.get(key)
            if existing is None:
                combined[key] = EntryAggregate(
                    text=aggregate.text,
                    reading=aggregate.reading,
                    occurrences=aggregate.occurrences,
                )
            else:
                existing.occurrences += aggregate.occurrences
                if not existing.reading and aggregate.reading:
                    existing.reading = aggregate.reading
    return combined


def sort_aggregates_desc(
    aggregates: dict[tuple[str, str], EntryAggregate]
) -> list[EntryAggregate]:
    return sorted(aggregates.values(), key=lambda agg: agg.occurrences, reverse=True)


def comprehension_cutoff_index(
    aggregates: list[EntryAggregate],
    target_percent: int,
) -> int:
    if target_percent >= 100:
        return len(aggregates)
    if target_percent <= 0:
        return 0

    total = sum(aggregate.occurrences for aggregate in aggregates)
    threshold = total * (target_percent / 100)

    running_total = 0
    for index, aggregate in enumerate(aggregates):
        running_total += aggregate.occurrences
        if running_total >= threshold:
            return index + 1
    return len(aggregates)


def min_occurrence_cutoff_index(
    aggregates: list[EntryAggregate],
    minimum: int,
) -> int:
    if minimum <= 1:
        return len(aggregates)
    for index, aggregate in enumerate(aggregates):
        if aggregate.occurrences < minimum:
            return index
    return len(aggregates)


def _find_header(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    lower = {header.strip().lower(): position for position, header in enumerate(headers)}
    for candidate in candidates:
        location = lower.get(candidate.lower())
        if location is not None:
            return location
    return None
