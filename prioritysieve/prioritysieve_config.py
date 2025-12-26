from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Union

from anki.models import NotetypeId
from anki.notes import Note
from aqt import mw
from aqt.qt import (  # pylint:disable=no-name-in-module
    QKeySequence,
    QMessageBox,
    QPushButton,
    Qt,
)

from . import prioritysieve_globals

FilterTypeAlias = dict[
    str,
    Union[str, bool, int, list[str], dict[str, Any], None],
]


class RawConfigFilterKeys:
    NOTE_TYPE = "note_type"
    TAGS = "tags"
    FIELD = "field"
    FURIGANA_FIELD = "furigana_field"
    READING_FIELD = "reading_field"
    READING_PRIORITY = "reading_priority"
    PRIORITY_FILES = "priority_files"
    READ = "read"
    MODIFY = "modify"
    EXTRA_READING_FIELD = "extra_reading_field"
    DUPLICATE_SORT_FIELD = "duplicate_sort_field"
    DUPLICATE_SORT_NUMERIC = "duplicate_sort_numeric"

    # Legacy keys we still accept when loading stored configs
    LegacyPrioritySelection = "morph_priority_selection"
    LegacyMorphemizerDescription = "morphemizer_description"
    LegacyExtraReadingField = "extra_morph_readings"


class RawConfigLanguageKeys:
    """Keys for per-language configuration."""

    NAME = "name"
    PREFIX = "prefix"
    LANGUAGE_TYPE = "language_type"
    FILTERS = "filters"
    PREPROCESS_IGNORE_BRACKET_CONTENTS = "preprocess_ignore_bracket_contents"
    PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS = "preprocess_ignore_round_bracket_contents"
    PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS = (
        "preprocess_ignore_slim_round_bracket_contents"
    )
    PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS = "preprocess_ignore_angle_bracket_contents"
    PREPROCESS_IGNORE_NUMBERS = "preprocess_ignore_numbers"
    PREPROCESS_IGNORE_CUSTOM_CHARACTERS = "preprocess_ignore_custom_characters"
    PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE = "preprocess_custom_characters_to_ignore"
    PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS = "preprocess_ignore_suspended_unless_tags"
    AUTO_SUSPEND_UNLISTED_ENTRIES = "auto_suspend_unlisted_entries"
    AUTO_SUSPEND_VARIANT_SPELLINGS = "auto_suspend_variant_spellings"
    MERGE_KANA_VARIANT_SPELLINGS = "merge_kana_variant_spellings"
    RECALC_OFFSET_PRIORITY_DECKS = "recalc_offset_priority_decks"
    DISABLED_DECKS = "disabled_decks"
    HIDE_RECALC_TOOLBAR = "hide_recalc_toolbar"
    HIDE_REVIEWED_COUNTER = "hide_reviewed_counter"
    HIDE_TRACKED_COUNTER = "hide_tracked_counter"
    HIDE_PENDING_COUNTER = "hide_pending_counter"
    DEDUPLICATE_TOOLBAR_COUNTS = "deduplicate_toolbar_counts"


# Language types
LANGUAGE_TYPE_JAPANESE = "japanese"
LANGUAGE_TYPE_OTHER = "other"


class RawConfigKeys:
    """Keys for global configuration."""

    LANGUAGES = "languages"
    SHORTCUT_RECALC = "shortcut_recalc"
    SHORTCUT_SETTINGS = "shortcut_settings"
    SHORTCUT_BROWSE_SAME_UNKNOWN = "shortcut_browse_same_unknown"
    SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD = "shortcut_browse_same_unknown_broad"
    SHORTCUT_SET_KNOWN_AND_SKIP = "shortcut_set_known_and_skip"
    SHORTCUT_LEARN_NOW = "shortcut_learn_now"
    SHORTCUT_GENERATORS = "shortcut_generators"
    SHORTCUT_PROGRESSION = "shortcut_progression"
    SHORTCUT_KNOWN_ENTRIES_EXPORTER = "shortcut_known_entries_exporter"
    RECALC_ON_SYNC = "recalc_on_sync"
    RECALC_AFTER_SYNC = "recalc_after_sync"
    TAG_READY = "tag_ready"
    TAG_NOT_READY = "tag_not_ready"
    TAG_KNOWN_MANUALLY = "tag_known_manually"
    TAG_SUSPENDED_AUTOMATICALLY = "tag_suspended_automatically"

    # Backward compatibility: per-language keys that can be accessed
    # via PrioritySieveConfig properties (delegate to first language)
    HIDE_RECALC_TOOLBAR = "hide_recalc_toolbar"
    HIDE_REVIEWED_COUNTER = "hide_reviewed_counter"
    HIDE_TRACKED_COUNTER = "hide_tracked_counter"
    HIDE_PENDING_COUNTER = "hide_pending_counter"
    DEDUPLICATE_TOOLBAR_COUNTS = "deduplicate_toolbar_counts"
    AUTO_SUSPEND_VARIANT_SPELLINGS = "auto_suspend_variant_spellings"
    MERGE_KANA_VARIANT_SPELLINGS = "merge_kana_variant_spellings"
    AUTO_SUSPEND_UNLISTED_ENTRIES = "auto_suspend_unlisted_entries"
    PREPROCESS_IGNORE_BRACKET_CONTENTS = "preprocess_ignore_bracket_contents"
    PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS = "preprocess_ignore_round_bracket_contents"
    PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS = (
        "preprocess_ignore_slim_round_bracket_contents"
    )
    PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS = "preprocess_ignore_angle_bracket_contents"
    PREPROCESS_IGNORE_NUMBERS = "preprocess_ignore_numbers"
    PREPROCESS_IGNORE_CUSTOM_CHARACTERS = "preprocess_ignore_custom_characters"
    PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE = "preprocess_custom_characters_to_ignore"
    PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS = "preprocess_ignore_suspended_unless_tags"
    RECALC_OFFSET_PRIORITY_DECKS = "recalc_offset_priority_decks"
    DISABLED_DECKS = "disabled_decks"
    FILTERS = "filters"

    # Legacy keys that are now per-language (used for migration)
    LEGACY_FILTERS = "filters"
    LEGACY_PREPROCESS_IGNORE_BRACKET_CONTENTS = "preprocess_ignore_bracket_contents"
    LEGACY_PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS = (
        "preprocess_ignore_round_bracket_contents"
    )
    LEGACY_PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS = (
        "preprocess_ignore_slim_round_bracket_contents"
    )
    LEGACY_PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS = (
        "preprocess_ignore_angle_bracket_contents"
    )
    LEGACY_PREPROCESS_IGNORE_NUMBERS = "preprocess_ignore_numbers"
    LEGACY_PREPROCESS_IGNORE_CUSTOM_CHARACTERS = "preprocess_ignore_custom_characters"
    LEGACY_PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE = (
        "preprocess_custom_characters_to_ignore"
    )
    LEGACY_PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS = (
        "preprocess_ignore_suspended_unless_tags"
    )
    LEGACY_AUTO_SUSPEND_UNLISTED_ENTRIES = "auto_suspend_unlisted_entries"
    LEGACY_AUTO_SUSPEND_VARIANT_SPELLINGS = "auto_suspend_variant_spellings"
    LEGACY_MERGE_KANA_VARIANT_SPELLINGS = "merge_kana_variant_spellings"
    LEGACY_RECALC_OFFSET_PRIORITY_DECKS = "recalc_offset_priority_decks"
    LEGACY_DISABLED_DECKS = "disabled_decks"
    LEGACY_HIDE_RECALC_TOOLBAR = "hide_recalc_toolbar"
    LEGACY_HIDE_REVIEWED_COUNTER = "hide_reviewed_counter"
    LEGACY_HIDE_TRACKED_COUNTER = "hide_tracked_counter"
    LEGACY_HIDE_PENDING_COUNTER = "hide_pending_counter"
    LEGACY_DEDUPLICATE_TOOLBAR_COUNTS = "deduplicate_toolbar_counts"

LEGACY_KEY_RENAMES: dict[str, str] = {
    "shortcut_browse_ready_same_unknown": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
    "shortcut_browse_all_same_unknown": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
    "shortcut_browse_ready_same_unknown_lemma": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD,
    "shortcut_known_morphs_exporter": RawConfigKeys.SHORTCUT_KNOWN_ENTRIES_EXPORTER,
    # These are now per-language settings (will be migrated by _migrate_to_language_config)
    "hide_lemma_toolbar": "hide_reviewed_counter",
    "hide_inflection_toolbar": "hide_tracked_counter",
}

LEGACY_KEYS_TO_DROP: set[str] = {
    "shortcut_view_morphemes",
    "skip_no_unknown_morphs",
    "skip_unknown_morph_seen_today_cards",
    "skip_show_num_of_skipped_cards",
    "preprocess_ignore_names_morphemizer",
    "preprocess_ignore_names_textfile",
    "interval_for_known_morphs",
    "read_known_morphs_folder",
    "evaluate_morph_lemma",
    "evaluate_morph_inflection",
    "extra_fields_display_inflections",
    "extra_fields_display_lemmas",
    "algorithm_total_priority_unknown_morphs_weight",
    "algorithm_total_priority_all_morphs_weight",
    "algorithm_average_priority_all_morphs_weight",
    "algorithm_total_priority_learning_morphs_weight",
    "algorithm_average_priority_learning_morphs_weight",
    "algorithm_all_morphs_target_difference_weight",
    "algorithm_learning_morphs_target_difference_weight",
    "algorithm_upper_target_all_morphs",
    "algorithm_upper_target_all_morphs_coefficient_a",
    "algorithm_upper_target_all_morphs_coefficient_b",
    "algorithm_upper_target_all_morphs_coefficient_c",
    "algorithm_lower_target_all_morphs",
    "algorithm_lower_target_all_morphs_coefficient_a",
    "algorithm_lower_target_all_morphs_coefficient_b",
    "algorithm_lower_target_all_morphs_coefficient_c",
    "algorithm_upper_target_learning_morphs",
    "algorithm_lower_target_learning_morphs",
    "algorithm_upper_target_learning_morphs_coefficient_a",
    "algorithm_upper_target_learning_morphs_coefficient_b",
    "algorithm_upper_target_learning_morphs_coefficient_c",
    "algorithm_lower_target_learning_morphs_coefficient_a",
    "algorithm_lower_target_learning_morphs_coefficient_b",
    "algorithm_lower_target_learning_morphs_coefficient_c",
    "tag_learn_card_now",
    "tag_known_automatically",
    "toolbar_stats_use_known",
    "toolbar_stats_use_seen",
}


def _normalize_filter_dict(
    filter_dict: FilterTypeAlias,
    defaults: FilterTypeAlias,
) -> FilterTypeAlias:
    """Return the same dict with legacy keys stripped/converted."""

    if RawConfigFilterKeys.LegacyMorphemizerDescription in filter_dict:
        filter_dict.pop(RawConfigFilterKeys.LegacyMorphemizerDescription, None)
        prioritysieve_globals.new_config_found = True

    if RawConfigFilterKeys.LegacyPrioritySelection in filter_dict:
        legacy_value = filter_dict.pop(RawConfigFilterKeys.LegacyPrioritySelection)
        if RawConfigFilterKeys.PRIORITY_FILES not in filter_dict:
            filter_dict[RawConfigFilterKeys.PRIORITY_FILES] = legacy_value
        prioritysieve_globals.new_config_found = True

    if RawConfigFilterKeys.LegacyExtraReadingField in filter_dict:
        legacy_extra = filter_dict.pop(RawConfigFilterKeys.LegacyExtraReadingField)
        if isinstance(legacy_extra, bool):
            filter_dict.setdefault(
                RawConfigFilterKeys.EXTRA_READING_FIELD,
                legacy_extra,
            )
        prioritysieve_globals.new_config_found = True

    for obsolete_key in (
        "extra_all_morphs",
        "extra_all_morphs_count",
        "extra_unknown_morphs",
        "extra_unknown_morphs_count",
        "extra_highlighted",
        "extra_score",
        "extra_score_terms",
        "extra_study_morphs",
    ):
        if filter_dict.pop(obsolete_key, None) is not None:
            prioritysieve_globals.new_config_found = True

    # Ensure required keys exist so downstream access does not explode.
    for key, default_value in defaults.items():
        filter_dict.setdefault(key, default_value)

    return filter_dict


class PrioritySieveConfigFilter:  # pylint:disable=too-many-instance-attributes
    def __init__(self, _filter: FilterTypeAlias, defaults: FilterTypeAlias) -> None:
        try:
            self._default_config_dict = defaults
            self._filter = _normalize_filter_dict(_filter, defaults)
            self.has_error: bool = False

            self.note_type: str = self._get_filter_item(
                key=RawConfigFilterKeys.NOTE_TYPE, expected_type=str
            )
            self.tags: dict[str, list[str]] = self._sanitize_tags()
            self.field: str = self._get_filter_item(
                key=RawConfigFilterKeys.FIELD, expected_type=str
            )
            self.furigana_field: str = self._get_filter_item(
                key=RawConfigFilterKeys.FURIGANA_FIELD, expected_type=str
            )
            self.reading_field: str = self._get_filter_item(
                key=RawConfigFilterKeys.READING_FIELD, expected_type=str
            )
            self.reading_priority: str = self._get_reading_priority()
            self._priority_files: list[str] = self._get_priority_files()
            self.read: bool = self._get_filter_item(
                key=RawConfigFilterKeys.READ, expected_type=bool
            )
            self.modify: bool = self._get_filter_item(
                key=RawConfigFilterKeys.MODIFY, expected_type=bool
            )
            self.extra_reading_field: bool = self._get_filter_item(
                key=RawConfigFilterKeys.EXTRA_READING_FIELD, expected_type=bool
            )
            self.duplicate_sort_field: str = self._get_filter_item(
                key=RawConfigFilterKeys.DUPLICATE_SORT_FIELD, expected_type=str
            )
            self.duplicate_sort_numeric: bool = self._get_filter_item(
                key=RawConfigFilterKeys.DUPLICATE_SORT_NUMERIC, expected_type=bool
            )

        except AssertionError:
            self.has_error = True
            if not prioritysieve_globals.config_broken:
                show_critical_config_error()
                prioritysieve_globals.config_broken = True

    @property
    def expression_field(self) -> str:
        return getattr(self, "field", "(none)")

    @property
    def priority_files(self) -> list[str]:
        return getattr(self, "_priority_files", [])

    def _sanitize_tags(self) -> dict[str, list[str]]:
        raw_tags = self._get_filter_item(
            key=RawConfigFilterKeys.TAGS, expected_type=dict
        )
        include = raw_tags.get("include", [])
        exclude = raw_tags.get("exclude", [])
        include_list = include if isinstance(include, list) else []
        exclude_list = exclude if isinstance(exclude, list) else []
        sanitized = {"include": include_list, "exclude": exclude_list}
        self._filter[RawConfigFilterKeys.TAGS] = sanitized
        return sanitized

    def _get_priority_files(self) -> list[str]:
        raw_value = self._filter.get(RawConfigFilterKeys.PRIORITY_FILES, [])
        normalized = self._normalize_priority_files(raw_value)
        self._filter[RawConfigFilterKeys.PRIORITY_FILES] = normalized
        return normalized

    @staticmethod
    def _normalize_priority_files(value: Any) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            candidates = []

        normalized: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            entry = candidate.strip()
            if not entry or entry == prioritysieve_globals.NONE_OPTION:
                continue
            if entry not in normalized:
                normalized.append(entry)

        return normalized

    def _get_reading_priority(self) -> str:
        default_value = self._default_config_dict[RawConfigFilterKeys.READING_PRIORITY]
        value = self._filter.get(RawConfigFilterKeys.READING_PRIORITY, default_value)

        if not isinstance(value, str):
            value = default_value

        if value not in (
            prioritysieve_globals.READING_PRIORITY_FURIGANA_FIRST,
            prioritysieve_globals.READING_PRIORITY_READING_FIRST,
        ):
            value = default_value

        self._filter[RawConfigFilterKeys.READING_PRIORITY] = value
        return value

    def _get_filter_item(self, key: str, expected_type: type) -> Any:
        try:
            filter_item = self._filter[key]
        except KeyError:
            filter_item = self._default_config_dict[key]
            prioritysieve_globals.new_config_found = True

        assert isinstance(filter_item, expected_type)
        return filter_item


LanguageTypeAlias = dict[
    str,
    Union[str, bool, int, list[Any], dict[str, Any], None],
]


class PrioritySieveLanguageConfig:  # pylint:disable=too-many-instance-attributes
    """Configuration for a single language profile."""

    def __init__(
        self,
        language_dict: LanguageTypeAlias,
        defaults: LanguageTypeAlias,
        filter_defaults: FilterTypeAlias,
    ) -> None:
        try:
            self._language_dict = language_dict
            self._defaults = defaults
            self._filter_defaults = filter_defaults
            self.has_error: bool = False

            self.name: str = self._get_item(
                key=RawConfigLanguageKeys.NAME, expected_type=str
            )
            self.prefix: str = self._get_item(
                key=RawConfigLanguageKeys.PREFIX, expected_type=str
            )
            self.language_type: str = self._get_language_type()
            self.filters: list[PrioritySieveConfigFilter] = self._get_filters()
            self.preprocess_ignore_bracket_contents: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS,
                expected_type=bool,
            )
            self.preprocess_ignore_round_bracket_contents: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS,
                expected_type=bool,
            )
            self.preprocess_ignore_slim_round_bracket_contents: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS,
                expected_type=bool,
            )
            self.preprocess_ignore_angle_bracket_contents: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS,
                expected_type=bool,
            )
            self.preprocess_ignore_numbers: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS,
                expected_type=bool,
            )
            self.preprocess_ignore_custom_characters: bool = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_CUSTOM_CHARACTERS,
                expected_type=bool,
            )
            self.preprocess_custom_characters_to_ignore: str = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE,
                expected_type=str,
            )
            self.preprocess_ignore_suspended_unless_tags: str = self._get_item(
                key=RawConfigLanguageKeys.PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS,
                expected_type=str,
            )
            self.auto_suspend_unlisted_entries: bool = self._get_item(
                key=RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES,
                expected_type=bool,
            )
            self.auto_suspend_variant_spellings: bool = self._get_item(
                key=RawConfigLanguageKeys.AUTO_SUSPEND_VARIANT_SPELLINGS,
                expected_type=bool,
            )
            self.merge_kana_variant_spellings: bool = self._get_item(
                key=RawConfigLanguageKeys.MERGE_KANA_VARIANT_SPELLINGS,
                expected_type=bool,
            )
            self.recalc_offset_priority_decks: list[str] = self._get_deck_list(
                RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS
            )
            self.disabled_decks: list[str] = self._get_deck_list(
                RawConfigLanguageKeys.DISABLED_DECKS
            )
            # Note: hide_recalc_toolbar, hide_reviewed_counter, hide_tracked_counter
            # are now global settings in PrioritySieveConfig, not per-language
            self.deduplicate_toolbar_counts: bool = self._get_item(
                key=RawConfigLanguageKeys.DEDUPLICATE_TOOLBAR_COUNTS,
                expected_type=bool,
            )

        except AssertionError:
            self.has_error = True
            if not prioritysieve_globals.config_broken:
                show_critical_config_error()
                prioritysieve_globals.config_broken = True

    def _get_language_type(self) -> str:
        default_value = self._defaults.get(
            RawConfigLanguageKeys.LANGUAGE_TYPE, LANGUAGE_TYPE_JAPANESE
        )
        value = self._language_dict.get(
            RawConfigLanguageKeys.LANGUAGE_TYPE, default_value
        )
        if value not in (LANGUAGE_TYPE_JAPANESE, LANGUAGE_TYPE_OTHER):
            value = default_value
        self._language_dict[RawConfigLanguageKeys.LANGUAGE_TYPE] = value
        return str(value)

    def _get_filters(self) -> list[PrioritySieveConfigFilter]:
        filters_raw = self._language_dict.get(RawConfigLanguageKeys.FILTERS, [])
        if not isinstance(filters_raw, list):
            filters_raw = []

        filters: list[PrioritySieveConfigFilter] = []
        for _filter in filters_raw:
            if isinstance(_filter, dict):
                am_filter = PrioritySieveConfigFilter(_filter, self._filter_defaults)
                if not am_filter.has_error:
                    filters.append(am_filter)
        return filters

    def _get_deck_list(self, key: str) -> list[str]:
        raw_value = self._language_dict.get(key, [])
        if not isinstance(raw_value, list):
            raw_value = []

        sanitized: list[str] = []
        seen: set[str] = set()
        for deck in raw_value:
            if not isinstance(deck, str):
                continue
            trimmed = deck.strip()
            if not trimmed or trimmed in seen:
                continue
            sanitized.append(trimmed)
            seen.add(trimmed)
        return sanitized

    def _get_item(self, key: str, expected_type: type) -> Any:
        try:
            item = self._language_dict[key]
        except KeyError:
            prioritysieve_globals.new_config_found = True
            item = self._defaults.get(key)
            if item is None:
                # Use empty default for the type
                if expected_type == bool:
                    item = False
                elif expected_type == str:
                    item = ""
                elif expected_type == list:
                    item = []
                else:
                    item = None
        assert isinstance(item, expected_type)
        return item

    def get_preprocess_ignore_suspended_unless_tag_list(self) -> list[str]:
        tags_value = self.preprocess_ignore_suspended_unless_tags
        if not isinstance(tags_value, str):
            return []

        seen: set[str] = set()
        sanitized: list[str] = []
        for raw_tag in tags_value.split(","):
            tag = raw_tag.strip()
            if not tag or tag in seen:
                continue
            sanitized.append(tag)
            seen.add(tag)

        return sanitized

    @property
    def is_japanese(self) -> bool:
        return self.language_type == LANGUAGE_TYPE_JAPANESE


class PrioritySieveConfig:  # pylint:disable=too-many-instance-attributes
    def __init__(self, is_default: bool = False) -> None:
        try:
            self._config_dict = normalize_config_keys(get_config_dict())
            self._default_config_dict = get_all_defaults_config_dict()
            self._is_default = is_default

            if not is_default and self._config_dict != get_config_dict():
                _persist_normalized_config(self._config_dict)

            # Global settings: shortcuts
            self.shortcut_recalc: QKeySequence = self._get_key_sequence_config(
                key=RawConfigKeys.SHORTCUT_RECALC,
                expected_type=str,
                use_default=is_default,
            )
            self.shortcut_settings: QKeySequence = self._get_key_sequence_config(
                key=RawConfigKeys.SHORTCUT_SETTINGS,
                expected_type=str,
                use_default=is_default,
            )
            self.shortcut_browse_same_unknown: QKeySequence = (
                self._get_key_sequence_config(
                    key=RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
                    expected_type=str,
                    use_default=is_default,
                )
            )
            self.shortcut_browse_same_unknown_broad: QKeySequence = (
                self._get_key_sequence_config(
                    key=RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD,
                    expected_type=str,
                    use_default=is_default,
                )
            )
            self.shortcut_set_known_and_skip: QKeySequence = (
                self._get_key_sequence_config(
                    key=RawConfigKeys.SHORTCUT_SET_KNOWN_AND_SKIP,
                    expected_type=str,
                    use_default=is_default,
                )
            )
            self.shortcut_learn_now: QKeySequence = self._get_key_sequence_config(
                key=RawConfigKeys.SHORTCUT_LEARN_NOW,
                expected_type=str,
                use_default=is_default,
            )
            self.shortcut_generators: QKeySequence = self._get_key_sequence_config(
                key=RawConfigKeys.SHORTCUT_GENERATORS,
                expected_type=str,
                use_default=is_default,
            )
            self.shortcut_progression: QKeySequence = self._get_key_sequence_config(
                key=RawConfigKeys.SHORTCUT_PROGRESSION,
                expected_type=str,
                use_default=is_default,
            )
            self.shortcut_known_entries_exporter: QKeySequence = (
                self._get_key_sequence_config(
                    key=RawConfigKeys.SHORTCUT_KNOWN_ENTRIES_EXPORTER,
                    expected_type=str,
                    use_default=is_default,
                )
            )

            # Global settings: sync
            self.recalc_on_sync: bool = self._get_config_item(
                key=RawConfigKeys.RECALC_ON_SYNC,
                expected_type=bool,
                use_default=is_default,
            )
            self.recalc_after_sync: bool = self._get_config_item(
                key=RawConfigKeys.RECALC_AFTER_SYNC,
                expected_type=bool,
                use_default=is_default,
            )

            # Global settings: tags
            self.tag_ready: str = self._get_config_item(
                key=RawConfigKeys.TAG_READY,
                expected_type=str,
                use_default=is_default,
            )
            self.tag_not_ready: str = self._get_config_item(
                key=RawConfigKeys.TAG_NOT_READY,
                expected_type=str,
                use_default=is_default,
            )
            self.tag_known_manually: str = self._get_config_item(
                key=RawConfigKeys.TAG_KNOWN_MANUALLY,
                expected_type=str,
                use_default=is_default,
            )
            self.tag_suspended_automatically: str = self._get_config_item(
                key=RawConfigKeys.TAG_SUSPENDED_AUTOMATICALLY,
                expected_type=str,
                use_default=is_default,
            )

            # Global settings: toolbar visibility
            self.hide_recalc_toolbar: bool = self._get_config_item(
                key=RawConfigKeys.HIDE_RECALC_TOOLBAR,
                expected_type=bool,
                use_default=is_default,
            )
            self.hide_reviewed_counter: bool = self._get_config_item(
                key=RawConfigKeys.HIDE_REVIEWED_COUNTER,
                expected_type=bool,
                use_default=is_default,
            )
            self.hide_tracked_counter: bool = self._get_config_item(
                key=RawConfigKeys.HIDE_TRACKED_COUNTER,
                expected_type=bool,
                use_default=is_default,
            )

            # Per-language settings
            self.languages: list[PrioritySieveLanguageConfig] = (
                self._get_language_configs()
            )

        except AssertionError:
            if not prioritysieve_globals.config_broken:
                show_critical_config_error()
                prioritysieve_globals.config_broken = True

    def _get_language_configs(self) -> list[PrioritySieveLanguageConfig]:
        source = (
            self._default_config_dict if self._is_default else self._config_dict
        )
        languages_raw = source.get(RawConfigKeys.LANGUAGES, [])
        if not isinstance(languages_raw, list):
            languages_raw = []

        default_languages = self._default_config_dict.get(RawConfigKeys.LANGUAGES, [])
        default_language = default_languages[0] if default_languages else {}
        default_filters = default_language.get(RawConfigLanguageKeys.FILTERS, [])
        default_filter = default_filters[0] if default_filters else {}

        languages: list[PrioritySieveLanguageConfig] = []
        for lang_dict in languages_raw:
            if isinstance(lang_dict, dict):
                lang_config = PrioritySieveLanguageConfig(
                    lang_dict, default_language, default_filter
                )
                if not lang_config.has_error:
                    languages.append(lang_config)

        return languages

    @property
    def filters(self) -> list[PrioritySieveConfigFilter]:
        """Return all filters from all languages (for backward compatibility)."""
        all_filters: list[PrioritySieveConfigFilter] = []
        for lang in self.languages:
            all_filters.extend(lang.filters)
        return all_filters

    def get_config_filters(
        self, is_default: bool = False  # noqa: ARG002
    ) -> list[PrioritySieveConfigFilter]:
        """Return all filters from all languages (for backward compatibility)."""
        return self.filters

    def get_language(self, name: str) -> PrioritySieveLanguageConfig | None:
        """Get a language config by name."""
        for lang in self.languages:
            if lang.name == name:
                return lang
        return None

    def get_language_for_note_type(
        self, note_type: str
    ) -> PrioritySieveLanguageConfig | None:
        """Get the language config that contains the given note type."""
        for lang in self.languages:
            for flt in lang.filters:
                if flt.note_type == note_type:
                    return lang
        return None

    def get_all_note_types(self) -> set[str]:
        """Get all note types used across all languages."""
        note_types: set[str] = set()
        for lang in self.languages:
            for flt in lang.filters:
                if flt.note_type != prioritysieve_globals.NONE_OPTION:
                    note_types.add(flt.note_type)
        return note_types

    def update(self) -> None:
        new_config = PrioritySieveConfig()
        self.__dict__.update(new_config.__dict__)

    # Backward compatibility properties that delegate to first language
    @property
    def _first_language(self) -> PrioritySieveLanguageConfig | None:
        return self.languages[0] if self.languages else None

    @property
    def preprocess_ignore_bracket_contents(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_bracket_contents if lang else False

    @property
    def preprocess_ignore_round_bracket_contents(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_round_bracket_contents if lang else False

    @property
    def preprocess_ignore_slim_round_bracket_contents(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_slim_round_bracket_contents if lang else False

    @property
    def preprocess_ignore_angle_bracket_contents(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_angle_bracket_contents if lang else False

    @property
    def preprocess_ignore_numbers(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_numbers if lang else False

    @property
    def preprocess_ignore_custom_characters(self) -> bool:
        lang = self._first_language
        return lang.preprocess_ignore_custom_characters if lang else False

    @property
    def preprocess_custom_characters_to_ignore(self) -> str:
        lang = self._first_language
        return lang.preprocess_custom_characters_to_ignore if lang else ""

    @property
    def preprocess_ignore_suspended_unless_tags(self) -> str:
        lang = self._first_language
        return lang.preprocess_ignore_suspended_unless_tags if lang else ""

    @property
    def auto_suspend_unlisted_entries(self) -> bool:
        lang = self._first_language
        return lang.auto_suspend_unlisted_entries if lang else False

    @property
    def auto_suspend_variant_spellings(self) -> bool:
        lang = self._first_language
        return lang.auto_suspend_variant_spellings if lang else False

    @property
    def merge_kana_variant_spellings(self) -> bool:
        lang = self._first_language
        return lang.merge_kana_variant_spellings if lang else False

    @property
    def recalc_offset_priority_decks(self) -> list[str]:
        lang = self._first_language
        return lang.recalc_offset_priority_decks if lang else []

    @property
    def disabled_decks(self) -> list[str]:
        lang = self._first_language
        return lang.disabled_decks if lang else []

    # Note: hide_recalc_toolbar, hide_reviewed_counter, hide_tracked_counter
    # are now global settings defined in __init__

    @property
    def deduplicate_toolbar_counts(self) -> bool:
        lang = self._first_language
        return lang.deduplicate_toolbar_counts if lang else False

    def get_preprocess_ignore_suspended_unless_tag_list(self) -> list[str]:
        lang = self._first_language
        return lang.get_preprocess_ignore_suspended_unless_tag_list() if lang else []

    def _get_key_sequence_config(
        self,
        key: str,
        expected_type: type,
        use_default: bool,
    ) -> QKeySequence:
        config_item: str = self._get_config_item(key, expected_type, use_default)
        assert isinstance(config_item, str)
        return QKeySequence(config_item)

    def _get_config_item(
        self,
        key: str,
        expected_type: type,
        use_default: bool,
    ) -> Any:
        try:
            item = (
                self._default_config_dict[key]
                if use_default
                else self._config_dict[key]
            )
        except KeyError:
            prioritysieve_globals.new_config_found = True
            item = self._default_config_dict[key]

        assert isinstance(item, expected_type)
        return item


def get_config_dict() -> dict[str, Any]:
    assert mw is not None
    config_dict: dict[str, Any] | None = mw.addonManager.getConfig(__name__)
    assert config_dict is not None
    return config_dict


def get_all_defaults_config_dict() -> dict[str, Any]:
    assert mw is not None
    addon = mw.addonManager.addonFromModule(__name__)
    default_config_dict: dict[str, Any] | None = mw.addonManager.addonConfigDefaults(
        addon
    )
    assert default_config_dict is not None
    return default_config_dict


def normalize_config_keys(configs: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(configs)

    for old_key, new_key in LEGACY_KEY_RENAMES.items():
        if old_key in normalized:
            if new_key not in normalized:
                normalized[new_key] = normalized[old_key]
            normalized.pop(old_key, None)
            prioritysieve_globals.new_config_found = True

    for obsolete_key in LEGACY_KEYS_TO_DROP:
        if obsolete_key in normalized:
            normalized.pop(obsolete_key, None)
            prioritysieve_globals.new_config_found = True

    legacy_fresh_tag = normalized.pop("tag_fresh", None)
    if isinstance(legacy_fresh_tag, str):
        trimmed_tag = legacy_fresh_tag.strip()
        if trimmed_tag:
            prioritysieve_globals.legacy_fresh_tags.add(trimmed_tag)
            prioritysieve_globals.new_config_found = True
    elif legacy_fresh_tag is not None:
        prioritysieve_globals.new_config_found = True

    legacy_known_auto_tag = normalized.pop("tag_known_automatically", None)
    if isinstance(legacy_known_auto_tag, str):
        trimmed_tag = legacy_known_auto_tag.strip()
        if trimmed_tag:
            prioritysieve_globals.legacy_known_automatically_tags.add(trimmed_tag)
            prioritysieve_globals.new_config_found = True
    elif legacy_known_auto_tag is not None:
        prioritysieve_globals.new_config_found = True

    # Migrate legacy config structure to new language-based structure
    if RawConfigKeys.LANGUAGES not in normalized:
        normalized = _migrate_to_language_config(normalized)
        prioritysieve_globals.new_config_found = True

    # Normalize filters within each language
    defaults = get_all_defaults_config_dict()
    default_languages = defaults.get(RawConfigKeys.LANGUAGES, [])
    default_language = default_languages[0] if default_languages else {}
    default_filters = default_language.get(RawConfigLanguageKeys.FILTERS, [])
    default_filter = default_filters[0] if default_filters else {}

    languages = normalized.get(RawConfigKeys.LANGUAGES, [])
    if isinstance(languages, list):
        for lang in languages:
            if isinstance(lang, dict):
                filters_obj = lang.get(RawConfigLanguageKeys.FILTERS, [])
                if isinstance(filters_obj, list):
                    for item in filters_obj:
                        if isinstance(item, dict):
                            _normalize_filter_dict(item, default_filter)

    return normalized


# Keys to migrate from root to language config
_LEGACY_LANGUAGE_KEYS = [
    (RawConfigKeys.LEGACY_FILTERS, RawConfigLanguageKeys.FILTERS),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_BRACKET_CONTENTS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_NUMBERS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_NUMBERS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_CUSTOM_CHARACTERS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_CUSTOM_CHARACTERS,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE,
        RawConfigLanguageKeys.PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE,
    ),
    (
        RawConfigKeys.LEGACY_PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS,
        RawConfigLanguageKeys.PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS,
    ),
    (
        RawConfigKeys.LEGACY_AUTO_SUSPEND_UNLISTED_ENTRIES,
        RawConfigLanguageKeys.AUTO_SUSPEND_UNLISTED_ENTRIES,
    ),
    (
        RawConfigKeys.LEGACY_AUTO_SUSPEND_VARIANT_SPELLINGS,
        RawConfigLanguageKeys.AUTO_SUSPEND_VARIANT_SPELLINGS,
    ),
    (
        RawConfigKeys.LEGACY_MERGE_KANA_VARIANT_SPELLINGS,
        RawConfigLanguageKeys.MERGE_KANA_VARIANT_SPELLINGS,
    ),
    (
        RawConfigKeys.LEGACY_RECALC_OFFSET_PRIORITY_DECKS,
        RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS,
    ),
    (RawConfigKeys.LEGACY_DISABLED_DECKS, RawConfigLanguageKeys.DISABLED_DECKS),
    # deduplicate_toolbar_counts stays per-language (depends on variant spelling logic)
    (
        RawConfigKeys.LEGACY_DEDUPLICATE_TOOLBAR_COUNTS,
        RawConfigLanguageKeys.DEDUPLICATE_TOOLBAR_COUNTS,
    ),
    # Note: Toolbar visibility settings (hide_recalc_toolbar, hide_reviewed_counter,
    # hide_tracked_counter) are intentionally NOT migrated to per-language config -
    # they remain global settings at the root level.
]


def _migrate_to_language_config(configs: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy flat config to language-based config."""
    # Create a "Default" language with settings from root
    default_language: dict[str, Any] = {
        RawConfigLanguageKeys.NAME: "Default",
        RawConfigLanguageKeys.PREFIX: "",
        RawConfigLanguageKeys.LANGUAGE_TYPE: LANGUAGE_TYPE_JAPANESE,
    }

    # Move per-language keys from root to language config
    for legacy_key, new_key in _LEGACY_LANGUAGE_KEYS:
        if legacy_key in configs:
            default_language[new_key] = configs.pop(legacy_key)

    # Also handle the legacy single-deck key
    if "recalc_offset_priority_deck" in configs:
        legacy_deck = configs.pop("recalc_offset_priority_deck")
        if isinstance(legacy_deck, str) and legacy_deck.strip():
            default_language[RawConfigLanguageKeys.RECALC_OFFSET_PRIORITY_DECKS] = [
                legacy_deck.strip()
            ]

    configs[RawConfigKeys.LANGUAGES] = [default_language]
    return configs


def load_stored_am_configs(
    stored_config: dict[str, str | int | float | bool | object],
) -> None:
    assert mw is not None

    default_configs = copy.deepcopy(get_all_defaults_config_dict())
    normalized_stored = normalize_config_keys(stored_config)

    for key, value in normalized_stored.items():
        default_configs[key] = value

    mw.addonManager.writeConfig(__name__, default_configs)
    save_config_to_am_file(default_configs)


def update_configs(new_configs: dict[str, Any]) -> None:
    assert mw is not None
    config = get_config_dict()
    config.update(new_configs)
    normalized = normalize_config_keys(config)
    _persist_normalized_config(normalized)


def update_language_config(
    language_name: str,
    language_settings: dict[str, Any],
    global_settings: dict[str, Any] | None = None,
) -> None:
    """Update settings for a specific language and optionally global settings."""
    assert mw is not None
    config = get_config_dict()

    # Update global settings at root level
    if global_settings:
        for key, value in global_settings.items():
            config[key] = value

    # Update language-specific settings in the languages array
    languages = config.get(RawConfigKeys.LANGUAGES, [])
    for lang in languages:
        if lang.get(RawConfigLanguageKeys.NAME) == language_name:
            for key, value in language_settings.items():
                lang[key] = value
            break

    config[RawConfigKeys.LANGUAGES] = languages
    normalized = normalize_config_keys(config)
    _persist_normalized_config(normalized)


def _persist_normalized_config(configs: dict[str, Any]) -> None:
    assert mw is not None
    mw.addonManager.writeConfig(__name__, configs)
    save_config_to_am_file(configs)


def save_config_to_am_file(
    configs: dict[str, str | int | float | bool | object],
) -> None:
    assert mw is not None
    profile_name = getattr(mw.pm, "name", None)
    if not profile_name:
        # During early startup, the profile name can be unset. Defer writing until the
        # profile is fully loaded to avoid TypeError from profileFolder().
        return
    profile_settings_path = Path(
        mw.pm.profileFolder(), prioritysieve_globals.PROFILE_SETTINGS_FILE_NAME
    )
    with open(profile_settings_path, mode="w", encoding="utf-8") as file:
        json.dump(configs, file, sort_keys=True)


def reset_all_configs() -> None:
    assert mw is not None
    default_configs = get_all_defaults_config_dict()
    mw.addonManager.writeConfig(__name__, default_configs)
    assert default_configs is not None
    save_config_to_am_file(default_configs)


def get_read_enabled_filters() -> list[PrioritySieveConfigFilter]:
    config_filters = PrioritySieveConfig().get_config_filters()
    assert isinstance(config_filters, list)
    return [flt for flt in config_filters if flt.read]


def get_modify_enabled_filters() -> list[PrioritySieveConfigFilter]:
    config_filters = PrioritySieveConfig().get_config_filters()
    assert isinstance(config_filters, list)
    return [flt for flt in config_filters if flt.modify]


def get_matching_filter(note: Note) -> PrioritySieveConfigFilter | None:
    assert mw is not None
    config_filters = PrioritySieveConfig().get_config_filters()
    assert isinstance(config_filters, list)

    for am_filter in config_filters:
        note_type_id: NotetypeId | None = mw.col.models.id_for_name(am_filter.note_type)
        if note_type_id == note.mid:
            return am_filter
    return None


def get_matching_modify_filter(note: Note) -> PrioritySieveConfigFilter | None:
    assert mw is not None
    modify_filters: list[PrioritySieveConfigFilter] = get_modify_enabled_filters()

    for am_filter in modify_filters:
        note_type_id: NotetypeId | None = mw.col.models.id_for_name(am_filter.note_type)
        if note_type_id == note.mid:
            return am_filter
    return None


def get_matching_read_filter(note: Note) -> PrioritySieveConfigFilter | None:
    assert mw is not None
    read_filters: list[PrioritySieveConfigFilter] = get_read_enabled_filters()
    for am_filter in read_filters:
        note_type_id: NotetypeId | None = mw.col.models.id_for_name(am_filter.note_type)
        if note_type_id == note.mid:
            return am_filter
    return None


def show_critical_config_error() -> None:
    critical_box = QMessageBox(mw)
    critical_box.setWindowTitle("PrioritySieve Error")
    critical_box.setIcon(QMessageBox.Icon.Critical)
    ok_button: QPushButton = QPushButton("OK")
    critical_box.addButton(ok_button, QMessageBox.ButtonRole.YesRole)
    body: str = (
        "<b>Unexpected config type!</b>"
        "<br><br>"
        "The saved configs are malformed and will cause exceptions if left as is."
        "<br><br>"
        "Please do the following:"
        "<ol>"
        "<li> Restart Anki without add-ons (hold shift while opening Anki)"
        "<li> Restore the default configs of PrioritySieve<br>"
        "    Tools -> add-ons -> select PrioritySieve -> config -> restore defaults"
        "<li> Delete the 'prioritysieve_profile_settings.json' file in the Anki profile folder"
        "<li> Restart Anki"
        "</ol>"
    )
    critical_box.setTextFormat(Qt.TextFormat.RichText)
    critical_box.setText(body)
    critical_box.exec()
