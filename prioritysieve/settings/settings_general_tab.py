from __future__ import annotations

from aqt.qt import (  # pylint:disable=no-name-in-module
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QRadioButton,
    QSpinBox,
)

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

        # Hide the deprecated morph evaluation controls.
        self.ui.groupBox_4.hide()

        self._raw_config_key_to_radio_button: dict[str, QRadioButton] = {
            RawConfigKeys.TOOLBAR_STATS_USE_SEEN: self.ui.toolbarStatsUseSeenRadioButton,
            RawConfigKeys.TOOLBAR_STATS_USE_KNOWN: self.ui.toolbarStatsUseKnownRadioButton,
        }

        self._raw_config_key_to_check_box: dict[str, QCheckBox] = {
            RawConfigKeys.RECALC_ON_SYNC: self.ui.recalcBeforeSyncCheckBox,
            RawConfigKeys.READ_KNOWN_MORPHS_FOLDER: self.ui.recalcReadKnownMorphsFolderCheckBox,
            RawConfigKeys.HIDE_RECALC_TOOLBAR: self.ui.hideRecalcCheckBox,
            RawConfigKeys.HIDE_LEMMA_TOOLBAR: self.ui.hideLemmaCheckBox,
            RawConfigKeys.HIDE_INFLECTION_TOOLBAR: self.ui.hideInflectionCheckBox,
        }

        self._raw_config_key_to_spin_box: dict[str, QSpinBox | QDoubleSpinBox] = {
            RawConfigKeys.INTERVAL_FOR_KNOWN_MORPHS: self.ui.recalcIntervalSpinBox,
        }

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
