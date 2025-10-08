from __future__ import annotations

from .entry_db import EntryDB
from .prioritysieve_config import PrioritySieveConfig


class EntryToolbarStats:
    def __init__(self) -> None:
        self.primary_name = "Reviewed"
        self.primary_label = "Reviewed: ?"
        self.secondary_name = "Tracked"
        self.secondary_label = "Tracked: ?"
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
        total_entries = len(entries)

        if config.toolbar_stats_use_known:
            primary_name = "Reviewed"
            primary_value = reviewed_count
        else:
            primary_name = "Tracked"
            primary_value = total_entries

        if config.toolbar_stats_use_seen:
            secondary_name = "Tracked"
            secondary_value = total_entries
        else:
            secondary_name = "Reviewed"
            secondary_value = reviewed_count

        if primary_name == secondary_name and primary_value == secondary_value:
            pending_value = max(total_entries - reviewed_count, 0)
            if pending_value > 0:
                secondary_name = "Pending"
                secondary_value = pending_value
            else:
                secondary_name = "Tracked"
                secondary_value = total_entries

        self.primary_name = primary_name
        self.primary_label = f"{primary_name}: {primary_value}"
        self.secondary_name = secondary_name
        self.secondary_label = f"{secondary_name}: {secondary_value}"
