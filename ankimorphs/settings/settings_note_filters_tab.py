from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import aqt
from anki.models import NotetypeDict, NotetypeNameId
from aqt import mw
from aqt.qt import (  # pylint:disable=no-name-in-module
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    Qt,
    QItemSelectionModel,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidgetItem,
    QVBoxLayout,
)
from aqt.utils import tooltip

from .. import (
    ankimorphs_globals,
    message_box_utils,
    morph_priority_utils,
    table_utils,
    tags_and_queue_utils,
)
from ..ankimorphs_config import (
    AnkiMorphsConfig,
    AnkiMorphsConfigFilter,
    FilterTypeAlias,
    RawConfigFilterKeys,
    RawConfigKeys,
)
from ..morphemizers.morphemizer_utils import get_all_morphemizers
from ..tag_selection_dialog import TagSelectionDialog
from ..ui.settings_dialog_ui import Ui_SettingsDialog
from .data_provider import DataProvider
from .settings_tab import SettingsTab


class PriorityFileSelectionDialog(QDialog):

    def __init__(
        self,
        parent: QDialog | None,
        available_options: list[str],
        selected_options: list[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Frequency Files")

        self._none_option = ankimorphs_globals.NONE_OPTION

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Choose the frequency files to combine. The lowest rank among selections will be used."
            )
        )

        self._list_widget = QListWidget(self)
        layout.addWidget(self._list_widget)

        normalized_selected = (
            selected_options if selected_options is not None else []
        )

        for option in available_options:
            item = QListWidgetItem(option)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            if option == self._none_option:
                item.setCheckState(
                    Qt.CheckState.Checked
                    if not normalized_selected
                    else Qt.CheckState.Unchecked
                )
            elif option in normalized_selected:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self._list_widget.addItem(item)

        self._list_widget.itemChanged.connect(self._on_item_changed)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if item.text() == self._none_option and item.checkState() == Qt.CheckState.Checked:
            self._clear_all_except_none()
        elif item.checkState() == Qt.CheckState.Checked:
            none_item = self._find_item(self._none_option)
            if none_item is not None and none_item.checkState() == Qt.CheckState.Checked:
                self._set_item_check_state(none_item, Qt.CheckState.Unchecked)

    def _clear_all_except_none(self) -> None:
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            if item is None or item.text() == self._none_option:
                continue
            self._set_item_check_state(item, Qt.CheckState.Unchecked)

    def _set_item_check_state(self, item: QListWidgetItem, state: Qt.CheckState) -> None:
        self._list_widget.blockSignals(True)
        item.setCheckState(state)
        self._list_widget.blockSignals(False)

    def _find_item(self, text: str) -> QListWidgetItem | None:
        for idx in range(self._list_widget.count()):
            candidate = self._list_widget.item(idx)
            if candidate is not None and candidate.text() == text:
                return candidate
        return None

    def selected_files(self) -> list[str]:
        selections: list[str] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked and item.text() != self._none_option:
                selections.append(item.text())
        return selections


class NoteFiltersTab(  # pylint:disable=too-many-instance-attributes
    SettingsTab, DataProvider
):

    def __init__(  # pylint:disable=too-many-arguments
        self,
        parent: QDialog,
        ui: Ui_SettingsDialog,
        config: AnkiMorphsConfig,
        default_config: AnkiMorphsConfig,
    ) -> None:
        assert mw is not None

        SettingsTab.__init__(self, parent, ui, config, default_config)
        DataProvider.__init__(self)

        self.ui.note_filters_table.cellClicked.connect(
            self._note_filters_table_cell_clicked
        )

        # disables manual editing of note filter table
        self.ui.note_filters_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self._note_filter_note_type_column: int = 0
        self._note_filter_tags_column: int = 1
        self._note_filter_field_column: int = 2
        self._note_filter_furigana_field_column: int = 3
        self._note_filter_reading_field_column: int = 4
        self._note_filter_morphemizer_column: int = 5
        self._note_filter_morph_priority_column: int = 6
        self._note_filter_read_column: int = 7
        self._note_filter_modify_column: int = 8

        headers = [
            "Note Type",
            "Tags",
            "Field",
            "Furigana Field",
            "Reading Field",
            "Morphemizer",
            "Priority",
            "Read",
            "Modify",
        ]
        self.ui.note_filters_table.setColumnCount(len(headers))
        self.ui.note_filters_table.setHorizontalHeaderLabels(headers)

        self._morphemizers = get_all_morphemizers()
        self._note_type_models: Sequence[NotetypeNameId] = (
            mw.col.models.all_names_and_ids()
        )

        # the tag selector dialog is spawned from the settings dialog,
        # so it makes the most sense to store it here instead of __init__.py
        self.tag_selector = TagSelectionDialog()
        self.tag_selector.ui.applyButton.clicked.connect(self._update_note_filter_tags)
        # close the tag selector dialog when the settings dialog closes
        self._parent.finished.connect(self.tag_selector.close)

        # Have the Anki dialog manager handle the tag selector dialog
        aqt.dialogs.register_dialog(
            name=ankimorphs_globals.TAG_SELECTOR_DIALOG_NAME,
            creator=self.tag_selector.show,
        )

        self._previous_config_filters: dict[str, str | int | bool | object] | None = (
            None
        )

        # key = source combobox
        self.reset_tags_warning_shown = {
            "field": False,
            "note type": False,
            "morphemizer": False,
        }

        # Dynamically added widgets in the rows can be randomly garbage collected
        # if there are no persistent references to them outside the function that creates them.
        # This dict acts as a workaround to that problem.
        self.widget_references_by_row: list[tuple[Any, ...]] = []

        # needed to prevent garbage collection
        self.selection_model: QItemSelectionModel | None = None

        self.populate()
        self.setup_buttons()
        self.update_previous_state()

    def notify_subscribers(self) -> None:
        assert self._subscriber is not None
        selected_note_types = self._get_selected_note_filters()
        self._subscriber.update(selected_note_types)

    def _get_selected_note_filters(self) -> list[str]:
        selected_note_types: list[str] = []
        for row in range(self.ui.note_filters_table.rowCount()):
            note_filter_note_type_widget: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_note_type_column
                )
            )
            note_type: str = note_filter_note_type_widget.itemText(
                note_filter_note_type_widget.currentIndex()
            )
            selected_note_types.append(note_type)
        return selected_note_types

    def _setup_note_filters_table(
        self, config_filters: list[AnkiMorphsConfigFilter]
    ) -> None:
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_note_type_column, 150
        )
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_field_column, 150
        )
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_furigana_field_column, 150
        )
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_reading_field_column, 150
        )
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_morphemizer_column, 150
        )
        self.ui.note_filters_table.setColumnWidth(
            self._note_filter_morph_priority_column, 150
        )
        self.ui.note_filters_table.setRowCount(len(config_filters))
        self.ui.note_filters_table.setAlternatingRowColors(True)

        for row, am_filter in enumerate(config_filters):
            self._set_note_filters_table_row(row, am_filter)

    def populate(self, use_default_config: bool = False) -> None:
        filters: list[AnkiMorphsConfigFilter]

        if use_default_config:
            filters = self._default_config.filters
        else:
            filters = self._config.filters

        self._clear_note_filters_table()
        self._setup_note_filters_table(filters)

    def setup_buttons(self) -> None:
        self.ui.addNewRowPushButton.setAutoDefault(False)
        self.ui.deleteRowPushButton.setAutoDefault(False)
        self.ui.restoreNoteFiltersPushButton.setAutoDefault(False)

        self.ui.addNewRowPushButton.clicked.connect(self._add_new_row)
        self.ui.deleteRowPushButton.clicked.connect(self._delete_row)
        self.ui.restoreNoteFiltersPushButton.clicked.connect(self.restore_defaults)

        # disable while no rows are selected
        self._on_no_row_selected()

        self.selection_model = self.ui.note_filters_table.selectionModel()
        assert self.selection_model is not None
        self.selection_model.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        assert self.selection_model is not None

        selected_rows = self.selection_model.selectedRows()
        selected_indexes = self.selection_model.selectedIndexes()

        if len(selected_indexes) == 1 or len(selected_rows) == 1:
            self._on_row_selected()
        else:
            self._on_no_row_selected()

    def _on_no_row_selected(self) -> None:
        self.ui.deleteRowPushButton.setDisabled(True)

    def _on_row_selected(self) -> None:
        self.ui.deleteRowPushButton.setEnabled(True)

    def restore_defaults(self, skip_confirmation: bool = False) -> None:
        if not skip_confirmation:
            title = "Confirmation"
            text = self.get_confirmation_text()
            confirmed = message_box_utils.show_warning_box(
                title, text, parent=self._parent
            )

            if not confirmed:
                return

        self._setup_note_filters_table(self._default_config.filters)
        self.notify_subscribers()

    def restore_to_config_state(self) -> None:
        self.populate()
        self.notify_subscribers()

    def get_filters(self) -> list[FilterTypeAlias]:
        filters: list[FilterTypeAlias] = []
        for row in range(self.ui.note_filters_table.rowCount()):
            note_type_cbox: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_note_type_column
                )
            )
            tags_widget: QTableWidgetItem = table_utils.get_table_item(
                self.ui.note_filters_table.item(row, self._note_filter_tags_column)
            )
            field_cbox: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_field_column
                )
            )
            furigana_field_cbox: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_furigana_field_column
                )
            )
            reading_field_cbox: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_reading_field_column
                )
            )
            morphemizer_widget: QComboBox = table_utils.get_combobox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_morphemizer_column
                )
            )
            priority_item: QTableWidgetItem | None = self.ui.note_filters_table.item(
                row, self._note_filter_morph_priority_column
            )
            raw_priority_data = (
                priority_item.data(Qt.ItemDataRole.UserRole)
                if priority_item is not None
                else None
            )
            try:
                morph_priority_selections: list[str] = (
                    json.loads(raw_priority_data)
                    if isinstance(raw_priority_data, str)
                    else []
                )
            except json.JSONDecodeError:
                morph_priority_selections = []
            read_widget: QCheckBox = table_utils.get_checkbox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_read_column
                )
            )
            modify_widget: QCheckBox = table_utils.get_checkbox_widget(
                self.ui.note_filters_table.cellWidget(
                    row, self._note_filter_modify_column
                )
            )

            note_type_name: str = note_type_cbox.itemText(note_type_cbox.currentIndex())

            _filter: FilterTypeAlias = {
                RawConfigFilterKeys.NOTE_TYPE: note_type_name,
                RawConfigFilterKeys.TAGS: json.loads(tags_widget.text()),
                RawConfigFilterKeys.FIELD: field_cbox.itemText(
                    field_cbox.currentIndex()
                ),
                RawConfigFilterKeys.FURIGANA_FIELD: furigana_field_cbox.itemText(
                    furigana_field_cbox.currentIndex()
                ),
                RawConfigFilterKeys.READING_FIELD: reading_field_cbox.itemText(
                    reading_field_cbox.currentIndex()
                ),
                RawConfigFilterKeys.MORPHEMIZER_DESCRIPTION: morphemizer_widget.itemText(
                    morphemizer_widget.currentIndex()
                ),
                RawConfigFilterKeys.MORPH_PRIORITY_SELECTION: morph_priority_selections,
                RawConfigFilterKeys.READ: read_widget.isChecked(),
                RawConfigFilterKeys.MODIFY: modify_widget.isChecked(),
            }
            filters.append(_filter)
        return filters

    def _get_settings_dict_with_filters(self) -> dict[str, str | int | bool | object]:
        settings_dict_with_filters: dict[str, str | int | bool | object] = {
            RawConfigKeys.FILTERS: self.get_filters()
        }
        return settings_dict_with_filters

    def _add_new_row(self) -> None:
        self.ui.note_filters_table.setRowCount(
            self.ui.note_filters_table.rowCount() + 1
        )
        config_filter = self._default_config.filters[0]
        row = self.ui.note_filters_table.rowCount() - 1
        self._set_note_filters_table_row(row, config_filter)

    def _delete_row(self) -> None:
        title = "Confirmation"
        text = (
            "Are you sure you want to delete the selected row?<br>"
            "Note: This will also unselect the respective extra fields!"
        )
        confirmed = message_box_utils.show_warning_box(title, text, parent=self._parent)

        if confirmed:
            selected_row = self.ui.note_filters_table.currentRow()
            self.ui.note_filters_table.removeRow(selected_row)

            # prevents memory leaks
            del self.widget_references_by_row[selected_row]

            self.notify_subscribers()

    def _clear_note_filters_table(self) -> None:
        """
        Prevents Memory Leaks
        """
        self.widget_references_by_row.clear()
        self.ui.note_filters_table.clearContents()
        self.ui.note_filters_table.setRowCount(0)  # uses removeRows()

    def _set_note_filters_table_row(
        self, row: int, config_filter: AnkiMorphsConfigFilter
    ) -> None:
        assert mw is not None
        self.ui.note_filters_table.setRowHeight(row, 35)

        note_type_cbox = self._setup_note_type_cbox(config_filter)
        note_type_cbox.setProperty("previousIndex", note_type_cbox.currentIndex())
        selected_note_type: str = note_type_cbox.itemText(note_type_cbox.currentIndex())

        tags_filter_widget = QTableWidgetItem(json.dumps(config_filter.tags))

        field_cbox = self._setup_fields_cbox(
            selected_note_type=selected_note_type,
            selected_value=config_filter.field,
        )
        field_cbox.setProperty("previousIndex", field_cbox.currentIndex())
        field_cbox.currentIndexChanged.connect(
            lambda index: self._potentially_reset_tags(
                new_index=index,
                combo_box=field_cbox,
                reason_for_reset="field",
            )
        )

        furigana_field_cbox = self._setup_fields_cbox(
            selected_note_type=selected_note_type,
            selected_value=config_filter.furigana_field,
        )

        reading_field_cbox = self._setup_fields_cbox(
            selected_note_type=selected_note_type,
            selected_value=config_filter.reading_field,
        )

        # Fields are dependent on note-type
        note_type_cbox.currentIndexChanged.connect(
            lambda _: self._update_fields_cbox(field_cbox, note_type_cbox)
        )
        note_type_cbox.currentIndexChanged.connect(
            lambda _: self._update_fields_cbox(
                furigana_field_cbox, note_type_cbox
            )
        )
        note_type_cbox.currentIndexChanged.connect(
            lambda _: self._update_fields_cbox(reading_field_cbox, note_type_cbox)
        )
        note_type_cbox.currentIndexChanged.connect(
            lambda index: self._potentially_reset_tags(
                new_index=index,
                combo_box=note_type_cbox,
                reason_for_reset="note type",
            )
        )
        note_type_cbox.currentIndexChanged.connect(self.notify_subscribers)

        morphemizer_cbox = self._setup_morphemizer_cbox(config_filter)
        morphemizer_cbox.setProperty("previousIndex", morphemizer_cbox.currentIndex())
        morphemizer_cbox.currentIndexChanged.connect(
            lambda index: self._potentially_reset_tags(
                new_index=index,
                combo_box=morphemizer_cbox,
                reason_for_reset="morphemizer",
            )
        )

        self._set_priority_item(row, config_filter.morph_priority_selections)

        read_checkbox = QCheckBox()
        read_checkbox.setChecked(config_filter.read)
        read_checkbox.setStyleSheet("margin-left:auto; margin-right:auto;")

        modify_checkbox = QCheckBox()
        modify_checkbox.setChecked(config_filter.modify)
        modify_checkbox.setStyleSheet("margin-left:auto; margin-right:auto;")

        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_note_type_column, note_type_cbox
        )
        self.ui.note_filters_table.setItem(
            row,
            self._note_filter_tags_column,
            tags_filter_widget,
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_field_column, field_cbox
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_furigana_field_column, furigana_field_cbox
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_reading_field_column, reading_field_cbox
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_morphemizer_column, morphemizer_cbox
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_read_column, read_checkbox
        )
        self.ui.note_filters_table.setCellWidget(
            row, self._note_filter_modify_column, modify_checkbox
        )

        # store widgets persistently to prevent garbage collection
        self.widget_references_by_row.append(
            (
                note_type_cbox,
                tags_filter_widget,
                field_cbox,
                furigana_field_cbox,
                reading_field_cbox,
                morphemizer_cbox,
                None,
                read_checkbox,
                modify_checkbox,
            )
        )

    def _format_priority_summary(self, selections: list[str]) -> str:
        if not selections:
            return ankimorphs_globals.NONE_OPTION

        if len(selections) <= 3:
            return ", ".join(selections)

        remaining = len(selections) - 3
        return ", ".join(selections[:3]) + f" (+{remaining})"

    def _set_priority_item(self, row: int, selections: list[str]) -> None:
        item = self.ui.note_filters_table.item(
            row, self._note_filter_morph_priority_column
        )
        if item is None:
            item = QTableWidgetItem()
            self.ui.note_filters_table.setItem(
                row, self._note_filter_morph_priority_column, item
            )

        item.setText(self._format_priority_summary(selections))
        item.setData(Qt.ItemDataRole.UserRole, json.dumps(selections))
        flags = item.flags()
        item.setFlags(
            (flags | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            & ~Qt.ItemFlag.ItemIsEditable
        )

    def _open_priority_selection_dialog(self, row: int) -> None:
        current_item = self.ui.note_filters_table.item(
            row, self._note_filter_morph_priority_column
        )
        raw_data = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else None
        )
        try:
            current_selections: list[str] = (
                json.loads(raw_data) if isinstance(raw_data, str) else []
            )
        except json.JSONDecodeError:
            current_selections = []

        available_options = [
            ankimorphs_globals.NONE_OPTION,
            ankimorphs_globals.COLLECTION_FREQUENCY_OPTION,
        ]
        available_options += morph_priority_utils.get_priority_files()

        dialog = PriorityFileSelectionDialog(
            parent=self._parent,
            available_options=available_options,
            selected_options=current_selections,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selections = dialog.selected_files()
        self._set_priority_item(row, selections)

    def _potentially_reset_tags(
        self, new_index: int, combo_box: QComboBox, reason_for_reset: str
    ) -> None:
        """
        To prevent annoying the user, we only want to show the warning dialog once
        per combobox, per setting.
        """

        if not self.reset_tags_warning_shown.get(reason_for_reset, False):
            if new_index == 0:  # Ignore the "(none)" selection
                return

            previous_index = combo_box.property("previousIndex")
            if previous_index == 0:  # Skip if no change
                return

            if self._want_to_reset_am_tags(reason_for_reset):
                tags_and_queue_utils.reset_am_tags(parent=self._parent)

            self.reset_tags_warning_shown[reason_for_reset] = True
            combo_box.setProperty("previousIndex", new_index)

    def _setup_note_type_cbox(self, config_filter: AnkiMorphsConfigFilter) -> QComboBox:
        note_type_cbox = QComboBox(self.ui.note_filters_table)
        note_types_string: list[str] = [ankimorphs_globals.NONE_OPTION] + [
            model.name for model in self._note_type_models
        ]
        note_type_cbox.addItems(note_types_string)
        note_type_name_index = table_utils.get_combobox_index(
            note_types_string, config_filter.note_type
        )
        note_type_cbox.setCurrentIndex(note_type_name_index)
        return note_type_cbox

    def _setup_fields_cbox(
        self, selected_note_type: str, selected_value: str
    ) -> QComboBox:
        assert mw is not None

        note_type_dict: NotetypeDict | None = mw.col.models.by_name(
            name=selected_note_type
        )
        note_type_fields: list[str] = [ankimorphs_globals.NONE_OPTION]

        if note_type_dict is not None:
            note_type_fields += mw.col.models.field_map(note_type_dict)

        field_cbox = QComboBox(self.ui.note_filters_table)
        field_cbox.addItems(note_type_fields)
        field_cbox_index = table_utils.get_combobox_index(
            note_type_fields, selected_value
        )
        if field_cbox_index is not None:
            field_cbox.setCurrentIndex(field_cbox_index)
        return field_cbox

    def _setup_morphemizer_cbox(
        self, config_filter: AnkiMorphsConfigFilter
    ) -> QComboBox:
        morphemizer_cbox = QComboBox(self.ui.note_filters_table)
        morphemizers: list[str] = [ankimorphs_globals.NONE_OPTION] + [
            mizer.get_description() for mizer in self._morphemizers
        ]
        morphemizer_cbox.addItems(morphemizers)
        morphemizer_cbox_index = table_utils.get_combobox_index(
            morphemizers, config_filter.morphemizer_description
        )
        if morphemizer_cbox_index is not None:
            morphemizer_cbox.setCurrentIndex(morphemizer_cbox_index)
        return morphemizer_cbox

    def _update_fields_cbox(
        self, field_cbox: QComboBox, note_type_cbox: QComboBox
    ) -> None:
        """
        When the note type selection changes we repopulate the fields list,
        and we set the selected field to (none)
        """
        assert mw

        field_cbox.blockSignals(True)  # prevent currentIndexChanged signals

        field_cbox.clear()
        note_type_fields: list[str] = [ankimorphs_globals.NONE_OPTION]

        selected_note_type: str = note_type_cbox.itemText(note_type_cbox.currentIndex())
        note_type_dict: NotetypeDict | None = mw.col.models.by_name(
            name=selected_note_type
        )

        if note_type_dict is not None:
            note_type_fields += mw.col.models.field_map(note_type_dict)

        field_cbox.addItems(note_type_fields)
        field_cbox.setCurrentIndex(0)

        field_cbox.blockSignals(False)  # prevent currentIndexChanged signals

    def _note_filters_table_cell_clicked(self, row: int, column: int) -> None:
        if column == self._note_filter_tags_column:
            tags_widget: QTableWidgetItem = table_utils.get_table_item(
                self.ui.note_filters_table.item(row, self._note_filter_tags_column)
            )
            self.tag_selector.set_selected_tags_and_row(
                selected_tags=tags_widget.text(), row=row
            )
            aqt.dialogs.open(
                name=ankimorphs_globals.TAG_SELECTOR_DIALOG_NAME,
            )
            return

        if column == self._note_filter_morph_priority_column:
            self._open_priority_selection_dialog(row)

    def _update_note_filter_tags(self) -> None:
        self.ui.note_filters_table.setItem(
            self.tag_selector.current_note_filter_row,
            1,
            QTableWidgetItem(self.tag_selector.selected_tags),
        )
        self.tag_selector.ui.tableWidget.clearContents()
        tooltip("Remember to save!", parent=self._parent)

    def get_confirmation_text(self) -> str:
        return (
            "Are you sure you want to restore default note filter settings?<br>"
            "Note: This will also unselect the respective extra fields!"
        )

    def settings_to_dict(self) -> dict[str, str | int | bool | object]:
        return {}

    def get_data(self) -> Any:
        return self.get_filters()

    def update_previous_state(self) -> None:
        self._previous_config_filters = self._get_settings_dict_with_filters()

    def contains_unsaved_changes(self) -> bool:
        assert self._previous_config_filters is not None

        current_state = self._get_settings_dict_with_filters()
        if current_state != self._previous_config_filters:
            return True

        return False
