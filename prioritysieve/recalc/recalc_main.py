from __future__ import annotations

import time
from pathlib import Path

from anki.cards import Card, CardId
from anki.consts import CARD_TYPE_NEW, CardQueue
from anki.models import FieldDict, ModelManager, NotetypeDict
from anki.notes import Note
from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import tooltip

from .. import (
    prioritysieve_config,
    prioritysieve_globals,
    message_box_utils,
    progress_utils,
    tags_and_queue_utils,
)
from ..prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from ..prioritysieve_db import PrioritySieveDB
from ..exceptions import (
    AnkiFieldNotFound,
    AnkiNoteTypeNotFound,
    CancelledOperationException,
    DefaultSettingsException,
    KnownMorphsFileMalformedException,
    MorphemizerNotFoundException,
    PriorityFileMalformedException,
    PriorityFileNotFoundException,
)
from ..morph_priority_utils import get_morph_priority
from ..morpheme import Morpheme
from ..morphemizers import morphemizer_utils
from . import caching, extra_field_utils
from .anki_data_utils import PrioritySieveCardData
from .card_morphs_metrics import CardMorphsMetrics
from .card_score import _MAX_SCORE, compute_due_from_priorities


_last_modified_cards_count: int = 0
_last_modified_notes_count: int = 0
_recent_card_diffs: list[str] = []
_recent_note_diffs: list[str] = []


def recalc() -> None:
    ################################################################
    #                          FREEZING
    ################################################################
    # Recalc can take a long time if there are many cards, so to
    # prevent Anki from freezing we need to run this on a background
    # thread by using QueryOp.
    #
    # QueryOp docs:
    # https://addon-docs.ankiweb.net/background-ops.html
    ################################################################
    assert mw is not None

    read_enabled_config_filters: list[PrioritySieveConfigFilter] = (
        prioritysieve_config.get_read_enabled_filters()
    )
    modify_enabled_config_filters: list[PrioritySieveConfigFilter] = (
        prioritysieve_config.get_modify_enabled_filters()
    )

    # Note: we check for potential errors before running the QueryOp because
    # these processes and confirmations can require gui elements being displayed,
    # which is less of a headache to do on the main thread.
    settings_error: Exception | None = _check_selected_settings_for_errors(
        read_enabled_config_filters, modify_enabled_config_filters
    )

    if settings_error is not None:
        _on_failure(error=settings_error, before_query_op=True)
        return

    if extra_field_utils.new_extra_fields_are_selected():
        confirmed = message_box_utils.confirm_new_extra_fields_selection(parent=mw)
        if not confirmed:
            return

    mw.progress.start(label="Recalculating")
    _start_time: float = time.time()

    # lambda is used to ignore the irrelevant arguments given by QueryOp
    operation = QueryOp(
        parent=mw,
        op=lambda _: _recalc_background_op(
            read_enabled_config_filters, modify_enabled_config_filters
        ),
        success=lambda _: _on_success(_start_time),
    )
    operation.failure(_on_failure)
    operation.with_progress().run_in_background()


def _check_selected_settings_for_errors(
    read_enabled_config_filters: list[PrioritySieveConfigFilter],
    modify_enabled_config_filters: list[PrioritySieveConfigFilter],
) -> Exception | None:
    assert mw is not None

    # ideally we would combine the read and modify filters into a set since they
    # usually have significant overlap, but they contain dicts, which makes
    # comparing them impractical, so we just combine them into a list.
    config_filters = read_enabled_config_filters + modify_enabled_config_filters

    model_manager: ModelManager = mw.col.models

    for config_filter in config_filters:
        if config_filter.note_type == prioritysieve_globals.NONE_OPTION:
            return DefaultSettingsException()

        if config_filter.field == prioritysieve_globals.NONE_OPTION:
            return DefaultSettingsException()

        if not config_filter.morph_priority_selections:
            return DefaultSettingsException()

        note_type_dict: NotetypeDict | None = mw.col.models.by_name(
            config_filter.note_type
        )
        if note_type_dict is None:
            return AnkiNoteTypeNotFound()

        note_type_field_name_dict: dict[str, tuple[int, FieldDict]] = (
            model_manager.field_map(note_type_dict)
        )

        if config_filter.field not in note_type_field_name_dict:
            return AnkiFieldNotFound()

        if (
            config_filter.furigana_field != prioritysieve_globals.NONE_OPTION
            and config_filter.furigana_field not in note_type_field_name_dict
        ):
            return AnkiFieldNotFound()

        if (
            config_filter.reading_field != prioritysieve_globals.NONE_OPTION
            and config_filter.reading_field not in note_type_field_name_dict
        ):
            return AnkiFieldNotFound()

        morphemizer_found = morphemizer_utils.get_morphemizer_by_description(
            config_filter.morphemizer_description
        )
        if morphemizer_found is None:
            return MorphemizerNotFoundException(config_filter.morphemizer_description)

        for selection in config_filter.morph_priority_selections:
            if selection in (
                prioritysieve_globals.NONE_OPTION,
                prioritysieve_globals.COLLECTION_FREQUENCY_OPTION,
            ):
                continue

            priority_file_path = Path(
                mw.pm.profileFolder(),
                prioritysieve_globals.PRIORITY_FILES_DIR_NAME,
                selection,
            )
            if not priority_file_path.is_file():
                return PriorityFileNotFoundException(path=str(priority_file_path))

    return None


def _recalc_background_op(
    read_enabled_config_filters: list[PrioritySieveConfigFilter],
    modify_enabled_config_filters: list[PrioritySieveConfigFilter],
) -> None:
    am_config = PrioritySieveConfig()
    caching.cache_anki_data(am_config, read_enabled_config_filters)
    _update_cards_and_notes(am_config, modify_enabled_config_filters)


def _update_cards_and_notes(  # pylint:disable=too-many-locals, too-many-statements, too-many-branches
    am_config: PrioritySieveConfig,
    modify_enabled_config_filters: list[PrioritySieveConfigFilter],
) -> None:
    assert mw is not None
    assert mw.col.db is not None
    assert mw.progress is not None

    am_db = PrioritySieveDB()
    model_manager: ModelManager = mw.col.models
    card_morph_map_cache: dict[int, list[Morpheme]] = am_db.get_card_morph_map_cache()
    handled_cards: dict[CardId, None] = {}  # we only care about the key lookup
    modified_cards: dict[CardId, Card] = {}
    modified_notes: dict[int, Note] = {}
    card_original_state: dict[CardId, tuple[int, int]] = {}
    note_original_state: dict[int, tuple[list[str], list[str]]] = {}

    global _recent_card_diffs
    global _recent_note_diffs
    _recent_card_diffs = []
    _recent_note_diffs = []

    # clear relevant caches between recalcs
    am_db.get_morph_priorities_from_collection.cache_clear()
    Morpheme.get_learning_status.cache_clear()

    auto_suspended_tag = am_config.tag_suspended_automatically

    for config_filter in modify_enabled_config_filters:
        note_type_dict: NotetypeDict = (
            extra_field_utils.potentially_add_extra_fields_to_note_type(
                model_manager=model_manager, config_filter=config_filter
            )
        )
        field_name_dict: dict[str, tuple[int, FieldDict]] = model_manager.field_map(
            notetype=note_type_dict
        )
        morph_priorities: dict[tuple[str, str, str], int] = get_morph_priority(
            am_db=am_db,
            morph_priority_selection=config_filter.morph_priority_selections,
        )
        cards_data_dict: dict[CardId, PrioritySieveCardData] = (
            am_db.get_am_cards_data_dict(
                note_type_id=model_manager.id_for_name(config_filter.note_type),
                include_tags=config_filter.tags["include"],
                exclude_tags=config_filter.tags["exclude"],
            )
        )
        card_amount = len(cards_data_dict)

        for counter, card_id in enumerate(cards_data_dict):
            progress_utils.background_update_progress_potentially_cancel(
                label=f"Updating {config_filter.note_type} cards<br>card: {counter} of {card_amount}",
                counter=counter,
                max_value=card_amount,
            )

            # check if the card has already been handled in a previous note filter
            if card_id in handled_cards:
                continue

            card: Card = mw.col.get_card(card_id)
            note: Note = card.note()

            # make sure to get the values and not references
            original_due: int = int(card.due)
            original_queue: int = int(card.queue)  # queue: suspended, buried, etc.
            original_fields: list[str] = note.fields.copy()
            original_tags: list[str] = note.tags.copy()

            card_original_state.setdefault(card_id, (original_due, original_queue))
            note_original_state.setdefault(note.id, (original_fields, original_tags))

            cards_morph_metrics = CardMorphsMetrics(
                am_config,
                card_id,
                card_morph_map_cache,
            )

            if card.type == CARD_TYPE_NEW:
                card_due = compute_due_from_priorities(
                    cards_morph_metrics.all_morphs, morph_priorities
                )
                card.due = card_due

                unknowns_amount = len(cards_morph_metrics.unknown_morphs)
                force_auto_suspend = (
                    am_config.auto_suspend_unlisted_entries
                    and unknowns_amount > 0
                    and card_due == prioritysieve_globals.DEFAULT_REVIEW_DUE
                )

                tags_and_queue_utils.update_tags_and_queue_of_new_card(
                    am_config=am_config,
                    note=note,
                    card=card,
                    unknowns=unknowns_amount,
                    has_learning_morphs=cards_morph_metrics.has_learning_morphs,
                    force_auto_suspend=force_auto_suspend,
                )
            else:
                tags_and_queue_utils.update_tags_of_review_cards(
                    am_config=am_config,
                    note=note,
                    has_learning_morphs=cards_morph_metrics.has_learning_morphs,
                )

            if (
                card.queue != tags_and_queue_utils.suspended
                and auto_suspended_tag in note.tags
            ):
                note.tags = [
                    tag for tag in note.tags if tag != auto_suspended_tag and tag.strip()
                ]
                modified_notes.setdefault(note.id, note)

            if config_filter.extra_reading_field:
                extra_field_utils.update_reading_field(
                    field_name_dict=field_name_dict,
                    note=note,
                    morphs=cards_morph_metrics.all_morphs,
                )

            # we only want anki to update the cards and notes that have actually changed
            if card.due != original_due or card.queue != original_queue:
                modified_cards[card_id] = card

            if original_fields != note.fields or original_tags != note.tags:
                modified_notes.setdefault(note.id, note)

            handled_cards[card_id] = None  # this marks the card as handled

    am_db.con.close()

    modified_cards = _add_offsets_to_new_cards(
        am_config=am_config,
        card_morph_map_cache=card_morph_map_cache,
        already_modified_cards=modified_cards,
        handled_cards=handled_cards,
        modified_notes=modified_notes,
        note_original_state=note_original_state,
    )

    final_modified_cards: dict[CardId, Card] = {}
    final_modified_notes: dict[int, Note] = {}

    for card_id, card in modified_cards.items():
        original_due, original_queue = card_original_state.get(
            card_id, (card.due, card.queue)
        )
        if card.due == original_due and card.queue == original_queue:
            continue
        if len(_recent_card_diffs) < 5:
            _recent_card_diffs.append(
                f"card {card_id}: due {original_due}→{card.due}, queue {original_queue}→{card.queue}"
            )
        final_modified_cards[card_id] = card

    for note_id, note in modified_notes.items():
        original_fields, original_tags = note_original_state.get(
            note_id, (note.fields, note.tags)
        )
        if original_fields == note.fields and original_tags == note.tags:
            continue

        if len(_recent_note_diffs) < 5:
            changes: list[str] = []
            if original_tags != note.tags:
                changes.append(f"tags {original_tags}→{note.tags}")
            if original_fields != note.fields:
                changes.append(f"fields {original_fields}→{note.fields}")
            _recent_note_diffs.append(f"note {note_id}: " + "; ".join(changes))

        final_modified_notes[note_id] = note

    progress_utils.background_update_progress(label="Inserting into Anki collection")
    mw.col.update_cards(list(final_modified_cards.values()))
    mw.col.update_notes(list(final_modified_notes.values()))

    global _last_modified_cards_count
    global _last_modified_notes_count
    _last_modified_cards_count = len(final_modified_cards)
    _last_modified_notes_count = len(final_modified_notes)


def _add_offsets_to_new_cards(
    am_config: PrioritySieveConfig,
    card_morph_map_cache: dict[int, list[Morpheme]],
    already_modified_cards: dict[CardId, Card],
    handled_cards: dict[CardId, None],
    modified_notes: dict[int, Note],
    note_original_state: dict[int, tuple[list[str], list[str]]],
) -> dict[CardId, Card]:
    assert mw is not None

    earliest_due_card_for_unknown_morph: dict[tuple[str, str, str], Card] = {}
    lowest_due_for_unknown_morph: dict[tuple[str, str, str], int] = {}
    earliest_card_priority: dict[tuple[str, str, str], int] = {}
    cards_with_morph: dict[tuple[str, str, str], set[CardId]] = {}
    deck_priority_lookup: dict[str, int] = {
        deck_name: index
        for index, deck_name in enumerate(am_config.recalc_offset_priority_decks)
    }
    default_priority = len(deck_priority_lookup)

    def _get_card_priority(card: Card) -> int:
        if not deck_priority_lookup:
            return default_priority

        deck_dict = mw.col.decks.get(card.did, None)
        if deck_dict is None:
            return default_priority

        deck_name = deck_dict.get("name")
        if not isinstance(deck_name, str):
            return default_priority

        return deck_priority_lookup.get(deck_name, default_priority)

    card_amount = len(handled_cards)
    for counter, card_id in enumerate(handled_cards):
        progress_utils.background_update_progress_potentially_cancel(
            label=f"Potentially offsetting cards<br>card: {counter} of {card_amount}",
            counter=counter,
            max_value=card_amount,
        )

        card_unknown_morphs = CardMorphsMetrics.get_unknown_morph_keys(
            card_morph_map_cache=card_morph_map_cache,
            card_id=card_id,
        )

        if len(card_unknown_morphs) != 1:
            continue

        unknown_morph = card_unknown_morphs.pop()
        card = mw.col.get_card(card_id)
        card_due = card.due

        lowest_due = lowest_due_for_unknown_morph.get(unknown_morph)
        if lowest_due is None or card_due < lowest_due:
            lowest_due_for_unknown_morph[unknown_morph] = card_due

        if unknown_morph not in earliest_due_card_for_unknown_morph:
            earliest_due_card_for_unknown_morph[unknown_morph] = card
            earliest_card_priority[unknown_morph] = _get_card_priority(card)
        else:
            current_card = earliest_due_card_for_unknown_morph[unknown_morph]
            current_priority = earliest_card_priority.get(
                unknown_morph, default_priority
            )
            card_priority = _get_card_priority(card)

            if card_priority < current_priority or (
                card_priority == current_priority and current_card.due > card_due
            ):
                earliest_due_card_for_unknown_morph[unknown_morph] = card
                earliest_card_priority[unknown_morph] = card_priority

        if unknown_morph not in cards_with_morph:
            cards_with_morph[unknown_morph] = {card_id}
        else:
            cards_with_morph[unknown_morph].add(card_id)

    progress_utils.background_update_progress(label="Applying offsets")

    sorted_unknown_morphs = sorted(
        earliest_due_card_for_unknown_morph.keys(),
        key=lambda morph: lowest_due_for_unknown_morph.get(morph, _MAX_SCORE),
    )
    earliest_due_card_for_unknown_morph = {
        morph: earliest_due_card_for_unknown_morph[morph] for morph in sorted_unknown_morphs
    }
    modified_offset_cards: dict[CardId, Card] = _apply_offsets(
        am_config=am_config,
        already_modified_cards=already_modified_cards,
        earliest_due_card_for_unknown_morph=earliest_due_card_for_unknown_morph,
        cards_with_morph=cards_with_morph,
        modified_notes=modified_notes,
        note_original_state=note_original_state,
    )

    # combine the "lists" of cards we want to modify
    already_modified_cards.update(modified_offset_cards)
    return already_modified_cards


def _apply_offsets(
    am_config: PrioritySieveConfig,
    already_modified_cards: dict[CardId, Card],
    earliest_due_card_for_unknown_morph: dict[tuple[str, str, str], Card],
    cards_with_morph: dict[tuple[str, str, str], set[CardId]],
    modified_notes: dict[int, Note],
    note_original_state: dict[int, tuple[list[str], list[str]]],
) -> dict[CardId, Card]:
    assert mw is not None

    modified_offset_cards: dict[CardId, Card] = {}

    auto_suspend_tag = am_config.tag_suspended_automatically

    def _sanitize_tags(note: Note) -> None:
        cleaned = [tag for tag in note.tags if tag and tag.strip()]
        if len(cleaned) != len(note.tags):
            note.tags = cleaned

    def _ensure_note(card: Card) -> Note:
        note = modified_notes.get(card.nid)
        if note is None:
            note = mw.col.get_note(card.nid)
        note_original_state.setdefault(note.id, (list(note.fields), list(note.tags)))
        return note

    original_positions_cache: dict[int, dict[str, int]] = {}

    def _insert_tag_preserving_order(note: Note, tag: str) -> None:
        positions = original_positions_cache.get(note.id)
        if positions is None:
            original_tags = note_original_state.get(note.id, ([], []))[1]
            positions = {tag_value: idx for idx, tag_value in enumerate(original_tags)}
            original_positions_cache[note.id] = positions

        position = positions.get(tag)
        if position is None or position >= len(note.tags):
            note.tags.append(tag)
        else:
            note.tags.insert(position, tag)

    for unknown_morph, earliest_due_card in earliest_due_card_for_unknown_morph.items():
        base_card = already_modified_cards.get(earliest_due_card.id, earliest_due_card)
        base_note = _ensure_note(base_card)

        tag_removed = False
        if auto_suspend_tag in base_note.tags and base_card.due != _MAX_SCORE:
            base_note.tags.remove(auto_suspend_tag)
            _sanitize_tags(base_note)
            modified_notes[base_note.id] = base_note
            tag_removed = True

        if tag_removed and base_card.queue == tags_and_queue_utils.suspended:
            base_card.queue = CardQueue(0)
            modified_offset_cards[base_card.id] = base_card

        already_modified_cards[base_card.id] = base_card

        remaining_cards = cards_with_morph[unknown_morph] - {base_card.id}

        for card_id in remaining_cards:
            existing_card = already_modified_cards.get(card_id)
            if existing_card is None:
                existing_card = mw.col.get_card(card_id)

            note = _ensure_note(existing_card)
            if auto_suspend_tag not in note.tags:
                _insert_tag_preserving_order(note, auto_suspend_tag)
                _sanitize_tags(note)
                modified_notes[note.id] = note

            card_modified = False

            if existing_card.queue != tags_and_queue_utils.suspended:
                existing_card.queue = tags_and_queue_utils.suspended
                card_modified = True

            if existing_card.due != _MAX_SCORE:
                existing_card.due = _MAX_SCORE
                card_modified = True

            if card_modified:
                modified_offset_cards[card_id] = existing_card

            already_modified_cards[card_id] = existing_card

    return modified_offset_cards


def _on_success(_start_time: float) -> None:
    # This function runs on the main thread.
    assert mw is not None
    assert mw.progress is not None

    mw.toolbar.draw()  # updates stats
    mw.progress.finish()

    if _last_modified_cards_count or _last_modified_notes_count:
        message = (
            "Finished Recalc – updated "
            f"{_last_modified_cards_count} card(s) and {_last_modified_notes_count} note(s)"
        )
    else:
        message = "Finished Recalc"

    tooltip(message, parent=mw)

    if _recent_card_diffs:
        print("PrioritySieve recalc modified cards sample:")
        for entry in _recent_card_diffs:
            print("  " + entry)

    if _recent_note_diffs:
        print("PrioritySieve recalc modified notes sample:")
        for entry in _recent_note_diffs:
            print("  " + entry)
    end_time: float = time.time()
    print(f"Recalc duration: {round(end_time - _start_time, 3)} seconds")


def _on_failure(  # pylint:disable=too-many-branches
    error: (
        Exception
        | DefaultSettingsException
        | MorphemizerNotFoundException
        | CancelledOperationException
        | PriorityFileNotFoundException
        | PriorityFileMalformedException
        | KnownMorphsFileMalformedException
        | AnkiNoteTypeNotFound
        | AnkiFieldNotFound
    ),
    before_query_op: bool = False,
) -> None:
    # This function runs on the main thread.
    assert mw is not None
    assert mw.progress is not None

    if not before_query_op:
        mw.progress.finish()

    if isinstance(error, CancelledOperationException):
        tooltip("Cancelled Recalc")
        return

    title = "PrioritySieve Error"

    if isinstance(error, DefaultSettingsException):
        text = (
            f'Found a note filter containing a "{prioritysieve_globals.NONE_OPTION}" option. Please select something else.<br><br>'
            f"See <a href='https://mortii.github.io/prioritysieve/user_guide/setup/settings/note-filter.html'> the note filter guide</a> for more info. "
        )
    elif isinstance(error, AnkiNoteTypeNotFound):
        text = "The PrioritySieve settings uses one or more note types that no longer exists. Please redo your settings."
    elif isinstance(error, AnkiFieldNotFound):
        text = "The PrioritySieve settings uses one or more fields that no longer exist. Please redo your settings."
    elif isinstance(error, MorphemizerNotFoundException):
        if error.morphemizer_name == "MecabMorphemizer":
            text = (
                'Parser "PrioritySieve: Japanese" was not found.<br><br>'
                "The Japanese parser can be added by installing a separate companion add-on:<br><br>"
                "Link: <a href='https://ankiweb.net/shared/info/1974309724'>https://ankiweb.net/shared/info/1974309724</a><br>"
                "Installation code: 1974309724 <br><br>"
                "The parser should be automatically found after the add-on is installed and Anki has restarted."
            )
        elif error.morphemizer_name == "JiebaMorphemizer":
            text = (
                'Parser "PrioritySieve: Chinese" was not found.<br><br>'
                "The Chinese parser can be added by installing a separate companion add-on:<br>"
                "Link: <a href='https://ankiweb.net/shared/info/1857311956'>https://ankiweb.net/shared/info/1857311956</a> <br>"
                "Installation code: 1857311956 <br><br>"
                "The parser should be automatically found after the add-on is installed and Anki has restarted."
            )
        else:
            text = f'Parser "{error.morphemizer_name}" was not found.'

    elif isinstance(error, PriorityFileNotFoundException):
        text = f"Priority file: {error.path} not found!"
    elif isinstance(error, PriorityFileMalformedException):
        text = (
            f"Priority file: {error.path} is malformed (possibly outdated).<br><br>"
            f"{error.reason}<br><br>"
            f"Please generate a new one."
        )
    elif isinstance(error, KnownMorphsFileMalformedException):
        text = (
            f"Known entries file: {error.path} is malformed.<br><br>"
            f"Please generate a new one."
        )
    else:
        raise error

    message_box_utils.show_error_box(title=title, body=text, parent=mw)
