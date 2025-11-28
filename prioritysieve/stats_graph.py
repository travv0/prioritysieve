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

    Returns the card_id of the oldest card in an enabled deck, but only if
    no older non-new card exists for this entry in ANY deck (including
    disabled decks). A non-new card in any deck means the entry was already
    "known" before this card was added.
    """
    cards_with_info: list[tuple[int, _CardInfo]] = []
    for cid in card_ids:
        info = card_info.get(cid)
        if info is not None:
            cards_with_info.append((cid, info))

    if not cards_with_info:
        return None

    cards_with_info.sort(key=lambda x: x[0])

    # Find the oldest non-new card across ALL decks (including disabled)
    oldest_non_new_id: int | None = None
    for cid, info in cards_with_info:
        if info.card_type != CARD_TYPE_NEW:
            oldest_non_new_id = cid
            break

    # Find the oldest card in an enabled deck
    oldest_enabled_id: int | None = None
    oldest_enabled_info: _CardInfo | None = None
    for cid, info in cards_with_info:
        deck_name = _get_deck_name(info.deck_id, info.odid, deck_name_cache)
        if deck_name not in disabled_deck_names:
            oldest_enabled_id = cid
            oldest_enabled_info = info
            break

    if oldest_enabled_id is None:
        return None

    # If there's an older non-new card (in any deck), the entry was already known
    if oldest_non_new_id is not None and oldest_non_new_id < oldest_enabled_id:
        return None

    return oldest_enabled_id


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


def _inject_new_stats_graph(webview) -> None:
    """Inject the graph into the new stats page."""
    try:
        from aqt.webview import AnkiWebViewKind
    except ImportError:
        return

    if webview.kind != AnkiWebViewKind.DECK_STATS:
        return

    assert mw is not None
    if mw.col is None:
        return

    data = get_first_entry_card_stats(
        day_cutoff_seconds=mw.col.sched.dayCutoff,
        bucket_size_days=1,
        num_buckets=31,
        additional_filter="",
    )

    if not data:
        return

    x_values = [x for x, y in data]
    y_values = [y for x, y in data]

    cumulative = []
    total = 0
    for y in y_values:
        total += y
        cumulative.append(total)

    import json

    js_code = f"""
    (function() {{
        if (document.getElementById('prioritysieve-new-entries-graph')) return;

        const xData = {json.dumps(x_values)};
        const yData = {json.dumps(y_values)};
        const cumData = {json.dumps(cumulative)};

        if (!xData.length) return;

        // Find the graphs container and clone its structure
        const existingGraph = document.querySelector('.graph');
        if (!existingGraph) return;

        const container = existingGraph.cloneNode(false);
        container.id = 'prioritysieve-new-entries-graph';

        // Create header
        const header = document.createElement('div');
        header.className = 'graph-header';
        header.innerHTML = '<div class="graph-title">New Entries Added</div><div class="graph-subtitle">First card added per entry (excluding disabled decks)</div>';
        container.appendChild(header);

        // Create SVG container
        const svgContainer = document.createElement('div');
        svgContainer.className = 'graph-svg-container';
        container.appendChild(svgContainer);

        // Create table for stats
        const totalEntries = cumData[cumData.length - 1] || 0;
        const avgPerDay = yData.length > 0 ? (totalEntries / yData.length).toFixed(1) : 0;

        const table = document.createElement('div');
        table.className = 'graph-table';
        table.innerHTML = `
            <div class="table-row"><span class="table-label">Average</span><span class="table-value">${{avgPerDay}} entries/day</span></div>
            <div class="table-row"><span class="table-label">Total</span><span class="table-value">${{totalEntries}} entries</span></div>
        `;
        container.appendChild(table);

        // Insert after the Added graph or at the end
        const graphsContainer = document.querySelector('.graphs-container');
        if (graphsContainer) {{
            graphsContainer.appendChild(container);
        }}

        // Use D3 to create the graph (D3 is available in Anki's stats page)
        const bounds = {{ width: 600, height: 200, marginLeft: 50, marginRight: 50, marginTop: 20, marginBottom: 40 }};

        const svg = d3.select(svgContainer)
            .append('svg')
            .attr('viewBox', `0 0 ${{bounds.width}} ${{bounds.height}}`)
            .attr('preserveAspectRatio', 'xMidYMid meet')
            .style('width', '100%')
            .style('height', 'auto');

        const maxY = Math.max(...yData, 1);
        const maxCum = Math.max(...cumData, 1);

        // Scales
        const x = d3.scaleBand()
            .domain(xData.map(String))
            .range([bounds.marginLeft, bounds.width - bounds.marginRight])
            .padding(0.1);

        const y = d3.scaleLinear()
            .domain([0, maxY])
            .nice()
            .range([bounds.height - bounds.marginBottom, bounds.marginTop]);

        const yCum = d3.scaleLinear()
            .domain([0, maxCum])
            .nice()
            .range([bounds.height - bounds.marginBottom, bounds.marginTop]);

        // X axis
        svg.append('g')
            .attr('transform', `translate(0,${{bounds.height - bounds.marginBottom}})`)
            .attr('class', 'x-ticks')
            .attr('opacity', 0.5)
            .call(d3.axisBottom(x).tickValues(x.domain().filter((d, i) => i % Math.ceil(xData.length / 7) === 0)));

        // Y axis (left)
        svg.append('g')
            .attr('transform', `translate(${{bounds.marginLeft}},0)`)
            .attr('class', 'y-ticks')
            .attr('opacity', 0.5)
            .call(d3.axisLeft(y).ticks(5));

        // Y axis (right) for cumulative
        svg.append('g')
            .attr('transform', `translate(${{bounds.width - bounds.marginRight}},0)`)
            .attr('class', 'y2-ticks')
            .attr('opacity', 0.5)
            .call(d3.axisRight(yCum).ticks(5));

        // Bars
        svg.append('g')
            .attr('class', 'bars')
            .selectAll('rect')
            .data(yData)
            .join('rect')
            .attr('x', (d, i) => x(String(xData[i])))
            .attr('y', d => y(d))
            .attr('width', x.bandwidth())
            .attr('height', d => y(0) - y(d))
            .attr('fill', '#9467bd')
            .attr('rx', 1);

        // Cumulative area
        const area = d3.area()
            .curve(d3.curveBasis)
            .x((d, i) => x(String(xData[i])) + x.bandwidth() / 2)
            .y0(bounds.height - bounds.marginBottom)
            .y1(d => yCum(d));

        svg.append('path')
            .datum(cumData)
            .attr('class', 'cumulative-overlay')
            .attr('fill', 'rgba(148, 103, 189, 0.3)')
            .attr('d', area);

        // Hover columns for tooltip
        const tooltip = d3.select('body').append('div')
            .attr('class', 'prioritysieve-tooltip')
            .style('position', 'absolute')
            .style('background', 'var(--canvas-elevated, #333)')
            .style('color', 'var(--fg, #fff)')
            .style('padding', '8px 12px')
            .style('border-radius', '4px')
            .style('font-size', '12px')
            .style('pointer-events', 'none')
            .style('opacity', 0)
            .style('z-index', 1000);

        svg.append('g')
            .attr('class', 'hover-columns')
            .selectAll('rect')
            .data(yData)
            .join('rect')
            .attr('x', (d, i) => x(String(xData[i])))
            .attr('y', bounds.marginTop)
            .attr('width', x.bandwidth())
            .attr('height', bounds.height - bounds.marginTop - bounds.marginBottom)
            .attr('fill', 'transparent')
            .on('mouseover', function(event, d) {{
                const i = yData.indexOf(d);
                const dayLabel = xData[i] === 0 ? 'Today' : xData[i] === -1 ? 'Yesterday' : `${{Math.abs(xData[i])}} days ago`;
                tooltip
                    .style('opacity', 1)
                    .html(`<strong>${{dayLabel}}</strong><br>Added: ${{d}}<br>Cumulative: ${{cumData[i]}}`);
                d3.select(this).attr('fill', 'rgba(148, 103, 189, 0.2)');
            }})
            .on('mousemove', function(event) {{
                tooltip
                    .style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY - 10) + 'px');
            }})
            .on('mouseout', function() {{
                tooltip.style('opacity', 0);
                d3.select(this).attr('fill', 'transparent');
            }});
    }})();
    """

    webview.eval(js_code)


def init_stats_graph() -> None:
    """Initialize the statistics graph hooks."""
    from anki.stats import CollectionStats
    from anki.hooks import wrap
    from aqt import gui_hooks

    CollectionStats.dueGraph = wrap(
        CollectionStats.dueGraph, first_entry_cards_graph, "around"
    )

    gui_hooks.webview_did_inject_style_into_page.append(_inject_new_stats_graph)
