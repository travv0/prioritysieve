from __future__ import annotations

from pathlib import Path
from typing import Callable

import os

import aqt
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QFileDialog, QMainWindow, QDialog, QtWidgets  # pylint:disable=no-name-in-module
from aqt.utils import tooltip

from .. import message_box_utils, prioritysieve_globals as am_globals
from ..exceptions import (
    CancelledOperationException,
    EmptyFileSelectionException,
    UnicodeException,
)
from ..extra_settings import extra_settings_keys
from ..extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from ..ui.generators_window_ui import Ui_GeneratorsWindow
from . import (
    priority_file_generator,
    readability_report_generator,
    study_plan_generator,
)
from .generators_output_dialog import GeneratorOutputDialog, OutputOptions


class GeneratorWindow(QMainWindow):
    def __init__(self, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)

        self.ui = Ui_GeneratorsWindow()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self.am_extra_settings = PrioritySieveExtraSettings()
        self.am_extra_settings.beginGroup(extra_settings_keys.Dialogs.GENERATORS_WINDOW)

        stored_geometry = self.am_extra_settings.value(
            extra_settings_keys.GeneratorsWindowKeys.WINDOW_GEOMETRY
        )
        if stored_geometry is not None:
            self.restoreGeometry(stored_geometry)

        stored_input_dir: str = self.am_extra_settings.value(
            extra_settings_keys.GeneratorsWindowKeys.INPUT_DIR, type=str
        )
        if stored_input_dir is not None:
            self.ui.inputDirLineEdit.setText(stored_input_dir)

        self.am_extra_settings.endGroup()

        self._input_dir_root: Path | None = None
        self._input_files: list[Path] = []

        self._connect_signals()
        self._initialise_button_state()

        self.show()

    def _connect_signals(self) -> None:
        self.ui.selectFolderPushButton.clicked.connect(self._on_select_folder_clicked)
        self.ui.loadFilesPushButton.clicked.connect(self._on_load_files_button_clicked)
        self.ui.viewReportPushButton.clicked.connect(self._generate_readability_report)
        self.ui.generatePriorityFilePushButton.clicked.connect(
            self._generate_priority_file
        )
        self.ui.generateStudyPlanPushButton.clicked.connect(self._generate_study_plan)

    def _initialise_button_state(self) -> None:
        self.ui.viewReportPushButton.setDisabled(True)
        self.ui.generatePriorityFilePushButton.setDisabled(True)
        self.ui.generateStudyPlanPushButton.setDisabled(True)

    def _on_select_folder_clicked(self) -> None:
        input_dir: str = QFileDialog.getExistingDirectory(
            parent=self,
            caption="Directory with files to analyze",
            directory=os.path.expanduser("~"),
        )
        if input_dir:
            self.ui.inputDirLineEdit.setText(input_dir)
            self.ui.loadFilesPushButton.setEnabled(True)

    def _on_load_files_button_clicked(self) -> None:
        assert mw is not None

        self._input_files.clear()
        self._input_dir_root = None
        self._reset_tables()
        self._initialise_button_state()

        mw.progress.start(label="Gathering CSV files")
        operation = QueryOp(
            parent=self,
            op=lambda _: self._background_gather_files(),
            success=lambda _: self._on_successfully_loaded_files(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _background_gather_files(self) -> None:
        assert mw is not None

        input_dir = self.ui.inputDirLineEdit.text().strip()
        if not input_dir:
            raise NotADirectoryError

        root = Path(input_dir)
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError

        discovered: list[Path] = []
        for file_path in root.rglob("*.csv"):
            if mw.progress.want_cancel():
                raise CancelledOperationException
            if file_path.is_file():
                discovered.append(file_path)

        discovered.sort()
        self._input_files = discovered
        self._input_dir_root = root

    def _on_successfully_loaded_files(self) -> None:
        assert mw is not None
        mw.progress.finish()

        if not self._input_files:
            tooltip("No CSV files were found", parent=self)
            self.ui.loadFilesPushButton.setEnabled(True)
            return

        self._populate_file_rows()
        self.ui.viewReportPushButton.setEnabled(True)
        self.ui.generatePriorityFilePushButton.setEnabled(True)
        self.ui.generateStudyPlanPushButton.setEnabled(True)
        self.ui.loadFilesPushButton.setEnabled(False)

    def _reset_tables(self) -> None:
        self.ui.numericalTableWidget.setSortingEnabled(False)
        self.ui.percentTableWidget.setSortingEnabled(False)

        self.ui.numericalTableWidget.clearContents()
        self.ui.percentTableWidget.clearContents()
        self.ui.numericalTableWidget.setRowCount(0)
        self.ui.percentTableWidget.setRowCount(0)

        self.ui.numericalTableWidget.setSortingEnabled(True)
        self.ui.percentTableWidget.setSortingEnabled(True)

    def _populate_file_rows(self) -> None:
        assert self._input_dir_root is not None

        self.ui.numericalTableWidget.setSortingEnabled(False)
        self.ui.percentTableWidget.setSortingEnabled(False)

        self.ui.numericalTableWidget.setRowCount(len(self._input_files))
        self.ui.percentTableWidget.setRowCount(len(self._input_files))

        for row, file_path in enumerate(self._input_files):
            relative_name = str(file_path.relative_to(self._input_dir_root))
            file_item_counts = QtWidgets.QTableWidgetItem(relative_name)
            file_item_percents = QtWidgets.QTableWidgetItem(relative_name)
            self.ui.numericalTableWidget.setItem(row, 0, file_item_counts)
            self.ui.percentTableWidget.setItem(row, 0, file_item_percents)

        self.ui.numericalTableWidget.setSortingEnabled(True)
        self.ui.percentTableWidget.setSortingEnabled(True)

    def _generate_readability_report(self) -> None:
        assert mw is not None

        if not self._input_files or self._input_dir_root is None:
            self._on_failure(EmptyFileSelectionException())
            return

        operation = QueryOp(
            parent=self,
            op=lambda _: readability_report_generator.background_generate_report(
                ui=self.ui,
                input_dir_root=self._input_dir_root,
                input_files=self._input_files,
            ),
            success=lambda _: self._on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _generate_priority_file(self) -> None:
        assert mw is not None

        if not self._input_files or self._input_dir_root is None:
            self._on_failure(EmptyFileSelectionException())
            return

        dialog = GeneratorOutputDialog(priority_file_mode=True)
        result_code: int = dialog.exec()
        if result_code != QDialog.DialogCode.Accepted:
            return

        selected_output_options: OutputOptions = dialog.get_selected_options()

        operation = QueryOp(
            parent=self,
            op=lambda _: priority_file_generator.background_generate_priority_file(
                selected_output_options=selected_output_options,
                input_dir_root=self._input_dir_root,
                input_files=self._input_files,
            ),
            success=lambda _: self._on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _generate_study_plan(self) -> None:
        assert mw is not None

        if not self._input_files or self._input_dir_root is None:
            self._on_failure(EmptyFileSelectionException())
            return

        dialog = GeneratorOutputDialog(study_plan_mode=True)
        result_code: int = dialog.exec()
        if result_code != QDialog.DialogCode.Accepted:
            return

        selected_output_options: OutputOptions = dialog.get_selected_options()

        operation = QueryOp(
            parent=self,
            op=lambda _: study_plan_generator.background_generate_study_plan(
                selected_output_options=selected_output_options,
                input_dir_root=self._input_dir_root,
                input_files=self._input_files,
            ),
            success=lambda _: self._on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def closeWithCallback(self, callback: Callable[[], None]) -> None:  # pylint:disable=invalid-name
        self.am_extra_settings.save_generators_window_settings(
            ui=self.ui, geometry=self.saveGeometry()
        )
        self.close()
        dialog_name = am_globals.GENERATOR_DIALOG_NAME
        aqt.dialogs.markClosed(dialog_name)
        callback()

    def reopen(self) -> None:
        self.show()

    def _on_success(self) -> None:
        assert mw is not None
        assert mw.progress is not None
        mw.progress.finish()
        tooltip("Generator finished", parent=self)

    def _on_failure(
        self,
        error: Exception
        | CancelledOperationException
        | EmptyFileSelectionException
        | UnicodeException
        | NotADirectoryError,
    ) -> None:
        assert mw is not None
        assert mw.progress is not None
        mw.progress.finish()

        if isinstance(error, CancelledOperationException):
            tooltip("Cancelled generator", parent=self)
        elif isinstance(error, EmptyFileSelectionException):
            tooltip("No input files", parent=self)
        elif isinstance(error, UnicodeException):
            title = "Decoding Error"
            text = (
                "Error: all files must be UTF-8 encoded.<br>"
                f"The file at path '{error.path}' does not have UTF-8 encoding."
            )
            message_box_utils.show_error_box(title=title, body=text, parent=self)
        elif isinstance(error, NotADirectoryError):
            tooltip("Input folder does not exist", parent=self)
        else:
            raise error
