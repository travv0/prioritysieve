from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
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
from ..extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
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
_recalc_in_progress: bool = False


def recalc_in_progress() -> bool:
    return _recalc_in_progress


@dataclass(slots=True)
class CardPlan:
    card_id: int
    note_id: int
    entry_key: tuple[str, str]
    is_new_card: bool
    entry_reviewed: bool
    deck_priority: int
    manually_suspended: bool
    original_due: int
    desired_due: int
    original_queue: int
    desired_queue: int
    auto_suspend: bool
    deck_id: int
    original_deck_id: int
    original_tags: list[str]
    desired_tags: list[str]
    extra_reading_field_index: int | None
    desired_reading: str | None


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

    start_time = time.time()
    operation = QueryOp(
        parent=mw,
        op=lambda _: _background_recalc(am_config, combined_filters, modify_filters),
        success=lambda _: _on_success(start_time),
    )
    operation.failure(_on_failure)
    global _recalc_in_progress
    _recalc_in_progress = True
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


def _get_deck_priority_for_ids(
    deck_priority_lookup: dict[str, int],
    deck_name_cache: dict[int, str],
    original_deck_id: int,
    current_deck_id: int,
) -> int:
    assert mw is not None
    if mw.col is None:
        raise CancelledOperationException()

    deck_id = original_deck_id or current_deck_id
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


def filters_have_pending_changes(
    am_config: PrioritySieveConfig,
    filters: list[PrioritySieveConfigFilter],
) -> bool:
    """Return True if any filter has cards/notes with unsynced changes."""

    assert mw is not None
    if mw.col is None:
        return False

    changed_filters: list[str] = []
    for config_filter in filters:
        identifier = _get_filter_identifier(config_filter)
        has_changes = _filter_has_pending_changes(am_config, config_filter)
        print(
            f"PrioritySieve pending-change probe: {identifier} -> {has_changes}"
        )
        if has_changes:
            changed_filters.append(identifier)

    if changed_filters:
        print(
            "PrioritySieve pending-change summary: detected changes in "
            + ", ".join(changed_filters)
        )
        return True

    print("PrioritySieve pending-change summary: no relevant changes detected")
    return False


def _filter_has_pending_changes(
    am_config: PrioritySieveConfig,
    config_filter: PrioritySieveConfigFilter,
) -> bool:
    assert mw is not None
    if mw.col is None or mw.col.db is None:
        return False

    note_type_id = mw.col.models.id_for_name(config_filter.note_type)
    if note_type_id is None:
        return False

    manual_known_tag = am_config.tag_known_manually.strip()
    auto_suspended_tag = am_config.tag_suspended_automatically.strip()
    exception_tags = [
        tag.strip()
        for tag in am_config.get_preprocess_ignore_suspended_unless_tag_list()
        if isinstance(tag, str) and tag.strip()
    ]

    ignore_clauses = ["cards.queue != ?"]
    ignore_params: list[object] = [QUEUE_TYPE_SUSPENDED]

    if manual_known_tag:
        ignore_clauses.append("notes.tags LIKE ?")
        ignore_params.append(f"% {manual_known_tag} %")
    if auto_suspended_tag:
        ignore_clauses.append("notes.tags LIKE ?")
        ignore_params.append(f"% {auto_suspended_tag} %")
    for tag in exception_tags:
        ignore_clauses.append("notes.tags LIKE ?")
        ignore_params.append(f"% {tag} %")

    include_tags = config_filter.tags.get("include", [])
    exclude_tags = config_filter.tags.get("exclude", [])

    where_clauses = ["notes.mid = ?"]
    params: list[object] = [note_type_id]

    for tag in include_tags:
        if isinstance(tag, str) and tag.strip():
            where_clauses.append("notes.tags LIKE ?")
            params.append(f"% {tag.strip()} %")

    for tag in exclude_tags:
        if isinstance(tag, str) and tag.strip():
            where_clauses.append("notes.tags NOT LIKE ?")
            params.append(f"% {tag.strip()} %")

    where_clauses.append("(" + " OR ".join(ignore_clauses) + ")")
    params.extend(ignore_params)
    where_clauses.append("(cards.usn != 0 OR notes.usn != 0)")

    sql = (
        "SELECT 1 FROM cards "
        "JOIN notes ON notes.id = cards.nid "
        "WHERE " + " AND ".join(where_clauses) + " LIMIT 1"
    )

    try:
        result = mw.col.db.scalar(sql, *params)
    except Exception as error:  # pylint:disable=broad-except
        print(
            "PrioritySieve pending-change probe error:"
            f" {error} (filter {_get_filter_identifier(config_filter)})"
        )
        return False

    if result is None:
        return False

    try:
        sample_sql = sql.replace(
            "SELECT 1",
            "SELECT cards.id, cards.usn, cards.queue, notes.usn, notes.tags",
        ).replace("LIMIT 1", "LIMIT 5")
        sample_rows = mw.col.db.all(sample_sql, *params)
    except Exception as error:  # pylint:disable=broad-except
        print(
            "PrioritySieve pending-change sample error:"
            f" {error} (filter {_get_filter_identifier(config_filter)})"
        )
        sample_rows = []

    if sample_rows:
        print("PrioritySieve pending-change samples (card_id, card_usn, queue, note_usn, tags):")
        for row in sample_rows:
            card_id, card_usn, queue, note_usn, tags = row
            print(
                f"  card {card_id}: card_usn={card_usn}, queue={queue}, note_usn={note_usn}, tags={tags}"
            )

    return True


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
    caching.cache_entries(am_config, all_filters)


def _apply_priorities(
    am_config: PrioritySieveConfig,
    modify_filters: list[PrioritySieveConfigFilter],
) -> None:
    assert mw is not None
    if mw.col is None:
        raise CancelledOperationException()

    with EntryDB() as db:
        entry_cache = db.get_card_entry_cache()

    touched_cards: dict[int, Card] = {}
    touched_notes: dict[int, Note] = {}
    card_original_state: dict[int, tuple[int, int]] = {}
    note_original_state: dict[int, tuple[list[str], list[str]]] = {}

    card_change_stats: dict[str, int] = {
        "total": 0,
        "due": 0,
        "queue": 0,
        "due_and_queue": 0,
    }
    note_change_stats: dict[str, int] = {
        "total": 0,
        "tags": 0,
        "fields": 0,
    }
    card_change_samples: list[str] = []
    note_change_samples: list[str] = []
    due_transition_counter: Counter[tuple[int, int]] = Counter()
    queue_transition_counter: Counter[tuple[int, int]] = Counter()
    tags_added_counter: Counter[str] = Counter()
    tags_removed_counter: Counter[str] = Counter()
    tag_reorder_samples: list[str] = []

    suspended_exception_tags = set(am_config.get_preprocess_ignore_suspended_unless_tag_list())
    deck_priority_lookup = _build_deck_priority_lookup(am_config.recalc_offset_priority_decks)
    deck_name_cache: dict[int, str] = {}
    plans: dict[int, CardPlan] = {}
    duplicates: defaultdict[tuple[str, str], list[CardPlan]] = defaultdict(list)

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

            tags_list = list(card_data.original_tags)
            tags_set = {tag for tag in tags_list if tag}
            has_exception_tag = any(tag in tags_set for tag in suspended_exception_tags)
            if (
                card_data.queue == QUEUE_TYPE_SUSPENDED
                and am_config.tag_suspended_automatically not in tags_set
                and not has_exception_tag
            ):
                continue

            entry = entry_cache.get(card_id)
            if entry is None:
                entry = Entry(
                    text=card_data.expression,
                    reading="",
                    reviewed=card_data.type != CARD_TYPE_NEW,
                )

            is_new_card = card_data.type == CARD_TYPE_NEW
            entry_reviewed = entry.reviewed
            base_auto_suspend = (
                am_config.auto_suspend_unlisted_entries
                and entry.key() not in priority_map
            )
            auto_suspend = base_auto_suspend or (entry_reviewed and is_new_card)

            manually_suspended_exception = (
                card_data.queue == QUEUE_TYPE_SUSPENDED
                and am_config.tag_suspended_automatically not in tags_set
                and has_exception_tag
            )

            desired_due = card_data.due
            desired_queue = card_data.queue
            desired_tags: list[str] = list(tags_list)
            desired_reading: str | None = None

            if is_new_card:
                card_original_state.setdefault(card_id, (card_data.due, card_data.queue))
                note_original_state.setdefault(
                    card_data.note_id,
                    (card_data.fields.copy(), card_data.original_tags.copy()),
                )

                if entry_reviewed or auto_suspend:
                    desired_due = DEFAULT_REVIEW_DUE
                else:
                    desired_due = priority_map.get(entry.key(), DEFAULT_REVIEW_DUE)

                allowed_new_queues = (QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED)
                if (
                    not entry_reviewed
                    and card_data.queue in allowed_new_queues
                    and not manually_suspended_exception
                ):
                    desired_queue = QUEUE_TYPE_NEW

                desired_tags = tags_and_queue_utils.compute_entry_tags(
                    am_config=am_config,
                    tags=card_data.original_tags,
                    auto_suspend=auto_suspend,
                )

                if config_filter.extra_reading_field and entry.reading:
                    reading_index = card_data.extra_reading_field_index
                    if reading_index is None or reading_index >= len(card_data.fields):
                        desired_reading = entry.reading
                    else:
                        current_reading = card_data.fields[reading_index]
                        if entry.reading != current_reading:
                            desired_reading = entry.reading
            else:
                manually_suspended_exception = False

            deck_priority = _get_deck_priority_for_ids(
                deck_priority_lookup=deck_priority_lookup,
                deck_name_cache=deck_name_cache,
                original_deck_id=card_data.original_deck_id,
                current_deck_id=card_data.deck_id,
            )

            plan = CardPlan(
                card_id=card_id,
                note_id=card_data.note_id,
                entry_key=entry.key(),
                is_new_card=is_new_card,
                entry_reviewed=entry_reviewed,
                deck_priority=deck_priority,
                manually_suspended=manually_suspended_exception,
                original_due=card_data.due,
                desired_due=desired_due,
                original_queue=card_data.queue,
                desired_queue=desired_queue,
                auto_suspend=auto_suspend,
                deck_id=card_data.deck_id,
                original_deck_id=card_data.original_deck_id,
                original_tags=list(card_data.original_tags),
                desired_tags=list(desired_tags),
                extra_reading_field_index=card_data.extra_reading_field_index,
                desired_reading=desired_reading,
            )

            plans[card_id] = plan
            card_original_state.setdefault(card_id, (plan.original_due, plan.original_queue))
            duplicates[entry.key()].append(plan)

    _apply_duplicate_rules(am_config, duplicates, note_original_state)

    card_cache: dict[int, Card] = {}
    note_cache: dict[int, Note] = {}

    cards_to_update: dict[int, Card] = {}
    notes_to_update: dict[int, Note] = {}
    touched_cards.clear()
    touched_notes.clear()

    for plan in plans.values():
        card_needs_update = (
            plan.desired_due != plan.original_due
            or plan.desired_queue != plan.original_queue
        )
        note_needs_update = (
            plan.desired_tags != plan.original_tags
            or plan.desired_reading is not None
        )

        if not card_needs_update and not note_needs_update:
            continue

        if card_needs_update:
            card = card_cache.get(plan.card_id)
            if card is None:
                card = mw.col.get_card(plan.card_id)
                card_cache[plan.card_id] = card
            touched_cards[plan.card_id] = card
            card.due = plan.desired_due
            card.queue = plan.desired_queue
            cards_to_update[plan.card_id] = card
        note: Note | None = None
        if note_needs_update:
            note = note_cache.get(plan.note_id)
            if note is None:
                note = mw.col.get_note(plan.note_id)
                note_cache[plan.note_id] = note
            touched_notes[plan.note_id] = note
            note_original_state.setdefault(
                plan.note_id,
                (note.fields.copy(), note.tags.copy()),
            )

            if plan.desired_tags != note.tags:
                note.tags = list(plan.desired_tags)

            if plan.desired_reading is not None:
                tags_and_queue_utils.update_entry_reading_field(
                    note,
                    plan.desired_reading,
                )

            notes_to_update[plan.note_id] = note

    for card_id, card in touched_cards.items():
        original_due, original_queue = card_original_state.get(
            card_id, (card.due, card.queue)
        )
        due_changed = card.due != original_due
        queue_changed = card.queue != original_queue
        if due_changed or queue_changed:
            cards_to_update[card_id] = card
            card_change_stats["total"] += 1
            if due_changed:
                card_change_stats["due"] += 1
                due_transition_counter[(original_due, card.due)] += 1
            if queue_changed:
                card_change_stats["queue"] += 1
                queue_transition_counter[(original_queue, card.queue)] += 1
            if due_changed and queue_changed:
                card_change_stats["due_and_queue"] += 1

            if len(card_change_samples) < 50:
                card_type_label = "new" if card.type == CARD_TYPE_NEW else "review"
                reason_parts: list[str] = []
                if due_changed:
                    reason_parts.append(f"due {original_due}->{card.due}")
                if queue_changed:
                    reason_parts.append(f"queue {original_queue}->{card.queue}")
                reason_parts.append(f"deck {card.did}")

                note = touched_notes.get(card.nid)
                tag_summary = ""
                if note is not None:
                    tag_summary = (
                        f", tags:{', '.join(sorted(tag for tag in note.tags if tag))}"
                        if note.tags
                        else ", tags:[]"
                    )

                sample = (
                    f"card {card_id} (note {card.nid}, {card_type_label}): "
                    + ", ".join(reason_parts)
                    + tag_summary
                )
                card_change_samples.append(sample)

    invalid_tag_notes: list[str] = []

    for note_id, note in touched_notes.items():
        original_fields, original_tags = note_original_state.get(
            note_id, (note.fields, note.tags)
        )
        fields_changed = note.fields != original_fields
        tags_changed = note.tags != original_tags

        invalid_tags = [tag for tag in note.tags if not isinstance(tag, str) or not tag.strip()]
        if invalid_tags and len(invalid_tag_notes) < 50:
            invalid_tag_notes.append(
                f"note {note_id}: invalid tags {', '.join(repr(tag) for tag in invalid_tags)}"
            )

        if fields_changed or tags_changed:
            notes_to_update[note_id] = note
            note_change_stats["total"] += 1
            changes_summary: list[str] = []

            if tags_changed:
                note_change_stats["tags"] += 1
                added_tags = sorted(set(note.tags) - set(original_tags))
                removed_tags = sorted(set(original_tags) - set(note.tags))
                for tag in added_tags:
                    tags_added_counter[tag] += 1
                for tag in removed_tags:
                    tags_removed_counter[tag] += 1
                tag_change_details: list[str] = []
                if added_tags:
                    tag_change_details.append("+" + ",".join(added_tags))
                if removed_tags:
                    tag_change_details.append("-" + ",".join(removed_tags))
                if not tag_change_details:
                    tag_change_details.append("reordered")
                    if len(tag_reorder_samples) < 25:
                        tag_reorder_samples.append(
                            f"note {note_id}: {original_tags} -> {note.tags}"
                        )
                changes_summary.append("tags " + " ".join(tag_change_details))

            if fields_changed:
                note_change_stats["fields"] += 1
                changed_field_indexes = []
                for index, (before, after) in enumerate(zip(original_fields, note.fields)):
                    if before != after:
                        changed_field_indexes.append(index)
                if changed_field_indexes:
                    changes_summary.append(
                        "fields idx "
                        + ",".join(str(index) for index in changed_field_indexes)
                    )
                elif len(original_fields) != len(note.fields):
                    changes_summary.append(
                        f"field count {len(original_fields)}->{len(note.fields)}"
                    )
                else:
                    changes_summary.append("fields changed")

            if len(note_change_samples) < 50:
                try:
                    note_type = note.note_type()
                    note_type_name = (
                        note_type.get("name", "") if isinstance(note_type, dict) else ""
                    )
                except Exception:
                    note_type_name = ""
                prefix = f"note {note_id}"
                if note_type_name:
                    prefix += f" ({note_type_name})"
                note_change_samples.append(prefix + ": " + "; ".join(changes_summary))

    if cards_to_update:
        card_changes = mw.col.update_cards(list(cards_to_update.values()))
        notify_op_execution(card_changes)
    if notes_to_update:
        note_changes = mw.col.update_notes(list(notes_to_update.values()))
        notify_op_execution(note_changes)

    global _last_modified_cards_count, _last_modified_notes_count
    _last_modified_cards_count = len(cards_to_update)
    _last_modified_notes_count = len(notes_to_update)

    _record_recent_changes(
        card_original_state,
        note_original_state,
        cards_to_update,
        notes_to_update,
    )

    total_touched_cards = len(touched_cards)
    total_touched_notes = len(touched_notes)

    if total_touched_cards or total_touched_notes:
        print("PrioritySieve recalc debug summary:")
        print(f"  config auto-suspend tag: {am_config.tag_suspended_automatically!r}")
        if invalid_tag_notes:
            print("  notes with invalid tags encountered:")
            for entry in invalid_tag_notes:
                print("    " + entry)
        print(
            f"  touched cards: {total_touched_cards}, cards to update: {card_change_stats['total']} "
            f"(due changes: {card_change_stats['due']}, queue changes: {card_change_stats['queue']}, "
            f"both: {card_change_stats['due_and_queue']})"
        )
        if due_transition_counter:
            print("  top due transitions:")
            for (old_due, new_due), count in due_transition_counter.most_common(5):
                print(f"    {old_due}->{new_due}: {count}")
        if queue_transition_counter:
            print("  top queue transitions:")
            for (old_queue, new_queue), count in queue_transition_counter.most_common(5):
                print(f"    {old_queue}->{new_queue}: {count}")
        if card_change_samples:
            print("  sample card changes:")
            for entry in card_change_samples:
                print("    " + entry)
            remaining_cards = card_change_stats["total"] - len(card_change_samples)
            if remaining_cards > 0:
                print(f"    ... {remaining_cards} more cards omitted")

        print(
            f"  touched notes: {total_touched_notes}, notes to update: {note_change_stats['total']} "
            f"(tag changes: {note_change_stats['tags']}, field changes: {note_change_stats['fields']})"
        )
        if tags_added_counter or tags_removed_counter:
            print("  tag delta summary:")
            if tags_added_counter:
                print("    added tags:")
                for tag, count in tags_added_counter.most_common(5):
                    print(f"      {tag}: {count}")
            if tags_removed_counter:
                print("    removed tags:")
                for tag, count in tags_removed_counter.most_common(5):
                    print(f"      {tag}: {count}")
        if note_change_samples:
            print("  sample note changes:")
            for entry in note_change_samples:
                print("    " + entry)
            remaining_notes = note_change_stats["total"] - len(note_change_samples)
            if remaining_notes > 0:
                print(f"    ... {remaining_notes} more notes omitted")
        if tag_reorder_samples:
            print("  tag reorder samples:")
            for entry in tag_reorder_samples:
                print("    " + entry)


def _apply_duplicate_rules(
    am_config: PrioritySieveConfig,
    duplicates: defaultdict[tuple[str, str], list[CardPlan]],
    note_original_state: dict[int, tuple[list[str], list[str]]],
) -> None:
    def _get_candidate_deck_id(candidate: CardPlan) -> int:
        return int(candidate.original_deck_id or candidate.deck_id or 0)

    def _get_candidate_creation_ts(candidate: CardPlan) -> int:
        try:
            return int(candidate.card_id)
        except (TypeError, ValueError):
            return 0

    def _remove_auto_tag(candidate: CardPlan) -> None:
        if not am_config.tag_suspended_automatically:
            return
        candidate.desired_tags = [
            tag for tag in candidate.desired_tags if tag != am_config.tag_suspended_automatically
        ]

    def _unsuspend_candidate(candidate: CardPlan) -> None:
        if candidate.desired_queue == QUEUE_TYPE_SUSPENDED:
            candidate.desired_queue = QUEUE_TYPE_NEW
        _remove_auto_tag(candidate)

    def _force_suspend_candidate(candidate: CardPlan) -> None:
        candidate.auto_suspend = True
        candidate.desired_queue = QUEUE_TYPE_SUSPENDED
        if candidate.is_new_card and candidate.desired_due != DEFAULT_REVIEW_DUE:
            candidate.desired_due = DEFAULT_REVIEW_DUE
        if am_config.tag_suspended_automatically:
            original_tags = note_original_state.get(
                candidate.note_id,
                ([], []),
            )[1]
            candidate.desired_tags = tags_and_queue_utils.ensure_tag_preserving_order_list(
                candidate.desired_tags,
                am_config.tag_suspended_automatically,
                original_tags,
            )

    for _, items in duplicates.items():
        items.sort(
            key=lambda item: (
                item.deck_priority,
                item.desired_due,
                item.card_id,
            )
        )
        has_review_card = any(not candidate.is_new_card for candidate in items)
        active_slot_available = True
        unsuspended_candidate: CardPlan | None = None

        for candidate in items:
            if not candidate.is_new_card:
                continue

            if candidate.manually_suspended:
                active_slot_available = False
                continue

            force_suspend = (
                candidate.auto_suspend
                or has_review_card
            )
            if active_slot_available and not force_suspend:
                active_slot_available = False
                unsuspended_candidate = candidate
                _unsuspend_candidate(candidate)
                continue

            should_promote = (
                not force_suspend
                and unsuspended_candidate is not None
                and _get_candidate_deck_id(candidate) == _get_candidate_deck_id(unsuspended_candidate)
                and candidate.deck_priority == unsuspended_candidate.deck_priority
                and _get_candidate_creation_ts(candidate) > _get_candidate_creation_ts(unsuspended_candidate)
            )

            if should_promote:
                _force_suspend_candidate(unsuspended_candidate)
                unsuspended_candidate = candidate
                _unsuspend_candidate(candidate)
            else:
                _force_suspend_candidate(candidate)


def _record_recent_changes(
    card_original_state: dict[int, tuple[int, int]],
    note_original_state: dict[int, tuple[list[str], list[str]]],
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
        original_fields, original_tags = note_original_state.get(
            note_id,
            (note.fields, note.tags),
        )
        tags_changed = note.tags != original_tags
        fields_changed = note.fields != original_fields
        if tags_changed or fields_changed:
            if len(_recent_note_diffs) < 5:
                changes: list[str] = []
                if tags_changed:
                    changes.append(f"tags {original_tags}→{note.tags}")
                if fields_changed:
                    changes.append(f"fields {original_fields}→{note.fields}")
                _recent_note_diffs.append(f"note {note_id}: " + "; ".join(changes))


def _on_success(start_time: float | None = None) -> None:
    assert mw is not None
    global _recalc_in_progress
    _recalc_in_progress = False

    try:
        filters_state = compute_modify_filters_state()
        settings = PrioritySieveExtraSettings()
        settings.set_recalc_collection_state(json.dumps(filters_state, sort_keys=True))
        try:
            settings_state = json.dumps(
                prioritysieve_config.get_config_dict(), sort_keys=True
            )
        except Exception as error:  # pylint:disable=broad-except
            print(
                f"PrioritySieve: failed to cache settings state after recalc ({error})"
            )
        else:
            settings.set_recalc_settings_state(settings_state)
        settings.sync()
    except Exception as error:  # pylint:disable=broad-except
        print(f"PrioritySieve: failed to cache recalc state ({error})")

    mw.toolbar.draw()

    if _last_modified_cards_count or _last_modified_notes_count:
        message = (
            "PrioritySieve recalc complete - updated "
            f"{_last_modified_cards_count} card(s) and {_last_modified_notes_count} note(s)"
        )
    else:
        message = "PrioritySieve recalc complete"

    tooltip(message, parent=mw)

    if _recent_card_diffs:
        print("PrioritySieve recalc modified cards sample:")
        for entry in _recent_card_diffs:
            print("  " + entry)

    if _recent_note_diffs:
        print("PrioritySieve recalc modified notes sample:")
        for entry in _recent_note_diffs:
            print("  " + entry)

    if start_time is not None:
        duration = time.time() - start_time
        print(f"PrioritySieve recalc duration: {duration:.3f} seconds")

    if _followup_sync_callback is not None:
        callback = _followup_sync_callback
        set_followup_sync_callback(None)
        try:
            callback()
        except Exception as error:  # pylint:disable=broad-except
            print(f"PrioritySieve: follow-up sync callback failed ({error})")
    else:
        set_followup_sync_callback(None)


def _on_failure(error: Exception | PriorityFileMalformedException) -> None:
    global _recalc_in_progress
    _recalc_in_progress = False
    set_followup_sync_callback(None)
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
