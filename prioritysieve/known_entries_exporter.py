from __future__ import annotations

import csv
import datetime
import os
from pathlib import Path
from typing import Callable

import aqt
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDialog, QFileDialog  # pylint:disable=no-name-in-module
from aqt.utils import tooltip

from . import prioritysieve_globals as am_globals
from .entry_db import EntryDB
from .priority_files import KNOWN_ENTRIES_DIR
from .exceptions import CancelledOperationException, EmptyFileSelectionException
from .extra_settings import extra_settings_keys
from .extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from .ui.known_morphs_exporter_dialog_ui import Ui_KnownMorphsExporterDialog


class KnownEntriesExporterDialog(QDialog):
    def __init__(
        self,
    ) -> None:
        assert mw is not None

        super().__init__(parent=None)  # no parent makes the dialog modeless
        self.ui = Ui_KnownMorphsExporterDialog()  # pylint:disable=invalid-name
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self.am_extra_settings = PrioritySieveExtraSettings()
        self.am_extra_settings.beginGroup(
            extra_settings_keys.Dialogs.KNOWN_ENTRIES_EXPORTER
        )

        self._default_output_dir = os.path.join(
            mw.pm.profileFolder(), KNOWN_ENTRIES_DIR
        )

        self._setup_output_path()
        self._setup_buttons()
        self._setup_checkboxes()
        self._setup_geometry()

        self.am_extra_settings.endGroup()
        self.show()

    def _setup_output_path(self) -> None:
        stored_output_dir: str = self.am_extra_settings.value(
            extra_settings_keys.KnownEntriesExporterKeys.OUTPUT_DIR,
            defaultValue=self._default_output_dir,
            type=str,
        )

        # create the parent directories if they don't exist
        Path(stored_output_dir).parent.mkdir(parents=True, exist_ok=True)
        self.ui.outputLineEdit.setText(stored_output_dir)

    def _setup_buttons(self) -> None:
        self.ui.selectOutputPushButton.setAutoDefault(False)
        self.ui.exportKnownMorphsPushButton.setAutoDefault(False)

        self.ui.selectOutputPushButton.clicked.connect(self._on_output_button_clicked)
        self.ui.exportKnownMorphsPushButton.clicked.connect(self._export_known_entries)

        stored_include_reading: bool | None = self.am_extra_settings.value(
            extra_settings_keys.KnownEntriesExporterKeys.INCLUDE_READING,
            type=bool,
        )
        if stored_include_reading is not None:
            self.ui.includeReadingCheckBox.setChecked(stored_include_reading)

        stored_reviewed_only: bool | None = self.am_extra_settings.value(
            extra_settings_keys.KnownEntriesExporterKeys.REVIEWED_ONLY,
            type=bool,
        )
        if stored_reviewed_only is not None:
            self.ui.includeReviewedOnlyCheckBox.setChecked(stored_reviewed_only)

    def _setup_checkboxes(self) -> None:
        stored_occurrences_selection: bool = self.am_extra_settings.value(
            extra_settings_keys.KnownEntriesExporterKeys.OCCURRENCES,
            defaultValue=False,
            type=bool,
        )
        self.ui.addOccurrencesColumnCheckBox.setChecked(stored_occurrences_selection)

    def _setup_geometry(self) -> None:
        stored_geometry = self.am_extra_settings.value(
            extra_settings_keys.KnownEntriesExporterKeys.WINDOW_GEOMETRY
        )
        if stored_geometry is not None:
            self.restoreGeometry(stored_geometry)

    def _on_output_button_clicked(self) -> None:
        output_dir: str = QFileDialog.getExistingDirectory(
            directory=self.ui.outputLineEdit.text(),
        )
        if output_dir == "":
            output_dir = self._default_output_dir

        self.ui.outputLineEdit.setText(output_dir)

    def _export_known_entries(self) -> None:
        assert mw is not None

        mw.progress.start(label="Exporting Known Entries")
        operation = QueryOp(
            parent=mw,
            op=lambda _: self._background_export_known_entries(),
            success=lambda _: self._on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _background_export_known_entries(self) -> None:
        assert mw is not None

        output_dir = self.ui.outputLineEdit.text()
        if output_dir == "":
            raise EmptyFileSelectionException

        include_reading = self.ui.includeReadingCheckBox.isChecked()
        reviewed_only = self.ui.includeReviewedOnlyCheckBox.isChecked()
        include_occurrences = self.ui.addOccurrencesColumnCheckBox.isChecked()

        self.am_extra_settings.beginGroup(
            extra_settings_keys.Dialogs.KNOWN_ENTRIES_EXPORTER
        )
        self.am_extra_settings.setValue(
            extra_settings_keys.KnownEntriesExporterKeys.OUTPUT_DIR, output_dir
        )
        self.am_extra_settings.setValue(
            extra_settings_keys.KnownEntriesExporterKeys.INCLUDE_READING,
            include_reading,
        )
        self.am_extra_settings.setValue(
            extra_settings_keys.KnownEntriesExporterKeys.REVIEWED_ONLY,
            reviewed_only,
        )
        self.am_extra_settings.setValue(
            extra_settings_keys.KnownEntriesExporterKeys.OCCURRENCES,
            include_occurrences,
        )
        self.am_extra_settings.endGroup()

        _datetime = datetime.datetime.now().strftime("%Y-%m-%d@%H-%M-%S")
        output_file = os.path.join(output_dir, f"known_entries-{_datetime}.csv")
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with EntryDB() as entry_db:
            entries_with_counts = entry_db.get_entries_with_counts(
                reviewed_only=reviewed_only
            )

        headers: list[str] = ["Entry"]
        if include_reading:
            headers.append("Reading")
        if include_occurrences:
            headers.append("Occurrences")

        with open(output_file, mode="w+", encoding="utf-8", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            for entry, count in entries_with_counts:
                row: list[str | int] = [entry.text]
                if include_reading:
                    row.append(entry.reading)
                if include_occurrences:
                    row.append(int(count))
                writer.writerow(row)

    def closeWithCallback(  # pylint:disable=invalid-name
        self, callback: Callable[[], None]
    ) -> None:
        # This is used by the Anki dialog manager
        self.am_extra_settings.save_known_entries_exporter_settings(
            ui=self.ui, geometry=self.saveGeometry()
        )
        self.close()
        aqt.dialogs.markClosed(am_globals.KNOWN_ENTRIES_EXPORTER_DIALOG_NAME)
        callback()

    def reopen(self) -> None:
        # This is used by the Anki dialog manager
        self.show()

    def _on_success(self) -> None:
        # This function runs on the main thread.
        assert mw is not None
        assert mw.progress is not None
        mw.toolbar.draw()  # updates stats
        mw.progress.finish()
        tooltip("Known entries file created", parent=self)

    def _on_failure(
        self,
        error: Exception | CancelledOperationException | EmptyFileSelectionException,
    ) -> None:
        # This function runs on the main thread.
        assert mw is not None
        assert mw.progress is not None
        mw.progress.finish()

        if isinstance(error, CancelledOperationException):
            tooltip("Cancelled Known Entries Export", parent=self)
        elif isinstance(error, EmptyFileSelectionException):
            tooltip("No file/folder selected", parent=self)
        else:
            raise error
