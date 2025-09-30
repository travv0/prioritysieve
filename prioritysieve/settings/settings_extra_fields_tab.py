from __future__ import annotations

from aqt.qt import (  # pylint:disable=no-name-in-module
    QDialog,
    Qt,
    QTreeWidgetItem,
)

from .. import prioritysieve_globals as ps_globals
from .. import message_box_utils
from ..prioritysieve_config import (
    PrioritySieveConfig,
    FilterTypeAlias,
    RawConfigFilterKeys,
    RawConfigKeys,
)
from ..ui.settings_dialog_ui import Ui_SettingsDialog
from .data_extractor import DataExtractor
from .data_provider import DataProvider
from .data_subscriber import DataSubscriber
from .settings_tab import SettingsTab


class ExtraFieldsTab(SettingsTab, DataSubscriber, DataExtractor):
    """Allow selecting which note types receive the generated reading field."""

    _EXTRA_FIELD_NAME = ps_globals.EXTRA_FIELD_READING

    def __init__(
        self,
        parent: QDialog,
        ui: Ui_SettingsDialog,
        config: PrioritySieveConfig,
        default_config: PrioritySieveConfig,
    ) -> None:
        SettingsTab.__init__(self, parent, ui, config, default_config)
        DataExtractor.__init__(self)

        self._selected_note_types: list[str] = [
            _filter.note_type for _filter in self._config.filters
        ]

        # hide the artificial header index
        self.ui.extraFieldsTreeWidget.setHeaderHidden(True)
        self.ui.extraFieldsTreeWidget.itemChanged.connect(self._tree_item_changed)

        self.populate()
        self.setup_buttons()

    def add_data_provider(self, data_provider: DataProvider) -> None:
        self.data_provider = data_provider
        self.update_previous_state()

    def update(self, selected_note_types: list[str]) -> None:
        self._selected_note_types = selected_note_types
        self._populate_tree()

    def populate(self, use_default_config: bool = False) -> None:
        super().populate(use_default_config)
        self._populate_tree(restore_defaults=use_default_config)

    def _populate_tree(self, restore_defaults: bool = False) -> None:
        self.ui.extraFieldsTreeWidget.clear()
        self.ui.extraFieldsTreeWidget.blockSignals(True)

        for note_type in self._selected_note_types:
            if note_type == ps_globals.NONE_OPTION:
                continue

            top_node = self._create_top_node(note_type, restore_defaults)
            self.ui.extraFieldsTreeWidget.addTopLevelItem(top_node)

        self.ui.extraFieldsTreeWidget.blockSignals(False)

    def _create_top_node(
        self, note_type: str, restore_defaults: bool = False
    ) -> QTreeWidgetItem:
        selected_in_config = self.get_selected_extra_fields_from_config(
            note_type, restore_defaults
        )

        top_node = QTreeWidgetItem()
        top_node.setText(0, note_type)
        top_node.setCheckState(0, Qt.CheckState.Unchecked)

        child_item = QTreeWidgetItem(top_node)
        child_item.setText(0, self._EXTRA_FIELD_NAME)

        if selected_in_config[self._EXTRA_FIELD_NAME]:
            top_node.setCheckState(0, Qt.CheckState.Checked)
            child_item.setCheckState(0, Qt.CheckState.Checked)
        else:
            child_item.setCheckState(0, Qt.CheckState.Unchecked)
            child_item.setDisabled(True)

        return top_node

    def get_selected_extra_fields_from_config(
        self, note_type: str, restore_defaults: bool = False
    ) -> dict[str, bool]:
        is_selected = False
        filters = (
            self._default_config.filters if restore_defaults else self._config.filters
        )

        for _filter in filters:
            if _filter.note_type == note_type:
                is_selected = getattr(
                    _filter, "extra_reading_field", False
                )
                break

        return {self._EXTRA_FIELD_NAME: is_selected}

    def _tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        self.ui.extraFieldsTreeWidget.blockSignals(True)

        parent = item.parent()
        if parent is None:
            # top-level toggled
            if item.checkState(column) == Qt.CheckState.Checked:
                child = item.child(0)
                if child is not None:
                    child.setDisabled(False)
                    child.setCheckState(0, Qt.CheckState.Checked)
            else:
                child = item.child(0)
                if child is not None:
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    child.setDisabled(True)

        self.ui.extraFieldsTreeWidget.blockSignals(False)

    def setup_buttons(self) -> None:
        self.ui.restoreExtraFieldsPushButton.setAutoDefault(False)
        self.ui.restoreExtraFieldsPushButton.clicked.connect(self.restore_defaults)

    def restore_defaults(self, skip_confirmation: bool = False) -> None:
        if not skip_confirmation:
            title = "Confirmation"
            text = self.get_confirmation_text()
            confirmed = message_box_utils.show_warning_box(
                title, text, parent=self._parent
            )
            if not confirmed:
                return

        self._populate_tree(restore_defaults=True)

    def get_selected_extra_fields(self, note_type_name: str) -> dict[str, bool]:
        for top_index in range(self.ui.extraFieldsTreeWidget.topLevelItemCount()):
            top_node = self.ui.extraFieldsTreeWidget.topLevelItem(top_index)
            if top_node is not None and top_node.text(0) == note_type_name:
                child = top_node.child(0)
                if child is not None:
                    is_checked = child.checkState(0) == Qt.CheckState.Checked
                    return {RawConfigFilterKeys.EXTRA_READING_FIELD: is_checked}
                break
        return {RawConfigFilterKeys.EXTRA_READING_FIELD: False}

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default extra field settings?"

    def settings_to_dict(self) -> dict[str, str | int | bool | object]:
        assert self.data_provider is not None

        filters: list[FilterTypeAlias] = self.data_provider.get_data()
        for _filter in filters:
            note_type_name = _filter[RawConfigFilterKeys.NOTE_TYPE]
            assert isinstance(note_type_name, str)
            _filter.update(
                self.get_selected_extra_fields(note_type_name)
            )

        return {RawConfigKeys.FILTERS: filters}
