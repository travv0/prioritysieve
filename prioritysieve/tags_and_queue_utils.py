from collections.abc import Sequence

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


def apply_entry_tags(
    am_config: PrioritySieveConfig,
    note: Note,
    reviewed: bool,
    auto_suspend: bool,
) -> None:
    """Apply tags for a single entry-based note."""

    tags = [tag for tag in note.tags if tag and tag.strip()]
    removal_tags = [
        am_config.tag_ready,
        am_config.tag_not_ready,
    ]
    removal_tags.extend(am_globals.legacy_fresh_tags)
    for tag in removal_tags:
        while tag in tags:
            tags.remove(tag)

    if auto_suspend:
        if am_config.tag_suspended_automatically not in tags:
            tags.append(am_config.tag_suspended_automatically)
    else:
        while am_config.tag_suspended_automatically in tags:
            tags.remove(am_config.tag_suspended_automatically)

    if reviewed:
        if am_config.tag_known_automatically not in tags:
            tags.append(am_config.tag_known_automatically)
    else:
        while am_config.tag_known_automatically in tags:
            tags.remove(am_config.tag_known_automatically)
        if auto_suspend:
            if am_config.tag_not_ready not in tags:
                tags.append(am_config.tag_not_ready)
        else:
            if am_config.tag_ready not in tags:
                tags.append(am_config.tag_ready)

    note.tags = tags


def update_entry_reading_field(note: Note, reading: str) -> None:
    mapping = note._field_map()
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
        am_config.tag_known_automatically,
        am_config.tag_ready,
        am_config.tag_not_ready,
        am_config.tag_suspended_automatically,
    ]
    tags_to_remove.extend(am_globals.legacy_fresh_tags)
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
    unknowns: int,
    has_learning_morphs: bool,
    force_auto_suspend: bool = False,
) -> None:
    auto_suspend = force_auto_suspend or unknowns == 0
    reviewed = unknowns == 0 and has_learning_morphs
    apply_entry_tags(am_config, note, reviewed=reviewed, auto_suspend=auto_suspend)
    if auto_suspend:
        card.queue = QUEUE_TYPE_SUSPENDED
    elif card.queue == QUEUE_TYPE_SUSPENDED:
        card.queue = QUEUE_TYPE_NEW


def update_tags_of_review_cards(
    am_config: PrioritySieveConfig,
    note: Note,
    has_learning_morphs: bool,
) -> None:
    apply_entry_tags(am_config, note, reviewed=not has_learning_morphs, auto_suspend=False)
