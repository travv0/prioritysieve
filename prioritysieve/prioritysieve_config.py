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

    # Legacy keys we still accept when loading stored configs
    LegacyPrioritySelection = "morph_priority_selection"
    LegacyMorphemizerDescription = "morphemizer_description"
    LegacyExtraReadingField = "extra_morph_readings"


class RawConfigKeys:
    FILTERS = "filters"
    SHORTCUT_RECALC = "shortcut_recalc"
    SHORTCUT_SETTINGS = "shortcut_settings"
    SHORTCUT_BROWSE_SAME_UNKNOWN = "shortcut_browse_same_unknown"
    SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD = "shortcut_browse_same_unknown_broad"
    SHORTCUT_SET_KNOWN_AND_SKIP = "shortcut_set_known_and_skip"
    SHORTCUT_LEARN_NOW = "shortcut_learn_now"
    SHORTCUT_GENERATORS = "shortcut_generators"
    SHORTCUT_PROGRESSION = "shortcut_progression"
    SHORTCUT_KNOWN_ENTRIES_EXPORTER = "shortcut_known_entries_exporter"
    TOOLBAR_STATS_USE_KNOWN = "toolbar_stats_use_known"
    TOOLBAR_STATS_USE_SEEN = "toolbar_stats_use_seen"
    PREPROCESS_IGNORE_BRACKET_CONTENTS = "preprocess_ignore_bracket_contents"
    PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS = "preprocess_ignore_round_bracket_contents"
    PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS = "preprocess_ignore_slim_round_bracket_contents"
    PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS = "preprocess_ignore_angle_bracket_contents"
    PREPROCESS_IGNORE_NUMBERS = "preprocess_ignore_numbers"
    PREPROCESS_IGNORE_CUSTOM_CHARACTERS = "preprocess_ignore_custom_characters"
    PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE = "preprocess_custom_characters_to_ignore"
    PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS = "preprocess_ignore_suspended_unless_tags"
    RECALC_ON_SYNC = "recalc_on_sync"
    RECALC_AFTER_SYNC = "recalc_after_sync"
    AUTO_SUSPEND_UNLISTED_ENTRIES = "auto_suspend_unlisted_entries"
    RECALC_OFFSET_PRIORITY_DECKS = "recalc_offset_priority_decks"
    HIDE_RECALC_TOOLBAR = "hide_recalc_toolbar"
    HIDE_REVIEWED_COUNTER = "hide_reviewed_counter"
    HIDE_TRACKED_COUNTER = "hide_tracked_counter"
    TAG_READY = "tag_ready"
    TAG_NOT_READY = "tag_not_ready"
    TAG_KNOWN_AUTOMATICALLY = "tag_known_automatically"
    TAG_KNOWN_MANUALLY = "tag_known_manually"
    TAG_SUSPENDED_AUTOMATICALLY = "tag_suspended_automatically"
    TAG_LEARN_CARD_NOW = "tag_learn_card_now"


LEGACY_KEY_RENAMES: dict[str, str] = {
    "shortcut_browse_ready_same_unknown": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
    "shortcut_browse_all_same_unknown": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN,
    "shortcut_browse_ready_same_unknown_lemma": RawConfigKeys.SHORTCUT_BROWSE_SAME_UNKNOWN_BROAD,
    "shortcut_known_morphs_exporter": RawConfigKeys.SHORTCUT_KNOWN_ENTRIES_EXPORTER,
    "hide_lemma_toolbar": RawConfigKeys.HIDE_REVIEWED_COUNTER,
    "hide_inflection_toolbar": RawConfigKeys.HIDE_TRACKED_COUNTER,
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


class PrioritySieveConfig:  # pylint:disable=too-many-instance-attributes
    def __init__(self, is_default: bool = False) -> None:
        try:
            self._config_dict = normalize_config_keys(get_config_dict())
            self._default_config_dict = get_all_defaults_config_dict()

            if not is_default and self._config_dict != get_config_dict():
                _persist_normalized_config(self._config_dict)

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
            self.toolbar_stats_use_known: bool = self._get_config_item(
                key=RawConfigKeys.TOOLBAR_STATS_USE_KNOWN,
                expected_type=bool,
                use_default=is_default,
            )
            self.toolbar_stats_use_seen: bool = self._get_config_item(
                key=RawConfigKeys.TOOLBAR_STATS_USE_SEEN,
                expected_type=bool,
                use_default=is_default,
            )
            self.preprocess_ignore_bracket_contents: bool = self._get_config_item(
                key=RawConfigKeys.PREPROCESS_IGNORE_BRACKET_CONTENTS,
                expected_type=bool,
                use_default=is_default,
            )
            self.preprocess_ignore_round_bracket_contents: bool = (
                self._get_config_item(
                    key=RawConfigKeys.PREPROCESS_IGNORE_ROUND_BRACKET_CONTENTS,
                    expected_type=bool,
                    use_default=is_default,
                )
            )
            self.preprocess_ignore_slim_round_bracket_contents: bool = (
                self._get_config_item(
                    key=RawConfigKeys.PREPROCESS_IGNORE_SLIM_ROUND_BRACKET_CONTENTS,
                    expected_type=bool,
                    use_default=is_default,
                )
            )
            self.preprocess_ignore_angle_bracket_contents: bool = (
                self._get_config_item(
                    key=RawConfigKeys.PREPROCESS_IGNORE_ANGLE_BRACKET_CONTENTS,
                    expected_type=bool,
                    use_default=is_default,
                )
            )
            self.preprocess_ignore_numbers: bool = self._get_config_item(
                key=RawConfigKeys.PREPROCESS_IGNORE_NUMBERS,
                expected_type=bool,
                use_default=is_default,
            )
            self.preprocess_ignore_custom_characters: bool = self._get_config_item(
                key=RawConfigKeys.PREPROCESS_IGNORE_CUSTOM_CHARACTERS,
                expected_type=bool,
                use_default=is_default,
            )
            self.preprocess_custom_characters_to_ignore: str = self._get_config_item(
                key=RawConfigKeys.PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE,
                expected_type=str,
                use_default=is_default,
            )
            self.preprocess_ignore_suspended_unless_tags: str = self._get_config_item(
                key=RawConfigKeys.PREPROCESS_IGNORE_SUSPENDED_UNLESS_TAGS,
                expected_type=str,
                use_default=is_default,
            )
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
            self.auto_suspend_unlisted_entries: bool = self._get_config_item(
                key=RawConfigKeys.AUTO_SUSPEND_UNLISTED_ENTRIES,
                expected_type=bool,
                use_default=is_default,
            )
            self.recalc_offset_priority_decks: list[str] = self._get_priority_deck_list(
                is_default
            )
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
            self.tag_known_automatically: str = self._get_config_item(
                key=RawConfigKeys.TAG_KNOWN_AUTOMATICALLY,
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
            self.tag_learn_card_now: str = self._get_config_item(
                key=RawConfigKeys.TAG_LEARN_CARD_NOW,
                expected_type=str,
                use_default=is_default,
            )

            self.filters: list[PrioritySieveConfigFilter] = self.get_config_filters(
                is_default
            )

        except AssertionError:
            if not prioritysieve_globals.config_broken:
                show_critical_config_error()
                prioritysieve_globals.config_broken = True

    def update(self) -> None:
        new_config = PrioritySieveConfig()
        self.__dict__.update(new_config.__dict__)

    def _get_key_sequence_config(
        self,
        key: str,
        expected_type: type,
        use_default: bool,
    ) -> QKeySequence:
        config_item: str = self._get_config_item(key, expected_type, use_default)
        assert isinstance(config_item, str)
        return QKeySequence(config_item)

    def get_config_filters(
        self, is_default: bool = False
    ) -> list[PrioritySieveConfigFilter]:
        config_filters = self._get_config_item(
            key=RawConfigKeys.FILTERS,
            expected_type=list,
            use_default=is_default,
        )

        defaults = self._default_config_dict.get(RawConfigKeys.FILTERS, [])
        default_filter = defaults[0] if defaults else {}

        filters: list[PrioritySieveConfigFilter] = []
        for _filter in config_filters:
            if isinstance(_filter, dict):
                am_filter = PrioritySieveConfigFilter(_filter, default_filter)
                if not am_filter.has_error:
                    filters.append(am_filter)
        return filters

    def _get_priority_deck_list(self, is_default: bool) -> list[str]:
        key = RawConfigKeys.RECALC_OFFSET_PRIORITY_DECKS
        legacy_key = "recalc_offset_priority_deck"
        source = self._default_config_dict if is_default else self._config_dict

        def sanitize(decks: list[object]) -> list[str]:
            sanitized: list[str] = []
            seen: set[str] = set()
            for deck in decks:
                if not isinstance(deck, str):
                    continue
                trimmed = deck.strip()
                if not trimmed or trimmed in seen:
                    continue
                sanitized.append(trimmed)
                seen.add(trimmed)
            return sanitized

        if key in source:
            decks = source[key]
            assert isinstance(decks, list)
            sanitized = sanitize(decks)
            if not is_default and sanitized != decks:
                self._persist_priority_decks(sanitized)
                source[key] = sanitized
            return sanitized

        if not is_default and legacy_key in source:
            legacy_value = source.get(legacy_key)
            legacy_list: list[object] = []
            if isinstance(legacy_value, str):
                trimmed = legacy_value.strip()
                if trimmed:
                    legacy_list = [trimmed]
            sanitized_legacy = sanitize(legacy_list)
            self._persist_priority_decks(sanitized_legacy)
            source[key] = sanitized_legacy
            source.pop(legacy_key, None)
            return sanitized_legacy

        default_value = self._default_config_dict.get(key, [])
        assert isinstance(default_value, list)
        sanitized_default = sanitize(default_value)
        if not is_default:
            self._persist_priority_decks(sanitized_default)
            source[key] = sanitized_default
        return sanitized_default

    def _persist_priority_decks(self, decks: list[str]) -> None:
        assert mw is not None
        config = get_config_dict()
        config[RawConfigKeys.RECALC_OFFSET_PRIORITY_DECKS] = decks
        if "recalc_offset_priority_deck" in config:
            config.pop("recalc_offset_priority_deck", None)
        mw.addonManager.writeConfig(__name__, config)
        save_config_to_am_file(config)

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

    filters_obj = normalized.get(RawConfigKeys.FILTERS)
    defaults = get_all_defaults_config_dict()
    default_filters = defaults.get(RawConfigKeys.FILTERS, [])
    default_filter = default_filters[0] if default_filters else {}
    if isinstance(filters_obj, list):
        for item in filters_obj:
            if isinstance(item, dict):
                _normalize_filter_dict(item, default_filter)

    return normalized


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


def _persist_normalized_config(configs: dict[str, Any]) -> None:
    assert mw is not None
    mw.addonManager.writeConfig(__name__, configs)
    save_config_to_am_file(configs)


def save_config_to_am_file(
    configs: dict[str, str | int | float | bool | object],
) -> None:
    assert mw is not None
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
