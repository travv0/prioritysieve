from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aqt import mw

from .entry import Entry


@dataclass(slots=True)
class StoredEntry:
    text: str
    reading: str
    reviewed: bool

    def to_entry(self) -> Entry:
        return Entry(text=self.text, reading=self.reading, reviewed=self.reviewed)


class EntryDB:
    """Lightweight storage for PrioritySieve entry metadata."""

    def __init__(self, db_path: Path | None = None) -> None:
        assert mw is not None
        if db_path is None:
            db_path = Path(mw.pm.profileFolder()) / "prioritysieve.db"
        self.con = sqlite3.connect(db_path)

    def __enter__(self) -> "EntryDB":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is None:
                self.con.commit()
            else:
                self.con.rollback()
        finally:
            self.con.close()

    def create_schema(self) -> None:
        with self.con:
            self.con.execute(
                """
                CREATE TABLE IF NOT EXISTS Entries (
                    text TEXT NOT NULL,
                    reading TEXT NOT NULL,
                    reviewed INTEGER NOT NULL,
                    PRIMARY KEY (text, reading)
                )
                """
            )
            self.con.execute(
                """
                CREATE TABLE IF NOT EXISTS Cards (
                    card_id INTEGER PRIMARY KEY,
                    note_id INTEGER NOT NULL,
                    note_type_id INTEGER NOT NULL,
                    card_type INTEGER NOT NULL,
                    tags TEXT NOT NULL
                )
                """
            )
            self.con.execute(
                """
                CREATE TABLE IF NOT EXISTS CardEntries (
                    card_id INTEGER PRIMARY KEY,
                    entry_text TEXT NOT NULL,
                    entry_reading TEXT NOT NULL,
                    FOREIGN KEY(card_id) REFERENCES Cards(card_id) ON DELETE CASCADE,
                    FOREIGN KEY(entry_text, entry_reading) REFERENCES Entries(text, reading)
                )
                """
            )

    def drop_schema(self) -> None:
        with self.con:
            self.con.execute("DROP TABLE IF EXISTS CardEntries")
            self.con.execute("DROP TABLE IF EXISTS Cards")
            self.con.execute("DROP TABLE IF EXISTS Entries")

    def replace_data(
        self,
        entries: Iterable[dict[str, object]],
        cards: Iterable[dict[str, object]],
        card_entries: Iterable[dict[str, object]],
    ) -> None:
        with self.con:
            self.drop_schema()
            self.create_schema()
            self.con.executemany(
                "INSERT OR REPLACE INTO Entries (text, reading, reviewed) VALUES (:text, :reading, :reviewed)",
                entries,
            )
            self.con.executemany(
                "INSERT OR REPLACE INTO Cards (card_id, note_id, note_type_id, card_type, tags) VALUES (:card_id, :note_id, :note_type_id, :card_type, :tags)",
                cards,
            )
            self.con.executemany(
                "INSERT OR REPLACE INTO CardEntries (card_id, entry_text, entry_reading) VALUES (:card_id, :entry_text, :entry_reading)",
                card_entries,
            )

    def get_card_entry_cache(self) -> dict[int, Entry]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT ce.card_id, e.text, e.reading, e.reviewed
            FROM CardEntries ce
            JOIN Entries e ON e.text = ce.entry_text AND e.reading = ce.entry_reading
            """
        )
        return {card_id: Entry(text, reading, bool(reviewed)) for card_id, text, reading, reviewed in cursor.fetchall()}

    def get_entries(self) -> list[StoredEntry]:
        cursor = self.con.cursor()
        cursor.execute("SELECT text, reading, reviewed FROM Entries")
        return [StoredEntry(text, reading, bool(reviewed)) for text, reading, reviewed in cursor.fetchall()]

