from __future__ import annotations

from collections.abc import Callable
from functools import partial

import aqt
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (  # pylint:disable=no-name-in-module
    QAbstractItemView,
    QHeaderView,
    QMainWindow,
    Qt,
    QTableWidget,
    QTableWidgetItem,
)
from aqt.utils import tooltip

from .. import prioritysieve_globals
from ..entry_db import EntryDB
from ..priority_files import available_priority_files, load_priority_map
from ..exceptions import (
    CancelledOperationException,
    InvalidBinsException,
    PriorityFileMalformedException,
)
from ..extra_settings import extra_settings_keys
from ..extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from ..table_utils import QTableWidgetIntegerItem, QTableWidgetPercentItem
from ..ui.progression_window_ui import Ui_ProgressionWindow
from .progression_utils import (
    Bins,
    ProgressReport,
    get_priority_ordered_entry_statuses,
    get_progress_reports,
)


class ProgressionWindow(QMainWindow):  # pylint:disable=too-many-instance-attributes
    def __init__(
        self,
        parent: QMainWindow | None = None,
    ) -> None:
        super().__init__(parent)

        self.ui = Ui_ProgressionWindow()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self.am_extra_settings = PrioritySieveExtraSettings()
        self.am_extra_settings.beginGroup(
            extra_settings_keys.Dialogs.PROGRESSION_WINDOW
        )

        self._columns = {}
        # For all tables
        self._columns["priority"] = 0
        # For numerical and percentage tables
        self._columns["total_entries"] = 1
        self._columns["reviewed"] = 2
        self._columns["pending"] = 3
        self._columns["missing"] = 4
        # For entry lists
        self._columns["text"] = 1
        self._columns["reading"] = 2
        self._columns["status"] = 3
        self.num_numerical_percent_columns = 5
        self.num_entry_columns = 4

        self._setup_numerical_percent_table(self.ui.numericalTableWidget)
        self._setup_numerical_percent_table(self.ui.percentTableWidget)
        self._setup_entry_table(self.ui.entryTableWidget)
        self._setup_buttons()
        self._setup_spin_boxes()
        self._setup_priority_file_cbox()
        self._setup_geometry()

        self.am_extra_settings.endGroup()
        self.show()

    def _setup_numerical_percent_table(self, table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setColumnCount(self.num_numerical_percent_columns)

        table.setColumnWidth(self._columns["priority"], 130)
        table.setColumnWidth(self._columns["total_entries"], 120)
        table.setColumnWidth(self._columns["reviewed"], 120)
        table.setColumnWidth(self._columns["pending"], 120)
        table.setColumnWidth(self._columns["missing"], 110)

        table_horizontal_headers: QHeaderView | None = table.horizontalHeader()
        assert table_horizontal_headers is not None
        table_horizontal_headers.setSectionsMovable(True)

        # disables manual editing of the table
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _setup_entry_table(self, table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setColumnCount(self.num_entry_columns)

        table.setColumnWidth(self._columns["priority"], 90)
        table.setColumnWidth(self._columns["text"], 120)
        table.setColumnWidth(self._columns["reading"], 120)
        table.setColumnWidth(self._columns["status"], 90)

        table_horizontal_headers: QHeaderView | None = table.horizontalHeader()
        assert table_horizontal_headers is not None
        table_horizontal_headers.setSectionsMovable(True)

        # disables manual editing of the table
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _setup_buttons(self) -> None:
        self.ui.viewProgressPushButton.clicked.connect(
            self._on_view_progress_button_clicked
        )

        stored_normal_bin_type: bool = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.BIN_TYPE_NORMAL,
            defaultValue=True,
            type=bool,
        )
        stored_cumulative_bin_type: bool = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.BIN_TYPE_CUMULATIVE,
            defaultValue=False,
            type=bool,
        )

        self.ui.normalRadioButton.setChecked(stored_normal_bin_type)
        self.ui.cumulativeRadioButton.setChecked(stored_cumulative_bin_type)

    def _setup_spin_boxes(self) -> None:
        stored_range_start: int = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.PRIORITY_RANGE_START,
            defaultValue=self.ui.minPrioritySpinBox.minimum(),
            type=int,
        )
        stored_range_end: int = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.PRIORITY_RANGE_END,
            defaultValue=self.ui.maxPrioritySpinBox.value(),
            type=int,
        )
        stored_bin_size: int = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.BIN_SIZE,
            defaultValue=self.ui.binSizeSpinBox.value(),
            type=int,
        )

        self.ui.minPrioritySpinBox.setValue(stored_range_start)
        self.ui.maxPrioritySpinBox.setValue(stored_range_end)
        self.ui.binSizeSpinBox.setValue(stored_bin_size)

    def _setup_priority_file_cbox(self) -> None:
        priority_files: list[str] = [prioritysieve_globals.NONE_OPTION]
        priority_files += available_priority_files()
        self.ui.priorityFileComboBox.addItems(priority_files)

        stored_priority_file: str = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.PRIORITY_FILE, type=str
        )

        for index, file in enumerate(priority_files):
            if file == stored_priority_file:
                self.ui.priorityFileComboBox.setCurrentIndex(index)
                break

    def _setup_geometry(self) -> None:
        stored_geometry = self.am_extra_settings.value(
            extra_settings_keys.ProgressionWindowKeys.WINDOW_GEOMETRY
        )
        if stored_geometry is not None:
            self.restoreGeometry(stored_geometry)

    def _on_view_progress_button_clicked(self) -> None:
        # calculate progress stats and populate table in the background,
        # since it could take a long time to complete
        assert mw is not None

        mw.progress.start(label="Processing progress report")
        operation = QueryOp(
            parent=self,
            op=lambda _: self._background_process_and_populate_tables(),
            success=lambda _: self._on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _get_selected_bins(self) -> Bins:
        return Bins(
            min_index=self.ui.minPrioritySpinBox.value(),
            max_index=self.ui.maxPrioritySpinBox.value(),
            bin_size=self.ui.binSizeSpinBox.value(),
            is_cumulative=self.ui.cumulativeRadioButton.isChecked(),
        )

    def _background_process_and_populate_tables(self) -> None:
        assert mw is not None

        bins = self._get_selected_bins()
        selected_file = self.ui.priorityFileComboBox.currentText()

        if selected_file == prioritysieve_globals.NONE_OPTION:
            priority_map: dict[tuple[str, str], int] = {}
        else:
            priority_map = load_priority_map([selected_file])

        with EntryDB() as entry_db:
            stored_entries = entry_db.get_entries()

        mw.taskman.run_on_main(
            partial(
                mw.progress.update,
                label="Calculating binned statistics",
            )
        )

        entry_iterable = (stored_entry.to_entry() for stored_entry in stored_entries)
        reports = get_progress_reports(entry_iterable, bins, priority_map)

        if mw.progress.want_cancel():
            raise CancelledOperationException

        entry_iterable = (stored_entry.to_entry() for stored_entry in stored_entries)

        mw.taskman.run_on_main(
            partial(
                mw.progress.update,
                label="Processing entry statuses",
            )
        )
        entry_statuses = get_priority_ordered_entry_statuses(
            entry_iterable, bins, priority_map
        )

        if mw.progress.want_cancel():
            raise CancelledOperationException

        mw.taskman.run_on_main(
            partial(
                mw.progress.update,
                label="Populating tables",
            )
        )
        self._populate_tables(reports, entry_statuses)

    def _populate_tables(
        self,
        reports: list[ProgressReport],
        entry_statuses: list[tuple[int, str, str, str]],
    ) -> None:
        assert mw is not None
        assert isinstance(self.ui, Ui_ProgressionWindow)

        self.ui.numericalTableWidget.clearContents()
        self.ui.percentTableWidget.clearContents()
        self.ui.entryTableWidget.clearContents()

        self.ui.numericalTableWidget.setRowCount(len(reports))
        self.ui.percentTableWidget.setRowCount(len(reports))
        self.ui.entryTableWidget.setRowCount(len(entry_statuses))

        error_indexes: tuple[int, int] | None = None

        for row, report in enumerate(reports):
            if report.get_total_entries() == 0:
                self.ui.numericalTableWidget.setRowCount(row)
                self.ui.percentTableWidget.setRowCount(row)
                error_indexes = (report.min_priority, report.max_priority)
                break
            self._populate_numerical_table(report, row)
            self._populate_percent_table(report, row)

        for row, entry_status in enumerate(entry_statuses):
            self._populate_entry_table(entry_status, row)

        if error_indexes is not None:
            mw.taskman.run_on_main(
                lambda: tooltip(
                    f"No entries in priority range {error_indexes[0]}-{error_indexes[1]}",
                    parent=self,
                )
            )

    def _populate_numerical_table(self, report: ProgressReport, row: int) -> None:
        priority_item = QTableWidgetItem(
            f"{report.min_priority}-{report.max_priority}"
        )
        total_entries_item = QTableWidgetIntegerItem(report.get_total_entries())
        reviewed_item = QTableWidgetIntegerItem(report.get_total_reviewed())
        pending_item = QTableWidgetIntegerItem(report.get_total_pending())
        missing_item = QTableWidgetIntegerItem(report.get_total_missing())

        priority_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        total_entries_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        reviewed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        pending_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        missing_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ui.numericalTableWidget.setItem(
            row, self._columns["priority"], priority_item
        )
        self.ui.numericalTableWidget.setItem(
            row, self._columns["total_entries"], total_entries_item
        )
        self.ui.numericalTableWidget.setItem(
            row, self._columns["reviewed"], reviewed_item
        )
        self.ui.numericalTableWidget.setItem(
            row, self._columns["pending"], pending_item
        )
        self.ui.numericalTableWidget.setItem(
            row, self._columns["missing"], missing_item
        )

    def _populate_percent_table(self, report: ProgressReport, row: int) -> None:
        reviewed_percent = round(
            report.get_total_reviewed() / report.get_total_entries() * 100, 1
        )
        pending_percent = round(
            report.get_total_pending() / report.get_total_entries() * 100, 1
        )
        missing_percent = round(
            100 - reviewed_percent - pending_percent, 1
        )

        priority_item = QTableWidgetItem(
            f"{report.min_priority}-{report.max_priority}"
        )
        total_entries_item = QTableWidgetIntegerItem(report.get_total_entries())
        reviewed_item = QTableWidgetPercentItem(reviewed_percent)
        pending_item = QTableWidgetPercentItem(pending_percent)
        missing_item = QTableWidgetPercentItem(missing_percent)

        priority_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        total_entries_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        reviewed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        pending_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        missing_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ui.percentTableWidget.setItem(
            row, self._columns["priority"], priority_item
        )
        self.ui.percentTableWidget.setItem(
            row, self._columns["total_entries"], total_entries_item
        )
        self.ui.percentTableWidget.setItem(
            row, self._columns["reviewed"], reviewed_item
        )
        self.ui.percentTableWidget.setItem(
            row, self._columns["pending"], pending_item
        )
        self.ui.percentTableWidget.setItem(row, self._columns["missing"], missing_item)

    def _populate_entry_table(
        self, entry_status: tuple[int, str, str, str], row: int
    ) -> None:

        priority_item = QTableWidgetIntegerItem(entry_status[0])
        text_item = QTableWidgetItem(entry_status[1])
        reading_item = QTableWidgetItem(entry_status[2])
        status_item = QTableWidgetItem(entry_status[3])

        priority_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        text_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ui.entryTableWidget.setItem(
            row, self._columns["priority"], priority_item
        )
        self.ui.entryTableWidget.setItem(row, self._columns["text"], text_item)
        self.ui.entryTableWidget.setItem(
            row, self._columns["reading"], reading_item
        )
        self.ui.entryTableWidget.setItem(row, self._columns["status"], status_item)

    def closeWithCallback(  # pylint:disable=invalid-name
        self, callback: Callable[[], None]
    ) -> None:
        # This is used by the Anki dialog manager
        self.am_extra_settings.save_progression_window_settings(
            ui=self.ui, geometry=self.saveGeometry()
        )
        self.close()
        dialog_name = prioritysieve_globals.PROGRESSION_DIALOG_NAME
        aqt.dialogs.markClosed(dialog_name)
        callback()

    def reopen(self) -> None:
        # This is used by the Anki dialog manager
        self.show()

    def _on_success(self) -> None:
        # This function runs on the main thread.
        assert mw is not None
        assert mw.progress is not None
        mw.progress.finish()
        tooltip("Progress report finished", parent=self)

    def _on_failure(
        self,
        error: (
            Exception
            | CancelledOperationException
            | PriorityFileMalformedException
            | InvalidBinsException
        ),
    ) -> None:
        # This function runs on the main thread.
        assert mw is not None
        assert mw.progress is not None

        mw.progress.finish()

        if isinstance(error, CancelledOperationException):
            tooltip("Cancelled progress report calculation", parent=self)
        elif isinstance(error, PriorityFileMalformedException):
            tooltip(error.reason, parent=self)
        elif isinstance(error, InvalidBinsException):
            tooltip("Invalid priority range", parent=self)

        else:
            raise error
