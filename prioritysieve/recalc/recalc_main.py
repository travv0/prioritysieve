from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

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
from ..entry import Entry
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


@dataclass(slots=True)
class DuplicateCandidate:
    card: Card
    note: Note
    due: int
    auto_suspend: bool
    is_new_card: bool
    entry_reviewed: bool
    deck_priority: int


def set_followup_sync_callback(callback: Callable[[], None] | None) -> None:
    global _followup_sync_callback
    _followup_sync_callback = callback


def _should_skip_card(
    card: Card,
    note: Note,
    auto_tag: str,
    suspended_exception_tags: Collection[str],
) -> bool:
    if card.queue != QUEUE_TYPE_SUSPENDED:
        return False

    if auto_tag in note.tags:
        return False

    for tag in suspended_exception_tags:
        if tag in note.tags:
            return False

    return True


def _collect_filters_state(filters: list[PrioritySieveConfigFilter]) -> list[dict[str, int | str]]:
    assert mw is not None
    if mw.col is None or mw.col.db is None:
        raise CancelledOperationException()

    state: list[dict[str, int | str]] = []
    model_manager = mw.col.models

    for config_filter in filters:
        note_type_name = config_filter.note_type
        if note_type_name == prioritysieve_globals.NONE_OPTION:
            raise DefaultSettingsException()

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


def _build_deck_priority_lookup(
    configured_order: Collection[str],
) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for index, raw_name in enumerate(configured_order):
        if not isinstance(raw_name, str):
            continue
        deck_name = raw_name.strip()
        if not deck_name or deck_name in lookup:
            continue
        lookup[deck_name] = index
    return lookup


def _get_deck_priority_for_card(
    card: Card,
    deck_priority_lookup: dict[str, int],
    deck_name_cache: dict[int, str],
) -> int:
    assert mw is not None
    if mw.col is None:
        raise CancelledOperationException()

    deck_id = getattr(card, "odid", 0) or card.did
    deck_name = deck_name_cache.get(deck_id)
    if deck_name is None:
        deck_dict = mw.col.decks.get(deck_id)
        name = deck_dict.get("name") if isinstance(deck_dict, dict) else None
        deck_name = name if isinstance(name, str) else ""
        deck_name_cache[deck_id] = deck_name

    default_priority = len(deck_priority_lookup)
    return deck_priority_lookup.get(deck_name, default_priority)


def _filters_requiring_state_snapshot() -> list[PrioritySieveConfigFilter]:
    """Return filters used to snapshot collection state before recalc."""

    modify_filters = prioritysieve_config.get_modify_enabled_filters()
    read_filters = prioritysieve_config.get_read_enabled_filters()
    return _merge_unique_filters(modify_filters + read_filters)


def _validate_filters(filters: list[PrioritySieveConfigFilter]) -> None:
    assert mw is not None
    if mw.col is None:
        raise CancelledOperationException()
    model_manager = mw.col.models

    invalid_filters: list[str] = []

    for index, config_filter in enumerate(filters, start=1):
        note_type_name = config_filter.note_type
        if note_type_name == prioritysieve_globals.NONE_OPTION:
            invalid_filters.append(
                f"Filter #{index} has note type set to {prioritysieve_globals.NONE_OPTION!r}"
            )
            continue

        note_type_id = model_manager.id_for_name(note_type_name)
        if note_type_id is None:
            raise AnkiNoteTypeNotFound()

        note_type_dict = model_manager.get(note_type_id)
        assert note_type_dict is not None
        field_names = model_manager.field_names(note_type_dict)

        if config_filter.field == prioritysieve_globals.NONE_OPTION:
            invalid_filters.append(
                f"Filter #{index} ({note_type_name}) has expression field set to {prioritysieve_globals.NONE_OPTION!r}"
            )
            continue

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

        for selection in config_filter.priority_files:
            if selection in (prioritysieve_globals.NONE_OPTION, prioritysieve_globals.COLLECTION_FREQUENCY_OPTION):
                continue
            path = (
                Path(mw.pm.profileFolder())
                / prioritysieve_globals.PRIORITY_FILES_DIR_NAME
                / selection
            )
            if not path.is_file():
                raise PriorityFileNotFoundException(str(path))

    if invalid_filters:
        raise DefaultSettingsException("\n".join(invalid_filters))


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
    if mw.col is None:
        raise CancelledOperationException()

    with EntryDB() as db:
        entry_cache = db.get_card_entry_cache()

    cards_to_update: dict[int, Card] = {}
    notes_to_update: dict[int, Note] = {}
    card_original_state: dict[int, tuple[int, int]] = {}
    note_original_tags: dict[int, list[str]] = {}

    duplicates: defaultdict[
        tuple[str, str],
        list[DuplicateCandidate],
    ] = defaultdict(list)

    suspended_exception_tags = set(am_config.get_preprocess_ignore_suspended_unless_tag_list())
    deck_priority_lookup = _build_deck_priority_lookup(am_config.recalc_offset_priority_decks)
    deck_name_cache: dict[int, str] = {}

    for config_filter in modify_filters:
        priority_map = load_priority_map(config_filter.priority_files)
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

            if _should_skip_card(
                card,
                note,
                am_config.tag_suspended_automatically,
                suspended_exception_tags,
            ):
                continue

            deck_priority = _get_deck_priority_for_card(
                card,
                deck_priority_lookup,
                deck_name_cache,
            )

            entry = entry_cache.get(card_id)
            if entry is None:
                entry = Entry(
                    text=card_data.expression,
                    reading="",
                    reviewed=card.type != CARD_TYPE_NEW,
                )

            is_new_card = card.type == CARD_TYPE_NEW
            entry_reviewed = entry.reviewed
            base_auto_suspend = (
                am_config.auto_suspend_unlisted_entries
                and entry.key() not in priority_map
            )
            auto_suspend = base_auto_suspend or (entry_reviewed and is_new_card)

            if is_new_card:
                if card_id not in card_original_state:
                    card_original_state[card_id] = (card.due, card.queue)
                if note.id not in note_original_tags:
                    note_original_tags[note.id] = note.tags.copy()

                if entry_reviewed or auto_suspend:
                    due = DEFAULT_REVIEW_DUE
                else:
                    due = priority_map.get(entry.key(), DEFAULT_REVIEW_DUE)
                card.due = due

                allowed_new_queues = (QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED)
                if not entry_reviewed and card.queue in allowed_new_queues:
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
            else:
                due = card.due

            duplicates[entry.key()].append(
                DuplicateCandidate(
                    card=card,
                    note=note,
                    due=due,
                    auto_suspend=auto_suspend,
                    is_new_card=is_new_card,
                    entry_reviewed=entry_reviewed,
                    deck_priority=deck_priority,
                )
            )

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
    duplicates: defaultdict[tuple[str, str], list[DuplicateCandidate]],
) -> None:
    for _, items in duplicates.items():
        items.sort(
            key=lambda item: (
                item.deck_priority,
                item.due,
                getattr(item.card, "id", 0),
            )
        )
        has_review_card = any(not candidate.is_new_card for candidate in items)
        active_slot_available = True

        for candidate in items:
            if not candidate.is_new_card:
                continue

            force_suspend = candidate.auto_suspend or has_review_card
            if active_slot_available and not force_suspend:
                active_slot_available = False
                if candidate.card.queue == QUEUE_TYPE_SUSPENDED:
                    candidate.card.queue = QUEUE_TYPE_NEW
                if am_config.tag_suspended_automatically in candidate.note.tags:
                    candidate.note.tags.remove(am_config.tag_suspended_automatically)
            else:
                candidate.auto_suspend = True
                candidate.card.queue = QUEUE_TYPE_SUSPENDED
                if (
                    candidate.card.type == CARD_TYPE_NEW
                    and candidate.card.due != DEFAULT_REVIEW_DUE
                ):
                    candidate.card.due = DEFAULT_REVIEW_DUE
                if am_config.tag_suspended_automatically not in candidate.note.tags:
                    candidate.note.tags.append(am_config.tag_suspended_automatically)


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

    if isinstance(error, DefaultSettingsException):
        base_message = (
            f'Found a note filter containing a "{prioritysieve_globals.NONE_OPTION}" option. '
            "Please select something else."
        )
        details = str(error).strip()
        if details:
            body = f"{base_message}<br><br>{details.replace(chr(10), '<br>')}"
        else:
            body = base_message
        message_box_utils.show_critical_error_box("PrioritySieve recalc failed", body)
        return

    message_box_utils.show_critical_error_box("PrioritySieve recalc failed", str(error))
