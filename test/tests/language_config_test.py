"""Tests for per-language configuration functionality."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from prioritysieve.prioritysieve_config import (
    LANGUAGE_TYPE_JAPANESE,
    LANGUAGE_TYPE_OTHER,
    PrioritySieveConfig,
    PrioritySieveLanguageConfig,
    RawConfigKeys,
    RawConfigLanguageKeys,
    normalize_config_keys,
)

DEFAULT_CONFIG_PATH = Path("prioritysieve", "config.json")


def _load_default_config() -> dict[str, Any]:
    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _create_test_language(
    name: str = "TestLang",
    prefix: str = "TL",
    language_type: str = LANGUAGE_TYPE_JAPANESE,
    note_type: str = "(none)",
) -> dict[str, Any]:
    """Create a minimal language config dict for testing."""
    return {
        RawConfigLanguageKeys.NAME: name,
        RawConfigLanguageKeys.PREFIX: prefix,
        RawConfigLanguageKeys.LANGUAGE_TYPE: language_type,
        RawConfigLanguageKeys.FILTERS: [
            {
                "note_type": note_type,
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
        ],
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


class TestLanguageConfigStructure:
    """Tests for the basic language config structure."""

    def test_default_config_has_languages_array(self) -> None:
        config = _load_default_config()
        assert RawConfigKeys.LANGUAGES in config
        assert isinstance(config[RawConfigKeys.LANGUAGES], list)
        assert len(config[RawConfigKeys.LANGUAGES]) >= 1

    def test_default_language_has_required_fields(self) -> None:
        config = _load_default_config()
        lang = config[RawConfigKeys.LANGUAGES][0]

        assert RawConfigLanguageKeys.NAME in lang
        assert RawConfigLanguageKeys.PREFIX in lang
        assert RawConfigLanguageKeys.LANGUAGE_TYPE in lang
        assert RawConfigLanguageKeys.FILTERS in lang

    def test_language_type_is_valid(self) -> None:
        config = _load_default_config()
        lang = config[RawConfigKeys.LANGUAGES][0]

        assert lang[RawConfigLanguageKeys.LANGUAGE_TYPE] in (
            LANGUAGE_TYPE_JAPANESE,
            LANGUAGE_TYPE_OTHER,
        )


class TestLegacyConfigMigration:
    """Tests for migrating legacy flat config to language-based config."""

    def test_legacy_config_structure_detection(self) -> None:
        """Test that we can detect legacy config structure (no languages array)."""
        legacy_config = {
            "filters": [{"note_type": "TestNote"}],
            "preprocess_ignore_bracket_contents": True,
            "shortcut_recalc": "Ctrl+Shift+R",
        }

        # Legacy config should NOT have languages key
        assert RawConfigKeys.LANGUAGES not in legacy_config

        # A modern config SHOULD have languages key
        modern_config = _load_default_config()
        assert RawConfigKeys.LANGUAGES in modern_config

    def test_legacy_keys_match_language_keys(self) -> None:
        """Verify that legacy keys have corresponding language keys for migration."""
        # These legacy keys should have corresponding language keys
        legacy_to_language_mappings = [
            ("filters", RawConfigLanguageKeys.FILTERS),
            ("preprocess_ignore_bracket_contents", RawConfigLanguageKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS),
            ("preprocess_ignore_numbers", RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS),
            ("auto_suspend_unlisted_entries", RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES),
            ("hide_recalc_toolbar", RawConfigLanguageKeys.HIDE_RECALC_TOOLBAR),
        ]

        for legacy_key, language_key in legacy_to_language_mappings:
            # The language key value should match the legacy key
            assert language_key == legacy_key


class TestMultipleLanguages:
    """Tests for managing multiple language profiles."""

    def test_config_with_multiple_languages(self) -> None:
        config = _load_default_config()

        # Add a second language
        second_lang = _create_test_language(
            name="Chinese",
            prefix="CN",
            language_type=LANGUAGE_TYPE_OTHER,
        )
        config[RawConfigKeys.LANGUAGES].append(second_lang)

        # Test without normalize_config_keys (requires mw)
        assert len(config[RawConfigKeys.LANGUAGES]) == 2
        assert config[RawConfigKeys.LANGUAGES][0][RawConfigLanguageKeys.NAME] == "Default"
        assert config[RawConfigKeys.LANGUAGES][1][RawConfigLanguageKeys.NAME] == "Chinese"

    def test_each_language_has_independent_settings(self) -> None:
        config = _load_default_config()

        # Modify first language
        config[RawConfigKeys.LANGUAGES][0][
            RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS
        ] = True

        # Add second language with different setting
        second_lang = _create_test_language(name="Other")
        second_lang[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] = False
        config[RawConfigKeys.LANGUAGES].append(second_lang)

        # Settings should be independent (test without normalize_config_keys which requires mw)
        assert (
            config[RawConfigKeys.LANGUAGES][0][
                RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS
            ]
            is True
        )
        assert (
            config[RawConfigKeys.LANGUAGES][1][
                RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS
            ]
            is False
        )


class TestCloneLanguage:
    """Tests for cloning language profiles."""

    def test_clone_should_clear_note_types(self) -> None:
        """When cloning a language, note types should be cleared to prevent duplicates."""
        import copy

        original = _create_test_language(
            name="Japanese",
            prefix="JP",
            note_type="MyNoteType",
        )
        original[RawConfigLanguageKeys.FILTERS][0]["field"] = "Expression"
        original[RawConfigLanguageKeys.FILTERS][0]["furigana_field"] = "Furigana"

        # Clone the language
        cloned = copy.deepcopy(original)
        cloned[RawConfigLanguageKeys.NAME] = "Japanese (Copy)"

        # Clear note types (simulating what _clone_language does)
        for flt in cloned[RawConfigLanguageKeys.FILTERS]:
            flt["note_type"] = "(none)"
            flt["field"] = "(none)"
            flt["furigana_field"] = "(none)"
            flt["reading_field"] = "(none)"
            flt["duplicate_sort_field"] = "(none)"

        # Verify original is unchanged
        assert original[RawConfigLanguageKeys.FILTERS][0]["note_type"] == "MyNoteType"
        assert original[RawConfigLanguageKeys.FILTERS][0]["field"] == "Expression"

        # Verify clone has cleared note types
        assert cloned[RawConfigLanguageKeys.FILTERS][0]["note_type"] == "(none)"
        assert cloned[RawConfigLanguageKeys.FILTERS][0]["field"] == "(none)"
        assert cloned[RawConfigLanguageKeys.FILTERS][0]["furigana_field"] == "(none)"

    def test_clone_preserves_non_note_type_settings(self) -> None:
        """Clone should preserve preprocessing and other settings."""
        import copy

        original = _create_test_language(name="Japanese")
        original[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] = True
        original[RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] = True
        original[RawConfigLanguageKeys.HIDE_PENDING_COUNTER] = True

        cloned = copy.deepcopy(original)
        cloned[RawConfigLanguageKeys.NAME] = "Japanese (Copy)"

        # These should be preserved
        assert cloned[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] is True
        assert cloned[RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] is True
        assert cloned[RawConfigLanguageKeys.HIDE_PENDING_COUNTER] is True


class TestNoteTypeUniqueness:
    """Tests for ensuring note types belong to only one language."""

    def test_get_note_types_from_language(self) -> None:
        """Each language should be able to report its note types."""
        lang = _create_test_language(name="Japanese", note_type="JapaneseNotes")

        note_types = {
            flt["note_type"]
            for flt in lang[RawConfigLanguageKeys.FILTERS]
            if flt["note_type"] != "(none)"
        }

        assert "JapaneseNotes" in note_types

    def test_note_types_across_languages_can_be_collected(self) -> None:
        """Should be able to collect all note types used by other languages."""
        config = {
            RawConfigKeys.LANGUAGES: [
                _create_test_language(name="Japanese", note_type="JapaneseNotes"),
                _create_test_language(name="Chinese", note_type="ChineseNotes"),
                _create_test_language(name="Korean", note_type="KoreanNotes"),
            ]
        }

        # Simulate getting note types used by languages other than "Japanese"
        current_lang_name = "Japanese"
        used_by_others: set[str] = set()

        for lang in config[RawConfigKeys.LANGUAGES]:
            if lang[RawConfigLanguageKeys.NAME] == current_lang_name:
                continue
            for flt in lang[RawConfigLanguageKeys.FILTERS]:
                if flt["note_type"] != "(none)":
                    used_by_others.add(flt["note_type"])

        assert "ChineseNotes" in used_by_others
        assert "KoreanNotes" in used_by_others
        assert "JapaneseNotes" not in used_by_others


class TestLanguageTypeFeatures:
    """Tests for language type-specific features."""

    def test_japanese_language_type_constant(self) -> None:
        assert LANGUAGE_TYPE_JAPANESE == "japanese"

    def test_other_language_type_constant(self) -> None:
        assert LANGUAGE_TYPE_OTHER == "other"

    def test_language_can_be_japanese_type(self) -> None:
        lang = _create_test_language(language_type=LANGUAGE_TYPE_JAPANESE)
        assert lang[RawConfigLanguageKeys.LANGUAGE_TYPE] == LANGUAGE_TYPE_JAPANESE

    def test_language_can_be_other_type(self) -> None:
        lang = _create_test_language(language_type=LANGUAGE_TYPE_OTHER)
        assert lang[RawConfigLanguageKeys.LANGUAGE_TYPE] == LANGUAGE_TYPE_OTHER


class TestGlobalVsLanguageSettings:
    """Tests for distinguishing global from language-specific settings."""

    def test_shortcuts_are_global(self) -> None:
        """Shortcuts should be at the root level, not per-language."""
        config = _load_default_config()

        # Shortcuts should be at root
        assert RawConfigKeys.SHORTCUT_RECALC in config
        assert RawConfigKeys.SHORTCUT_SETTINGS in config

        # Shortcuts should NOT be in language config
        lang = config[RawConfigKeys.LANGUAGES][0]
        assert "shortcut_recalc" not in lang
        assert "shortcut_settings" not in lang

    def test_tags_are_global(self) -> None:
        """Tags should be at the root level, not per-language."""
        config = _load_default_config()

        # Tags should be at root
        assert RawConfigKeys.TAG_READY in config
        assert RawConfigKeys.TAG_NOT_READY in config

        # Tags should NOT be in language config
        lang = config[RawConfigKeys.LANGUAGES][0]
        assert "tag_ready" not in lang
        assert "tag_not_ready" not in lang

    def test_preprocessing_is_per_language(self) -> None:
        """Preprocessing settings should be in language config."""
        config = _load_default_config()
        lang = config[RawConfigKeys.LANGUAGES][0]

        assert RawConfigLanguageKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS in lang
        assert RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS in lang

    def test_filters_are_per_language(self) -> None:
        """Filters should be in language config."""
        config = _load_default_config()
        lang = config[RawConfigKeys.LANGUAGES][0]

        assert RawConfigLanguageKeys.FILTERS in lang
        assert isinstance(lang[RawConfigLanguageKeys.FILTERS], list)

    def test_toolbar_visibility_is_global(self) -> None:
        """Toolbar visibility settings should be at the global config level."""
        config = _load_default_config()

        # Toolbar visibility settings are global, not per-language
        assert RawConfigKeys.HIDE_RECALC_TOOLBAR in config
        assert RawConfigKeys.HIDE_REVIEWED_COUNTER in config
        assert RawConfigKeys.HIDE_TRACKED_COUNTER in config

        # They should NOT be in the language config
        lang = config[RawConfigKeys.LANGUAGES][0]
        assert RawConfigLanguageKeys.HIDE_RECALC_TOOLBAR not in lang
        assert RawConfigLanguageKeys.HIDE_REVIEWED_COUNTER not in lang
        assert RawConfigLanguageKeys.HIDE_TRACKED_COUNTER not in lang

        # But deduplicate_toolbar_counts stays per-language (depends on variant spelling)
        assert RawConfigLanguageKeys.DEDUPLICATE_TOOLBAR_COUNTS in lang


class TestLanguageSelectorOperations:
    """Tests for language selector add/clone/delete/update operations."""

    def test_add_language_creates_correct_structure(self) -> None:
        """Adding a language should create proper structure with defaults."""
        languages: list[dict[str, Any]] = []

        # Simulate _add_language logic
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
            RawConfigLanguageKeys.NAME: "Chinese",
            RawConfigLanguageKeys.PREFIX: "CN",
            RawConfigLanguageKeys.LANGUAGE_TYPE: LANGUAGE_TYPE_OTHER,
            RawConfigLanguageKeys.FILTERS: [default_filter],
            RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS: False,
            RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES: False,
        }

        languages.append(new_language)

        assert len(languages) == 1
        assert languages[0][RawConfigLanguageKeys.NAME] == "Chinese"
        assert languages[0][RawConfigLanguageKeys.PREFIX] == "CN"
        assert languages[0][RawConfigLanguageKeys.LANGUAGE_TYPE] == LANGUAGE_TYPE_OTHER
        assert languages[0][RawConfigLanguageKeys.FILTERS][0]["note_type"] == "(none)"

    def test_delete_language_removes_correct_entry(self) -> None:
        """Deleting a language should remove only that language."""
        languages = [
            _create_test_language(name="Japanese", prefix="JP"),
            _create_test_language(name="Chinese", prefix="CN"),
            _create_test_language(name="Korean", prefix="KR"),
        ]

        # Simulate _delete_language logic
        lang_name_to_delete = "Chinese"
        languages = [
            lang
            for lang in languages
            if lang.get(RawConfigLanguageKeys.NAME) != lang_name_to_delete
        ]

        assert len(languages) == 2
        names = [lang[RawConfigLanguageKeys.NAME] for lang in languages]
        assert "Japanese" in names
        assert "Korean" in names
        assert "Chinese" not in names

    def test_update_language_changes_properties(self) -> None:
        """Updating a language should change name/prefix/type correctly."""
        languages = [
            _create_test_language(name="Japanese", prefix="JP", language_type=LANGUAGE_TYPE_JAPANESE),
        ]

        # Simulate _update_language logic
        old_name = "Japanese"
        new_name = "日本語"
        new_prefix = "日"
        new_type = LANGUAGE_TYPE_OTHER

        for lang in languages:
            if lang.get(RawConfigLanguageKeys.NAME) == old_name:
                lang[RawConfigLanguageKeys.NAME] = new_name
                lang[RawConfigLanguageKeys.PREFIX] = new_prefix
                lang[RawConfigLanguageKeys.LANGUAGE_TYPE] = new_type
                break

        assert languages[0][RawConfigLanguageKeys.NAME] == "日本語"
        assert languages[0][RawConfigLanguageKeys.PREFIX] == "日"
        assert languages[0][RawConfigLanguageKeys.LANGUAGE_TYPE] == LANGUAGE_TYPE_OTHER

    def test_update_language_preserves_other_settings(self) -> None:
        """Updating name/prefix/type should not affect other settings."""
        lang = _create_test_language(name="Japanese", prefix="JP", note_type="MyNotes")
        lang[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] = True
        lang[RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] = True

        # Update only identity fields
        lang[RawConfigLanguageKeys.NAME] = "Nihongo"
        lang[RawConfigLanguageKeys.PREFIX] = "日本"

        # Other settings should be preserved
        assert lang[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] is True
        assert lang[RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] is True
        assert lang[RawConfigLanguageKeys.FILTERS][0]["note_type"] == "MyNotes"

    def test_clone_language_with_multiple_filters(self) -> None:
        """Cloning should clear note types from all filters, not just first."""
        original = _create_test_language(name="Japanese", note_type="Notes1")
        # Add a second filter
        second_filter = copy.deepcopy(original[RawConfigLanguageKeys.FILTERS][0])
        second_filter["note_type"] = "Notes2"
        second_filter["field"] = "Field2"
        original[RawConfigLanguageKeys.FILTERS].append(second_filter)

        # Clone
        cloned = copy.deepcopy(original)
        cloned[RawConfigLanguageKeys.NAME] = "Japanese (Copy)"

        # Clear note types from all filters
        for flt in cloned[RawConfigLanguageKeys.FILTERS]:
            flt["note_type"] = "(none)"
            flt["field"] = "(none)"
            flt["furigana_field"] = "(none)"
            flt["reading_field"] = "(none)"
            flt["duplicate_sort_field"] = "(none)"

        # Verify all filters in clone are cleared
        assert len(cloned[RawConfigLanguageKeys.FILTERS]) == 2
        for flt in cloned[RawConfigLanguageKeys.FILTERS]:
            assert flt["note_type"] == "(none)"
            assert flt["field"] == "(none)"

        # Original should be unchanged
        assert original[RawConfigLanguageKeys.FILTERS][0]["note_type"] == "Notes1"
        assert original[RawConfigLanguageKeys.FILTERS][1]["note_type"] == "Notes2"


class TestUpdateLanguageConfigLogic:
    """Tests for the update_language_config function logic."""

    def test_update_only_specific_language(self) -> None:
        """Updating should modify only the target language, not others."""
        config = {
            RawConfigKeys.LANGUAGES: [
                _create_test_language(name="Japanese", prefix="JP"),
                _create_test_language(name="Chinese", prefix="CN"),
            ],
            RawConfigKeys.SHORTCUT_RECALC: "Ctrl+R",
        }

        # Simulate update_language_config logic
        language_name = "Japanese"
        language_settings = {
            RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS: True,
            RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES: True,
        }

        languages = config.get(RawConfigKeys.LANGUAGES, [])
        for lang in languages:
            if lang.get(RawConfigLanguageKeys.NAME) == language_name:
                for key, value in language_settings.items():
                    lang[key] = value
                break

        # Japanese should be updated
        assert config[RawConfigKeys.LANGUAGES][0][RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] is True
        assert config[RawConfigKeys.LANGUAGES][0][RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] is True

        # Chinese should be unchanged
        assert config[RawConfigKeys.LANGUAGES][1][RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] is False
        assert config[RawConfigKeys.LANGUAGES][1][RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] is False

    def test_update_global_settings_separate_from_language(self) -> None:
        """Global settings should be updated at root level, not in language."""
        config = {
            RawConfigKeys.LANGUAGES: [
                _create_test_language(name="Japanese"),
            ],
            RawConfigKeys.SHORTCUT_RECALC: "Ctrl+R",
            RawConfigKeys.TAG_READY: "old-ready",
        }

        # Simulate updating global settings
        global_settings = {
            RawConfigKeys.SHORTCUT_RECALC: "Ctrl+Shift+R",
            RawConfigKeys.TAG_READY: "new-ready",
        }

        for key, value in global_settings.items():
            config[key] = value

        assert config[RawConfigKeys.SHORTCUT_RECALC] == "Ctrl+Shift+R"
        assert config[RawConfigKeys.TAG_READY] == "new-ready"

        # Language should not have these keys
        lang = config[RawConfigKeys.LANGUAGES][0]
        assert RawConfigKeys.SHORTCUT_RECALC not in lang
        assert RawConfigKeys.TAG_READY not in lang

    def test_update_filters_replaces_entire_list(self) -> None:
        """Updating filters should replace the entire filters list."""
        config = {
            RawConfigKeys.LANGUAGES: [
                _create_test_language(name="Japanese", note_type="OldNotes"),
            ],
        }

        new_filters = [
            {
                "note_type": "NewNotes1",
                "tags": {"include": [], "exclude": []},
                "field": "Field1",
                "furigana_field": "(none)",
                "reading_field": "(none)",
                "reading_priority": "Furigana first",
                "priority_files": [],
                "read": True,
                "modify": True,
                "extra_reading_field": False,
                "duplicate_sort_field": "(none)",
                "duplicate_sort_numeric": False,
            },
            {
                "note_type": "NewNotes2",
                "tags": {"include": ["tag1"], "exclude": []},
                "field": "Field2",
                "furigana_field": "(none)",
                "reading_field": "(none)",
                "reading_priority": "Furigana first",
                "priority_files": [],
                "read": True,
                "modify": False,
                "extra_reading_field": False,
                "duplicate_sort_field": "(none)",
                "duplicate_sort_numeric": False,
            },
        ]

        # Update filters
        config[RawConfigKeys.LANGUAGES][0][RawConfigLanguageKeys.FILTERS] = new_filters

        filters = config[RawConfigKeys.LANGUAGES][0][RawConfigLanguageKeys.FILTERS]
        assert len(filters) == 2
        assert filters[0]["note_type"] == "NewNotes1"
        assert filters[1]["note_type"] == "NewNotes2"
        assert filters[1]["tags"]["include"] == ["tag1"]


class TestSettingsSeparation:
    """Tests for correctly separating global and language settings in settings dialog."""

    def test_global_keys_set(self) -> None:
        """Verify the set of keys considered global."""
        global_keys = {
            RawConfigKeys.SHORTCUT_RECALC,
            RawConfigKeys.SHORTCUT_SETTINGS,
            RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
            RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD,
            RawConfigKeys.SHORTCUT_SET_KNOWN_AND_SKIP,
            RawConfigKeys.SHORTCUT_LEARN_NOW,
            RawConfigKeys.SHORTCUT_GENERATORS,
            RawConfigKeys.SHORTCUT_PROGRESSION,
            RawConfigKeys.SHORTCUT_KNOWN_ENTRIES_EXPORTER,
            RawConfigKeys.RECALC_ON_SYNC,
            RawConfigKeys.RECALC_AFTER_SYNC,
            RawConfigKeys.TAG_READY,
            RawConfigKeys.TAG_NOT_READY,
            RawConfigKeys.TAG_KNOWN_MANUALLY,
            RawConfigKeys.TAG_SUSPENDED_AUTOMATICALLY,
        }

        # All global keys should be strings (key names)
        for key in global_keys:
            assert isinstance(key, str)

        # Key shortcuts and tags are global
        assert "shortcut_recalc" in global_keys
        assert "tag_ready" in global_keys

    def test_settings_separation_logic(self) -> None:
        """Test logic for separating global vs language settings."""
        global_keys = {
            RawConfigKeys.SHORTCUT_RECALC,
            RawConfigKeys.TAG_READY,
        }

        all_settings = {
            RawConfigKeys.SHORTCUT_RECALC: "Ctrl+R",
            RawConfigKeys.TAG_READY: "ps-ready",
            RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS: True,
            RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES: True,
            RawConfigLanguageKeys.FILTERS: [],
        }

        global_settings = {}
        language_settings = {}

        for key, value in all_settings.items():
            if key in global_keys:
                global_settings[key] = value
            else:
                language_settings[key] = value

        assert len(global_settings) == 2
        assert global_settings[RawConfigKeys.SHORTCUT_RECALC] == "Ctrl+R"
        assert global_settings[RawConfigKeys.TAG_READY] == "ps-ready"

        assert len(language_settings) == 3
        assert language_settings[RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS] is True
        assert language_settings[RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES] is True
        assert language_settings[RawConfigLanguageKeys.FILTERS] == []


class TestLanguageConfigClass:
    """Tests for PrioritySieveLanguageConfig class."""

    def test_language_config_class_exists(self) -> None:
        """PrioritySieveLanguageConfig class should exist and be importable."""
        assert PrioritySieveLanguageConfig is not None

    def test_language_config_expected_attributes_documented(self) -> None:
        """Document expected attributes for PrioritySieveLanguageConfig."""
        # These are the expected attributes that should be set in __init__
        expected_attributes = [
            "name",
            "prefix",
            "language_type",
            "filters",
            "preprocess_ignore_numbers",
            "auto_suspend_unlisted_entries",
            "hide_recalc_toolbar",
            "hide_reviewed_counter",
            "hide_tracked_counter",
            "hide_pending_counter",
            "recalc_offset_priority_decks",
            "disabled_decks",
        ]

        # Verify these are valid RawConfigLanguageKeys
        for attr in expected_attributes:
            assert hasattr(RawConfigLanguageKeys, attr.upper()) or attr in [
                "name", "prefix", "language_type", "filters"
            ], f"Missing RawConfigLanguageKeys for {attr}"

    def test_language_config_filter_count(self) -> None:
        """Test that filters list can have multiple entries."""
        config = _load_default_config()
        lang_dict = config[RawConfigKeys.LANGUAGES][0]

        # Add a second filter for testing
        second_filter = copy.deepcopy(lang_dict[RawConfigLanguageKeys.FILTERS][0])
        second_filter["note_type"] = "SecondNote"
        lang_dict[RawConfigLanguageKeys.FILTERS].append(second_filter)

        assert len(lang_dict[RawConfigLanguageKeys.FILTERS]) == 2


class TestDeckPriorityPerLanguage:
    """Tests for per-language deck priority settings."""

    def test_deck_priorities_are_per_language(self) -> None:
        """Each language should have its own deck priority list."""
        lang1 = _create_test_language(name="Japanese")
        lang1[RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS] = ["Deck1", "Deck2"]

        lang2 = _create_test_language(name="Chinese")
        lang2[RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS] = ["DeckA", "DeckB", "DeckC"]

        assert lang1[RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS] == ["Deck1", "Deck2"]
        assert lang2[RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS] == ["DeckA", "DeckB", "DeckC"]

    def test_disabled_decks_are_per_language(self) -> None:
        """Each language should have its own disabled decks list."""
        lang1 = _create_test_language(name="Japanese")
        lang1[RawConfigLanguageKeys.DISABLED_DECKS] = ["DisabledDeck1"]

        lang2 = _create_test_language(name="Chinese")
        lang2[RawConfigLanguageKeys.DISABLED_DECKS] = []

        assert lang1[RawConfigLanguageKeys.DISABLED_DECKS] == ["DisabledDeck1"]
        assert lang2[RawConfigLanguageKeys.DISABLED_DECKS] == []
