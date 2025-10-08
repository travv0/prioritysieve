from __future__ import annotations

from collections.abc import Iterable
from typing import Iterable as TypingIterable

from anki.consts import CARD_TYPE_NEW

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


def _compute_note_counts(
    config: PrioritySieveConfig,
    cards: TypingIterable[StoredCard],
) -> tuple[int, int]:
    """Return (tracked_notes, reviewed_notes) counts."""

    auto_tag = config.tag_suspended_automatically.strip()
    known_auto_tag = config.tag_known_automatically.strip()
    known_manual_tag = config.tag_known_manually.strip()
    exception_tags = {
        tag.strip()
        for tag in config.get_preprocess_ignore_suspended_unless_tag_list()
        if isinstance(tag, str)
    }

    tracked_notes: set[int] = set()
    reviewed_notes: set[int] = set()

    for card in cards:
        tag_words = {
            tag for tag in card.tags.strip().split() if tag and tag.strip()
        }

        if auto_tag and auto_tag in tag_words and not (
            exception_tags & tag_words
        ):
            # Automatically suspended duplicate; skip for toolbar counts.
            continue

        tracked_notes.add(card.note_id)

        is_reviewed = (
            card.card_type != CARD_TYPE_NEW
            or (known_auto_tag and known_auto_tag in tag_words)
            or (known_manual_tag and known_manual_tag in tag_words)
        )
        if is_reviewed:
            reviewed_notes.add(card.note_id)

    return len(tracked_notes), len(reviewed_notes)
