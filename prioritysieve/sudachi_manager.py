from __future__ import annotations

from typing import Callable

import aqt
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (  # pylint:disable=no-name-in-module
    QColor,
    QDialog,
    QIcon,
    QListWidgetItem,
    QPixmap,
    QStyle,
    Qt,
)
from aqt.utils import tooltip

from . import prioritysieve_globals as am_globals
from . import message_box_utils
from .extra_settings import extra_settings_keys
from .extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from .morphemizers import sudachi_wrapper
from .ui.sudachi_manager_dialog_ui import Ui_SudachiManagerDialog


class SudachiManagerDialog(QDialog):
    def __init__(self) -> None:
        assert mw is not None

        super().__init__(parent=None)
        self.ui = Ui_SudachiManagerDialog()  # pylint:disable=invalid-name
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self._variant_labels: dict[str, str] = {
            "small": "small (minimal)",
            "core": "core (recommended)",
            "full": "full (largest)",
        }

        self._setup_icons()
        self._setup_buttons()
        self._setup_lists()
        self._refresh()

        self.am_extra_settings = PrioritySieveExtraSettings()
        self.am_extra_settings.beginGroup(
            extra_settings_keys.Dialogs.SUDACHI_MANAGER_WINDOW
        )
        self._setup_geometry()
        self.am_extra_settings.endGroup()

        self.show()

    def _setup_icons(self) -> None:
        style: QStyle | None = self.style()
        assert style is not None

        transparent_pixmap = QPixmap(16, 16)
        transparent_pixmap.fill(QColor(0, 0, 0, 0))

        self.transparent_icon = QIcon(transparent_pixmap)
        self.apply_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)

    def _setup_buttons(self) -> None:
        self.ui.installSudachiButton.setAutoDefault(False)
        self.ui.removeSudachiButton.setAutoDefault(False)
        self.ui.installDictionaryButton.setAutoDefault(False)
        self.ui.removeDictionaryButton.setAutoDefault(False)

        self.ui.installSudachiButton.clicked.connect(self._on_install_sudachi_clicked)
        self.ui.removeSudachiButton.clicked.connect(self._on_remove_sudachi_clicked)
        self.ui.installDictionaryButton.clicked.connect(
            self._on_install_dictionary_clicked
        )
        self.ui.removeDictionaryButton.clicked.connect(
            self._on_remove_dictionary_clicked
        )

        self.ui.installDictionaryButton.setDisabled(True)
        self.ui.removeDictionaryButton.setDisabled(True)

    def _setup_lists(self) -> None:
        self.ui.dictionariesListWidget.clear()

        for variant in sudachi_wrapper.SUDACHI_DICTIONARY_VARIANTS:
            label = self._variant_labels.get(variant, variant)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, variant)
            self.ui.dictionariesListWidget.addItem(item)

        self.ui.dictionariesListWidget.currentItemChanged.connect(
            self._toggle_dictionary_action_buttons
        )

    def _refresh(self) -> None:
        self._update_status_label()
        self._populate_dictionary_icons()
        self._toggle_dictionary_action_buttons(
            self.ui.dictionariesListWidget.currentItem(), None
        )

    def _update_status_label(self) -> None:
        if sudachi_wrapper.is_sudachipy_installed():
            text = "SudachiPy is installed"
            self.ui.installSudachiButton.setDisabled(True)
            self.ui.removeSudachiButton.setEnabled(True)
        else:
            text = "SudachiPy is not installed"
            self.ui.installSudachiButton.setEnabled(True)
            self.ui.removeSudachiButton.setDisabled(True)
        self.ui.sudachiStatusLabel.setText(text)

    def _populate_dictionary_icons(self) -> None:
        installed_variants = set(sudachi_wrapper.list_installed_dictionary_variants())

        for index in range(self.ui.dictionariesListWidget.count()):
            item = self.ui.dictionariesListWidget.item(index)
            variant = item.data(Qt.ItemDataRole.UserRole)
            if variant in installed_variants:
                item.setIcon(self.apply_icon)
            else:
                item.setIcon(self.transparent_icon)

    def _toggle_dictionary_action_buttons(
        self,
        current_item: QListWidgetItem | None,
        _previous_item: QListWidgetItem | None,
    ) -> None:
        if current_item is None:
            self.ui.installDictionaryButton.setDisabled(True)
            self.ui.removeDictionaryButton.setDisabled(True)
            return

        variant = current_item.data(Qt.ItemDataRole.UserRole)
        installed_variants = set(sudachi_wrapper.list_installed_dictionary_variants())

        if variant in installed_variants:
            self.ui.installDictionaryButton.setDisabled(True)
            self.ui.removeDictionaryButton.setEnabled(True)
        else:
            self.ui.installDictionaryButton.setEnabled(True)
            self.ui.removeDictionaryButton.setDisabled(True)

    def _on_install_sudachi_clicked(self) -> None:
        title = "Install SudachiPy"
        body = "Download and install SudachiPy?"
        if not message_box_utils.show_warning_box(title=title, body=body, parent=self):
            return

        def _on_success() -> None:
            mw.progress.finish()
            tooltip("Please restart Anki", period=5000, parent=self)
            self._refresh()

        self.ui.installSudachiButton.setDisabled(True)
        mw.progress.start(label="Installing SudachiPy")

        operation = QueryOp(
            parent=self,
            op=lambda _: sudachi_wrapper.install_sudachipy(),
            success=lambda _: _on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _on_remove_sudachi_clicked(self) -> None:
        title = "Remove SudachiPy"
        body = "Uninstall SudachiPy and all Sudachi dictionaries?"
        if not message_box_utils.show_warning_box(title=title, body=body, parent=self):
            return

        def _on_success() -> None:
            mw.progress.finish()
            tooltip("SudachiPy removed", period=4000, parent=self)
            self._refresh()

        mw.progress.start(label="Removing SudachiPy")
        operation = QueryOp(
            parent=self,
            op=lambda _: sudachi_wrapper.uninstall_sudachipy(),
            success=lambda _: _on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _on_install_dictionary_clicked(self) -> None:
        current_item = self.ui.dictionariesListWidget.currentItem()
        assert current_item is not None

        variant = current_item.data(Qt.ItemDataRole.UserRole)
        label = current_item.text()

        title = "Install dictionary"
        body = f"Download and install the {label} dictionary?"
        if not message_box_utils.show_warning_box(title=title, body=body, parent=self):
            return

        def _on_success() -> None:
            mw.progress.finish()
            tooltip(
                f"Installed Sudachi dictionary: {label}", period=4000, parent=self
            )
            self._refresh()

        mw.progress.start(label=f"Installing {label}")
        operation = QueryOp(
            parent=self,
            op=lambda _: sudachi_wrapper.install_dictionary(variant),
            success=lambda _: _on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _on_remove_dictionary_clicked(self) -> None:
        current_item = self.ui.dictionariesListWidget.currentItem()
        assert current_item is not None

        variant = current_item.data(Qt.ItemDataRole.UserRole)
        label = current_item.text()

        title = "Remove dictionary"
        body = f"Remove the installed {label} dictionary?"
        if not message_box_utils.show_warning_box(title=title, body=body, parent=self):
            return

        def _on_success() -> None:
            mw.progress.finish()
            tooltip(
                f"Removed Sudachi dictionary: {label}", period=4000, parent=self
            )
            self._refresh()

        mw.progress.start(label=f"Removing {label}")
        operation = QueryOp(
            parent=self,
            op=lambda _: sudachi_wrapper.remove_dictionary(variant),
            success=lambda _: _on_success(),
        )
        operation.failure(self._on_failure)
        operation.with_progress().run_in_background()

    def _setup_geometry(self) -> None:
        stored_geometry = self.am_extra_settings.value(
            extra_settings_keys.SudachiManagerWindowKeys.WINDOW_GEOMETRY
        )
        if stored_geometry is not None:
            self.restoreGeometry(stored_geometry)

    def _on_failure(self, failure: Exception) -> None:
        mw.progress.finish()
        message_box_utils.show_error_box(
            title="Error",
            body=f"{failure}",
            parent=self,
        )
        self._refresh()

    def closeWithCallback(  # pylint:disable=invalid-name
        self, callback: Callable[[], None]
    ) -> None:
        self.am_extra_settings.sudachi_manager_window_settings(
            geometry=self.saveGeometry()
        )
        self.close()
        aqt.dialogs.markClosed(am_globals.SUDACHI_MANAGER_DIALOG_NAME)
        callback()

    def reopen(self) -> None:
        self.show()
