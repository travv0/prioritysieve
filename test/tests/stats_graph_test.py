from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.entry_db import EntryDB
from prioritysieve.stats_graph import get_first_entry_card_stats


def test_get_first_entry_card_stats_counts_first_cards_only(tmp_path, monkeypatch) -> None:
    """Verify that get_first_entry_card_stats only counts the first card per entry."""
    db_path = tmp_path / "prioritysieve.db"

    mw_stub = SimpleNamespace(
        pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)),
        col=SimpleNamespace(
            db=SimpleNamespace(),
            sched=SimpleNamespace(dayCutoff=1700000000),
        ),
    )
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub, raising=False)
    monkeypatch.setattr("prioritysieve.stats_graph.mw", mw_stub, raising=False)

    day_cutoff_ms = 1700000000 * 1000

    card1_id = day_cutoff_ms - (86400 * 1000 * 2)
    card2_id = day_cutoff_ms - (86400 * 1000 * 2) + 1000
    card3_id = day_cutoff_ms - (86400 * 1000 * 5)

    entries = [
        {"text": "word1", "reading": "reading1", "reviewed": 1},
        {"text": "word2", "reading": "reading2", "reviewed": 1},
    ]
    cards = [
        {
            "card_id": card1_id,
            "note_id": 10,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "",
            "card_queue": 0,
        },
        {
            "card_id": card2_id,
            "note_id": 11,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "",
            "card_queue": 0,
        },
        {
            "card_id": card3_id,
            "note_id": 12,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "",
            "card_queue": 0,
        },
    ]
    card_entry_links = [
        {"card_id": card1_id, "entry_text": "word1", "entry_reading": "reading1"},
        {"card_id": card2_id, "entry_text": "word1", "entry_reading": "reading1"},
        {"card_id": card3_id, "entry_text": "word2", "entry_reading": "reading2"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 2

    data_dict = dict(data)
    assert data_dict.get(-2, 0) == 1
    assert data_dict.get(-5, 0) == 1


def test_get_first_entry_card_stats_empty_db_returns_empty(tmp_path, monkeypatch) -> None:
    """Verify that an empty database returns an empty list."""
    db_path = tmp_path / "prioritysieve.db"

    mw_stub = SimpleNamespace(
        pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)),
        col=SimpleNamespace(
            db=SimpleNamespace(),
            sched=SimpleNamespace(dayCutoff=1700000000),
        ),
    )
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub, raising=False)
    monkeypatch.setattr("prioritysieve.stats_graph.mw", mw_stub, raising=False)

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=[], cards=[], card_entry_links=[])

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    assert data == []


def test_get_first_entry_card_stats_respects_num_buckets(tmp_path, monkeypatch) -> None:
    """Verify that cards older than num_buckets days are excluded."""
    db_path = tmp_path / "prioritysieve.db"

    mw_stub = SimpleNamespace(
        pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)),
        col=SimpleNamespace(
            db=SimpleNamespace(),
            sched=SimpleNamespace(dayCutoff=1700000000),
        ),
    )
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub, raising=False)
    monkeypatch.setattr("prioritysieve.stats_graph.mw", mw_stub, raising=False)

    day_cutoff_ms = 1700000000 * 1000

    recent_card_id = day_cutoff_ms - (86400 * 1000 * 5)
    old_card_id = day_cutoff_ms - (86400 * 1000 * 100)

    entries = [
        {"text": "recent", "reading": "", "reviewed": 1},
        {"text": "old", "reading": "", "reviewed": 1},
    ]
    cards = [
        {
            "card_id": recent_card_id,
            "note_id": 10,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "",
            "card_queue": 0,
        },
        {
            "card_id": old_card_id,
            "note_id": 11,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "",
            "card_queue": 0,
        },
    ]
    card_entry_links = [
        {"card_id": recent_card_id, "entry_text": "recent", "entry_reading": ""},
        {"card_id": old_card_id, "entry_text": "old", "entry_reading": ""},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

    data = get_first_entry_card_stats(
        day_cutoff_seconds=1700000000,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    total_first_cards = sum(count for _, count in data)
    assert total_first_cards == 1
