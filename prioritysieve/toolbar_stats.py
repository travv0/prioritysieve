from __future__ import annotations

from .entry_db import EntryDB
from .prioritysieve_config import PrioritySieveConfig


class EntryToolbarStats:
    def __init__(self) -> None:
        self.lemmas = "L: ?"
        self.variants = "V: ?"
        self.update_stats()

    def update_stats(self) -> None:
        try:
            with EntryDB() as db:
                entries = db.get_entries()
        except TypeError:
            # Toolbar initialises before profile opens; db path is unknown.
            return
        except Exception:  # pragma: no cover - safeguard
            return

        config = PrioritySieveConfig()
        reviewed_count = sum(1 for entry in entries if entry.reviewed)
        if config.toolbar_stats_use_seen:
            total_variants = len(entries)
        else:
            total_variants = reviewed_count

        if config.toolbar_stats_use_known:
            self.lemmas = f"L: {reviewed_count}"
        else:
            self.lemmas = f"L: {len(entries)}"

        self.variants = f"V: {total_variants}"
