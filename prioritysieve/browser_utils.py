from __future__ import annotations

from collections.abc import Sequence

from anki.cards import CardId
from anki.collection import SearchNode
from anki.notes import Note
from anki.utils import ids2str
from aqt import dialogs, mw
from aqt.browser.browser import Browser
from aqt.qt import QLineEdit  # pylint:disable=no-name-in-module
from aqt.reviewer import RefreshNeeded
from aqt.utils import tooltip

from . import prioritysieve_config, prioritysieve_globals
from .prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from .entry_db import EntryDB
from .anki_op_utils import notify_op_execution

browser: Browser | None = None


def run_browse_entry(
    search_unknowns: bool = False,
    match_text_only: bool = False,
) -> None:
    assert mw is not None
    assert browser is not None

    am_config = PrioritySieveConfig()

    # Only use the first selected card since note-types can be different
    card_id: CardId = browser.selectedCards()[0]

    card = mw.col.get_card(card_id)
    note = card.note()
    browse_same_entries(
        am_config,
        card_id=card_id,
        note=note,
        search_unknowns=search_unknowns,
        match_text_only=match_text_only,
    )


def browse_same_entries(  # pylint:disable=too-many-arguments
    am_config: PrioritySieveConfig,
    card_id: CardId | None = None,
    note: Note | None = None,
    search_unknowns: bool = False,
    search_ready_tag: bool = False,
    match_text_only: bool = False,
) -> None:
    # Opens browser and displays all notes with the same focus entry.
    # Useful to quickly find alternative notes to learn focus from.
    #
    # The query is a list of card ids so we precisely target the stored entry metadata,
    # avoiding false positives that could arise from identical display text with different readings.

    global browser
    assert mw is not None

    if card_id is None:
        assert mw.reviewer is not None
        assert mw.reviewer.card is not None
        card_id = mw.reviewer.card.id

    if note is None:
        assert mw.reviewer is not None
        assert mw.reviewer.card is not None
        note = mw.reviewer.card.note()

    am_filter = prioritysieve_config.get_matching_read_filter(note)

    if am_filter is None:
        tooltip(
            "Card's note type is either not configured in settings, or does not have 'Modify' checked"
        )
        return

    include_reviewed = not search_unknowns
    lookup_text_only = match_text_only

    with EntryDB() as entry_db:
        entry = entry_db.get_entry_for_card(card_id)
        if entry is None:
            tooltip("Run PrioritySieve → Recalc before browsing matching entries.")
            return

        matching_ids = entry_db.get_card_ids_for_entry(
            entry,
            include_reviewed=include_reviewed,
            text_only=lookup_text_only,
        )

    card_ids: set[CardId] = {CardId(cid) for cid in matching_ids}
    if not card_ids:
        error_text = "No entries" if include_reviewed else "No unknown entries"
        tooltip(error_text)
        return

    query = focus_query(am_config, card_ids, search_ready_tag)
    browser = dialogs.open("Browser", mw)
    assert browser is not None

    search_edit: QLineEdit | None = browser.form.searchEdit.lineEdit()
    assert search_edit is not None

    search_edit.setText(query)
    browser.onSearchActivated()





def focus_query(
    am_config: PrioritySieveConfig,
    card_ids: set[CardId],
    ready_tag: bool = False,
) -> str | None:
    assert mw is not None

    if len(card_ids) == 0:
        return None

    query = "cid:" + "".join([f"{card_id}," for card_id in card_ids])
    query = query[:-1]  # removes the last comma

    if ready_tag:
        # we can escape characters like underscore in tags by using SearchNode
        query += " " + mw.col.build_search_string(SearchNode(tag=am_config.tag_ready))

    return query


def run_already_known_tagger() -> None:
    assert mw is not None
    assert browser is not None

    am_config = PrioritySieveConfig()

    known_tag: str = am_config.tag_known_manually
    selected_cards: Sequence[CardId] = browser.selectedCards()

    for card_id in selected_cards:
        card = mw.col.get_card(card_id)
        note = card.note()
        note.add_tag(known_tag)
        note_changes = mw.col.update_note(note)
        notify_op_execution(note_changes)

    tooltip(f"{len(selected_cards)} note(s) given the {known_tag} tag")


def run_learn_card_now() -> None:
    assert mw is not None
    assert mw.col.db is not None
    assert browser is not None

    am_config = PrioritySieveConfig()

    selected_cards = browser.selectedCards()
    note_ids = mw.col.db.list(
        f"select distinct nid from cards where id in {ids2str(selected_cards)}"
    )

    reposition_changes = mw.col.sched.reposition_new_cards(
        selected_cards,
        starting_from=0,
        step_size=0,  # we want all the selected cards to be placed in the same position
        randomize=False,
        shift_existing=False,  # shifting exiting causes a full sync, which is terrible
    )
    notify_op_execution(reposition_changes)

    mw.moveToState("review")
    mw.activateWindow()
    mw.reviewer._refresh_needed = RefreshNeeded.QUEUES
    mw.reviewer.refresh_if_needed()

    tooltip(f"Next new card(s) will be {selected_cards}")


def run_view_morphs() -> None:  # pylint:disable=too-many-locals
    tooltip("Entry breakdown view is no longer available.")
