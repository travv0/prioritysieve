"""
Statistics graph for PrioritySieve.

Adds a graph to Anki's old statistics page showing newly learned entries -
cards that were the first non-new card for an entry that didn't already
have a non-new, non-suspended card.
"""

from __future__ import annotations

import inspect
import math
import sqlite3
from collections import defaultdict

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from aqt import mw

from .entry_db import EntryDB
from .prioritysieve_config import PrioritySieveConfig

_COLOR_FIRST_ENTRY = "#9467bd"  # purple


def get_first_entry_card_stats(
    day_cutoff_seconds: int,
    bucket_size_days: int,
    num_buckets: int | None,
    additional_filter: str,
) -> list[tuple[int, int]]:
    """
    Calculate stats for cards that introduced new entries.

    A card counts as introducing an entry if:
    1. It's in an enabled deck (not in disabled_decks)
    2. It's the oldest card for its entry (by card_id/creation time)
    3. No older non-new, non-suspended card exists for that entry
       (across any configured note type, regardless of deck)

    Returns a list of (bucket_offset, count) tuples.
    """
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    config = PrioritySieveConfig()
    disabled_deck_names = set(config.disabled_decks)
    exception_tags = set(config.get_preprocess_ignore_suspended_unless_tag_list())

    try:
        with EntryDB() as entry_db:
            card_ids_by_entry = entry_db.get_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        return []

    if not card_ids_by_entry:
        return []

    all_card_ids: set[int] = set()
    for card_ids in card_ids_by_entry.values():
        all_card_ids.update(card_ids)

    if not all_card_ids:
        return []

    card_info = _load_card_info(all_card_ids, exception_tags)

    deck_name_cache: dict[int, str] = {}

    first_entry_card_ids: set[int] = set()

    for entry_key, card_ids in card_ids_by_entry.items():
        first_card_id = _find_first_entry_card(
            card_ids=card_ids,
            card_info=card_info,
            disabled_deck_names=disabled_deck_names,
            deck_name_cache=deck_name_cache,
        )
        if first_card_id is not None:
            first_entry_card_ids.add(first_card_id)

    if not first_entry_card_ids:
        return []

    day_cutoff_ms = day_cutoff_seconds * 1000

    bucket_counts: dict[int, int] = defaultdict(int)

    for card_id in first_entry_card_ids:
        days_ago = (day_cutoff_ms - card_id) // (86400 * 1000)
        bucket_offset = -(days_ago // bucket_size_days)

        if num_buckets is not None and bucket_offset < -num_buckets:
            continue

        bucket_counts[bucket_offset] += 1

    if not bucket_counts:
        return []

    min_bucket = min(bucket_counts.keys())
    max_bucket = max(bucket_counts.keys())

    result: list[tuple[int, int]] = []
    for bucket in range(min_bucket, max_bucket + 1):
        result.append((bucket, bucket_counts.get(bucket, 0)))

    return result


class _CardInfo:
    __slots__ = ("card_type", "queue", "deck_id", "odid", "tags", "is_active")

    def __init__(
        self,
        card_type: int,
        queue: int,
        deck_id: int,
        odid: int,
        tags: str,
        exception_tags: set[str],
    ) -> None:
        self.card_type = card_type
        self.queue = queue
        self.deck_id = deck_id
        self.odid = odid
        self.tags = tags

        is_suspended = queue == QUEUE_TYPE_SUSPENDED
        has_exception = _has_any_tag(tags, exception_tags) if exception_tags else False
        self.is_active = not is_suspended or has_exception


def _has_any_tag(tags_text: str, exception_tags: set[str]) -> bool:
    if not tags_text or not exception_tags:
        return False
    card_tags = {tag.strip().lower() for tag in tags_text.split() if tag.strip()}
    normalized_exceptions = {tag.lower() for tag in exception_tags}
    return bool(card_tags & normalized_exceptions)


def _load_card_info(
    card_ids: set[int],
    exception_tags: set[str],
) -> dict[int, _CardInfo]:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    result: dict[int, _CardInfo] = {}
    card_ids_list = list(card_ids)
    chunk_size = 900

    for start in range(0, len(card_ids_list), chunk_size):
        chunk = card_ids_list[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = mw.col.db.all(
            f"""
            SELECT cards.id, cards.type, cards.queue, cards.did,
                   COALESCE(cards.odid, 0), notes.tags
            FROM cards
            JOIN notes ON notes.id = cards.nid
            WHERE cards.id IN ({placeholders})
            """,
            *chunk,
        )
        for card_id, card_type, queue, did, odid, tags in rows:
            result[int(card_id)] = _CardInfo(
                card_type=int(card_type),
                queue=int(queue),
                deck_id=int(did),
                odid=int(odid),
                tags=tags if isinstance(tags, str) else "",
                exception_tags=exception_tags,
            )

    return result


def _get_deck_name(
    deck_id: int,
    odid: int,
    deck_name_cache: dict[int, str],
) -> str:
    assert mw is not None
    assert mw.col is not None

    effective_deck_id = odid or deck_id
    if effective_deck_id in deck_name_cache:
        return deck_name_cache[effective_deck_id]

    deck_dict = mw.col.decks.get(effective_deck_id)
    name = deck_dict.get("name") if isinstance(deck_dict, dict) else ""
    deck_name = name if isinstance(name, str) else ""
    deck_name_cache[effective_deck_id] = deck_name
    return deck_name


def _find_first_entry_card(
    card_ids: list[int],
    card_info: dict[int, _CardInfo],
    disabled_deck_names: set[str],
    deck_name_cache: dict[int, str],
) -> int | None:
    """
    Find the card that introduced this entry, if any.

    Returns the card_id of the oldest card in an enabled deck,
    but only if no older non-new, non-suspended card exists for this entry
    (which would mean the entry was already known before this card was added).
    """
    cards_with_info: list[tuple[int, _CardInfo]] = []
    for cid in card_ids:
        info = card_info.get(cid)
        if info is not None:
            cards_with_info.append((cid, info))

    if not cards_with_info:
        return None

    cards_with_info.sort(key=lambda x: x[0])

    oldest_card_id = cards_with_info[0][0]
    oldest_card_info = cards_with_info[0][1]

    # Check if there's an older non-new active card - if so, the entry
    # was already "known" before this card was added
    for cid, info in cards_with_info:
        if cid == oldest_card_id:
            continue
        # If an older card is non-new and active, entry was already known
        if info.card_type != CARD_TYPE_NEW and info.is_active:
            # This shouldn't happen since we sorted by card_id,
            # but check anyway for safety
            if cid < oldest_card_id:
                return None

    # Check if the oldest card is in a disabled deck
    deck_name = _get_deck_name(oldest_card_info.deck_id, oldest_card_info.odid, deck_name_cache)
    if deck_name in disabled_deck_names:
        return None

    return oldest_card_id


def _round_up_max(max_val: int | float) -> int:
    """Round up a maximum value for y-axis scaling."""
    max_val = max(10, max_val)

    e = int(math.log10(max_val))
    if e >= 2:
        e -= 1
    m = 10**e
    return int(math.ceil(float(max_val) / m) * m)


def _round_down_min(min_val: int | float) -> int:
    """Round down a minimum value for y-axis scaling."""
    min_val = min(0, min_val)

    if not min_val:
        return 0

    return -1 * _round_up_max(-1 * min_val)


_graph_counter = 0


def _plot_first_entry_cards(
    stats_self,
    data: list[tuple[int, int]],
    bucket_size_days: int,
) -> str:
    """Generate the HTML for the first-entry cards graph."""
    global _graph_counter

    if not data:
        return ""

    cumulative_total = 0
    cumulative_data: list[tuple[int, int]] = []
    for x, y in data:
        cumulative_total += y
        cumulative_data.append((x, cumulative_total))

    title = "New Entries Added"
    subtitle = "First card added per entry (excluding disabled decks)"

    txt = stats_self._title(title, subtitle)

    graph_data = [dict(data=data, color=_COLOR_FIRST_ENTRY)]

    graph_data.append(
        dict(
            data=cumulative_data,
            color=_COLOR_FIRST_ENTRY,
            label="Cumulative",
            yaxis=2,
            bars={"show": False},
            lines=dict(show=True),
            stack=False,
        )
    )

    min_y = min(y for x, y in data) if data else 0
    max_y = max(y for x, y in data) if data else 10

    yaxes = [dict(min=_round_down_min(min_y), max=_round_up_max(max_y))]

    if cumulative_data:
        cum_min_y = min(y for x, y in cumulative_data)
        cum_max_y = max(y for x, y in cumulative_data)
        yaxes.append(
            dict(
                min=_round_down_min(cum_min_y),
                max=_round_up_max(cum_max_y),
                position="right",
            )
        )

    graph_kwargs = {
        "id": f"prioritysieve-first-entry-{_graph_counter}",
        "data": graph_data,
        "conf": dict(xaxis=dict(max=0.5, tickDecimals=0), yaxes=yaxes),
    }

    try:
        if "xunit" in inspect.signature(stats_self._graph).parameters:
            graph_kwargs["xunit"] = bucket_size_days
    except Exception:  # pylint:disable=broad-except
        pass

    txt += stats_self._graph(**graph_kwargs)
    _graph_counter += 1

    text_lines: list = []

    if data:
        avg_cards = cumulative_total / float(len(data) * bucket_size_days)
        stats_self._line(text_lines, "Average", f"{avg_cards:.1f} entries/day")
        stats_self._line(text_lines, "Total", f"{cumulative_total} entries")

    txt += stats_self._lineTbl(text_lines)

    return txt


def first_entry_cards_graph(*args, **kwargs) -> str:
    """
    Hook function for Anki's old statistics page.

    This wraps the original dueGraph function to append our custom graph.
    """
    stats_self = args[0]
    old = kwargs["_old"]

    result = old(stats_self)

    if hasattr(stats_self, "get_start_end_chunk"):
        _, num_buckets, bucket_size_days = stats_self.get_start_end_chunk()
    else:
        if stats_self.type == 0:
            num_buckets = 31
            bucket_size_days = 1
        elif stats_self.type == 1:
            num_buckets = 52
            bucket_size_days = 7
        else:
            num_buckets = None
            bucket_size_days = 31

    additional_filter = ""
    if hasattr(stats_self, "_revlogLimit"):
        additional_filter = stats_self._revlogLimit()

    data = get_first_entry_card_stats(
        day_cutoff_seconds=stats_self.col.sched.dayCutoff,
        bucket_size_days=bucket_size_days,
        num_buckets=num_buckets,
        additional_filter=additional_filter,
    )

    result += _plot_first_entry_cards(stats_self, data, bucket_size_days)

    return result


def init_stats_graph() -> None:
    """Initialize the statistics graph hook."""
    from anki.stats import CollectionStats
    from anki.hooks import wrap

    CollectionStats.dueGraph = wrap(
        CollectionStats.dueGraph, first_entry_cards_graph, "around"
    )
