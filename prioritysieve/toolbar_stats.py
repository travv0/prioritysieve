from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable as TypingIterable

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from .entry_db import EntryDB, StoredCard
from .prioritysieve_config import PrioritySieveConfig
from .recalc import recalc_main

_COUNTER_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("tracked", "Tracked"),
    ("reviewed", "Reviewed"),
    ("pending", "Pending"),
)
_LAST_KNOWN_VALUES: dict[str, int] | None = None


@dataclass(slots=True)
class ToolbarCounter:
    key: str
    name: str
    value: int

    @property
    def label(self) -> str:
        initials = "".join(word[0] for word in self.name.split() if word)
        return f"{initials.upper()}: {self.value}"

    @property
    def tooltip(self) -> str:
        return f"{self.name} entry count"


class EntryToolbarStats:
    def __init__(self) -> None:
        initial_values = _LAST_KNOWN_VALUES or {}
        self._counters: list[ToolbarCounter] = [
            ToolbarCounter(key, name, initial_values.get(key, 0))
            for key, name in _COUNTER_DEFINITIONS
        ]
        self._counter_map: dict[str, ToolbarCounter] = {
            counter.key: counter for counter in self._counters
        }
        self.update_stats()

    @property
    def counters(self) -> list[ToolbarCounter]:
        return self._counters

    def get_counter(self, key: str) -> ToolbarCounter | None:
        return self._counter_map.get(key)

    def update_stats(self) -> None:
        if recalc_main.recalc_in_progress():
            return

        config = PrioritySieveConfig()
        try:
            with EntryDB() as db:
                cards = db.get_cards()
        except TypeError:
            return
        except Exception:  # pragma: no cover - safeguard
            return

        tracked_count, reviewed_count = _compute_note_counts(config, cards)
        pending_count = max(tracked_count - reviewed_count, 0)

        global _LAST_KNOWN_VALUES
        _LAST_KNOWN_VALUES = {
            "tracked": tracked_count,
            "reviewed": reviewed_count,
            "pending": pending_count,
        }

        updated_counters = [
            ToolbarCounter(key, name, _LAST_KNOWN_VALUES[key])
            for key, name in _COUNTER_DEFINITIONS
        ]
        self._counters = updated_counters
        self._counter_map = {counter.key: counter for counter in updated_counters}


@dataclass(slots=True)
class _NoteState:
    tags: set[str]
    has_exception: bool
    active_any: bool = False
    active_non_new: bool = False


def _compute_note_counts(
    config: PrioritySieveConfig,
    cards: TypingIterable[StoredCard],
) -> tuple[int, int]:
    """Return (tracked_notes, reviewed_notes) counts."""

    exception_tags = {
        tag.strip()
        for tag in config.get_preprocess_ignore_suspended_unless_tag_list()
        if isinstance(tag, str) and tag.strip()
    }

    note_states: dict[int, _NoteState] = {}

    for card in cards:
        state = note_states.get(card.note_id)
        if state is None:
            tag_words = {
                tag for tag in card.tags.split() if tag and tag.strip()
            }
            state = _NoteState(
                tags=tag_words,
                has_exception=bool(exception_tags & tag_words),
            )
            note_states[card.note_id] = state

        is_suspended = card.card_queue == QUEUE_TYPE_SUSPENDED
        is_active = not is_suspended or state.has_exception

        if is_active:
            state.active_any = True
            if card.card_type != CARD_TYPE_NEW:
                state.active_non_new = True

    tracked_notes = sum(1 for state in note_states.values() if state.active_any)
    reviewed_notes = sum(1 for state in note_states.values() if state.active_non_new)

    return tracked_notes, reviewed_notes
