from pathlib import Path

from aqt import mw
from aqt.qt import QByteArray, QSettings  # pylint:disable=no-name-in-module

from .. import prioritysieve_globals
from ..ui.generator_output_dialog_ui import Ui_GeneratorOutputDialog
from ..ui.generators_window_ui import Ui_GeneratorsWindow
from ..ui.known_entries_exporter_dialog_ui import Ui_KnownEntriesExporterDialog
from ..ui.progression_window_ui import Ui_ProgressionWindow
from . import extra_settings_keys as keys  # pylint:disable=no-name-in-module
from .extra_settings_keys import (
    GeneratorsOutputKeys,
    GeneratorsWindowKeys,
    KnownEntriesExporterKeys,
    ProgressionWindowKeys,
)


class PrioritySieveExtraSettings(QSettings):
    def __init__(self) -> None:
        assert mw is not None
        extra_settings_path = Path(
            mw.pm.profileFolder(), "prioritysieve_extra_settings.ini"
        )
        super().__init__(str(extra_settings_path), QSettings.Format.IniFormat)

    def save_current_prioritysieve_version(self) -> None:
        self.setValue(keys.General.PRIORITYSIEVE_VERSION, prioritysieve_globals.__version__)

    def save_generators_window_settings(
        self, ui: Ui_GeneratorsWindow, geometry: QByteArray
    ) -> None:
        self.beginGroup(keys.Dialogs.GENERATORS_WINDOW)
        self.setValue(GeneratorsWindowKeys.WINDOW_GEOMETRY, geometry)
        self.setValue(GeneratorsWindowKeys.INPUT_DIR, ui.inputDirLineEdit.text())
        self.endGroup()

    def save_known_entries_exporter_settings(
        self, ui: Ui_KnownEntriesExporterDialog, geometry: QByteArray
    ) -> None:
        # fmt: off
        self.beginGroup(keys.Dialogs.KNOWN_ENTRIES_EXPORTER)
        self.setValue(KnownEntriesExporterKeys.WINDOW_GEOMETRY, geometry)
        self.setValue(KnownEntriesExporterKeys.OUTPUT_DIR, ui.outputLineEdit.text())
        self.setValue(KnownEntriesExporterKeys.INCLUDE_READING, ui.includeReadingCheckBox.isChecked())
        self.setValue(KnownEntriesExporterKeys.REVIEWED_ONLY, ui.includeReviewedOnlyCheckBox.isChecked())
        self.setValue(KnownEntriesExporterKeys.OCCURRENCES, ui.addOccurrencesColumnCheckBox.isChecked())
        self.endGroup()
        # fmt: on

    def get_recalc_collection_state(self) -> str | None:
        return self.value(keys.General.RECALC_COLLECTION_STATE, None, type=str)

    def set_recalc_collection_state(self, state: str | None) -> None:
        if state is None:
            self.remove(keys.General.RECALC_COLLECTION_STATE)
        else:
            self.setValue(keys.General.RECALC_COLLECTION_STATE, state)

    def get_recalc_settings_state(self) -> str | None:
        return self.value(keys.General.RECALC_SETTINGS_STATE, None, type=str)

    def set_recalc_settings_state(self, state: str | None) -> None:
        if state is None:
            self.remove(keys.General.RECALC_SETTINGS_STATE)
        else:
            self.setValue(keys.General.RECALC_SETTINGS_STATE, state)
    def save_progression_window_settings(
        self, ui: Ui_ProgressionWindow, geometry: QByteArray
    ) -> None:
        # fmt: off
        self.beginGroup(keys.Dialogs.PROGRESSION_WINDOW)
        self.setValue(ProgressionWindowKeys.WINDOW_GEOMETRY, geometry)
        self.setValue(ProgressionWindowKeys.PRIORITY_FILE, ui.morphPriorityCBox.currentText())
        self.setValue(ProgressionWindowKeys.PRIORITY_RANGE_START, ui.minPrioritySpinBox.value())
        self.setValue(ProgressionWindowKeys.PRIORITY_RANGE_END, ui.maxPrioritySpinBox.value())
        self.setValue(ProgressionWindowKeys.BIN_SIZE, ui.binSizeSpinBox.value())
        self.setValue(ProgressionWindowKeys.BIN_TYPE_NORMAL, ui.normalRadioButton.isChecked())
        self.setValue(ProgressionWindowKeys.BIN_TYPE_CUMULATIVE, ui.cumulativeRadioButton.isChecked())
        self.endGroup()
        # fmt: on

    def save_generator_priority_file_settings(
        self, ui: Ui_GeneratorOutputDialog, geometry: QByteArray
    ) -> None:
        # fmt: off
        self.beginGroup(keys.Dialogs.GENERATOR_OUTPUT_PRIORITY_FILE)
        self.setValue(GeneratorsOutputKeys.WINDOW_GEOMETRY, geometry)
        self.setValue(GeneratorsOutputKeys.OUTPUT_FILE_PATH, ui.outputLineEdit.text())
        self.setValue(GeneratorsOutputKeys.INCLUDE_READING, ui.includeReadingCheckBox.isChecked())
        self.setValue(GeneratorsOutputKeys.MIN_OCCURRENCE_SELECTED, ui.minOccurrenceRadioButton.isChecked())
        self.setValue(GeneratorsOutputKeys.MIN_OCCURRENCE_CUTOFF, ui.minOccurrenceSpinBox.value())
        self.setValue(GeneratorsOutputKeys.COMPREHENSION_SELECTED, ui.comprehensionRadioButton.isChecked())
        self.setValue(GeneratorsOutputKeys.COMPREHENSION_CUTOFF, ui.comprehensionSpinBox.value())
        self.setValue(GeneratorsOutputKeys.OCCURRENCES_COLUMN_SELECTED, ui.addOccurrencesColumnCheckBox.isChecked())
        self.endGroup()
        # fmt: on

    def save_generator_study_plan_settings(
        self, ui: Ui_GeneratorOutputDialog, geometry: QByteArray
    ) -> None:
        # fmt: off
        self.beginGroup(keys.Dialogs.GENERATOR_OUTPUT_STUDY_PLAN)
        self.setValue(GeneratorsOutputKeys.WINDOW_GEOMETRY, geometry)
        self.setValue(GeneratorsOutputKeys.OUTPUT_FILE_PATH, ui.outputLineEdit.text())
        self.setValue(GeneratorsOutputKeys.INCLUDE_READING, ui.includeReadingCheckBox.isChecked())
        self.setValue(GeneratorsOutputKeys.MIN_OCCURRENCE_SELECTED, ui.minOccurrenceRadioButton.isChecked())
        self.setValue(GeneratorsOutputKeys.MIN_OCCURRENCE_CUTOFF, ui.minOccurrenceSpinBox.value())
        self.setValue(GeneratorsOutputKeys.COMPREHENSION_SELECTED, ui.comprehensionRadioButton.isChecked())
        self.setValue(GeneratorsOutputKeys.COMPREHENSION_CUTOFF, ui.comprehensionSpinBox.value())
        self.setValue(GeneratorsOutputKeys.OCCURRENCES_COLUMN_SELECTED, ui.addOccurrencesColumnCheckBox.isChecked())
        self.endGroup()
        # fmt: on


    
    def save_settings_dialog_settings(self, geometry: QByteArray) -> None:
        self.beginGroup(keys.Dialogs.SETTINGS_DIALOG)
        self.setValue(GeneratorsOutputKeys.WINDOW_GEOMETRY, geometry)
        self.endGroup()
