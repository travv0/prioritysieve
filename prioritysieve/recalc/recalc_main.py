from __future__ import annotations

import time
from pathlib import Path

from anki.cards import Card, CardId
from anki.consts import CARD_TYPE_NEW
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
    modified_notes: list[Note] = []

    # clear relevant caches between recalcs
    am_db.get_morph_priorities_from_collection.cache_clear()
    Morpheme.get_learning_status.cache_clear()

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

                tags_and_queue_utils.update_tags_and_queue_of_new_card(
                    am_config=am_config,
                    note=note,
                    card=card,
                    unknowns=len(cards_morph_metrics.unknown_morphs),
                    has_learning_morphs=cards_morph_metrics.has_learning_morphs,
                )
            else:
                tags_and_queue_utils.update_tags_of_review_cards(
                    am_config=am_config,
                    note=note,
                    has_learning_morphs=cards_morph_metrics.has_learning_morphs,
                )

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
                modified_notes.append(note)

            handled_cards[card_id] = None  # this marks the card as handled

    am_db.con.close()

    if am_config.recalc_offset_new_cards:
        modified_cards = _add_offsets_to_new_cards(
            am_config=am_config,
            card_morph_map_cache=card_morph_map_cache,
            already_modified_cards=modified_cards,
            handled_cards=handled_cards,
        )

    progress_utils.background_update_progress(label="Inserting into Anki collection")
    mw.col.update_cards(list(modified_cards.values()))
    mw.col.update_notes(modified_notes)


def _add_offsets_to_new_cards(
    am_config: PrioritySieveConfig,
    card_morph_map_cache: dict[int, list[Morpheme]],
    already_modified_cards: dict[CardId, Card],
    handled_cards: dict[CardId, None],
) -> dict[CardId, Card]:
    # This essentially replaces the need for the "skip" options, which in turn
    # makes reviewing cards on mobile a viable alternative.
    assert mw is not None

    earliest_due_card_for_unknown_morph: dict[tuple[str, str, str], Card] = {}
    lowest_due_for_unknown_morph: dict[tuple[str, str, str], int] = {}
    earliest_card_is_priority: dict[tuple[str, str, str], bool] = {}
    cards_with_morph: dict[tuple[str, str, str], set[CardId]] = {}
    priority_deck_name: str = am_config.recalc_offset_priority_deck.strip()

    def _is_priority_card(card: Card) -> bool:
        if not priority_deck_name:
            return False

        deck_dict = mw.col.decks.get(card.did, None)
        if deck_dict is None:
            return False

        deck_name = deck_dict.get("name")
        return isinstance(deck_name, str) and deck_name == priority_deck_name

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

        # we don't want to do anything to cards that have multiple unknown morphs
        if len(card_unknown_morphs) == 1:
            unknown_morph = card_unknown_morphs.pop()
            card = mw.col.get_card(card_id)
            card_due = card.due

            lowest_due = lowest_due_for_unknown_morph.get(unknown_morph)
            if lowest_due is None or card_due < lowest_due:
                lowest_due_for_unknown_morph[unknown_morph] = card_due

            is_priority_card = _is_priority_card(card)

            if unknown_morph not in earliest_due_card_for_unknown_morph:
                earliest_due_card_for_unknown_morph[unknown_morph] = card
                earliest_card_is_priority[unknown_morph] = is_priority_card
            else:
                current_card = earliest_due_card_for_unknown_morph[unknown_morph]
                current_is_priority = earliest_card_is_priority.get(unknown_morph, False)

                if is_priority_card and not current_is_priority:
                    earliest_due_card_for_unknown_morph[unknown_morph] = card
                    earliest_card_is_priority[unknown_morph] = True
                elif (
                    is_priority_card == current_is_priority
                    and current_card.due > card_due
                ):
                    earliest_due_card_for_unknown_morph[unknown_morph] = card
                    earliest_card_is_priority[unknown_morph] = current_is_priority

            if unknown_morph not in cards_with_morph:
                cards_with_morph[unknown_morph] = {card_id}
            else:
                cards_with_morph[unknown_morph].add(card_id)

    progress_utils.background_update_progress(label="Applying offsets")

    # sort so we can limit to the top x unknown morphs
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
    )

    # combine the "lists" of cards we want to modify
    already_modified_cards.update(modified_offset_cards)
    return already_modified_cards


def _apply_offsets(
    am_config: PrioritySieveConfig,
    already_modified_cards: dict[CardId, Card],
    earliest_due_card_for_unknown_morph: dict[tuple[str, str, str], Card],
    cards_with_morph: dict[tuple[str, str, str], set[CardId]],
) -> dict[CardId, Card]:
    assert mw is not None

    modified_offset_cards: dict[CardId, Card] = {}

    for counter, _unknown_morph in enumerate(earliest_due_card_for_unknown_morph):
        if counter > am_config.recalc_number_of_morphs_to_offset:
            break

        earliest_due_card = earliest_due_card_for_unknown_morph[_unknown_morph]
        all_new_cards_with_morph = cards_with_morph[_unknown_morph]
        all_new_cards_with_morph.remove(earliest_due_card.id)

        for card_id in all_new_cards_with_morph:
            _card = mw.col.get_card(card_id)
            score_and_offset: int | None = None

            # we don't want to offset the card due if it has already been offset previously
            if card_id in already_modified_cards:
                # limit to _MAX_SCORE to prevent integer overflow
                score_and_offset = min(
                    already_modified_cards[card_id].due + am_config.recalc_due_offset,
                    _MAX_SCORE,
                )
                if _card.due == score_and_offset:
                    del already_modified_cards[card_id]
                    continue

            if score_and_offset is None:
                score_and_offset = min(
                    _card.due + am_config.recalc_due_offset,
                    _MAX_SCORE,
                )

            _card.due = score_and_offset
            modified_offset_cards[card_id] = _card

    return modified_offset_cards


def _on_success(_start_time: float) -> None:
    # This function runs on the main thread.
    assert mw is not None
    assert mw.progress is not None

    mw.toolbar.draw()  # updates stats
    mw.progress.finish()

    tooltip("Finished Recalc", parent=mw)
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
