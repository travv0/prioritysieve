from __future__ import annotations

from aqt.qt import QCheckBox, QDialog  # pylint:disable=no-name-in-module

from ..prioritysieve_config import (
    LANGUAGE_TYPE_JAPANESE,
    PrioritySieveConfig,
    PrioritySieveLanguageConfig,
    RawConfigKeys,
)
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
        language_config: PrioritySieveLanguageConfig | None = None,
        default_language_config: PrioritySieveLanguageConfig | None = None,
    ) -> None:
        super().__init__(
            parent,
            ui,
            config,
            default_config,
            language_config,
            default_language_config,
        )

        self._raw_config_key_to_check_box: dict[str, QCheckBox] = {
            RawConfigKeys.RECALC_AFTER_SYNC: self.ui.recalcAfterSyncCheckBox,
            RawConfigKeys.HIDE_RECALC_TOOLBAR: self.ui.hideRecalcCheckBox,
            RawConfigKeys.HIDE_TRACKED_COUNTER: self.ui.hideTrackedCheckBox,
            RawConfigKeys.HIDE_REVIEWED_COUNTER: self.ui.hideReviewedCheckBox,
            RawConfigKeys.DEDUPLICATE_TOOLBAR_COUNTS: self.ui.deduplicateToolbarCountsCheckBox,
            RawConfigKeys.DISABLE_STATS_GRAPH: self.ui.disableStatsGraphCheckBox,
            RawConfigKeys.AUTO_SUSPEND_VARIANT_SPELLINGS: self.ui.autoSuspendKanjiSubsetCheckBox,
            RawConfigKeys.MERGE_KANA_VARIANT_SPELLINGS: self.ui.mergeKanaVariantsCheckBox,
        }

        self._raw_config_key_to_spin_box = {}

        # Hide the pending checkbox since pending is no longer shown in toolbar
        self.ui.hidePendingCheckBox.hide()

        self.populate()
        self.setup_buttons()
        self.update_previous_state()

        # Hide Japanese-specific options for non-Japanese languages
        self._update_japanese_options_visibility()

    def populate(self, use_default_config: bool = False) -> None:
        super().populate(use_default_config)

    def setup_buttons(self) -> None:
        self.ui.restoreGeneralPushButton.setAutoDefault(False)
        self.ui.restoreGeneralPushButton.clicked.connect(self.restore_defaults)

    def _update_japanese_options_visibility(self) -> None:
        """Hide Japanese-specific options when language type is not Japanese."""
        is_japanese = (
            self._language_config is not None
            and self._language_config.language_type == LANGUAGE_TYPE_JAPANESE
        )

        # Japanese-specific checkboxes
        self.ui.autoSuspendKanjiSubsetCheckBox.setVisible(is_japanese)
        self.ui.mergeKanaVariantsCheckBox.setVisible(is_japanese)

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default general settings?"
