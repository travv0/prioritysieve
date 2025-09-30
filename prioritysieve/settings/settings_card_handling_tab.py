from __future__ import annotations

from aqt.qt import (  # pylint:disable=no-name-in-module
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    Qt,
)

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

        self._raw_config_key_to_line_edit: dict[str, QLineEdit] = {
            RawConfigKeys.RECALC_OFFSET_PRIORITY_DECK: self.ui.priorityDeckLineEdit,
        }

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

        self._toggle_disable_shift_cards_settings()

    def setup_buttons(self) -> None:
        self.ui.restoreCardHandlingPushButton.setAutoDefault(False)
        self.ui.restoreCardHandlingPushButton.clicked.connect(self.restore_defaults)

        self.ui.shiftNewCardsCheckBox.stateChanged.connect(
            self._toggle_disable_shift_cards_settings
        )

    def _toggle_disable_shift_cards_settings(self) -> None:
        if self.ui.shiftNewCardsCheckBox.checkState() == Qt.CheckState.Unchecked:
            self.ui.dueOffsetSpinBox.setDisabled(True)
            self.ui.offsetFirstMorphsSpinBox.setDisabled(True)
            self.ui.priorityDeckLineEdit.setDisabled(True)
        else:
            self.ui.dueOffsetSpinBox.setEnabled(True)
            self.ui.offsetFirstMorphsSpinBox.setEnabled(True)
            self.ui.priorityDeckLineEdit.setEnabled(True)



    def settings_to_dict(self) -> dict[str, str | int | float | bool | object]:
        settings = super().settings_to_dict()
        for action, button in self._new_card_action_buttons.items():
            if button.isChecked():
                settings[RawConfigKeys.KNOWN_ENTRY_NEW_CARD_ACTION] = action
                break
        else:
            settings[RawConfigKeys.KNOWN_ENTRY_NEW_CARD_ACTION] = "move"
        return settings

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default skip settings?"
