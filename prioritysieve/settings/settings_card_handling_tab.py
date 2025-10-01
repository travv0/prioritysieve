from __future__ import annotations

from aqt import mw
from aqt.qt import (  # pylint:disable=no-name-in-module
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QListWidget,
    QPushButton,
    QSpinBox,
    Qt,
)

from .. import prioritysieve_globals as ps_globals
from ..prioritysieve_config import PrioritySieveConfig, RawConfigKeys
from ..ui.settings_dialog_ui import Ui_SettingsDialog
from .settings_tab import SettingsTab


class CardHandlingTab(SettingsTab):
    def __init__(
        self,
        parent: QDialog,
        ui: Ui_SettingsDialog,
        config: PrioritySieveConfig,
        default_config: PrioritySieveConfig,
    ) -> None:
        super().__init__(parent, ui, config, default_config)

        self._raw_config_key_to_check_box: dict[str, QCheckBox] = {
            RawConfigKeys.SKIP_NO_UNKNOWN_MORPHS: self.ui.skipNoUnKnownMorphsCheckBox,
            RawConfigKeys.SKIP_UNKNOWN_MORPH_SEEN_TODAY_CARDS: self.ui.skipAlreadySeenCheckBox,
            RawConfigKeys.SKIP_SHOW_NUM_OF_SKIPPED_CARDS: self.ui.skipNotificationsCheckBox,
            RawConfigKeys.RECALC_OFFSET_NEW_CARDS: self.ui.shiftNewCardsCheckBox,
        }

        self._raw_config_key_to_spin_box: dict[str, QSpinBox | QDoubleSpinBox] = {
            RawConfigKeys.RECALC_DUE_OFFSET: self.ui.dueOffsetSpinBox,
            RawConfigKeys.RECALC_NUMBER_OF_MORPHS_TO_OFFSET: self.ui.offsetFirstMorphsSpinBox,
        }

        self._priority_deck_list_widget: QListWidget = self.ui.priorityDecksListWidget
        self._priority_deck_move_up_button: QPushButton = self.ui.priorityDeckMoveUpButton
        self._priority_deck_move_down_button: QPushButton = self.ui.priorityDeckMoveDownButton
        self._priority_deck_refresh_button: QPushButton = self.ui.priorityDeckRefreshButton

        self._new_card_action_buttons = {"move": self.ui.knownEntryMoveRadioButton, "suspend": self.ui.knownEntrySuspendRadioButton}

        self.populate()
        self.setup_buttons()
        self.update_previous_state()

    def populate(self, use_default_config: bool = False) -> None:
        super().populate(use_default_config)

        source = self._default_config if use_default_config else self._config
        action = getattr(source, "known_entry_new_card_action", "move")
        for key, button in self._new_card_action_buttons.items():
            button.setChecked(key == action)

        deck_order = self._build_priority_deck_list(
            source, source.recalc_offset_priority_decks
        )
        self._set_priority_deck_items(deck_order)

        self._toggle_disable_shift_cards_settings()

    def setup_buttons(self) -> None:
        self.ui.restoreCardHandlingPushButton.setAutoDefault(False)
        self.ui.restoreCardHandlingPushButton.clicked.connect(self.restore_defaults)

        self.ui.shiftNewCardsCheckBox.stateChanged.connect(
            self._toggle_disable_shift_cards_settings
        )

        self._priority_deck_move_up_button.clicked.connect(
            self._move_priority_deck_up
        )
        self._priority_deck_move_down_button.clicked.connect(
            self._move_priority_deck_down
        )
        self._priority_deck_refresh_button.clicked.connect(
            self._refresh_priority_decks
        )
        self._priority_deck_list_widget.currentRowChanged.connect(
            self._on_priority_deck_selection_changed
        )

    def _toggle_disable_shift_cards_settings(self) -> None:
        enabled = self.ui.shiftNewCardsCheckBox.checkState() != Qt.CheckState.Unchecked
        self.ui.dueOffsetSpinBox.setEnabled(enabled)
        self.ui.offsetFirstMorphsSpinBox.setEnabled(enabled)
        self._update_priority_deck_controls(enabled)

    def settings_to_dict(self) -> dict[str, str | int | float | bool | object]:
        settings = super().settings_to_dict()
        for action, button in self._new_card_action_buttons.items():
            if button.isChecked():
                settings[RawConfigKeys.KNOWN_ENTRY_NEW_CARD_ACTION] = action
                break
        else:
            settings[RawConfigKeys.KNOWN_ENTRY_NEW_CARD_ACTION] = "move"
        settings[RawConfigKeys.RECALC_OFFSET_PRIORITY_DECKS] = (
            self._get_priority_decks_from_ui()
        )
        return settings

    def _on_priority_deck_selection_changed(self, _row: int) -> None:
        self._update_priority_deck_controls()

    def _update_priority_deck_controls(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = (
                self.ui.shiftNewCardsCheckBox.checkState()
                != Qt.CheckState.Unchecked
            )

        self._priority_deck_list_widget.setEnabled(enabled)
        self._priority_deck_refresh_button.setEnabled(enabled)

        current_row = self._priority_deck_list_widget.currentRow()
        count = self._priority_deck_list_widget.count()

        self._priority_deck_move_up_button.setEnabled(enabled and current_row > 0)
        self._priority_deck_move_down_button.setEnabled(
            enabled and current_row != -1 and current_row < count - 1
        )

    def _move_priority_deck_up(self) -> None:
        self._move_priority_deck(-1)

    def _move_priority_deck_down(self) -> None:
        self._move_priority_deck(1)

    def _move_priority_deck(self, offset: int) -> None:
        current_row = self._priority_deck_list_widget.currentRow()
        if current_row == -1:
            return

        new_row = current_row + offset
        if new_row < 0 or new_row >= self._priority_deck_list_widget.count():
            return

        item = self._priority_deck_list_widget.takeItem(current_row)
        if item is None:
            return

        self._priority_deck_list_widget.insertItem(new_row, item)
        self._priority_deck_list_widget.setCurrentRow(new_row)
        self._update_priority_deck_controls()

    def _refresh_priority_decks(self) -> None:
        preferred_order = self._get_priority_decks_from_ui()
        deck_order = self._build_priority_deck_list(self._config, preferred_order)
        self._set_priority_deck_items(deck_order)

    def _build_priority_deck_list(
        self,
        source_config: PrioritySieveConfig,
        preferred_order: list[str] | None = None,
    ) -> list[str]:
        available_decks = self._get_available_decks_for_note_types(source_config)
        if preferred_order is None:
            preferred_order = source_config.recalc_offset_priority_decks

        ordered: list[str] = []
        seen: set[str] = set()

        for deck_name in preferred_order:
            if deck_name in available_decks and deck_name not in seen:
                ordered.append(deck_name)
                seen.add(deck_name)

        for deck_name in available_decks:
            if deck_name not in seen:
                ordered.append(deck_name)
                seen.add(deck_name)

        return ordered

    def _set_priority_deck_items(self, deck_names: list[str]) -> None:
        current_item = self._priority_deck_list_widget.currentItem()
        current_text = current_item.text() if current_item is not None else None

        self._priority_deck_list_widget.clear()
        for deck_name in deck_names:
            self._priority_deck_list_widget.addItem(deck_name)

        if deck_names:
            if current_text in deck_names:
                target_row = deck_names.index(current_text)
            else:
                target_row = 0
            self._priority_deck_list_widget.setCurrentRow(target_row)
        else:
            self._priority_deck_list_widget.setCurrentRow(-1)

        self._update_priority_deck_controls()

    def _get_priority_decks_from_ui(self) -> list[str]:
        decks: list[str] = []
        for index in range(self._priority_deck_list_widget.count()):
            item = self._priority_deck_list_widget.item(index)
            if item is None:
                continue
            deck_name = item.text().strip()
            if deck_name:
                decks.append(deck_name)
        return decks

    def _get_available_decks_for_note_types(
        self, config: PrioritySieveConfig
    ) -> list[str]:
        if mw is None or mw.col is None or mw.col.db is None:
            return []

        note_type_names = {
            config_filter.note_type
            for config_filter in config.filters
            if config_filter.note_type != ps_globals.NONE_OPTION
        }

        if not note_type_names:
            return []

        note_type_ids: list[int] = []
        for note_type_name in note_type_names:
            note_type_id = mw.col.models.id_for_name(note_type_name)
            if note_type_id is not None:
                note_type_ids.append(note_type_id)

        if not note_type_ids:
            return []

        placeholders = ",".join("?" for _ in note_type_ids)
        query = f"""
            SELECT DISTINCT c.did
            FROM cards c
            JOIN notes n ON c.nid = n.id
            WHERE n.mid IN ({placeholders})
        """

        deck_ids = mw.col.db.list(query, *note_type_ids)
        if deck_ids is None:
            return []

        deck_names: set[str] = set()
        for deck_id in deck_ids:
            deck_dict = mw.col.decks.get(deck_id)
            if deck_dict is None:
                continue

            deck_name = deck_dict.get("name")
            if isinstance(deck_name, str):
                deck_names.add(deck_name)

        return sorted(deck_names)

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default skip settings?"
