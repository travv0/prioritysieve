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
        {"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1},
        {"text": "word2", "reading": "reading2", "reviewed": 1, "listed": 1},
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
    # Returns: card_id, card_type, queue, did, odid, tags, due
    mock_col_db.all.return_value = [
        (card1_id, 2, 0, 1, 0, "", 0),  # non-new, active
        (card2_id, 2, 0, 1, 0, "", 0),  # non-new, active
        (card3_id, 2, 0, 1, 0, "", 0),  # non-new, active
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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 0, "listed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # Card is type=0 (new) but should still count
    mock_col_db.all.return_value = [(card1_id, 0, 0, 1, 0, "", 1)]

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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is queue=-1 (suspended) without auto-suspend tag, should NOT count
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "", 0)]

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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "keep-suspended", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is suspended but has exception tag, so it should count as active
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "keep-suspended", 0)]

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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "ps-auto-suspend", "card_queue": -1}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    # card is suspended but has auto-suspend tag, so it should count as active
    mock_col_db.all.return_value = [(card1_id, 2, -1, 1, 0, "ps-auto-suspend", 0)]

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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1}]
    cards = [{"card_id": card1_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0}]
    card_entry_links = [{"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"}]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [(card1_id, 2, 0, 1, 0, "", 0)]

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

    entries = [{"text": "word1", "reading": "reading1", "reviewed": 1, "listed": 1}]
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
        (old_card_id, 2, 0, 2, 0, "", 0),  # non-new, in deck 2
        (new_card_id, 0, 0, 1, 0, "", 1),  # new, in deck 1
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


def test_get_first_entry_card_stats_skips_subset_with_superset_non_new(mock_anki_env) -> None:
    """Verify that subset entries are not counted if a superset has an older non-new card."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_variant_spellings = True

    day_cutoff_ms = 1700000000 * 1000
    # older superset card (思い出す) - non-new
    superset_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer subset card (思いだす) - new, auto-suspended
    subset_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 1, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": subset_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "ps-auto-suspend", "card_queue": -1},
    ]
    card_entry_links = [
        {"card_id": superset_card_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card_id, 2, 0, 1, 0, "", 0),  # non-new, active
        (subset_card_id, 0, -1, 1, 0, "ps-auto-suspend", 1),  # new, auto-suspended
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only the superset should be counted, not the subset
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_skips_subset_with_superset_new_due_before(
    mock_anki_env,
) -> None:
    """Verify that subset entries are skipped if superset new card is due before."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.tag_suspended_automatically = "ps-auto-suspend"
    mock_config.auto_suspend_variant_spellings = True

    day_cutoff_ms = 1700000000 * 1000
    # older superset card (思い出す) - new, due=1 (earlier)
    superset_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer subset card (思いだす) - new, due=5 (later)
    subset_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 0, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
        {"card_id": subset_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": superset_card_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card_id, 0, 0, 1, 0, "", 1),  # new, due=1
        (subset_card_id, 0, 0, 1, 0, "", 5),  # new, due=5
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only the superset should be counted (it's due first, so subset would be auto-suspended)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_counts_both_when_subset_due_before_superset(
    mock_anki_env,
) -> None:
    """Verify that both entries are counted if subset new card is due before superset."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.tag_suspended_automatically = "ps-auto-suspend"
    mock_config.auto_suspend_variant_spellings = True

    day_cutoff_ms = 1700000000 * 1000
    # older superset card (思い出す) - new, due=5 (later)
    superset_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer subset card (思いだす) - new, due=1 (earlier)
    subset_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 0, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
        {"card_id": subset_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": superset_card_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card_id, 0, 0, 1, 0, "", 5),  # new, due=5
        (subset_card_id, 0, 0, 1, 0, "", 1),  # new, due=1
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # both should be counted (subset is due first, so superset would be auto-suspended)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2


def test_get_first_entry_card_stats_skips_kana_variant_with_older_non_new(
    mock_anki_env,
) -> None:
    """Verify that katakana entries are skipped if hiragana variant has older non-new card."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.merge_kana_variant_spellings = True

    day_cutoff_ms = 1700000000 * 1000
    # older hiragana card (ぱらぱら) - non-new
    hiragana_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer katakana card (パラパラ) - new
    katakana_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "ぱらぱら", "reading": "ぱらぱら", "reviewed": 1, "listed": 1},
        {"text": "パラパラ", "reading": "ぱらぱら", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": hiragana_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": katakana_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": hiragana_card_id, "entry_text": "ぱらぱら", "entry_reading": "ぱらぱら"},
        {"card_id": katakana_card_id, "entry_text": "パラパラ", "entry_reading": "ぱらぱら"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (hiragana_card_id, 2, 0, 1, 0, "", 0),  # non-new
        (katakana_card_id, 0, 0, 1, 0, "", 1),  # new
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only the hiragana entry should be counted (katakana is a kana variant)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_kana_variant_requires_setting(
    mock_anki_env,
) -> None:
    """Verify that kana variants are NOT filtered when setting is off."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.merge_kana_variant_spellings = False

    day_cutoff_ms = 1700000000 * 1000
    # older hiragana card (ぱらぱら) - non-new
    hiragana_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer katakana card (パラパラ) - new
    katakana_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "ぱらぱら", "reading": "ぱらぱら", "reviewed": 1, "listed": 1},
        {"text": "パラパラ", "reading": "ぱらぱら", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": hiragana_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": katakana_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": hiragana_card_id, "entry_text": "ぱらぱら", "entry_reading": "ぱらぱら"},
        {"card_id": katakana_card_id, "entry_text": "パラパラ", "entry_reading": "ぱらぱら"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (hiragana_card_id, 2, 0, 1, 0, "", 0),  # non-new
        (katakana_card_id, 0, 0, 1, 0, "", 1),  # new
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # both should be counted when setting is off
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2


def test_get_first_entry_card_stats_skips_pure_kana_with_kanji_variant_non_new(
    mock_anki_env,
) -> None:
    """Verify that pure kana entries are skipped if kanji variant has older non-new card."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_variant_spellings = True

    day_cutoff_ms = 1700000000 * 1000
    # older kanji variant (見窄らしい) - non-new
    kanji_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer pure kana (みすぼらしい) - new
    kana_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "見窄らしい", "reading": "みすぼらしい", "reviewed": 1, "listed": 1},
        {"text": "みすぼらしい", "reading": "みすぼらしい", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": kanji_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": kana_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": kanji_card_id, "entry_text": "見窄らしい", "entry_reading": "みすぼらしい"},
        {"card_id": kana_card_id, "entry_text": "みすぼらしい", "entry_reading": "みすぼらしい"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (kanji_card_id, 2, 0, 1, 0, "", 0),  # non-new
        (kana_card_id, 0, 0, 1, 0, "", 1),  # new
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only the kanji entry should be counted (pure kana is dominated by kanji variant)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_kana_variant_dominated_by_non_first_non_new(
    mock_anki_env,
) -> None:
    """Verify katakana is skipped when hiragana's first card is new but has older non-new card."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.merge_kana_variant_spellings = True
    mock_config.tag_suspended_automatically = "ps-auto-suspend"

    day_cutoff_ms = 1700000000 * 1000
    # ぱらぱら has multiple cards:
    # - oldest card is new (auto-suspended) - this is the "first" card
    # - second card is non-new (reviewed)
    hiragana_card1_id = day_cutoff_ms - (86400 * 1000 * 20)  # oldest, new, auto-suspended
    hiragana_card2_id = day_cutoff_ms - (86400 * 1000 * 15)  # second, non-new
    # パラパラ has one card (newer than both hiragana cards)
    katakana_card_id = day_cutoff_ms - (86400 * 1000 * 2)  # newest

    entries = [
        {"text": "ぱらぱら", "reading": "ぱらぱら", "reviewed": 1, "listed": 1},
        {"text": "パラパラ", "reading": "ぱらぱら", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": hiragana_card1_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "ps-auto-suspend", "card_queue": -1},
        {"card_id": hiragana_card2_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 2},
        {"card_id": katakana_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": hiragana_card1_id, "entry_text": "ぱらぱら", "entry_reading": "ぱらぱら"},
        {"card_id": hiragana_card2_id, "entry_text": "ぱらぱら", "entry_reading": "ぱらぱら"},
        {"card_id": katakana_card_id, "entry_text": "パラパラ", "entry_reading": "ぱらぱら"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (hiragana_card1_id, 0, -1, 1, 0, "ps-auto-suspend", 1),  # new, auto-suspended
        (hiragana_card2_id, 2, 2, 1, 0, "", 0),  # non-new, reviewed
        (katakana_card_id, 0, 0, 1, 0, "", 1),  # new
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only ぱらぱら should count - パラパラ is dominated because ぱらぱら has an older non-new card
    # (even though ぱらぱら's "first" card is new/auto-suspended)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_variant_filter_requires_setting(
    mock_anki_env,
) -> None:
    """Verify that kanji subset filtering requires auto_suspend_variant_spellings enabled."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_variant_spellings = False

    day_cutoff_ms = 1700000000 * 1000
    # older superset card (思い出す) - non-new
    superset_card_id = day_cutoff_ms - (86400 * 1000 * 10)
    # newer subset card (思いだす) - new
    subset_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 1, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": subset_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": superset_card_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card_id, 2, 0, 1, 0, "", 0),  # non-new
        (subset_card_id, 0, 0, 1, 0, "", 1),  # new
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # both should be counted when auto_suspend_variant_spellings is off
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2


def test_get_first_entry_card_stats_uses_min_due_for_auto_suspended_first_card(
    mock_anki_env,
) -> None:
    """Verify that min due is used when comparing variants with auto-suspended first cards."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_variant_spellings = True
    mock_config.tag_suspended_automatically = "ps-auto-suspend"

    day_cutoff_ms = 1700000000 * 1000
    # superset entry (思い出す) has two cards:
    # - oldest card is auto-suspended with max due (2147483647)
    # - newer card is unsuspended with due=1
    superset_card1_id = day_cutoff_ms - (86400 * 1000 * 20)  # oldest, auto-suspended
    superset_card2_id = day_cutoff_ms - (86400 * 1000 * 15)  # newer, unsuspended, due=1
    # subset entry (思いだす) has one card with due=5
    subset_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 0, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card1_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "ps-auto-suspend", "card_queue": -1},
        {"card_id": superset_card2_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
        {"card_id": subset_card_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": superset_card1_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": superset_card2_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card1_id, 0, -1, 1, 0, "ps-auto-suspend", 2147483647),  # auto-suspended, max due
        (superset_card2_id, 0, 0, 1, 0, "", 1),  # unsuspended, due=1
        (subset_card_id, 0, 0, 1, 0, "", 5),  # due=5
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only superset should count - subset is dominated because superset's min due (1) < subset's due (5)
    # even though superset's first card has max due (2147483647)
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_uses_min_due_for_both_entries(
    mock_anki_env,
) -> None:
    """Verify both entries use min due for comparison when both have auto-suspended first cards."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_variant_spellings = True
    mock_config.tag_suspended_automatically = "ps-auto-suspend"

    day_cutoff_ms = 1700000000 * 1000
    # superset entry (思い出す) has two cards:
    # - oldest card is auto-suspended with max due
    # - newer card is unsuspended with due=5 (later than subset)
    superset_card1_id = day_cutoff_ms - (86400 * 1000 * 20)  # oldest, auto-suspended
    superset_card2_id = day_cutoff_ms - (86400 * 1000 * 15)  # newer, unsuspended, due=5
    # subset entry (思いだす) has two cards:
    # - oldest card is auto-suspended with max due
    # - newer card is unsuspended with due=1 (earlier than superset)
    subset_card1_id = day_cutoff_ms - (86400 * 1000 * 10)  # auto-suspended
    subset_card2_id = day_cutoff_ms - (86400 * 1000 * 5)  # unsuspended, due=1

    entries = [
        {"text": "思い出す", "reading": "おもいだす", "reviewed": 0, "listed": 1},
        {"text": "思いだす", "reading": "おもいだす", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {"card_id": superset_card1_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "ps-auto-suspend", "card_queue": -1},
        {"card_id": superset_card2_id, "note_id": 10, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
        {"card_id": subset_card1_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "ps-auto-suspend", "card_queue": -1},
        {"card_id": subset_card2_id, "note_id": 11, "note_type_id": 100, "card_type": 0, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": superset_card1_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": superset_card2_id, "entry_text": "思い出す", "entry_reading": "おもいだす"},
        {"card_id": subset_card1_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
        {"card_id": subset_card2_id, "entry_text": "思いだす", "entry_reading": "おもいだす"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (superset_card1_id, 0, -1, 1, 0, "ps-auto-suspend", 2147483647),  # auto-suspended, max due
        (superset_card2_id, 0, 0, 1, 0, "", 5),  # unsuspended, due=5
        (subset_card1_id, 0, -1, 1, 0, "ps-auto-suspend", 2147483647),  # auto-suspended, max due
        (subset_card2_id, 0, 0, 1, 0, "", 1),  # unsuspended, due=1
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # both should count - subset's min due (1) < superset's min due (5), so subset is NOT dominated
    # even though superset is older by card_id
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2


def test_get_first_entry_card_stats_skips_unlisted_entries(mock_anki_env) -> None:
    """Verify unlisted entries are not counted when auto_suspend_unlisted_entries is enabled."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_unlisted_entries = True

    day_cutoff_ms = 1700000000 * 1000
    listed_card_id = day_cutoff_ms - (86400 * 1000 * 5)
    unlisted_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "listed_word", "reading": "reading1", "reviewed": 1, "listed": 1},
        {"text": "unlisted_word", "reading": "reading2", "reviewed": 1, "listed": 0},
    ]
    cards = [
        {"card_id": listed_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": unlisted_card_id, "note_id": 11, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": listed_card_id, "entry_text": "listed_word", "entry_reading": "reading1"},
        {"card_id": unlisted_card_id, "entry_text": "unlisted_word", "entry_reading": "reading2"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (listed_card_id, 2, 0, 1, 0, "", 0),
        (unlisted_card_id, 2, 0, 1, 0, "", 0),
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # only the listed entry should be counted
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1


def test_get_first_entry_card_stats_counts_unlisted_when_setting_disabled(mock_anki_env) -> None:
    """Verify unlisted entries are counted when auto_suspend_unlisted_entries is disabled."""
    db_path = mock_anki_env["db_path"]
    mock_col_db = mock_anki_env["mock_col_db"]
    mock_config = mock_anki_env["mock_config"]

    mock_config.auto_suspend_unlisted_entries = False

    day_cutoff_ms = 1700000000 * 1000
    listed_card_id = day_cutoff_ms - (86400 * 1000 * 5)
    unlisted_card_id = day_cutoff_ms - (86400 * 1000 * 2)

    entries = [
        {"text": "listed_word", "reading": "reading1", "reviewed": 1, "listed": 1},
        {"text": "unlisted_word", "reading": "reading2", "reviewed": 1, "listed": 0},
    ]
    cards = [
        {"card_id": listed_card_id, "note_id": 10, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
        {"card_id": unlisted_card_id, "note_id": 11, "note_type_id": 100, "card_type": 2, "tags": "", "card_queue": 0},
    ]
    card_entry_links = [
        {"card_id": listed_card_id, "entry_text": "listed_word", "entry_reading": "reading1"},
        {"card_id": unlisted_card_id, "entry_text": "unlisted_word", "entry_reading": "reading2"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    mock_col_db.all.return_value = [
        (listed_card_id, 2, 0, 1, 0, "", 0),
        (unlisted_card_id, 2, 0, 1, 0, "", 0),
    ]

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    # both entries should be counted when setting is disabled
    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2
