from __future__ import annotations

from typing import Iterable

from ..entry import Entry
from ..exceptions import InvalidBinsException


class Bins:
    """Bins, used for entry priority."""

    def __init__(
        self, min_index: int, max_index: int, bin_size: int, is_cumulative: bool
    ) -> None:
        self.min_index = min_index
        self.max_index = max_index
        self.bin_size = bin_size
        self.is_cumulative = is_cumulative

        if min_index >= max_index:
            raise InvalidBinsException(min_index, max_index)

        self.indexes = []
        working_min_index = min_index
        while working_min_index + bin_size - 1 < max_index:
            if is_cumulative:
                self.indexes.append((min_index, working_min_index + bin_size - 1))
            else:
                self.indexes.append(
                    (working_min_index, working_min_index + bin_size - 1)
                )

            working_min_index += bin_size

        if is_cumulative:
            self.indexes.append((min_index, max_index))
        else:
            self.indexes.append((working_min_index, max_index))


class ProgressReport:
    """Stores lists of reviewed, pending, and missing entries."""

    def __init__(self, min_priority: int, max_priority: int) -> None:

        self.min_priority = min_priority
        self.max_priority = max_priority

        # Entries are represented as (text, reading) keys
        self.reviewed_entries: set[tuple[str, str]] = set()
        self.pending_entries: set[tuple[str, str]] = set()
        self.missing_entries: set[tuple[str, str]] = set()

    def get_total_reviewed(self) -> int:
        return len(self.reviewed_entries)

    def get_total_pending(self) -> int:
        return len(self.pending_entries)

    def get_total_missing(self) -> int:
        return len(self.missing_entries)

    def get_total_morphs(self) -> int:
        return (
            self.get_total_reviewed()
            + self.get_total_pending()
            + self.get_total_missing()
        )

    def get_total_entries(self) -> int:
        """Return the total count of tracked entries (alias for get_total_morphs)."""
        return self.get_total_morphs()


def _update_progress_report(
    progress_report: ProgressReport,
    key: tuple[str, str],
    status: str,
) -> None:
    """Adds entry and status information to a progress report."""
    assert status in ["reviewed", "pending", "missing"]
    if status == "reviewed":
        progress_report.reviewed_entries.add(key)
    elif status == "pending":
        progress_report.pending_entries.add(key)
    else:
        progress_report.missing_entries.add(key)


def get_progress_reports(
    entries: Iterable[Entry],
    bins: Bins,
    priority_map: dict[tuple[str, str], int],
) -> list[ProgressReport]:
    reports = []

    entry_lookup = {(entry.text, entry.reading): entry for entry in entries}

    for min_priority, max_priority in bins.indexes:
        report = ProgressReport(min_priority, max_priority)
        priority_subset = _get_priority_subset(
            priority_map, min_priority, max_priority
        )

        for key in priority_subset:
            entry = entry_lookup.get(key)
            if entry is None:
                status = "missing"
            elif entry.reviewed:
                status = "reviewed"
            else:
                status = "pending"
            _update_progress_report(report, key, status)

        reports.append(report)

    return reports


def get_priority_ordered_entry_statuses(
    entries: Iterable[Entry],
    bins: Bins,
    priority_map: dict[tuple[str, str], int],
) -> list[tuple[int, str, str, str]]:
    """Return (priority, text, reading, status) tuples ordered by increasing priority."""

    priority_subset = _get_priority_subset(priority_map, bins.min_index, bins.max_index)

    sorted_priorities = dict(
        sorted(
            priority_subset.items(),
            key=lambda item: item[1],
        )
    )

    entry_lookup = {(entry.text, entry.reading): entry for entry in entries}
    statuses: list[tuple[int, str, str, str]] = []

    for key, priority in sorted_priorities.items():
        entry = entry_lookup.get(key)
        if entry is None:
            status = "missing"
        elif entry.reviewed:
            status = "reviewed"
        else:
            status = "pending"
        text, reading = key
        statuses.append((priority, text, reading, status))

    return statuses


def _get_priority_subset(
    priority_map: dict[tuple[str, str], int],
    min_priority: int,
    max_priority: int,
) -> dict[tuple[str, str], int]:
    """Returns entry priorities within a priority range."""

    def is_in_range(item: tuple[tuple[str, str], int]) -> bool:
        _, priority = item
        return min_priority <= priority <= max_priority

    return dict(filter(is_in_range, priority_map.items()))
