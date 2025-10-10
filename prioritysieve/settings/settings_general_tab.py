from __future__ import annotations

from aqt.qt import QCheckBox, QDialog  # pylint:disable=no-name-in-module

from ..prioritysieve_config import PrioritySieveConfig, RawConfigKeys
from ..ui.settings_dialog_ui import Ui_SettingsDialog
from .settings_tab import SettingsTab


class GeneralTab(SettingsTab):
    """General settings excluding legacy morph evaluation controls."""

    def __init__(
        self,
        parent: QDialog,
        ui: Ui_SettingsDialog,
        config: PrioritySieveConfig,
        default_config: PrioritySieveConfig,
    ) -> None:
        super().__init__(parent, ui, config, default_config)

        self._raw_config_key_to_check_box: dict[str, QCheckBox] = {
            RawConfigKeys.RECALC_AFTER_SYNC: self.ui.recalcAfterSyncCheckBox,
            RawConfigKeys.HIDE_RECALC_TOOLBAR: self.ui.hideRecalcCheckBox,
            RawConfigKeys.HIDE_TRACKED_COUNTER: self.ui.hideTrackedCheckBox,
            RawConfigKeys.HIDE_REVIEWED_COUNTER: self.ui.hideReviewedCheckBox,
            RawConfigKeys.HIDE_PENDING_COUNTER: self.ui.hidePendingCheckBox,
        }

        self._raw_config_key_to_spin_box = {}

        self.populate()
        self.setup_buttons()
        self.update_previous_state()

    def populate(self, use_default_config: bool = False) -> None:
        super().populate(use_default_config)

    def setup_buttons(self) -> None:
        self.ui.restoreGeneralPushButton.setAutoDefault(False)
        self.ui.restoreGeneralPushButton.clicked.connect(self.restore_defaults)

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default general settings?"
