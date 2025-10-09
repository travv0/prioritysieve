from __future__ import annotations

from pathlib import Path

from aqt import mw
from aqt.qt import Qt, QTableWidgetItem  # pylint:disable=no-name-in-module

from ..exceptions import EmptyFileSelectionException
from ..table_utils import QTableWidgetIntegerItem, QTableWidgetPercentItem
from ..ui.generators_window_ui import Ui_GeneratorsWindow
from . import generators_utils
from .generators_utils import CountColumn, PercentColumn, FileEntryStats


def background_generate_report(
    ui: Ui_GeneratorsWindow,
    input_dir_root: Path,
    input_files: list[Path],
) -> None:
    assert mw is not None

    if not input_files:
        raise EmptyFileSelectionException

    mw.progress.start(label="Generating readability report")

    entries_by_file = generators_utils.read_entries_for_files(input_files)
    reviewed_lookup = generators_utils.build_reviewed_lookup()

    stats_by_file: dict[Path, FileEntryStats] = {}
    for path in input_files:
        stats_by_file[path] = generators_utils.compute_file_stats(
            entries_by_file[path], reviewed_lookup
        )

    total_stats = generators_utils.combine_totals(entries_by_file, reviewed_lookup)

    mw.taskman.run_on_main(lambda: _populate_tables(ui, input_dir_root, stats_by_file, total_stats))


def _populate_tables(
    ui: Ui_GeneratorsWindow,
    input_dir_root: Path,
    stats_by_file: dict[Path, FileEntryStats],
    total_stats: FileEntryStats,
) -> None:
    ui.numericalTableWidget.setSortingEnabled(False)
    ui.percentTableWidget.setSortingEnabled(False)

    row_count = len(stats_by_file) + 1
    ui.numericalTableWidget.setRowCount(row_count)
    ui.percentTableWidget.setRowCount(row_count)

    for row, (path, stats) in enumerate(stats_by_file.items()):
        relative = str(path.relative_to(input_dir_root))
        _populate_counts_row(ui, row, relative, stats)
        _populate_percent_row(ui, row, relative, stats)

    _populate_counts_row(ui, len(stats_by_file), "Total", total_stats)
    _populate_percent_row(ui, len(stats_by_file), "Total", total_stats)

    ui.numericalTableWidget.setSortingEnabled(True)
    ui.percentTableWidget.setSortingEnabled(True)


def _populate_counts_row(
    ui: Ui_GeneratorsWindow,
    row: int,
    filename: str,
    stats: FileEntryStats,
) -> None:
    filename_item = QTableWidgetItem(filename)
    filename_item.setFlags(filename_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
    ui.numericalTableWidget.setItem(row, CountColumn.FILE_NAME.value, filename_item)

    ui.numericalTableWidget.setItem(
        row, CountColumn.UNIQUE_ENTRIES.value, QTableWidgetIntegerItem(stats.unique_entries)
    )
    ui.numericalTableWidget.setItem(
        row, CountColumn.UNIQUE_REVIEWED.value, QTableWidgetIntegerItem(stats.unique_reviewed)
    )
    ui.numericalTableWidget.setItem(
        row, CountColumn.UNIQUE_UNREVIEWED.value, QTableWidgetIntegerItem(stats.unique_unreviewed)
    )
    ui.numericalTableWidget.setItem(
        row, CountColumn.TOTAL_OCCURRENCES.value, QTableWidgetIntegerItem(stats.total_occurrences)
    )
    ui.numericalTableWidget.setItem(
        row,
        CountColumn.REVIEWED_OCCURRENCES.value,
        QTableWidgetIntegerItem(stats.reviewed_occurrences),
    )
    ui.numericalTableWidget.setItem(
        row,
        CountColumn.UNREVIEWED_OCCURRENCES.value,
        QTableWidgetIntegerItem(stats.unreviewed_occurrences),
    )


def _populate_percent_row(
    ui: Ui_GeneratorsWindow,
    row: int,
    filename: str,
    stats: FileEntryStats,
) -> None:
    filename_item = QTableWidgetItem(filename)
    filename_item.setFlags(filename_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
    ui.percentTableWidget.setItem(row, PercentColumn.FILE_NAME.value, filename_item)

    unique_total = max(stats.unique_entries, 1)
    occurrences_total = max(stats.total_occurrences, 1)

    reviewed_entries_percent = stats.unique_reviewed / unique_total * 100
    unreviewed_entries_percent = stats.unique_unreviewed / unique_total * 100
    reviewed_occurrences_percent = stats.reviewed_occurrences / occurrences_total * 100
    unreviewed_occurrences_percent = stats.unreviewed_occurrences / occurrences_total * 100

    ui.percentTableWidget.setItem(
        row,
        PercentColumn.REVIEWED_ENTRIES.value,
        QTableWidgetPercentItem(reviewed_entries_percent),
    )
    ui.percentTableWidget.setItem(
        row,
        PercentColumn.UNREVIEWED_ENTRIES.value,
        QTableWidgetPercentItem(unreviewed_entries_percent),
    )
    ui.percentTableWidget.setItem(
        row,
        PercentColumn.REVIEWED_OCCURRENCES.value,
        QTableWidgetPercentItem(reviewed_occurrences_percent),
    )
    ui.percentTableWidget.setItem(
        row,
        PercentColumn.UNREVIEWED_OCCURRENCES.value,
        QTableWidgetPercentItem(unreviewed_occurrences_percent),
    )
