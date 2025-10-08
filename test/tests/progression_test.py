from __future__ import annotations

from test.fake_environment_module import (  # pylint:disable=unused-import
    FakeEnvironment,
    FakeEnvironmentParams,
    fake_environment_fixture,
)
from typing import Any

import pytest
from aqt.qt import QTableWidgetItem  # pylint:disable=no-name-in-module

from prioritysieve.progression.progression_window import ProgressionWindow

################################################################
# Checks if progression is properly reported with a specified
# db/collection and the various evaluation/statistics options;
# various table entries are checked.
################################################################

case_big_japanese_collection_params = FakeEnvironmentParams(
    actual_col="big_japanese_collection",
    expected_col="big_japanese_collection",
    am_db="big_japanese_collection.db",
)

case_some_studied_japanese_params = FakeEnvironmentParams(
    actual_col="some_studied_japanese_collection",
    expected_col="some_studied_japanese_collection",
    am_db="some_studied_japanese.db",
)


@pytest.mark.parametrize(
    "fake_environment_fixture, priority_mode,"  # inputs
    "cumulative, min_priority, max_priority, bin_size,"  # inputs
    "k_priority_range, k_unique_entries, k_total_reviewed,"  # expected numeric values
    "k_percent_missing, k_entry_texts, k_entry_readings,"  # expected entry list values
    "k_statuses",  # expected entry statuses
    [
        (
            case_big_japanese_collection_params,  # fake_environment_fixture
            "Collection frequency",  # priority_mode
            False,  # cumulative
            1,  # min_priority
            50000,  # max_priority
            500,  # bin_size
            "11501-12000",  # k_priority_range
            357,  # k_unique_entries
            0,  # k_total_reviewed
            "100.0 %",  # k_percent_missing
            ["の", "は", "た"],  # k_entry_texts
            ["-", "-", "-"],  # k_entry_readings
            ["unknown", "unknown", "unknown"],  # k_statuses
        ),
        (
            case_big_japanese_collection_params,  # fake_environment_fixture
            "Collection frequency",  # priority_mode
            True,  # cumulative
            1001,  # min_priority
            1500,  # max_priority
            1600,  # bin_size
            "1001-1500",  # k_priority_range
            500,  # k_unique_entries
            0,  # k_total_reviewed
            "100.0 %",  # k_percent_missing
            ["難しい", "面白い", "頑張る"],  # k_entry_texts
            ["難しい", "面白い", "頑張れ"],  # k_entry_readings
            ["unknown", "unknown", "unknown"],  # k_statuses
        ),
        (
            case_some_studied_japanese_params,  # fake_environment_fixture
            "ja_core_news_sm_freq_inflection_min_occurrence.csv",  # priority_mode
            False,  # cumulative
            1,  # min_priority
            500,  # max_priority
            100,  # bin_size
            "401-500",  # k_priority_range
            100,  # k_unique_entries
            4,  # k_total_reviewed
            "0.0 %",  # k_percent_missing
            ["の", "に", "は"],  # k_entry_texts
            ["-", "-", "-"],  # k_entry_readings
            ["missing", "missing", "pending"],  # k_statuses
        ),
        (
            case_some_studied_japanese_params,  # fake_environment_fixture
            "ja_core_news_sm_freq_inflection_min_occurrence.csv",  # priority_mode
            True,  # cumulative
            1,  # min_priority
            10,  # max_priority
            100,  # bin_size
            "1-10",  # k_priority_range
            10,  # k_unique_entries
            0,  # k_total_reviewed
            "0.0 %",  # k_percent_missing
            ["だ", "に", "は"],  # k_entry_texts
            ["だ", "に", "は"],  # k_entry_readings
            ["missing", "missing", "pending"],  # k_statuses
        ),
    ],
    indirect=["fake_environment_fixture"],
)
def test_progression(  # pylint:disable=too-many-arguments, unused-argument, too-many-locals too-many-statements
    fake_environment_fixture: FakeEnvironment,
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
    qtbot: Any,
) -> None:

    # Set window and options
    pw = ProgressionWindow()
    pw.ui.morphPriorityCBox.setCurrentText(priority_mode)
    pw.ui.cumulativeRadioButton.setChecked(cumulative)
    pw.ui.minPrioritySpinBox.setValue(min_priority)
    pw.ui.maxPrioritySpinBox.setValue(max_priority)
    pw.ui.binSizeSpinBox.setValue(bin_size)

    # Calculate progress
    pw._background_process_and_populate_tables()

    # Compare to known output
    _item: QTableWidgetItem | None

    _row = pw.ui.numericalTableWidget.rowCount() - 1
    _column = 0
    _item = pw.ui.numericalTableWidget.item(_row, _column)
    assert _item is not None
    assert _item.text() == k_priority_range

    _row = pw.ui.numericalTableWidget.rowCount() - 1
    _column = 1
    _item = pw.ui.numericalTableWidget.item(_row, _column)
    assert _item is not None
    assert int(_item.text()) == k_unique_entries

    _row = 0
    _column = 2
    _item = pw.ui.numericalTableWidget.item(_row, _column)
    assert _item is not None
    assert int(_item.text()) == k_total_reviewed

    _row = 0
    _column = 4
    _item = pw.ui.percentTableWidget.item(_row, _column)
    assert _item is not None
    assert _item.text() == k_percent_missing

    _entry_texts: list[str] = []
    for _row in [0, 1, 2]:
        _column = 1
    _item = pw.ui.entryTableWidget.item(_row, _column)
        assert _item is not None
        _entry_texts.append(_item.text())
    assert _entry_texts == k_entry_texts

    _entry_readings: list[str] = []
    for _row in [0, 1, 2]:
        _column = 2
    _item = pw.ui.entryTableWidget.item(_row, _column)
        assert _item is not None
        _entry_readings.append(_item.text())
    assert _entry_readings == k_entry_readings

    _status_list: list[str] = []
    for _row in [0, 1, 2]:
        _column = 3
    _item = pw.ui.entryTableWidget.item(_row, _column)
        assert _item is not None
        _status_list.append(_item.text())
    assert _status_list == k_statuses
