from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aqt import mw
from anki.consts import CARD_TYPE_NEW

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

    def get_entries_with_counts(
        self,
        reviewed_only: bool = True,
    ) -> list[tuple[Entry, int]]:
        cursor = self.con.cursor()
        where_clause = "WHERE e.reviewed = 1" if reviewed_only else ""
        cursor.execute(
            f"""
            SELECT e.text, e.reading, e.reviewed, COUNT(ce.card_id)
            FROM Entries e
            LEFT JOIN CardEntries ce
                ON ce.entry_text = e.text AND ce.entry_reading = e.reading
            {where_clause}
            GROUP BY e.text, e.reading, e.reviewed
            ORDER BY e.text COLLATE NOCASE, e.reading COLLATE NOCASE
            """
        )
        results: list[tuple[Entry, int]] = []
        for text, reading, reviewed, count in cursor.fetchall():
            entry = Entry(text=text, reading=reading, reviewed=bool(reviewed))
            results.append((entry, int(count)))
        return results

    def get_entry_for_card(self, card_id: int) -> Entry | None:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT e.text, e.reading, e.reviewed
            FROM CardEntries ce
            JOIN Entries e
                ON e.text = ce.entry_text AND e.reading = ce.entry_reading
            WHERE ce.card_id = ?
            """,
            (card_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        text, reading, reviewed = row
        return Entry(text=text, reading=reading, reviewed=bool(reviewed))

    def get_card_ids_for_entry(
        self,
        entry: Entry,
        include_reviewed: bool = True,
        text_only: bool = False,
    ) -> list[int]:
        cursor = self.con.cursor()
        if text_only:
            cursor.execute(
                """
                SELECT ce.card_id, e.reviewed
                FROM CardEntries ce
                JOIN Entries e
                    ON e.text = ce.entry_text AND e.reading = ce.entry_reading
                WHERE e.text = ?
                """,
                (entry.text,),
            )
        else:
            cursor.execute(
                """
                SELECT ce.card_id, e.reviewed
                FROM CardEntries ce
                JOIN Entries e
                    ON e.text = ce.entry_text AND e.reading = ce.entry_reading
                WHERE e.text = ? AND e.reading = ?
                """,
                (entry.text, entry.reading),
            )

        result: list[int] = []
        for card_id, reviewed in cursor.fetchall():
            if include_reviewed or not bool(reviewed):
                result.append(int(card_id))
        return result

    def get_card_ids_grouped_by_entry(self) -> dict[tuple[str, str], list[int]]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT entry_text, entry_reading, card_id
            FROM CardEntries
            """
        )
        groups: dict[tuple[str, str], list[int]] = {}
        for text, reading, card_id in cursor.fetchall():
            key = (text, reading)
            groups.setdefault(key, []).append(int(card_id))
        return groups

    def get_non_new_card_ids_grouped_by_entry(self) -> dict[tuple[str, str], set[int]]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT ce.entry_text, ce.entry_reading, ce.card_id, IFNULL(c.card_type, ?)
            FROM CardEntries ce
            LEFT JOIN Cards c ON c.card_id = ce.card_id
            """,
            (CARD_TYPE_NEW,),
        )
        result: dict[tuple[str, str], set[int]] = {}
        for text, reading, card_id, card_type in cursor.fetchall():
            if int(card_type) == CARD_TYPE_NEW:
                continue
            key = (text, reading)
            result.setdefault(key, set()).add(int(card_id))
        return result
