"""
Statistics graph for PrioritySieve.

Adds a graph to Anki's old statistics page showing newly added cards
that were the first card for their respective entry.
"""

from __future__ import annotations

import inspect
import math
import sqlite3
from collections import defaultdict

from aqt import mw

from .entry_db import EntryDB

_COLOR_FIRST_ENTRY = "#9467bd"  # purple


def get_first_entry_card_stats(
    day_cutoff_seconds: int,
    bucket_size_days: int,
    num_buckets: int | None,
    additional_filter: str,
) -> list[tuple[int, int]]:
    """
    Calculate stats for cards that were the first card added for their entry.

    Returns a list of (bucket_offset, count) tuples where bucket_offset is
    negative days from today and count is the number of first-entry cards
    added in that bucket.
    """
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    try:
        with EntryDB() as entry_db:
            card_ids_by_entry = entry_db.get_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        return []

    if not card_ids_by_entry:
        return []

    first_card_ids: set[int] = set()
    for card_ids in card_ids_by_entry.values():
        if card_ids:
            first_card_ids.add(min(card_ids))

    if not first_card_ids:
        return []

    day_cutoff_ms = day_cutoff_seconds * 1000

    bucket_counts: dict[int, int] = defaultdict(int)

    for card_id in first_card_ids:
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

    title = "First Entry Cards Added"
    subtitle = "Cards that were the first card added for their PrioritySieve entry"

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
        stats_self._line(text_lines, "Average", f"{avg_cards:.1f} cards/day")
        stats_self._line(text_lines, "Total", f"{cumulative_total} cards")

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
