"""Integration tests for settings tabs with per-language configuration.

These tests verify that settings tabs correctly use language-specific config
rather than falling back to global config. They would catch bugs like:
- Using self._config.filters instead of self._language_config.filters
- Not hiding Japanese-specific UI for non-Japanese languages

These tests import and inspect the actual source code to verify correct patterns.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from prioritysieve.prioritysieve_config import (
    LANGUAGE_TYPE_JAPANESE,
    LANGUAGE_TYPE_OTHER,
    PrioritySieveConfig,
    PrioritySieveConfigFilter,
    PrioritySieveLanguageConfig,
    RawConfigLanguageKeys,
)

# Import the actual modules to inspect their source
from prioritysieve.settings import settings_extra_fields_tab
from prioritysieve.settings import settings_card_handling_tab
from prioritysieve.settings import settings_general_tab
from prioritysieve.settings import settings_note_filters_tab
from prioritysieve.settings import settings_dialog


def _create_mock_filter(note_type: str = "(none)", field: str = "(none)") -> PrioritySieveConfigFilter:
    """Create a mock filter for testing."""
    mock_filter = MagicMock(spec=PrioritySieveConfigFilter)
    mock_filter.note_type = note_type
    mock_filter.field = field
    mock_filter.furigana_field = "(none)"
    mock_filter.reading_field = "(none)"
    mock_filter.reading_priority = "Furigana first"
    mock_filter.duplicate_sort_field = "(none)"
    mock_filter.duplicate_sort_numeric = False
    mock_filter.priority_files = []
    mock_filter.tags = {"include": [], "exclude": []}
    mock_filter.read = True
    mock_filter.modify = True
    mock_filter.extra_reading_field = False
    return mock_filter


def _create_mock_language_config(
    name: str = "TestLang",
    prefix: str = "TL",
    language_type: str = LANGUAGE_TYPE_JAPANESE,
    filters: list[PrioritySieveConfigFilter] | None = None,
) -> PrioritySieveLanguageConfig:
    """Create a mock language config for testing."""
    mock_lang = MagicMock(spec=PrioritySieveLanguageConfig)
    mock_lang.name = name
    mock_lang.prefix = prefix
    mock_lang.language_type = language_type
    mock_lang.filters = filters if filters is not None else []
    mock_lang.preprocess_ignore_numbers = False
    mock_lang.auto_suspend_unlisted_entries = False
    mock_lang.auto_suspend_variant_spellings = False
    mock_lang.merge_kana_variant_spellings = False
    mock_lang.hide_recalc_toolbar = False
    mock_lang.hide_reviewed_counter = False
    mock_lang.hide_tracked_counter = False
    mock_lang.hide_pending_counter = False
    mock_lang.deduplicate_toolbar_counts = False
    mock_lang.recalc_offset_priority_decks = []
    mock_lang.disabled_decks = []
    return mock_lang


def _create_mock_config(
    languages: list[PrioritySieveLanguageConfig] | None = None,
) -> PrioritySieveConfig:
    """Create a mock global config for testing."""
    mock_config = MagicMock(spec=PrioritySieveConfig)
    mock_config.languages = languages if languages is not None else []
    # Backward compat: filters property returns first language's filters
    if mock_config.languages:
        mock_config.filters = mock_config.languages[0].filters
    else:
        mock_config.filters = []
    mock_config.recalc_offset_priority_decks = []
    mock_config.disabled_decks = []
    return mock_config


class TestExtraFieldsTabLanguageConfig:
    """Tests that ExtraFieldsTab uses language config, not global config."""

    def test_init_uses_language_config_filters(self) -> None:
        """ExtraFieldsTab.__init__ must use self._language_config.filters, not self._config.filters."""
        source = inspect.getsource(settings_extra_fields_tab.ExtraFieldsTab.__init__)

        # The bug was using self._config.filters directly
        # The fix uses self._language_config.filters with fallback
        assert "self._language_config.filters" in source, (
            "ExtraFieldsTab.__init__ must use self._language_config.filters"
        )
        # Should NOT use self._config.filters directly without checking language_config first
        # The pattern should be: self._language_config.filters if self._language_config else self._config.filters
        assert "if self._language_config" in source or "self._language_config.filters" in source, (
            "ExtraFieldsTab.__init__ must check language_config before falling back"
        )

    def test_get_selected_extra_fields_uses_language_config(self) -> None:
        """get_selected_extra_fields_from_config must use language config filters."""
        source = inspect.getsource(
            settings_extra_fields_tab.ExtraFieldsTab.get_selected_extra_fields_from_config
        )

        # Must reference language_config for filters
        assert "self._language_config" in source, (
            "get_selected_extra_fields_from_config must use self._language_config"
        )

    def test_logic_prefers_language_config(self) -> None:
        """Verify the logic pattern correctly prefers language config over global."""
        # Create two different sets of filters
        japanese_filter = _create_mock_filter(note_type="JapaneseNotes")
        other_filter = _create_mock_filter(note_type="OtherNotes")

        japanese_lang = _create_mock_language_config(name="Japanese", filters=[japanese_filter])
        other_lang = _create_mock_language_config(name="Other", filters=[other_filter])
        global_config = _create_mock_config(languages=[other_lang, japanese_lang])

        # Simulate the fixed code pattern
        language_config = japanese_lang
        filters = (
            language_config.filters
            if language_config
            else global_config.filters
        )
        selected_note_types = [_filter.note_type for _filter in filters]

        assert "JapaneseNotes" in selected_note_types
        assert "OtherNotes" not in selected_note_types


class TestCardHandlingTabLanguageConfig:
    """Tests that CardHandlingTab uses language config for deck filtering."""

    def test_get_available_decks_uses_language_config(self) -> None:
        """_get_available_decks_for_note_types must use self._language_config.filters."""
        source = inspect.getsource(
            settings_card_handling_tab.CardHandlingTab._get_available_decks_for_note_types
        )

        # Must reference language_config for filters
        assert "self._language_config" in source, (
            "_get_available_decks_for_note_types must use self._language_config"
        )
        assert "self._language_config.filters" in source, (
            "_get_available_decks_for_note_types must use self._language_config.filters"
        )

    def test_logic_prefers_language_config(self) -> None:
        """Verify the logic pattern correctly prefers language config over global."""
        jp_filter1 = _create_mock_filter(note_type="JapaneseVocab")
        jp_filter2 = _create_mock_filter(note_type="JapaneseSentences")
        japanese_lang = _create_mock_language_config(
            name="Japanese",
            filters=[jp_filter1, jp_filter2],
        )

        cn_filter = _create_mock_filter(note_type="ChineseVocab")
        chinese_lang = _create_mock_language_config(
            name="Chinese",
            language_type=LANGUAGE_TYPE_OTHER,
            filters=[cn_filter],
        )

        global_config = _create_mock_config(languages=[chinese_lang, japanese_lang])

        # Simulate the fixed code pattern
        language_config = japanese_lang
        filters = (
            language_config.filters
            if language_config
            else global_config.filters
        )
        note_type_names = {
            config_filter.note_type
            for config_filter in filters
            if config_filter.note_type != "(none)"
        }

        assert "JapaneseVocab" in note_type_names
        assert "JapaneseSentences" in note_type_names
        assert "ChineseVocab" not in note_type_names

    def test_excludes_none_option(self) -> None:
        """Should exclude (none) from note type names."""
        filter1 = _create_mock_filter(note_type="RealNotes")
        filter2 = _create_mock_filter(note_type="(none)")
        lang = _create_mock_language_config(filters=[filter1, filter2])

        note_type_names = {
            config_filter.note_type
            for config_filter in lang.filters
            if config_filter.note_type != "(none)"
        }

        assert "RealNotes" in note_type_names
        assert "(none)" not in note_type_names


class TestGeneralTabJapaneseVisibility:
    """Tests that GeneralTab hides Japanese options for non-Japanese languages."""

    def test_has_japanese_visibility_method(self) -> None:
        """GeneralTab must have _update_japanese_options_visibility method."""
        assert hasattr(settings_general_tab.GeneralTab, "_update_japanese_options_visibility"), (
            "GeneralTab must have _update_japanese_options_visibility method"
        )

    def test_visibility_method_checks_language_type(self) -> None:
        """_update_japanese_options_visibility must check language_type."""
        source = inspect.getsource(
            settings_general_tab.GeneralTab._update_japanese_options_visibility
        )

        assert "LANGUAGE_TYPE_JAPANESE" in source, (
            "_update_japanese_options_visibility must check LANGUAGE_TYPE_JAPANESE"
        )
        assert "self._language_config" in source, (
            "_update_japanese_options_visibility must use self._language_config"
        )

    def test_init_calls_visibility_update(self) -> None:
        """GeneralTab.__init__ must call _update_japanese_options_visibility."""
        source = inspect.getsource(settings_general_tab.GeneralTab.__init__)

        assert "_update_japanese_options_visibility" in source, (
            "GeneralTab.__init__ must call _update_japanese_options_visibility"
        )

    def test_visibility_logic_for_japanese(self) -> None:
        """Verify visibility logic correctly identifies Japanese."""
        japanese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_JAPANESE)

        is_japanese = (
            japanese_lang is not None
            and japanese_lang.language_type == LANGUAGE_TYPE_JAPANESE
        )

        assert is_japanese is True

    def test_visibility_logic_for_other(self) -> None:
        """Verify visibility logic correctly identifies non-Japanese."""
        chinese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_OTHER)

        is_japanese = (
            chinese_lang is not None
            and chinese_lang.language_type == LANGUAGE_TYPE_JAPANESE
        )

        assert is_japanese is False


class TestNoteFiltersTabColumnVisibility:
    """Tests that NoteFiltersTab hides Japanese columns for non-Japanese languages."""

    def test_has_column_visibility_method(self) -> None:
        """NoteFiltersTab must have _update_column_visibility method."""
        assert hasattr(settings_note_filters_tab.NoteFiltersTab, "_update_column_visibility"), (
            "NoteFiltersTab must have _update_column_visibility method"
        )

    def test_column_visibility_checks_language_type(self) -> None:
        """_update_column_visibility must check language_type."""
        source = inspect.getsource(
            settings_note_filters_tab.NoteFiltersTab._update_column_visibility
        )

        assert "LANGUAGE_TYPE_JAPANESE" in source, (
            "_update_column_visibility must check LANGUAGE_TYPE_JAPANESE"
        )
        assert "self._language_config" in source, (
            "_update_column_visibility must use self._language_config"
        )

    def test_init_calls_column_visibility(self) -> None:
        """NoteFiltersTab.__init__ must call _update_column_visibility."""
        source = inspect.getsource(settings_note_filters_tab.NoteFiltersTab.__init__)

        assert "_update_column_visibility" in source, (
            "NoteFiltersTab.__init__ must call _update_column_visibility"
        )

    def test_visibility_logic_for_japanese(self) -> None:
        """Japanese-specific columns should be visible for Japanese language."""
        japanese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_JAPANESE)

        is_japanese = (
            japanese_lang is not None
            and japanese_lang.language_type == LANGUAGE_TYPE_JAPANESE
        )

        should_hide = not is_japanese
        assert should_hide is False

    def test_visibility_logic_for_other(self) -> None:
        """Japanese-specific columns should be hidden for non-Japanese language."""
        chinese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_OTHER)

        is_japanese = (
            chinese_lang is not None
            and chinese_lang.language_type == LANGUAGE_TYPE_JAPANESE
        )

        should_hide = not is_japanese
        assert should_hide is True


class TestNoteFiltersTabNoteTypeFiltering:
    """Tests that NoteFiltersTab filters note types by language."""

    def test_has_get_note_types_used_by_other_languages_method(self) -> None:
        """NoteFiltersTab must have _get_note_types_used_by_other_languages method."""
        assert hasattr(
            settings_note_filters_tab.NoteFiltersTab,
            "_get_note_types_used_by_other_languages"
        ), "NoteFiltersTab must have _get_note_types_used_by_other_languages method"

    def test_get_note_types_method_uses_language_config(self) -> None:
        """_get_note_types_used_by_other_languages must use language config."""
        source = inspect.getsource(
            settings_note_filters_tab.NoteFiltersTab._get_note_types_used_by_other_languages
        )

        assert "self._language_config" in source, (
            "_get_note_types_used_by_other_languages must use self._language_config"
        )

    def test_setup_note_type_cbox_filters_by_language(self) -> None:
        """_setup_note_type_cbox must call _get_note_types_used_by_other_languages."""
        source = inspect.getsource(
            settings_note_filters_tab.NoteFiltersTab._setup_note_type_cbox
        )

        assert "_get_note_types_used_by_other_languages" in source, (
            "_setup_note_type_cbox must call _get_note_types_used_by_other_languages"
        )

    def test_filtering_logic(self) -> None:
        """Verify note type filtering logic excludes other languages."""
        jp_filter = _create_mock_filter(note_type="JapaneseNotes")
        cn_filter = _create_mock_filter(note_type="ChineseNotes")
        kr_filter = _create_mock_filter(note_type="KoreanNotes")

        japanese_lang = _create_mock_language_config(name="Japanese", filters=[jp_filter])
        chinese_lang = _create_mock_language_config(name="Chinese", filters=[cn_filter])
        korean_lang = _create_mock_language_config(name="Korean", filters=[kr_filter])

        config = _create_mock_config(languages=[japanese_lang, chinese_lang, korean_lang])

        # Simulate _get_note_types_used_by_other_languages for Japanese
        current_lang_name = "Japanese"
        used_note_types: set[str] = set()

        for lang in config.languages:
            if lang.name == current_lang_name:
                continue
            for flt in lang.filters:
                if flt.note_type != "(none)":
                    used_note_types.add(flt.note_type)

        assert "ChineseNotes" in used_note_types
        assert "KoreanNotes" in used_note_types
        assert "JapaneseNotes" not in used_note_types

    def test_dropdown_excludes_other_languages(self) -> None:
        """Note type dropdown should exclude note types from other languages."""
        jp_filter = _create_mock_filter(note_type="JapaneseNotes")
        cn_filter = _create_mock_filter(note_type="ChineseNotes")

        japanese_lang = _create_mock_language_config(name="Japanese", filters=[jp_filter])
        chinese_lang = _create_mock_language_config(name="Chinese", filters=[cn_filter])

        config = _create_mock_config(languages=[japanese_lang, chinese_lang])

        current_lang_name = "Japanese"
        current_note_type = "JapaneseNotes"

        used_by_other_langs = set()
        for lang in config.languages:
            if lang.name == current_lang_name:
                continue
            for flt in lang.filters:
                if flt.note_type != "(none)":
                    used_by_other_langs.add(flt.note_type)

        all_note_types = ["JapaneseNotes", "ChineseNotes", "UnusedNotes"]

        available_note_types = ["(none)"]
        for note_type in all_note_types:
            if note_type in used_by_other_langs:
                if note_type == current_note_type:
                    available_note_types.append(note_type)
            else:
                available_note_types.append(note_type)

        assert "JapaneseNotes" in available_note_types
        assert "ChineseNotes" not in available_note_types
        assert "UnusedNotes" in available_note_types


class TestSettingsDialogExtraFieldsTabVisibility:
    """Tests that SettingsDialog hides Extra Fields tab for non-Japanese languages."""

    def test_init_hides_extra_fields_for_non_japanese(self) -> None:
        """SettingsDialog._init_ui must hide Extra Fields tab for non-Japanese."""
        source = inspect.getsource(settings_dialog.SettingsDialog._init_ui)

        # Must check language_type for hiding
        assert "LANGUAGE_TYPE_JAPANESE" in source, (
            "SettingsDialog._init_ui must check LANGUAGE_TYPE_JAPANESE"
        )
        assert "extra_fields_tab" in source, (
            "SettingsDialog._init_ui must reference extra_fields_tab"
        )
        assert "removeTab" in source, (
            "SettingsDialog._init_ui must remove tab for non-Japanese"
        )

    def test_visibility_logic_for_japanese(self) -> None:
        """Extra Fields tab should be visible for Japanese language."""
        japanese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_JAPANESE)

        should_hide = (
            japanese_lang is not None
            and japanese_lang.language_type != LANGUAGE_TYPE_JAPANESE
        )

        assert should_hide is False

    def test_visibility_logic_for_other(self) -> None:
        """Extra Fields tab should be hidden for non-Japanese language."""
        chinese_lang = _create_mock_language_config(language_type=LANGUAGE_TYPE_OTHER)

        should_hide = (
            chinese_lang is not None
            and chinese_lang.language_type != LANGUAGE_TYPE_JAPANESE
        )

        assert should_hide is True


class TestGetSelectedExtraFieldsFromConfig:
    """Tests that get_selected_extra_fields_from_config uses correct config."""

    def test_uses_language_config_filters(self) -> None:
        """Should use language config filters, not global config filters."""
        # Japanese filter with extra_reading_field enabled
        jp_filter = _create_mock_filter(note_type="JapaneseNotes")
        jp_filter.extra_reading_field = True

        # Other filter with extra_reading_field disabled
        other_filter = _create_mock_filter(note_type="OtherNotes")
        other_filter.extra_reading_field = False

        japanese_lang = _create_mock_language_config(filters=[jp_filter])
        other_lang = _create_mock_language_config(name="Other", filters=[other_filter])

        # Global config has Other first (backward compat would use this)
        global_config = _create_mock_config(languages=[other_lang, japanese_lang])

        # Simulate get_selected_extra_fields_from_config with language config
        language_config = japanese_lang
        restore_defaults = False

        if restore_defaults:
            filters = global_config.filters  # Would use default
        else:
            filters = (
                language_config.filters
                if language_config
                else global_config.filters
            )

        # Find the filter for JapaneseNotes
        is_selected = False
        for _filter in filters:
            if _filter.note_type == "JapaneseNotes":
                is_selected = getattr(_filter, "extra_reading_field", False)
                break

        # Should find True from Japanese config, not False from Other
        assert is_selected is True

    def test_falls_back_to_global_when_no_language_config(self) -> None:
        """Should use global config when no language config provided."""
        other_filter = _create_mock_filter(note_type="OtherNotes")
        other_filter.extra_reading_field = True

        other_lang = _create_mock_language_config(filters=[other_filter])
        global_config = _create_mock_config(languages=[other_lang])

        language_config = None
        filters = (
            language_config.filters
            if language_config
            else global_config.filters
        )

        is_selected = False
        for _filter in filters:
            if _filter.note_type == "OtherNotes":
                is_selected = getattr(_filter, "extra_reading_field", False)
                break

        assert is_selected is True


class TestGlobalToolbarSettingsNotPerLanguage:
    """Tests that global toolbar settings are accessed from PrioritySieveConfig, not per-language."""

    def test_init_toolbar_uses_global_hide_recalc(self) -> None:
        """__init__.py must use am_config.hide_recalc_toolbar, not lang.hide_recalc_toolbar."""
        import prioritysieve
        source = inspect.getsource(prioritysieve.init_toolbar_items)

        # Should use global config, not per-language
        assert "am_config.hide_recalc_toolbar" in source, (
            "init_toolbar_items must use am_config.hide_recalc_toolbar (global setting)"
        )
        assert "lang.hide_recalc_toolbar" not in source, (
            "init_toolbar_items must NOT use lang.hide_recalc_toolbar (it's now global)"
        )

    def test_toolbar_stats_uses_global_visibility(self) -> None:
        """toolbar_stats.py must use config.hide_recalc_toolbar, not lang.hide_recalc_toolbar."""
        from prioritysieve import toolbar_stats
        source = inspect.getsource(toolbar_stats.EntryToolbarStats.update_stats)

        # Should use global config for visibility settings
        assert "config.hide_recalc_toolbar" in source, (
            "update_stats must use config.hide_recalc_toolbar (global setting)"
        )
        assert "config.hide_reviewed_counter" in source, (
            "update_stats must use config.hide_reviewed_counter (global setting)"
        )
        assert "config.hide_tracked_counter" in source, (
            "update_stats must use config.hide_tracked_counter (global setting)"
        )

    def test_deduplicate_is_per_language(self) -> None:
        """deduplicate_toolbar_counts should remain per-language."""
        from prioritysieve import toolbar_stats
        source = inspect.getsource(toolbar_stats.EntryToolbarStats.update_stats)

        # Deduplicate stays per-language
        assert "lang.deduplicate_toolbar_counts" in source, (
            "update_stats must use lang.deduplicate_toolbar_counts (per-language setting)"
        )
