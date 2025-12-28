from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aqt import mw
from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from .entry import Entry


@dataclass(slots=True)
class StoredEntry:
    text: str
    reading: str
    language_name: str
    reviewed: bool

    def to_entry(self) -> Entry:
        return Entry(text=self.text, reading=self.reading, language_name=self.language_name, reviewed=self.reviewed)


def _profile_folder() -> Path:
    assert mw is not None
    return Path(mw.pm.profileFolder())


def _default_db_path() -> Path:
    return _profile_folder() / "prioritysieve.db"


class EntryDB:
    """Lightweight storage for PrioritySieve entry metadata."""

    def __init__(self, db_path: Path | None = None) -> None:
        assert mw is not None
        if db_path is None:
            db_path = _default_db_path()
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
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
                    language_name TEXT NOT NULL,
                    reviewed INTEGER NOT NULL,
                    listed INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (text, reading, language_name)
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
                    tags TEXT NOT NULL,
                    card_queue INTEGER NOT NULL
                )
                """
            )
            self.con.execute(
                """
                CREATE TABLE IF NOT EXISTS CardEntries (
                    card_id INTEGER PRIMARY KEY,
                    entry_text TEXT NOT NULL,
                    entry_reading TEXT NOT NULL,
                    entry_language TEXT NOT NULL,
                    FOREIGN KEY(card_id) REFERENCES Cards(card_id) ON DELETE CASCADE,
                    FOREIGN KEY(entry_text, entry_reading, entry_language) REFERENCES Entries(text, reading, language_name)
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
        card_entry_links: Iterable[dict[str, object]],
        languages_to_replace: Iterable[str] | None = None,
    ) -> None:
        with self.con:
            if languages_to_replace is None:
                # Full replacement: drop and recreate all tables
                self.drop_schema()
                self.create_schema()
            else:
                # Partial replacement: only clear data for specified languages
                self.create_schema()  # ensure schema exists
                languages = list(languages_to_replace)
                if languages:
                    placeholders = ",".join("?" for _ in languages)
                    # Delete card entries for the specified languages
                    self.con.execute(
                        f"DELETE FROM CardEntries WHERE entry_language IN ({placeholders})",
                        languages,
                    )
                    # Delete entries for the specified languages
                    self.con.execute(
                        f"DELETE FROM Entries WHERE language_name IN ({placeholders})",
                        languages,
                    )
                    # Get card IDs that no longer have entries and delete them
                    self.con.execute(
                        """
                        DELETE FROM Cards WHERE card_id NOT IN (
                            SELECT card_id FROM CardEntries
                        )
                        """
                    )
            self.con.executemany(
                "INSERT OR REPLACE INTO Entries (text, reading, language_name, reviewed, listed) VALUES (:text, :reading, :language_name, :reviewed, :listed)",
                entries,
            )
            self.con.executemany(
                "INSERT OR REPLACE INTO Cards (card_id, note_id, note_type_id, card_type, tags, card_queue) VALUES (:card_id, :note_id, :note_type_id, :card_type, :tags, :card_queue)",
                cards,
            )
            self.con.executemany(
                "INSERT OR REPLACE INTO CardEntries (card_id, entry_text, entry_reading, entry_language) VALUES (:card_id, :entry_text, :entry_reading, :entry_language)",
                card_entry_links,
            )

    def get_card_entry_cache(self) -> dict[int, Entry]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT ce.card_id, e.text, e.reading, e.language_name, e.reviewed
            FROM CardEntries ce
            JOIN Entries e ON e.text = ce.entry_text AND e.reading = ce.entry_reading AND e.language_name = ce.entry_language
            """
        )
        return {card_id: Entry(text, reading, language_name, bool(reviewed)) for card_id, text, reading, language_name, reviewed in cursor.fetchall()}

    def get_entries(self) -> list[StoredEntry]:
        cursor = self.con.cursor()
        cursor.execute("SELECT text, reading, language_name, reviewed FROM Entries")
        return [StoredEntry(text, reading, language_name, bool(reviewed)) for text, reading, language_name, reviewed in cursor.fetchall()]

    def get_cards(self) -> list[StoredCard]:
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                SELECT card_id, note_id, note_type_id, card_type, tags, card_queue
                FROM Cards
                """
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:  # pragma: no cover - legacy database fallback
            cursor.execute(
                """
                SELECT card_id, note_id, note_type_id, card_type, tags
                FROM Cards
                """
            )
            rows = [
                (card_id, note_id, note_type_id, card_type, tags, QUEUE_TYPE_SUSPENDED)
                for card_id, note_id, note_type_id, card_type, tags in cursor.fetchall()
            ]

        return [
            StoredCard(
                card_id=int(card_id),
                note_id=int(note_id),
                note_type_id=int(note_type_id),
                card_type=int(card_type),
                tags=str(tags),
                card_queue=int(card_queue),
            )
            for card_id, note_id, note_type_id, card_type, tags, card_queue in rows
        ]

    def get_entries_with_counts(
        self,
        reviewed_only: bool = True,
    ) -> list[tuple[Entry, int]]:
        cursor = self.con.cursor()
        where_clause = "WHERE e.reviewed = 1" if reviewed_only else ""
        cursor.execute(
            f"""
            SELECT e.text, e.reading, e.language_name, e.reviewed, COUNT(ce.card_id)
            FROM Entries e
            LEFT JOIN CardEntries ce
                ON ce.entry_text = e.text AND ce.entry_reading = e.reading AND ce.entry_language = e.language_name
            {where_clause}
            GROUP BY e.text, e.reading, e.language_name, e.reviewed
            ORDER BY e.text COLLATE NOCASE, e.reading COLLATE NOCASE
            """
        )
        results: list[tuple[Entry, int]] = []
        for text, reading, language_name, reviewed, count in cursor.fetchall():
            entry = Entry(text=text, reading=reading, language_name=language_name, reviewed=bool(reviewed))
            results.append((entry, int(count)))
        return results

    def get_entry_for_card(self, card_id: int) -> Entry | None:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT e.text, e.reading, e.language_name, e.reviewed
            FROM CardEntries ce
            JOIN Entries e
                ON e.text = ce.entry_text AND e.reading = ce.entry_reading AND e.language_name = ce.entry_language
            WHERE ce.card_id = ?
            """,
            (card_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        text, reading, language_name, reviewed = row
        return Entry(text=text, reading=reading, language_name=language_name, reviewed=bool(reviewed))

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
                    ON e.text = ce.entry_text AND e.reading = ce.entry_reading AND e.language_name = ce.entry_language
                WHERE e.text = ? AND e.language_name = ?
                """,
                (entry.text, entry.language_name),
            )
        else:
            cursor.execute(
                """
                SELECT ce.card_id, e.reviewed
                FROM CardEntries ce
                JOIN Entries e
                    ON e.text = ce.entry_text AND e.reading = ce.entry_reading AND e.language_name = ce.entry_language
                WHERE e.text = ? AND e.reading = ? AND e.language_name = ?
                """,
                (entry.text, entry.reading, entry.language_name),
            )

        result: list[int] = []
        for card_id, reviewed in cursor.fetchall():
            if include_reviewed or not bool(reviewed):
                result.append(int(card_id))
        return result

    def get_card_ids_grouped_by_entry(self) -> dict[tuple[str, str, str], list[int]]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT entry_text, entry_reading, entry_language, card_id
            FROM CardEntries
            """
        )
        groups: dict[tuple[str, str, str], list[int]] = {}
        for text, reading, language, card_id in cursor.fetchall():
            key = (text, reading, language)
            groups.setdefault(key, []).append(int(card_id))
        return groups

    def get_non_new_card_ids_grouped_by_entry(self) -> dict[tuple[str, str, str], set[int]]:
        cursor = self.con.cursor()
        cursor.execute(
            """
            SELECT ce.entry_text, ce.entry_reading, ce.entry_language, ce.card_id, IFNULL(c.card_type, ?)
            FROM CardEntries ce
            LEFT JOIN Cards c ON c.card_id = ce.card_id
            """,
            (CARD_TYPE_NEW,),
        )
        result: dict[tuple[str, str, str], set[int]] = {}
        for text, reading, language, card_id, card_type in cursor.fetchall():
            if int(card_type) == CARD_TYPE_NEW:
                continue
            key = (text, reading, language)
            result.setdefault(key, set()).add(int(card_id))
        return result

    def get_listed_entries(self) -> set[tuple[str, str, str]]:
        cursor = self.con.cursor()
        try:
            cursor.execute(
                """
                SELECT text, reading, language_name FROM Entries WHERE listed = 1
                """
            )
        except sqlite3.OperationalError:
            # legacy db without listed or language_name column - assume all entries are listed
            cursor.execute("SELECT text, reading FROM Entries")
            # Return empty set for legacy databases - they will be rebuilt on next recalc
            return set()
        return {(text, reading, language) for text, reading, language in cursor.fetchall()}


@dataclass(slots=True)
class StoredCard:
    card_id: int
    note_id: int
    note_type_id: int
    card_type: int
    tags: str
    card_queue: int
