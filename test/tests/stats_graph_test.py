from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from prioritysieve.entry_db import EntryDB
from prioritysieve.stats_graph import get_first_entry_card_stats


@pytest.fixture
def mock_anki_env(tmp_path, monkeypatch):
    """Set up mocked Anki environment for stats_graph tests."""
    db_path = tmp_path / "prioritysieve.db"

    mock_col_db = MagicMock()
    mock_col_db.all = MagicMock(return_value=[])

    mock_decks = MagicMock()
    mock_decks.get = MagicMock(return_value={"name": "Default"})

    mw_stub = SimpleNamespace(
        pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)),
        col=SimpleNamespace(
            db=mock_col_db,
            sched=SimpleNamespace(dayCutoff=1700000000),
            decks=mock_decks,
        ),
    )
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub, raising=False)
    monkeypatch.setattr("prioritysieve.stats_graph.mw", mw_stub, raising=False)

    mock_config = MagicMock()
    mock_config.disabled_decks = []
    mock_config.get_preprocess_ignore_suspended_unless_tag_list = MagicMock(
        return_value=[]
    )
    monkeypatch.setattr(
        "prioritysieve.stats_graph.PrioritySieveConfig",
        lambda: mock_config,
        raising=False,
    )

    return {
        "db_path": db_path,
        "mw_stub": mw_stub,
        "mock_config": mock_config,
        "mock_col_db": mock_col_db,
        "mock_decks": mock_decks,
    }


def test_get_first_entry_card_stats_counts_oldest_card_per_entry(mock_anki_env) -> None:
    """Verify that only the oldest card per entry is counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]

    day_cutoff_ms = 1700000000 * 1000

    # Card 1: oldest for word1 -> should count
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)
    # Card 2: newer for word1 -> should NOT count (card1 is older)
    card2_id = day_cutoff_ms - (86400 * 1000 * 1)
    # Card 3: oldest for word2 -> should count
    card3_id = day_cutoff_ms - (86400 * 1000 * 5)

    entries = [
        {"text": "word1", "reading": "reading1", "reviewed": 1},
        {"text": "word2", "reading": "reading2", "reviewed": 1},
    ]
    cards = [
        {"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": card2_id, "note_id": 11, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": card3_id, "note_id": 12, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"},
        {"card_id": card2_id, "entry_text": "word1", "entry_reading": "reading1"},
        {"card_id": card3_id, "entry_text": "word2", "entry_reading": "reading2"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # Mock the Anki DB query to return card info
    # Returns: card_id, card_type, queue, did, odid, tags
    mock_col_db.all.return_value = [
        (card1_id, 2, 0, 1, 0, ""),  # non-new, active
        (card2_id, 2, 0, 1, 0, ""),  # non-new, active
        (card3_id, 2, 0, 1, 0, ""),  # non-new, active
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2  # One per entry


def test_get_first_entry_card_stats_counts_new_cards(mock_anki_env) -> None:
    """Verify that new cards (type=0) ARE counted if they're the first for their entry."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]

    day_cutoff_ms = 1700000000 * 1000
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 0}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # Card is type=0 (new) but should still count
    mock_col_db.all.return_value = [(card1_id, 0, 0, 1, 0, "")]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_counts_suspended_cards(mock_anki_env) -> None:
    """Verify that manually suspended cards are NOT counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]

    day_cutoff_ms = 1700000000 * 1000
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is queue=-1 (suspended) without auto-suspend tag, should NOT count
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "")]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 0


def test_get_first_entry_card_stats_counts_suspended_with_exception_tag(mock_anki_env) -> None:
    """Verify that suspended cards with exception tags ARE counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.get_preprocess_ignore_suspended_unless_tag_list.return_value = ["keep-suspended"]

    day_cutoff_ms = 1700000000 * 1000
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "keep-suspended", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is suspended but has exception tag, so it should count as active
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "keep-suspended")]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_counts_auto_suspended_cards(mock_anki_env) -> None:
    """Verify that auto-suspended cards ARE counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.tag_suspended_automatically = "ps-auto-suspend"

    day_cutoff_ms = 1700000000 * 1000
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "ps-auto-suspend", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is suspended but has auto-suspend tag, so it should count as active
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "ps-auto-suspend")]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_skips_disabled_decks(mock_anki_env) -> None:
    """Verify that cards in disabled decks are not counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]
    mock_decks = mock_anki_env["mock_decks"]

    mock_config.disabled_decks = ["DisabledDeck"]
    mock_decks.get.return_value = {"name": "DisabledDeck"}

    day_cutoff_ms = 1700000000 * 1000
    card1_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [(card1_id, 2, 0, 1, 0, "")]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    assert data == []


def test_get_first_entry_card_stats_empty_db_returns_empty(mock_anki_env) -> None:
    """Verify that an empty database returns an empty list."""
    db_path = mock_anki_env["db_path"]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=[], cards=[], card_entry_links=[])

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    assert data == []


def test_get_first_entry_card_stats_skips_if_older_non_new_in_disabled_deck(mock_anki_env) -> None:
    """Verify that entries with older non-new cards in disabled decks are not counted."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]
    mock_decks = mock_anki_env["mock_decks"]

    mock_config.disabled_decks = ["DisabledDeck"]

    day_cutoff_ms = 1700000000 * 1000
    # Older card in disabled deck (non-new)
    old_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # Newer card in enabled deck
    new_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1}]
    cards = [
        {"card_id": old_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": new_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": old_card_id, "entry_text": "word1", "entry_reading": "reading1"},
        {"card_id": new_card_id, "entry_text": "word1", "entry_reading": "reading1"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # Old card in disabled deck (did=2), new card in enabled deck (did=1)
    mock_col_db.all.return_value = [
        (old_card_id, 2, 0, 2, 0, ""),  # non-new, in deck 2
        (new_card_id, 0, 0, 1, 0, ""),  # new, in deck 1
    ]

    def mock_get_deck(deck_id):
        if deck_id == 1:
            return {"name": "EnabledDeck"}
        elif deck_id == 2:
            return {"name": "DisabledDeck"}
        return {"name": "Default"}

    mock_decks.get.side_effect = mock_get_deck

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # Should not count because there's an older non-new card in a disabled deck
    assert data == []
