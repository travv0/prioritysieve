from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable

from anki.cards import Card
from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from anki.notes import Note
from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import tooltip

from .. import (
    message_box_utils,
    prioritysieve_config,
    prioritysieve_globals,
    progress_utils,
    tags_and_queue_utils,
)
from ..entry_db import EntryDB
from ..priority_files import load_priority_map
from ..prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from ..prioritysieve_globals import DEFAULT_REVIEW_DUE, GENERATOR_DIALOG_NAME
from ..priority_files import ensure_directories
from ..exceptions import (
    AnkiFieldNotFound,
    AnkiNoteTypeNotFound,
    CancelledOperationException,
    DefaultSettingsException,
    PriorityFileMalformedException,
    PriorityFileNotFoundException,
)
from ..anki_op_utils import notify_op_execution
from . import caching
from .anki_data_utils import create_card_data_dict

_last_modified_cards_count: int = 0
_last_modified_notes_count: int = 0
_recent_card_diffs: list[str] = []
_recent_note_diffs: list[str] = []
_followup_sync_callback: Callable[[], None] | None = None


def set_followup_sync_callback(callback: Callable[[], None] | None) -> None:
    global _followup_sync_callback
    _followup_sync_callback = callback


def _collect_filters_state(filters: list[PrioritySieveConfigFilter]) -> list[dict[str, int | str]]:
    assert mw is not None
    assert mw.col is not None and mw.col.db is not None

    state: list[dict[str, int | str]] = []
    model_manager = mw.col.models

    for config_filter in filters:
        note_type_name = config_filter.note_type
        if note_type_name == prioritysieve_globals.NONE_OPTION:
            continue

        note_type_id = model_manager.id_for_name(note_type_name)
        if note_type_id is None:
            continue

        include_tags = config_filter.tags.get("include", [])
        exclude_tags = config_filter.tags.get("exclude", [])

        where_clauses = ["notes.mid = ?"]
        params: list[object] = [note_type_id]

        for tag in include_tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
            where_clauses.append("notes.tags LIKE ?")
            params.append(f"% {tag.strip()} %")

        for tag in exclude_tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
            where_clauses.append("notes.tags NOT LIKE ?")
            params.append(f"% {tag.strip()} %")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1"
        params_tuple = tuple(params)

        card_stats = mw.col.db.first(
            f"""
            SELECT COUNT(cards.id), COALESCE(MAX(cards.mod), 0), COALESCE(MAX(cards.id), 0)
            FROM cards
            JOIN notes ON notes.id = cards.nid
            WHERE {where_sql}
            """,
            *params_tuple,
        )

        note_stats = mw.col.db.first(
            f"""
            SELECT COUNT(notes.id), COALESCE(MAX(notes.mod), 0), COALESCE(MAX(notes.id), 0)
            FROM notes
            WHERE {where_sql}
            """,
            *params_tuple,
        )

        if card_stats is None or note_stats is None:
            continue

        card_count, card_max_mod, card_max_id = card_stats
        note_count, note_max_mod, note_max_id = note_stats

        state.append(
            {
                "id": _get_filter_identifier(config_filter),
                "card_count": int(card_count),
                "card_max_mod": int(card_max_mod),
                "card_max_id": int(card_max_id),
                "note_count": int(note_count),
                "note_max_mod": int(note_max_mod),
                "note_max_id": int(note_max_id),
            }
        )

    state.sort(key=lambda entry: entry["id"])
    return state


def _get_filter_identifier(config_filter: PrioritySieveConfigFilter) -> str:
    include_tags = sorted(
        tag.strip()
        for tag in config_filter.tags.get("include", [])
        if isinstance(tag, str) and tag.strip()
    )
    exclude_tags = sorted(
        tag.strip()
        for tag in config_filter.tags.get("exclude", [])
        if isinstance(tag, str) and tag.strip()
    )

    return "|".join(
        (
            config_filter.note_type,
            f"inc:{','.join(include_tags)}",
            f"exc:{','.join(exclude_tags)}",
        )
    )


def compute_modify_filters_state() -> list[dict[str, int | str]]:
    filters = prioritysieve_config.get_modify_enabled_filters()
    filters += prioritysieve_config.get_read_enabled_filters()
    return _collect_filters_state(filters)


def recalc() -> None:
    assert mw is not None

    am_config = PrioritySieveConfig()
    read_filters = prioritysieve_config.get_read_enabled_filters()
    modify_filters = prioritysieve_config.get_modify_enabled_filters()
    combined_filters = _merge_unique_filters(read_filters + modify_filters)

    try:
        _validate_filters(combined_filters)
    except DefaultSettingsException:
        message_box_utils.show_warning_box(
            "Default settings detected",
            "Configure PrioritySieve in Tools → PrioritySieve Settings before running Recalc.",
        )
        return

    mw.checkpoint("PrioritySieve Recalc")

    operation = QueryOp(
        parent=mw,
        op=lambda _: _background_recalc(am_config, combined_filters, modify_filters),
        success=lambda _: _on_success(),
    )
    operation.failure(_on_failure)
    operation.with_progress().run_in_background()


def _merge_unique_filters(
    filters: list[PrioritySieveConfigFilter],
) -> list[PrioritySieveConfigFilter]:
    seen: set[str] = set()
    unique: list[PrioritySieveConfigFilter] = []
    for config_filter in filters:
        identifier = _get_filter_identifier(config_filter)
        if identifier in seen:
            continue
        seen.add(identifier)
        unique.append(config_filter)
    return unique


def _validate_filters(filters: list[PrioritySieveConfigFilter]) -> None:
    assert mw is not None
    model_manager = mw.col.models

    for config_filter in filters:
        note_type_name = config_filter.note_type
        if note_type_name == prioritysieve_globals.NONE_OPTION:
            raise DefaultSettingsException()

        note_type_id = model_manager.id_for_name(note_type_name)
        if note_type_id is None:
            raise AnkiNoteTypeNotFound()

        note_type_dict = model_manager.get(note_type_id)
        assert note_type_dict is not None
        field_names = model_manager.field_names(note_type_dict)

        if config_filter.field not in field_names:
            raise AnkiFieldNotFound()
        if (
            config_filter.furigana_field != prioritysieve_globals.NONE_OPTION
            and config_filter.furigana_field not in field_names
        ):
            raise AnkiFieldNotFound()
        if (
            config_filter.reading_field != prioritysieve_globals.NONE_OPTION
            and config_filter.reading_field not in field_names
        ):
            raise AnkiFieldNotFound()

        for selection in config_filter.morph_priority_selections:
            if selection in (prioritysieve_globals.NONE_OPTION, prioritysieve_globals.COLLECTION_FREQUENCY_OPTION):
                continue
            path = (
                Path(mw.pm.profileFolder())
                / prioritysieve_globals.PRIORITY_FILES_DIR_NAME
                / selection
            )
            if not path.is_file():
                raise PriorityFileNotFoundException(str(path))


def _background_recalc(
    am_config: PrioritySieveConfig,
    all_filters: list[PrioritySieveConfigFilter],
    modify_filters: list[PrioritySieveConfigFilter],
) -> None:
    ensure_directories()
    caching.cache_entries(am_config, all_filters)
    _apply_priorities(am_config, modify_filters)


def _apply_priorities(
    am_config: PrioritySieveConfig,
    modify_filters: list[PrioritySieveConfigFilter],
) -> None:
    assert mw is not None
    assert mw.col is not None

    with EntryDB() as db:
        entry_cache = db.get_card_entry_cache()

    cards_to_update: dict[int, Card] = {}
    notes_to_update: dict[int, Note] = {}
    card_original_state: dict[int, tuple[int, int]] = {}
    note_original_tags: dict[int, list[str]] = {}

    duplicates: defaultdict[
        tuple[str, str],
        list[tuple[Card, Note, int, bool]],
    ] = defaultdict(list)

    for config_filter in modify_filters:
        priority_map = load_priority_map(config_filter.morph_priority_selections)
        card_data_dict = create_card_data_dict(am_config, config_filter)

        total_cards = len(card_data_dict)
        for index, (card_id, card_data) in enumerate(card_data_dict.items(), start=1):
            progress_utils.background_update_progress_potentially_cancel(
                label=f"Updating {config_filter.note_type} cards<br>card: {index} of {total_cards}",
                counter=index,
                max_value=total_cards,
            )

            card = mw.col.get_card(card_id)
            note = card.note()

            entry = entry_cache.get(card_id)
            if entry is None:
                entry = Entry(text=card_data.expression, reading="", reviewed=False)

            due = priority_map.get(entry.key(), DEFAULT_REVIEW_DUE)
            auto_suspend = am_config.auto_suspend_unlisted_entries and entry.key() not in priority_map

            if card_id not in card_original_state:
                card_original_state[card_id] = (card.due, card.queue)
            if note.id not in note_original_tags:
                note_original_tags[note.id] = note.tags.copy()

            card.due = due
            allowed_new_queues = (QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED)
            if card.type == CARD_TYPE_NEW and card.queue in allowed_new_queues:
                card.queue = QUEUE_TYPE_NEW

            tags_and_queue_utils.apply_entry_tags(
                am_config=am_config,
                note=note,
                reviewed=entry.reviewed,
                auto_suspend=auto_suspend,
            )

            if config_filter.extra_reading_field and entry.reading:
                tags_and_queue_utils.update_entry_reading_field(note, entry.reading)

            cards_to_update[card_id] = card
            notes_to_update[note.id] = note

            duplicates[entry.key()].append((card, note, due, auto_suspend))

    _apply_duplicate_rules(am_config, duplicates)

    if cards_to_update:
        card_changes = mw.col.update_cards(list(cards_to_update.values()))
        notify_op_execution(card_changes)
    if notes_to_update:
        note_changes = mw.col.update_notes(list(notes_to_update.values()))
        notify_op_execution(note_changes)

    _record_recent_changes(card_original_state, note_original_tags, cards_to_update, notes_to_update)


def _apply_duplicate_rules(
    am_config: PrioritySieveConfig,
    duplicates: defaultdict[tuple[str, str], list[tuple[Card, Note, int, bool]]],
) -> None:
    for entry_key, items in duplicates.items():
        items.sort(key=lambda item: item[2])
        for index, (card, note, _due, auto_suspend) in enumerate(items):
            if index == 0 and not auto_suspend:
                if card.queue == QUEUE_TYPE_SUSPENDED:
                    card.queue = QUEUE_TYPE_NEW
                if am_config.tag_suspended_automatically in note.tags:
                    note.tags.remove(am_config.tag_suspended_automatically)
            else:
                card.queue = QUEUE_TYPE_SUSPENDED
                if am_config.tag_suspended_automatically not in note.tags:
                    note.tags.append(am_config.tag_suspended_automatically)


def _record_recent_changes(
    card_original_state: dict[int, tuple[int, int]],
    note_original_tags: dict[int, list[str]],
    cards: dict[int, Card],
    notes: dict[int, Note],
) -> None:
    global _recent_card_diffs, _recent_note_diffs
    _recent_card_diffs.clear()
    _recent_note_diffs.clear()

    for card_id, card in cards.items():
        original_due, original_queue = card_original_state.get(card_id, (card.due, card.queue))
        if card.due != original_due or card.queue != original_queue:
            if len(_recent_card_diffs) < 5:
                _recent_card_diffs.append(
                    f"card {card_id}: due {original_due}→{card.due}, queue {original_queue}→{card.queue}"
                )

    for note_id, note in notes.items():
        original_tags = note_original_tags.get(note_id, note.tags)
        if note.tags != original_tags:
            if len(_recent_note_diffs) < 5:
                _recent_note_diffs.append(
                    f"note {note_id}: tags {original_tags}→{note.tags}"
                )


def _on_success() -> None:
    tooltip("PrioritySieve recalc complete", parent=mw)


def _on_failure(error: Exception | PriorityFileMalformedException) -> None:
    if isinstance(error, CancelledOperationException):
        tooltip("PrioritySieve recalc cancelled", parent=mw)
        return

    message_box_utils.show_critical_error_box("PrioritySieve recalc failed", str(error))

