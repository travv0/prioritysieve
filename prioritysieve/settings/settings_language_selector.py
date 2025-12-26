from __future__ import annotations

from typing import Callable

import aqt
from aqt import mw
from aqt.qt import (  # pylint:disable=no-name-in-module
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QComboBox,
)

from .. import message_box_utils, prioritysieve_globals
from ..prioritysieve_config import (
    LANGUAGE_TYPE_JAPANESE,
    LANGUAGE_TYPE_OTHER,
    PrioritySieveConfig,
    RawConfigKeys,
    RawConfigLanguageKeys,
    get_config_dict,
    update_configs,
)


class LanguageSelectorDialog(QDialog):
    """Dialog for selecting and managing language profiles."""

    def __init__(self, on_language_selected: Callable[[str], None] | None = None) -> None:
        super().__init__(parent=mw)
        self._on_language_selected = on_language_selected
        self._init_ui()
        self._refresh_language_list()

    def _init_ui(self) -> None:
        self.setWindowTitle("PrioritySieve - Language Profiles")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)

        # Instructions label
        label = QLabel("Select a language profile to configure:")
        layout.addWidget(label)

        # Language list
        self._language_list = QListWidget()
        self._language_list.itemDoubleClicked.connect(self._on_open_settings)
        layout.addWidget(self._language_list)

        # Buttons layout
        buttons_layout = QHBoxLayout()

        self._open_btn = QPushButton("Open Settings")
        self._open_btn.clicked.connect(self._on_open_settings)
        buttons_layout.addWidget(self._open_btn)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.clicked.connect(self._on_edit_language)
        buttons_layout.addWidget(self._edit_btn)

        self._new_btn = QPushButton("New")
        self._new_btn.clicked.connect(self._on_new_language)
        buttons_layout.addWidget(self._new_btn)

        self._clone_btn = QPushButton("Clone")
        self._clone_btn.clicked.connect(self._on_clone_language)
        buttons_layout.addWidget(self._clone_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete_language)
        buttons_layout.addWidget(self._delete_btn)

        layout.addLayout(buttons_layout)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _refresh_language_list(self) -> None:
        self._language_list.clear()
        config = PrioritySieveConfig()
        for lang in config.languages:
            display_text = lang.name
            if lang.prefix:
                display_text += f" [{lang.prefix}]"
            display_text += f" ({lang.language_type})"
            item = QListWidgetItem(display_text)
            item.setData(256, lang.name)  # Qt.UserRole = 256
            self._language_list.addItem(item)

        # Select first item if available
        if self._language_list.count() > 0:
            self._language_list.setCurrentRow(0)

        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = self._language_list.currentItem() is not None
        has_languages = self._language_list.count() > 0

        self._open_btn.setEnabled(has_selection)
        self._edit_btn.setEnabled(has_selection)
        self._clone_btn.setEnabled(has_selection)
        # Always allow at least one language to exist
        self._delete_btn.setEnabled(has_selection and self._language_list.count() > 1)

    def _get_selected_language_name(self) -> str | None:
        item = self._language_list.currentItem()
        if item is None:
            return None
        return item.data(256)  # Qt.UserRole

    def _on_open_settings(self) -> None:
        lang_name = self._get_selected_language_name()
        if lang_name is None:
            return

        self.accept()

        if self._on_language_selected:
            self._on_language_selected(lang_name)

    def _on_edit_language(self) -> None:
        lang_name = self._get_selected_language_name()
        if lang_name is None:
            return

        config = PrioritySieveConfig()
        lang = config.get_language(lang_name)
        if lang is None:
            return

        dialog = EditLanguageDialog(
            self,
            current_name=lang.name,
            current_prefix=lang.prefix,
            current_language_type=lang.language_type,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.get_name()
            new_prefix = dialog.get_prefix()
            new_language_type = dialog.get_language_type()

            # Check for duplicate name (if name changed)
            if new_name != lang_name:
                for other_lang in config.languages:
                    if other_lang.name == new_name:
                        QMessageBox.warning(
                            self,
                            "Duplicate Name",
                            f"A language profile named '{new_name}' already exists.",
                        )
                        return

            # Update the language
            self._update_language(lang_name, new_name, new_prefix, new_language_type)
            self._refresh_language_list()

    def _update_language(
        self, old_name: str, new_name: str, new_prefix: str, new_language_type: str
    ) -> None:
        config_dict = get_config_dict()
        languages = config_dict.get(RawConfigKeys.LANGUAGES, [])

        for lang in languages:
            if lang.get(RawConfigLanguageKeys.NAME) == old_name:
                lang[RawConfigLanguageKeys.NAME] = new_name
                lang[RawConfigLanguageKeys.PREFIX] = new_prefix
                lang[RawConfigLanguageKeys.LANGUAGE_TYPE] = new_language_type
                break

        update_configs({RawConfigKeys.LANGUAGES: languages})

    def _on_new_language(self) -> None:
        dialog = NewLanguageDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_name()
            prefix = dialog.get_prefix()
            language_type = dialog.get_language_type()

            # Check for duplicate name
            config = PrioritySieveConfig()
            for lang in config.languages:
                if lang.name == name:
                    QMessageBox.warning(
                        self,
                        "Duplicate Name",
                        f"A language profile named '{name}' already exists.",
                    )
                    return

            # Add new language to config
            self._add_language(name, prefix, language_type)
            self._refresh_language_list()

    def _on_clone_language(self) -> None:
        source_name = self._get_selected_language_name()
        if source_name is None:
            return

        # Get new name
        name, ok = QInputDialog.getText(
            self,
            "Clone Language",
            "Enter name for the cloned language profile:",
            QLineEdit.EchoMode.Normal,
            f"{source_name} (Copy)",
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Check for duplicate
        config = PrioritySieveConfig()
        for lang in config.languages:
            if lang.name == name:
                QMessageBox.warning(
                    self,
                    "Duplicate Name",
                    f"A language profile named '{name}' already exists.",
                )
                return

        # Clone the language
        self._clone_language(source_name, name)
        self._refresh_language_list()

    def _on_delete_language(self) -> None:
        lang_name = self._get_selected_language_name()
        if lang_name is None:
            return

        # Check for note types using this language
        config = PrioritySieveConfig()
        lang = config.get_language(lang_name)
        if lang is None:
            return

        note_type_count = sum(
            1
            for flt in lang.filters
            if flt.note_type != prioritysieve_globals.NONE_OPTION
        )

        warning_text = f"Are you sure you want to delete the language profile '{lang_name}'?"
        if note_type_count > 0:
            warning_text += (
                f"\n\nThis language has {note_type_count} note type(s) configured. "
                "Deleting will remove these configurations."
            )

        confirmed = message_box_utils.show_warning_box(
            "Delete Language",
            warning_text,
            parent=self,
        )

        if confirmed:
            self._delete_language(lang_name)
            self._refresh_language_list()

    def _add_language(self, name: str, prefix: str, language_type: str) -> None:
        config_dict = get_config_dict()
        languages = config_dict.get(RawConfigKeys.LANGUAGES, [])

        # Get default filter structure from first language
        default_filter = {
            "note_type": "(none)",
            "tags": {"include": [], "exclude": []},
            "field": "(none)",
            "furigana_field": "(none)",
            "reading_field": "(none)",
            "reading_priority": "Furigana first",
            "priority_files": [],
            "read": True,
            "modify": True,
            "extra_reading_field": False,
            "duplicate_sort_field": "(none)",
            "duplicate_sort_numeric": False,
        }

        new_language = {
            RawConfigLanguageKeys.NAME: name,
            RawConfigLanguageKeys.PREFIX: prefix,
            RawConfigLanguageKeys.LANGUAGE_TYPE: language_type,
            RawConfigLanguageKeys.FILTERS: [default_filter],
            RawConfigLanguageKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS: False,
            RawConfigLanguageKeys.PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS: False,
            RawConfigLanguageKeys.PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS: False,
            RawConfigLanguageKeys.PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS: False,
            RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS: False,
            RawConfigLanguageKeys.PREPROCESS_IGNORE_CUSTOM_CHARACTERS: False,
            RawConfigLanguageKeys.PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE: "",
            RawConfigLanguageKeys.PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS: "",
            RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES: False,
            RawConfigLanguageKeys.AUTO_SUSPEND_VARIANT_SPELLINGS: False,
            RawConfigLanguageKeys.MERGE_KANA_VARIANT_SPELLINGS: False,
            RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS: [],
            RawConfigLanguageKeys.DISABLED_DECKS: [],
            RawConfigLanguageKeys.HIDE_RECALC_TOOLBAR: False,
            RawConfigLanguageKeys.HIDE_REVIEWED_COUNTER: False,
            RawConfigLanguageKeys.HIDE_TRACKED_COUNTER: False,
            RawConfigLanguageKeys.HIDE_PENDING_COUNTER: False,
            RawConfigLanguageKeys.DEDUPLICATE_TOOLBAR_COUNTS: False,
        }

        languages.append(new_language)
        update_configs({RawConfigKeys.LANGUAGES: languages})

    def _clone_language(self, source_name: str, new_name: str) -> None:
        import copy

        config_dict = get_config_dict()
        languages = config_dict.get(RawConfigKeys.LANGUAGES, [])

        source_lang = None
        for lang in languages:
            if lang.get(RawConfigLanguageKeys.NAME) == source_name:
                source_lang = lang
                break

        if source_lang is None:
            return

        cloned = copy.deepcopy(source_lang)
        cloned[RawConfigLanguageKeys.NAME] = new_name

        # Clear note types from filters to avoid duplicates across languages
        # Note types must belong to only one language
        if RawConfigLanguageKeys.FILTERS in cloned:
            for flt in cloned[RawConfigLanguageKeys.FILTERS]:
                flt["note_type"] = "(none)"
                flt["field"] = "(none)"
                flt["furigana_field"] = "(none)"
                flt["reading_field"] = "(none)"
                flt["duplicate_sort_field"] = "(none)"

        languages.append(cloned)
        update_configs({RawConfigKeys.LANGUAGES: languages})

    def _delete_language(self, lang_name: str) -> None:
        config_dict = get_config_dict()
        languages = config_dict.get(RawConfigKeys.LANGUAGES, [])

        languages = [
            lang
            for lang in languages
            if lang.get(RawConfigLanguageKeys.NAME) != lang_name
        ]

        update_configs({RawConfigKeys.LANGUAGES: languages})


class NewLanguageDialog(QDialog):
    """Dialog for creating a new language profile."""

    def __init__(self, parent: QDialog) -> None:
        super().__init__(parent=parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("New Language Profile")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Japanese")
        name_layout.addWidget(self._name_edit)
        layout.addLayout(name_layout)

        # Prefix input
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self._prefix_edit = QLineEdit()
        self._prefix_edit.setPlaceholderText("e.g., JP (shown on toolbar)")
        self._prefix_edit.setMaxLength(10)
        prefix_layout.addWidget(self._prefix_edit)
        layout.addLayout(prefix_layout)

        # Language type dropdown
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItem("Japanese", LANGUAGE_TYPE_JAPANESE)
        self._type_combo.addItem("Other", LANGUAGE_TYPE_OTHER)
        type_layout.addWidget(self._type_combo)
        layout.addLayout(type_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        ok_btn = QPushButton("Create")
        ok_btn.clicked.connect(self._on_ok)
        buttons_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def _on_ok(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a name.")
            return
        self.accept()

    def get_name(self) -> str:
        return self._name_edit.text().strip()

    def get_prefix(self) -> str:
        return self._prefix_edit.text().strip()

    def get_language_type(self) -> str:
        return self._type_combo.currentData()


class EditLanguageDialog(QDialog):
    """Dialog for editing an existing language profile."""

    def __init__(
        self,
        parent: QDialog,
        current_name: str,
        current_prefix: str,
        current_language_type: str,
    ) -> None:
        super().__init__(parent=parent)
        self._current_name = current_name
        self._current_prefix = current_prefix
        self._current_language_type = current_language_type
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Edit Language Profile")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setText(self._current_name)
        name_layout.addWidget(self._name_edit)
        layout.addLayout(name_layout)

        # Prefix input
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self._prefix_edit = QLineEdit()
        self._prefix_edit.setText(self._current_prefix)
        self._prefix_edit.setPlaceholderText("e.g., JP (shown on toolbar)")
        self._prefix_edit.setMaxLength(10)
        prefix_layout.addWidget(self._prefix_edit)
        layout.addLayout(prefix_layout)

        # Language type dropdown
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItem("Japanese", LANGUAGE_TYPE_JAPANESE)
        self._type_combo.addItem("Other", LANGUAGE_TYPE_OTHER)

        # Set current type
        if self._current_language_type == LANGUAGE_TYPE_JAPANESE:
            self._type_combo.setCurrentIndex(0)
        else:
            self._type_combo.setCurrentIndex(1)

        type_layout.addWidget(self._type_combo)
        layout.addLayout(type_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.clicked.connect(self._on_ok)
        buttons_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def _on_ok(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a name.")
            return
        self.accept()

    def get_name(self) -> str:
        return self._name_edit.text().strip()

    def get_prefix(self) -> str:
        return self._prefix_edit.text().strip()

    def get_language_type(self) -> str:
        return self._type_combo.currentData()
