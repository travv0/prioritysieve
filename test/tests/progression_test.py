from __future__ import annotations

from typing import Any

import pytest

from prioritysieve.entry_db import StoredEntry
from prioritysieve.progression.progression_window import ProgressionWindow

from test.fake_environment_module import (  # pylint:disable=unused-import
    FakeEnvironment,
    FakeEnvironmentParams,
    fake_environment_fixture,
)

SAMPLE_PRIORITY_FILES = ["Collection frequency"]
SAMPLE_PRIORITY_MAP = {
    "Collection frequency": {
        ("alpha", "-"): 1,
        ("beta", "-"): 2,
        ("gamma", "-"): 3,
    }
}
SAMPLE_ENTRIES = [
    StoredEntry(text="alpha", reading="-", reviewed=True),
    StoredEntry(text="beta", reading="-", reviewed=False),
]

default_fake_environment = FakeEnvironmentParams()


@pytest.mark.parametrize(
    "fake_environment_fixture, priority_mode, cumulative, min_priority, max_priority, bin_size, "
    "k_priority_range, k_unique_entries, k_total_reviewed, k_percent_missing, "
    "k_entry_texts, k_entry_readings, k_statuses",
    [
        (
            default_fake_environment,
            "Collection frequency",
            False,
            1,
            3,
            2,
            "1-3",
            3,
            1,
            "33.4 %",
            ["alpha", "beta", "gamma"],
            ["-", "-", "-"],
            ["reviewed", "pending", "missing"],
        ),
        (
            default_fake_environment,
            "Collection frequency",
            True,
            1,
            3,
            2,
            "1-3",
            3,
            1,
            "33.4 %",
            ["alpha", "beta", "gamma"],
            ["-", "-", "-"],
            ["reviewed", "pending", "missing"],
        ),
    ],
    indirect=["fake_environment_fixture"],
)
def test_progression(
    fake_environment_fixture: FakeEnvironment,  # pylint:disable=unused-argument
    priority_mode: str,
    cumulative: bool,
    min_priority: int,
    max_priority: int,
    bin_size: int,
    k_priority_range: str,
    k_unique_entries: int,
    k_total_reviewed: int,
    k_percent_missing: str,
    k_entry_texts: list[str],
    k_entry_readings: list[str],
    k_statuses: list[str],
    qtbot: Any,  # pylint:disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyEntryDB:
        def __enter__(self) -> DummyEntryDB:
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:  # noqa: D401
            return None

        def get_entries(self) -> list[StoredEntry]:
            return SAMPLE_ENTRIES

    def fake_available_priority_files() -> list[str]:
        return SAMPLE_PRIORITY_FILES.copy()

    def fake_load_priority_map(
        priority_files: list[str] | str,
    ) -> dict[tuple[str, str], int]:
        if isinstance(priority_files, str):
            key = priority_files
        else:
            key = priority_files[0] if priority_files else ""
        return SAMPLE_PRIORITY_MAP.get(key, {}).copy()

    monkeypatch.setattr(
        "prioritysieve.progression.progression_window.EntryDB",
        lambda: DummyEntryDB(),
    )
    monkeypatch.setattr(
        "prioritysieve.progression.progression_window.available_priority_files",
        fake_available_priority_files,
    )
    monkeypatch.setattr(
        "prioritysieve.progression.progression_window.load_priority_map",
        fake_load_priority_map,
    )

    pw = ProgressionWindow()
    pw.ui.priorityFileComboBox.setCurrentText(priority_mode)
    pw.ui.cumulativeRadioButton.setChecked(cumulative)
    pw.ui.minPrioritySpinBox.setValue(min_priority)
    pw.ui.maxPrioritySpinBox.setValue(max_priority)
    pw.ui.binSizeSpinBox.setValue(bin_size)

    pw._background_process_and_populate_tables()  # pylint:disable=protected-access

    last_row = pw.ui.numericalTableWidget.rowCount() - 1

    assert pw.ui.numericalTableWidget.item(last_row, 0).text() == k_priority_range
    assert int(pw.ui.numericalTableWidget.item(last_row, 1).text()) == k_unique_entries
    assert int(pw.ui.numericalTableWidget.item(0, 2).text()) == k_total_reviewed
    assert pw.ui.percentTableWidget.item(0, 4).text() == k_percent_missing

    observed_texts = [
        pw.ui.entryTableWidget.item(row, 1).text() for row in range(3)
    ]
    observed_readings = [
        pw.ui.entryTableWidget.item(row, 2).text() for row in range(3)
    ]
    observed_statuses = [
        pw.ui.entryTableWidget.item(row, 3).text() for row in range(3)
    ]

    assert observed_texts == k_entry_texts
    assert observed_readings == k_entry_readings
    assert observed_statuses == k_statuses
