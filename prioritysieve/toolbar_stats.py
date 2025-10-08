from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable as TypingIterable

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from .entry_db import EntryDB, StoredCard
from .prioritysieve_config import PrioritySieveConfig


class EntryToolbarStats:
    def __init__(self) -> None:
        self.primary_name = "Reviewed"
        self.primary_label = "Reviewed: ?"
        self.secondary_name = "Tracked"
        self.secondary_label = "Tracked: ?"
        self.update_stats()

    def update_stats(self) -> None:
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

        if config.toolbar_stats_use_known:
            primary_name = "Reviewed"
            primary_value = reviewed_count
        else:
            primary_name = "Tracked"
            primary_value = tracked_count

        if config.toolbar_stats_use_seen:
            secondary_name = "Tracked"
            secondary_value = tracked_count
        else:
            secondary_name = "Reviewed"
            secondary_value = reviewed_count

        if primary_name == secondary_name and primary_value == secondary_value:
            if pending_count > 0:
                secondary_name = "Pending"
                secondary_value = pending_count
            else:
                secondary_name = "Tracked"
                secondary_value = tracked_count

        self.primary_name = primary_name
        self.primary_label = f"{primary_name}: {primary_value}"
        self.secondary_name = secondary_name
        self.secondary_label = f"{secondary_name}: {secondary_value}"


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
