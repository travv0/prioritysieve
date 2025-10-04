from collections.abc import Sequence

from anki.cards import Card
from anki.consts import CardQueue
from anki.notes import Note, NoteId
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QWidget  # pylint:disable=no-name-in-module
from aqt.utils import tooltip

from . import prioritysieve_globals as am_globals
from . import progress_utils
from .prioritysieve_config import PrioritySieveConfig
from .recalc.card_score import _MAX_SCORE
from .anki_op_utils import notify_op_execution

suspended = CardQueue(-1)


def update_tags_and_queue_of_new_card(
    am_config: PrioritySieveConfig,
    note: Note,
    card: Card,
    unknowns: int,
    has_learning_morphs: bool,
    force_auto_suspend: bool = False,
) -> None:
    # There are 3 different tags that we want recalc to update:
    # - am-ready
    # - am-not-ready
    # - am-known-automatically
    #
    # These tags should be mutually exclusive, and there are many
    # complicated scenarios where a normal tag progression might
    # not occur, so we have to make sure that we remove all the
    # tags that shouldn't be there for each case, even if it seems
    # redundant.
    #
    # Note: only new cards are handled in this function!

    mutually_exclusive_tags: list[str] = [
        am_config.tag_ready,
        am_config.tag_not_ready,
        am_config.tag_known_automatically,
    ]

    tracked_tags = set(mutually_exclusive_tags)
    tracked_tags.add(am_config.tag_suspended_automatically)
    original_positions: dict[str, int] = {}
    for index, tag in enumerate(note.tags):
        if tag in tracked_tags and tag not in original_positions:
            original_positions[tag] = index

    def _insert_tag(tag: str) -> None:
        position = original_positions.get(tag)
        if position is None or position >= len(note.tags):
            note.tags.append(tag)
        else:
            note.tags.insert(position, tag)

    has_learning_for_tag = has_learning_morphs and unknowns > 0

    if has_learning_for_tag:
        if am_config.tag_fresh not in note.tags:
            note.tags.append(am_config.tag_fresh)
    else:
        if am_config.tag_fresh in note.tags:
            note.tags.remove(am_config.tag_fresh)

    auto_suspended_tag = am_config.tag_suspended_automatically

    should_auto_suspend = force_auto_suspend or unknowns == 0

    if should_auto_suspend:
        if auto_suspended_tag not in note.tags:
            _insert_tag(auto_suspended_tag)
        if card.queue != suspended:
            card.queue = suspended
        if card.due != _MAX_SCORE:
            card.due = _MAX_SCORE
    elif auto_suspended_tag in note.tags:
        note.tags.remove(auto_suspended_tag)
        if card.queue == suspended:
            card.queue = CardQueue(0)

    if unknowns == 0:
        if am_config.tag_known_manually in note.tags:
            _remove_exclusive_tags(note, mutually_exclusive_tags)
        elif am_config.tag_known_automatically not in note.tags:
            _remove_exclusive_tags(note, mutually_exclusive_tags)
            _insert_tag(am_config.tag_known_automatically)
    elif unknowns == 1:
        if should_auto_suspend:
            _remove_exclusive_tags(note, mutually_exclusive_tags)
            if am_config.tag_not_ready not in note.tags:
                _insert_tag(am_config.tag_not_ready)
        else:
            if am_config.tag_ready not in note.tags:
                _remove_exclusive_tags(note, mutually_exclusive_tags)
                _insert_tag(am_config.tag_ready)
    else:
        if am_config.tag_not_ready not in note.tags:
            _remove_exclusive_tags(note, mutually_exclusive_tags)
            _insert_tag(am_config.tag_not_ready)

    _sanitize_tags(note)


def _remove_exclusive_tags(note: Note, mutually_exclusive_tags: list[str]) -> None:
    for tag in mutually_exclusive_tags:
        if tag in note.tags:
            note.tags.remove(tag)


def _sanitize_tags(note: Note) -> None:
    cleaned = [tag for tag in note.tags if tag and tag.strip()]
    if len(cleaned) != len(note.tags):
        note.tags = cleaned


def update_tags_of_review_cards(
    am_config: PrioritySieveConfig,
    note: Note,
    has_learning_morphs: bool,
) -> None:
    if am_config.tag_ready in note.tags:
        note.tags.remove(am_config.tag_ready)
    elif am_config.tag_not_ready in note.tags:
        note.tags.remove(am_config.tag_not_ready)

    if am_config.tag_suspended_automatically in note.tags:
        note.tags.remove(am_config.tag_suspended_automatically)

    if has_learning_morphs:
        if am_config.tag_fresh not in note.tags:
            note.tags.append(am_config.tag_fresh)
    else:
        if am_config.tag_fresh in note.tags:
            note.tags.remove(am_config.tag_fresh)

    _sanitize_tags(note)


def reset_am_tags(parent: QWidget) -> None:
    assert mw is not None

    # lambda is used to ignore the irrelevant arguments given by QueryOp
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
        am_config.tag_fresh,
    ]
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
            note.tags.remove(tag)
            modified_notes[note_id] = note

    if modified_notes:
        note_changes = mw.col.update_notes(list(modified_notes.values()))
        notify_op_execution(note_changes)
