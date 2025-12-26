from __future__ import annotations

from aqt.qt import QDialog, QLineEdit  # pylint:disable=no-name-in-module

from ..prioritysieve_config import (
    PrioritySieveConfig,
    PrioritySieveLanguageConfig,
    RawConfigKeys,
)
from ..ui.settings_dialog_ui import Ui_SettingsDialog
from .settings_tab import SettingsTab


class TagsTab(SettingsTab):

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

        self._raw_config_key_to_line_edit: dict[str, QLineEdit] = {
            RawConfigKeys.TAG_READY: self.ui.tagReadyLineEdit,
            RawConfigKeys.TAG_NOT_READY: self.ui.tagNotReadyLineEdit,
            RawConfigKeys.TAG_KNOWN_MANUALLY: self.ui.tagKnownManuallyLineEdit,
            RawConfigKeys.TAG_SUSPENDED_AUTOMATICALLY: self.ui.tagSuspendedAutomaticallyLineEdit,
        }
        self.populate()
        self.setup_buttons()
        self.update_previous_state()

    def setup_buttons(self) -> None:
        self.ui.restoreTagsPushButton.setAutoDefault(False)
        self.ui.restoreTagsPushButton.clicked.connect(self.restore_defaults)

    def get_confirmation_text(self) -> str:
        return "Are you sure you want to restore default tags settings?"
