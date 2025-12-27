from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.entry import Entry
from prioritysieve.entry_db import EntryDB


def test_entry_db_replace_and_fetch(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "prioritysieve.db"

    mw_stub = SimpleNamespace(pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)))
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub, raising=False)

    entries = [
        {"text": "alpha", "reading": "reading1", "language_name": "Test", "reviewed": 1, "listed": 1},
        {"text": "alpha", "reading": "reading2", "language_name": "Test", "reviewed": 0, "listed": 1},
        {"text": "beta", "reading": "", "language_name": "Test", "reviewed": 0, "listed": 1},
    ]
    cards = [
        {
            "card_id": 1,
            "note_id": 10,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "alpha",
            "card_queue": 0,
        },
        {
            "card_id": 2,
            "note_id": 11,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "alpha",
            "card_queue": 0,
        },
        {
            "card_id": 3,
            "note_id": 12,
            "note_type_id": 100,
            "card_type": 0,
            "tags": "beta",
            "card_queue": 0,
        },
    ]
    card_entry_links = [
        {"card_id": 1, "entry_text": "alpha", "entry_reading": "reading1", "entry_language": "Test"},
        {"card_id": 2, "entry_text": "alpha", "entry_reading": "reading2", "entry_language": "Test"},
        {"card_id": 3, "entry_text": "beta", "entry_reading": "", "entry_language": "Test"},
    ]

    with EntryDB(db_path=db_path) as db:
        db.replace_data(entries=entries, cards=cards, card_entry_links=card_entry_links)

        stored_entries = db.get_entries()
        assert {entry.text for entry in stored_entries} == {"alpha", "beta"}

        cache = db.get_card_entry_cache()
        assert cache[1].text == "alpha"
        assert cache[2].reading == "reading2"

        reviewed_only = db.get_entries_with_counts()
        assert len(reviewed_only) == 1
        assert reviewed_only[0][0].text == "alpha"
        assert reviewed_only[0][1] == 1

        all_entries = db.get_entries_with_counts(reviewed_only=False)
        counts_by_text: dict[str, int] = {}
        for entry_obj, count in all_entries:
            counts_by_text.setdefault(entry_obj.text, 0)
            counts_by_text[entry_obj.text] += count
        assert counts_by_text == {"alpha": 2, "beta": 1}

        assert db.get_entry_for_card(2).reading == "reading2"

        entry = Entry(text="alpha", reading="reading2", language_name="Test", reviewed=False)
        ids_with_text = db.get_card_ids_for_entry(entry, include_reviewed=True, text_only=True)
        assert set(ids_with_text) == {1, 2}

        ids_strict = db.get_card_ids_for_entry(entry, include_reviewed=False, text_only=False)
        assert ids_strict == [2]

    with EntryDB(db_path=db_path) as db:
        restored = db.get_entries()
        assert len(restored) == 3
