from collections.abc import Sequence

from typing import Any, Iterable

from anki.cards import Card
from anki.consts import QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from anki.notes import Note, NoteId
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QWidget  # pylint:disable=no-name-in-module
from aqt.utils import tooltip

from . import prioritysieve_globals as am_globals
from . import progress_utils
from .prioritysieve_config import PrioritySieveConfig
from .anki_op_utils import notify_op_execution

suspended_queue = QUEUE_TYPE_SUSPENDED


def _sanitize_tags(tags: Iterable[str]) -> list[str]:
    sanitized: list[str] = []
    for raw in tags:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if value:
            sanitized.append(value)
    return sanitized


def compute_entry_tags(
    am_config: PrioritySieveConfig,
    tags: Sequence[str],
    auto_suspend: bool,
) -> list[str]:
    """Return the new tag list for a note given the recalc inputs."""

    def _is_valid(tag: str) -> bool:
        return isinstance(tag, str) and tag.strip()

    cleaned_tags = [tag for tag in tags if _is_valid(tag)]

    tracked_tags = {
        am_config.tag_ready,
        am_config.tag_not_ready,
        am_config.tag_suspended_automatically,
    }
    tracked_tags.update(am_globals.legacy_fresh_tags)
    tracked_tags.update(am_globals.legacy_known_automatically_tags)

    original_positions: dict[str, int] = {}
    for index, tag in enumerate(tags):
        if tag in tracked_tags and tag not in original_positions:
            original_positions[tag] = index

    def _remove_tag(tag: str) -> None:
        if not _is_valid(tag):
            return
        while tag in cleaned_tags:
            cleaned_tags.remove(tag)

    def _insert_tag(tag: str) -> None:
        if not _is_valid(tag):
            return
        if tag in cleaned_tags:
            return
        position = original_positions.get(tag)
        if position is None or position >= len(cleaned_tags):
            cleaned_tags.append(tag)
        else:
            cleaned_tags.insert(position, tag)

    removal_tags = [
        am_config.tag_ready,
        am_config.tag_not_ready,
    ]
    removal_tags.extend(am_globals.legacy_fresh_tags)
    removal_tags.extend(am_globals.legacy_known_automatically_tags)
    for tag in removal_tags:
        _remove_tag(tag)

    if auto_suspend:
        _insert_tag(am_config.tag_suspended_automatically)
        _insert_tag(am_config.tag_not_ready)
    else:
        _remove_tag(am_config.tag_suspended_automatically)
        _remove_tag(am_config.tag_not_ready)
        _insert_tag(am_config.tag_ready)

    return cleaned_tags


def apply_entry_tags(
    am_config: PrioritySieveConfig,
    note: Note,
    reviewed: bool,
    auto_suspend: bool,
) -> None:
    """Apply tags for a single entry-based note."""

    note.tags = compute_entry_tags(
        am_config=am_config,
        tags=note.tags,
        auto_suspend=auto_suspend,
    )


def ensure_tag_preserving_order(
    note: Note, tag: str, original_tags: Sequence[str]
) -> None:
    """Ensure `tag` exists on `note` using the order from `original_tags`."""

    note.tags = ensure_tag_preserving_order_list(note.tags, tag, original_tags)


def ensure_tag_preserving_order_list(
    current_tags: Sequence[str], tag: str, original_tags: Sequence[str]
) -> list[str]:
    """Return a tag list that guarantees ``tag`` is present using the original ordering."""

    if not isinstance(tag, str):
        return list(current_tags)
    tag = tag.strip()
    if not tag:
        return list(current_tags)

    sanitized_current = [
        existing
        for existing in current_tags
        if isinstance(existing, str) and existing.strip()
    ]

    if tag in sanitized_current:
        return sanitized_current

    sanitized_original = _sanitize_tags(original_tags)

    try:
        target_index = sanitized_original.index(tag)
    except ValueError:
        sanitized_current.append(tag)
        return sanitized_current

    original_positions = {
        value: index for index, value in enumerate(sanitized_original)
    }
    insert_position = len(current_tags)
    for index, existing_tag in enumerate(sanitized_current):
        original_index = original_positions.get(existing_tag)
        if original_index is not None and original_index > target_index:
            insert_position = index
            break

    sanitized_current.insert(insert_position, tag)
    return sanitized_current


def _resolve_field_map(note: Note) -> dict[str, tuple[int, Any]]:
    """Return the field map for the provided note, resilient to API changes."""

    # Older Anki versions exposed a callable private helper.
    field_map_callable = getattr(note, "_field_map", None)
    if callable(field_map_callable):
        mapping = field_map_callable()
        if isinstance(mapping, dict):
            return mapping

    # Recent versions store the mapping on _fmap.
    fmap = getattr(note, "_fmap", None)
    if isinstance(fmap, dict):
        return fmap

    # Fall back to recomputing the map from the collection.
    note_type = note.note_type()
    collection = getattr(note, "col", None)
    if note_type is None or collection is None:
        return {}

    models = getattr(collection, "models", None)
    if models is None:
        return {}

    try:
        mapping = models.field_map(note_type)
    except Exception:  # pragma: no cover - defensive fallback
        return {}

    return mapping if isinstance(mapping, dict) else {}


def update_entry_reading_field(note: Note, reading: str) -> None:
    mapping = _resolve_field_map(note)
    field_info = mapping.get(am_globals.EXTRA_FIELD_READING)
    if not field_info:
        return
    index = field_info[0]
    if note.fields[index] != reading:
        note.fields[index] = reading


def reset_am_tags(parent: QWidget) -> None:
    assert mw is not None

    operation = QueryOp(
        parent=parent,
        op=lambda _: _reset_am_tags_background_op(),
        success=lambda _: tooltip(msg="Successfully removed tags", parent=parent),
    )
    operation.with_progress().run_in_background()


def _reset_am_tags_background_op() -> None:
    assert mw is not None

    am_config = PrioritySieveConfig()
    modified_notes: dict[NoteId, Note] = {}

    tags_to_remove = [
        am_config.tag_ready,
        am_config.tag_not_ready,
        am_config.tag_suspended_automatically,
    ]
    tags_to_remove.extend(am_globals.legacy_fresh_tags)
    tags_to_remove.extend(am_globals.legacy_known_automatically_tags)
    for tag in tags_to_remove:
        note_ids: Sequence[NoteId] = mw.col.find_notes(f"tag:{tag}")
        note_amount = len(note_ids)

        for counter, note_id in enumerate(note_ids):
            progress_utils.background_update_progress_potentially_cancel(
                label=f"Removing {tag} tag from notes<br>note: {counter} of {note_amount}",
                counter=counter,
                max_value=note_amount,
                increment=100,
            )
            note: Note = modified_notes.get(note_id, mw.col.get_note(note_id))
            while tag in note.tags:
                note.tags.remove(tag)
            modified_notes[note_id] = note

    if modified_notes:
        note_changes = mw.col.update_notes(list(modified_notes.values()))
        notify_op_execution(note_changes)


# Backwards compatibility wrappers for older code paths.
def update_tags_and_queue_of_new_card(
    am_config: PrioritySieveConfig,
    note: Note,
    card: Card,
    pending_entries: int,
    entry_reviewed: bool,
    force_auto_suspend: bool = False,
) -> None:
    """
    Update tags and queue state for a new-entry card.

    :param pending_entries: How many entries linked to the note remain unreviewed.
    :param entry_reviewed: Whether the shared entry is already marked reviewed.
    :param force_auto_suspend: Optionally suspend regardless of pending count.
    """

    auto_suspend = force_auto_suspend or pending_entries == 0
    apply_entry_tags(
        am_config,
        note,
        reviewed=entry_reviewed,
        auto_suspend=auto_suspend,
    )
    if auto_suspend:
        card.queue = QUEUE_TYPE_SUSPENDED
    elif card.queue == QUEUE_TYPE_SUSPENDED:
        card.queue = QUEUE_TYPE_NEW


def update_tags_of_review_cards(
    am_config: PrioritySieveConfig,
    note: Note,
    entry_reviewed: bool,
) -> None:
    """Update tags for an existing review card without altering the queue."""

    apply_entry_tags(
        am_config,
        note,
        reviewed=entry_reviewed,
        auto_suspend=False,
    )
