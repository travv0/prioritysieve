"""
Statistics graph for PrioritySieve.

Adds a graph to Anki's old statistics page showing newly added entries.
An entry is counted when the first card for it is added, unless a superset
variant entry already has an older card that would cause this entry to be
auto-suspended (either a non-new superset, or a new superset due before).
"""

from __future__ import annotations

import inspect
import math
import sqlite3
from collections import defaultdict

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from aqt import mw

from .entry_db import EntryDB
from .kanji_utils import (
    contains_hiragana,
    contains_katakana,
    extract_kanji_sequence,
    is_kanji_subsequence,
)
from .prioritysieve_config import PrioritySieveConfig
from .reading_utils import canonicalize_long_vowels, normalize_reading

_COLOR_FIRST_ENTRY = "#9467bd"  # purple

# type alias for pure kana variant info: (normalized_text, scripts)
_KanaInfo = tuple[str, frozenset[str]]


def _get_kana_info(text: str) -> _KanaInfo | None:
    """Get kana variant info for pure kana text."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    normalized = normalize_reading(stripped)
    if not normalized:
        return None
    scripts: set[str] = set()
    if contains_hiragana(stripped):
        scripts.add("hiragana")
    if contains_katakana(stripped):
        scripts.add("katakana")
    if not scripts:
        return None
    return (normalized, frozenset(scripts))


def _is_kana_variant(info1: _KanaInfo | None, info2: _KanaInfo | None) -> bool:
    """Check if two entries are kana variants (same normalized text, different scripts)."""
    if info1 is None or info2 is None:
        return False
    normalized1, scripts1 = info1
    normalized2, scripts2 = info2
    if normalized1 != normalized2:
        return False
    combined = scripts1 | scripts2
    return "hiragana" in combined and "katakana" in combined


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
    2. It's the oldest countable card for its entry (by card_id/creation time)
    3. No older countable non-new card exists for that entry
    4. No superset variant would cause this entry to be auto-suspended:
       - No superset has an older non-new card, AND
       - No superset has an older new card with an earlier due date

    A card is countable if it's not manually suspended.

    Returns a list of (bucket_offset, count) tuples.
    """
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    config = PrioritySieveConfig()
    disabled_deck_names = set(config.disabled_decks)
    exception_tags = set(config.get_preprocess_ignore_suspended_unless_tag_list())
    auto_suspend_tag = config.tag_suspended_automatically
    auto_suspend_variants = getattr(config, "auto_suspend_variant_spellings", False)
    merge_kana_variants = getattr(config, "merge_kana_variant_spellings", False)

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

    card_info = _load_card_info(all_card_ids, exception_tags, auto_suspend_tag)

    deck_name_cache: dict[int, str] = {}

    # first pass: find oldest card for each entry and collect variant info
    first_cards_by_entry: dict[tuple[str, str], int] = {}
    # entries with non-new cards (first card is non-new): reading -> [(kanji_seq, kana_info, card_id)]
    # kana_info is (normalized_text, scripts) or None
    entries_with_non_new: dict[str, list[tuple[str, _KanaInfo | None, int]]] = (
        defaultdict(list)
    )
    # entries with new cards (first card is new): reading -> [(kanji_seq, kana_info, card_id, due)]
    entries_with_new: dict[str, list[tuple[str, _KanaInfo | None, int, int]]] = (
        defaultdict(list)
    )
    # entries that have ANY non-new card (for variant detection even if first card is new)
    # reading -> [(kanji_seq, kana_info, oldest_non_new_card_id)]
    entries_with_any_non_new: dict[str, list[tuple[str, _KanaInfo | None, int]]] = (
        defaultdict(list)
    )
    # entries with ANY new card, using minimum due (for variant detection when first card is auto-suspended)
    # reading -> [(kanji_seq, kana_info, oldest_new_card_id, min_due)]
    entries_with_any_new: dict[str, list[tuple[str, _KanaInfo | None, int, int]]] = (
        defaultdict(list)
    )

    for entry_key, card_ids in card_ids_by_entry.items():
        text, reading = entry_key
        first_card_id = _find_first_entry_card(
            card_ids=card_ids,
            card_info=card_info,
            disabled_deck_names=disabled_deck_names,
            deck_name_cache=deck_name_cache,
        )
        if first_card_id is not None:
            first_cards_by_entry[entry_key] = first_card_id

            # track entries by canonicalized reading for variant detection
            info = card_info.get(first_card_id)
            if info is not None:
                canon_reading = canonicalize_long_vowels(reading)
                kanji_seq = extract_kanji_sequence(text)
                kana_info = _get_kana_info(text) if merge_kana_variants else None
                if info.card_type != CARD_TYPE_NEW:
                    entries_with_non_new[canon_reading].append(
                        (kanji_seq, kana_info, first_card_id)
                    )
                else:
                    entries_with_new[canon_reading].append(
                        (kanji_seq, kana_info, first_card_id, info.due)
                    )

        # also track oldest non-new card for this entry (regardless of first card type)
        # this is needed for variant detection when the first card is new but entry has older non-new cards
        canon_reading = canonicalize_long_vowels(reading)
        kanji_seq = extract_kanji_sequence(text)
        kana_info = _get_kana_info(text) if merge_kana_variants else None
        oldest_non_new_id = _find_oldest_non_new_card(card_ids, card_info)
        if oldest_non_new_id is not None:
            entries_with_any_non_new[canon_reading].append(
                (kanji_seq, kana_info, oldest_non_new_id)
            )

        # also track new cards with minimum due (for when first card is auto-suspended with max due)
        new_card_info = _find_new_card_info(card_ids, card_info)
        if new_card_info is not None:
            oldest_new_id, min_due = new_card_info
            entries_with_any_new[canon_reading].append(
                (kanji_seq, kana_info, oldest_new_id, min_due)
            )

    # second pass: filter out entries dominated by variant cards
    # an entry is dominated if:
    # 1. a kanji superset has an older non-new card (already reviewed), OR
    # 2. a kanji superset has an older new card with an earlier due date, OR
    # 3. a kana variant (hiragana/katakana) has an older non-new card, OR
    # 4. a kana variant has an older new card with an earlier due date
    first_entry_card_ids: set[int] = set()

    for entry_key, first_card_id in first_cards_by_entry.items():
        text, reading = entry_key
        canon_reading = canonicalize_long_vowels(reading)
        kanji_seq = extract_kanji_sequence(text)
        kana_info = _get_kana_info(text) if merge_kana_variants else None
        info = card_info.get(first_card_id)
        is_new = info is not None and info.card_type == CARD_TYPE_NEW
        card_due = info.due if info is not None else 0

        # get min due for this entry (in case first card is auto-suspended with max due)
        min_due_for_entry = card_due
        for other_seq, other_kana, other_card_id, other_due in entries_with_any_new.get(
            canon_reading, []
        ):
            if other_seq == kanji_seq and other_kana == kana_info:
                min_due_for_entry = other_due
                break

        dominated = False

        # check non-new cards (already reviewed -> would dominate)
        for other_seq, other_kana, other_card_id in entries_with_non_new.get(
            canon_reading, []
        ):
            if other_card_id >= first_card_id:
                continue  # not older
            if other_seq == kanji_seq and other_kana == kana_info:
                continue  # same entry, not a variant
            # check kanji superset relation (only if auto_suspend_variants enabled)
            if auto_suspend_variants and kanji_seq and other_seq and is_kanji_subsequence(kanji_seq, other_seq):
                dominated = True
                break
            # pure kana entry dominated by any entry with kanji (only if auto_suspend_variants enabled)
            if auto_suspend_variants and not kanji_seq and other_seq:
                dominated = True
                break
            # check kana variant relation (for pure kana entries)
            if not kanji_seq and not other_seq and _is_kana_variant(kana_info, other_kana):
                dominated = True
                break

        # also check entries that have ANY non-new card (even if first card is new)
        # this catches cases like ぱらぱら where first card is new but there's an older non-new card
        if not dominated:
            for other_seq, other_kana, other_card_id in entries_with_any_non_new.get(
                canon_reading, []
            ):
                if other_card_id >= first_card_id:
                    continue  # not older
                if other_seq == kanji_seq and other_kana == kana_info:
                    continue  # same entry, not a variant
                # check kanji superset relation (only if auto_suspend_variants enabled)
                if auto_suspend_variants and kanji_seq and other_seq and is_kanji_subsequence(kanji_seq, other_seq):
                    dominated = True
                    break
                # pure kana entry dominated by any entry with kanji (only if auto_suspend_variants enabled)
                if auto_suspend_variants and not kanji_seq and other_seq:
                    dominated = True
                    break
                # check kana variant relation (for pure kana entries)
                if not kanji_seq and not other_seq and _is_kana_variant(kana_info, other_kana):
                    dominated = True
                    break

        # check new cards (due before this card -> would be reviewed first)
        if not dominated and is_new:
            for other_seq, other_kana, other_card_id, other_due in entries_with_new.get(
                canon_reading, []
            ):
                if other_card_id >= first_card_id:
                    continue  # not older
                if other_seq == kanji_seq and other_kana == kana_info:
                    continue  # same entry, not a variant
                if other_due >= min_due_for_entry:
                    continue  # other is due after or same time
                # check kanji superset relation (only if auto_suspend_variants enabled)
                if auto_suspend_variants and kanji_seq and other_seq and is_kanji_subsequence(kanji_seq, other_seq):
                    dominated = True
                    break
                # pure kana entry dominated by any entry with kanji (only if auto_suspend_variants enabled)
                if auto_suspend_variants and not kanji_seq and other_seq:
                    dominated = True
                    break
                # check kana variant relation (for pure kana entries)
                if (
                    not kanji_seq
                    and not other_seq
                    and _is_kana_variant(kana_info, other_kana)
                ):
                    dominated = True
                    break

        # also check entries that have ANY new card with min due (for auto-suspended first cards)
        if not dominated and is_new:
            for other_seq, other_kana, other_card_id, other_min_due in entries_with_any_new.get(
                canon_reading, []
            ):
                if other_card_id >= first_card_id:
                    continue  # not older
                if other_seq == kanji_seq and other_kana == kana_info:
                    continue  # same entry, not a variant
                if other_min_due >= min_due_for_entry:
                    continue  # other is due after or same time
                # check kanji superset relation (only if auto_suspend_variants enabled)
                if auto_suspend_variants and kanji_seq and other_seq and is_kanji_subsequence(kanji_seq, other_seq):
                    dominated = True
                    break
                # pure kana entry dominated by any entry with kanji (only if auto_suspend_variants enabled)
                if auto_suspend_variants and not kanji_seq and other_seq:
                    dominated = True
                    break
                # check kana variant relation (for pure kana entries)
                if (
                    not kanji_seq
                    and not other_seq
                    and _is_kana_variant(kana_info, other_kana)
                ):
                    dominated = True
                    break

        if not dominated:
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
    __slots__ = ("card_type", "queue", "deck_id", "odid", "tags", "due", "is_countable")

    def __init__(
        self,
        card_type: int,
        queue: int,
        deck_id: int,
        odid: int,
        tags: str,
        due: int,
        exception_tags: set[str],
        auto_suspend_tag: str,
    ) -> None:
        self.card_type = card_type
        self.queue = queue
        self.deck_id = deck_id
        self.odid = odid
        self.tags = tags
        self.due = due

        is_suspended = queue == QUEUE_TYPE_SUSPENDED
        has_exception = _has_any_tag(tags, exception_tags) if exception_tags else False
        has_auto_suspend = auto_suspend_tag and _has_any_tag(tags, {auto_suspend_tag})
        # a card is countable if it's not manually suspended
        # (auto-suspended cards are countable because we filter by superset variants separately)
        self.is_countable = not is_suspended or has_exception or has_auto_suspend


def _has_any_tag(tags_text: str, exception_tags: set[str]) -> bool:
    if not tags_text or not exception_tags:
        return False
    card_tags = {tag.strip().lower() for tag in tags_text.split() if tag.strip()}
    normalized_exceptions = {tag.lower() for tag in exception_tags}
    return bool(card_tags & normalized_exceptions)


def _load_card_info(
    card_ids: set[int],
    exception_tags: set[str],
    auto_suspend_tag: str,
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
                   COALESCE(cards.odid, 0), notes.tags, cards.due
            FROM cards
            JOIN notes ON notes.id = cards.nid
            WHERE cards.id IN ({placeholders})
            """,
            *chunk,
        )
        for card_id, card_type, queue, did, odid, tags, due in rows:
            result[int(card_id)] = _CardInfo(
                card_type=int(card_type),
                queue=int(queue),
                deck_id=int(did),
                odid=int(odid),
                tags=tags if isinstance(tags, str) else "",
                due=int(due) if due is not None else 0,
                exception_tags=exception_tags,
                auto_suspend_tag=auto_suspend_tag,
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


def _find_oldest_non_new_card(
    card_ids: list[int],
    card_info: dict[int, _CardInfo],
) -> int | None:
    """Find the oldest countable non-new card for an entry, if any."""
    cards_with_info: list[tuple[int, _CardInfo]] = []
    for cid in card_ids:
        info = card_info.get(cid)
        if info is not None:
            cards_with_info.append((cid, info))

    if not cards_with_info:
        return None

    cards_with_info.sort(key=lambda x: x[0])

    for cid, info in cards_with_info:
        if info.card_type != CARD_TYPE_NEW and info.is_countable:
            return cid

    return None


def _find_new_card_info(
    card_ids: list[int],
    card_info: dict[int, _CardInfo],
) -> tuple[int, int] | None:
    """Find the oldest new card and minimum due among all new cards for an entry.

    Returns (oldest_new_card_id, min_due) or None if no new cards exist.
    """
    cards_with_info: list[tuple[int, _CardInfo]] = []
    for cid in card_ids:
        info = card_info.get(cid)
        if info is not None:
            cards_with_info.append((cid, info))

    if not cards_with_info:
        return None

    cards_with_info.sort(key=lambda x: x[0])

    oldest_new_id: int | None = None
    min_due: int | None = None

    for cid, info in cards_with_info:
        if info.card_type == CARD_TYPE_NEW and info.is_countable:
            if oldest_new_id is None:
                oldest_new_id = cid
            if min_due is None or info.due < min_due:
                min_due = info.due

    if oldest_new_id is None or min_due is None:
        return None

    return (oldest_new_id, min_due)


def _find_first_entry_card(
    card_ids: list[int],
    card_info: dict[int, _CardInfo],
    disabled_deck_names: set[str],
    deck_name_cache: dict[int, str],
) -> int | None:
    """
    Find the card that introduced this entry, if any.

    Returns the card_id of the oldest countable card in an enabled deck, but only
    if no older countable non-new card exists for this entry in ANY deck
    (including disabled decks).

    A card is countable if it's not manually suspended (i.e., not suspended,
    has an exception tag, or was auto-suspended).
    """
    cards_with_info: list[tuple[int, _CardInfo]] = []
    for cid in card_ids:
        info = card_info.get(cid)
        if info is not None:
            cards_with_info.append((cid, info))

    if not cards_with_info:
        return None

    cards_with_info.sort(key=lambda x: x[0])

    # Find the oldest countable non-new card across ALL decks (including disabled)
    oldest_countable_non_new_id: int | None = None
    for cid, info in cards_with_info:
        if info.card_type != CARD_TYPE_NEW and info.is_countable:
            oldest_countable_non_new_id = cid
            break

    # Find the oldest countable card in an enabled deck
    oldest_enabled_id: int | None = None
    for cid, info in cards_with_info:
        deck_name = _get_deck_name(info.deck_id, info.odid, deck_name_cache)
        if deck_name not in disabled_deck_names and info.is_countable:
            oldest_enabled_id = cid
            break

    if oldest_enabled_id is None:
        return None

    # If there's an older countable non-new card (in any deck), the entry was already known
    if oldest_countable_non_new_id is not None and oldest_countable_non_new_id < oldest_enabled_id:
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

    day_cutoff = mw.col.sched.dayCutoff

    # Generate data for all 4 time ranges:
    # 0: 1 month (31 days, bucket=1)
    # 1: 3 months (93 days, bucket=1)
    # 2: 1 year (365 days, bucket=1)
    # 3: All time (no limit, bucket=1)
    ranges = [
        (31, 1),    # 1 month
        (93, 1),    # 3 months
        (365, 1),   # 1 year
        (None, 1),  # all time
    ]

    all_data = []
    for num_buckets, bucket_size in ranges:
        data = get_first_entry_card_stats(
            day_cutoff_seconds=day_cutoff,
            bucket_size_days=bucket_size,
            num_buckets=num_buckets,
            additional_filter="",
        )
        x_values = [x for x, y in data]
        y_values = [y for x, y in data]
        cumulative = []
        total = 0
        for y in y_values:
            total += y
            cumulative.append(total)
        all_data.append({
            "x": x_values,
            "y": y_values,
            "cum": cumulative,
        })

    # Skip if no data for any range
    if not any(d["x"] for d in all_data):
        return

    import json

    js_code = f"""
    (function() {{
        function injectGraph() {{
            if (document.getElementById('prioritysieve-new-entries-graph')) {{
                return true;
            }}

            const allData = {json.dumps(all_data)};

            if (!allData.some(d => d.x.length > 0)) {{
                return true;
            }}

            let gridContainer = document.querySelector('.graphs-container');
            if (!gridContainer) {{
                return false;
            }}

            let currentRange = 0;
            const svgNS = 'http://www.w3.org/2000/svg';
            const width = 600;
            const height = 250;
            const margin = {{ left: 70, right: 70, top: 20, bottom: 25 }};
            const innerWidth = width - margin.left - margin.right;
            const innerHeight = height - margin.top - margin.bottom;

            function niceNum(range, round) {{
                if (range <= 0) return 1;
                const exponent = Math.floor(Math.log10(range));
                const fraction = range / Math.pow(10, exponent);
                let niceFraction;
                if (round) {{
                    if (fraction < 1.5) niceFraction = 1;
                    else if (fraction < 3) niceFraction = 2;
                    else if (fraction < 7) niceFraction = 5;
                    else niceFraction = 10;
                }} else {{
                    if (fraction <= 1) niceFraction = 1;
                    else if (fraction <= 2) niceFraction = 2;
                    else if (fraction <= 5) niceFraction = 5;
                    else niceFraction = 10;
                }}
                return niceFraction * Math.pow(10, exponent);
            }}

            function getNiceTicks(minVal, maxVal, maxTicks) {{
                if (maxVal <= minVal) maxVal = minVal + 1;
                const range = niceNum(maxVal - minVal, false);
                const tickSpacing = niceNum(range / (maxTicks - 1), true);
                const niceMin = Math.floor(minVal / tickSpacing) * tickSpacing;
                const niceMax = Math.ceil(maxVal / tickSpacing) * tickSpacing;
                const ticks = [];
                for (let t = niceMin; t <= niceMax + tickSpacing * 0.5; t += tickSpacing) {{
                    ticks.push(Math.round(t));
                }}
                return {{ ticks, min: niceMin, max: niceMax }};
            }}

            // Create container
            const container = document.createElement('div');
            container.id = 'prioritysieve-new-entries-graph';
            container.className = 'container d-flex flex-column svelte-dkvlwr light';
            container.style.cssText = '--gutter-block: 2px; --container-margin: 0;';

            const titleWrapper = document.createElement('div');
            titleWrapper.className = 'position-relative';
            const titleEl = document.createElement('h1');
            titleEl.className = 'svelte-dkvlwr';
            titleEl.textContent = '追加（エントリー）';
            titleWrapper.appendChild(titleEl);
            container.appendChild(titleWrapper);

            const graphWrapper = document.createElement('div');
            graphWrapper.className = 'graph d-flex flex-grow-1 flex-column justify-content-center svelte-3fyu6y';

            const subtitle = document.createElement('div');
            subtitle.className = 'subtitle svelte-3fyu6y';
            subtitle.textContent = 'エントリーごとの最初のカード追加数';
            graphWrapper.appendChild(subtitle);

            // Range selector
            const rangeSelector = document.createElement('div');
            rangeSelector.className = 'svelte-1a4bkik';
            const labels = ['1か月', '3か月', '1年', '全期間'];
            labels.forEach((label, idx) => {{
                const lbl = document.createElement('label');
                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'prioritysieve-range';
                radio.value = idx;
                if (idx === 0) radio.checked = true;
                radio.addEventListener('change', () => {{
                    currentRange = idx;
                    renderGraph();
                }});
                lbl.appendChild(radio);
                lbl.appendChild(document.createTextNode(' ' + label));
                rangeSelector.appendChild(lbl);
                rangeSelector.appendChild(document.createTextNode(' '));
            }});
            graphWrapper.appendChild(rangeSelector);

            // SVG container
            const svgContainer = document.createElement('div');
            svgContainer.id = 'prioritysieve-svg-container';
            graphWrapper.appendChild(svgContainer);

            // Stats table
            const tableWrapper = document.createElement('div');
            tableWrapper.className = 'svelte-1blhjzb';
            tableWrapper.id = 'prioritysieve-stats-table';
            graphWrapper.appendChild(tableWrapper);

            container.appendChild(graphWrapper);

            function renderGraph() {{
                const data = allData[currentRange];
                const xData = data.x;
                const yData = data.y;
                const cumData = data.cum;

                if (!xData.length) {{
                    svgContainer.innerHTML = '<div style="text-align:center;padding:40px;opacity:0.5;">データなし</div>';
                    tableWrapper.innerHTML = '';
                    return;
                }}

                const totalEntries = cumData[cumData.length - 1] || 0;
                const avgPerDay = yData.length > 0 ? (totalEntries / yData.length).toFixed(0) : 0;

                const maxY = Math.max(...yData, 1);
                const maxCum = Math.max(...cumData, 1);
                const yTickInfo = getNiceTicks(0, maxY, 6);
                const cumTickInfo = getNiceTicks(0, maxCum, 5);
                const yMax = yTickInfo.max || maxY;
                const cumMax = cumTickInfo.max || maxCum;

                // Dynamic bar width based on data length
                const barWidth = Math.min(13.375, (innerWidth - xData.length) / xData.length);
                const barGap = 1;
                const totalBarWidth = barWidth + barGap;

                const colorScale = (i) => {{
                    const t = i / Math.max(1, xData.length - 1);
                    const r = Math.round(177 - t * (177 - 47));
                    const g = Math.round(210 - t * (210 - 126));
                    const b = Math.round(232 - t * (232 - 188));
                    return `rgb(${{r}}, ${{g}}, ${{b}})`;
                }};

                const svg = document.createElementNS(svgNS, 'svg');
                svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);

                // Bars
                const barsGroup = document.createElementNS(svgNS, 'g');
                barsGroup.setAttribute('class', 'bars');
                for (let i = 0; i < yData.length; i++) {{
                    const barHeight = (yData[i] / yMax) * innerHeight;
                    const x = margin.left + i * totalBarWidth;
                    const y = margin.top + innerHeight - barHeight;
                    const rect = document.createElementNS(svgNS, 'rect');
                    rect.setAttribute('rx', '1');
                    rect.setAttribute('x', x);
                    rect.setAttribute('y', y);
                    rect.setAttribute('height', Math.max(0, barHeight));
                    rect.setAttribute('width', barWidth);
                    rect.setAttribute('fill', colorScale(i));
                    barsGroup.appendChild(rect);
                }}
                svg.appendChild(barsGroup);

                // Hover columns
                const hoverGroup = document.createElementNS(svgNS, 'g');
                hoverGroup.setAttribute('class', 'hover-columns svelte-psugqn');
                for (let i = 0; i < yData.length; i++) {{
                    const x = margin.left + i * totalBarWidth;
                    const hoverRect = document.createElementNS(svgNS, 'rect');
                    hoverRect.setAttribute('x', x);
                    hoverRect.setAttribute('y', margin.top);
                    hoverRect.setAttribute('width', barWidth);
                    hoverRect.setAttribute('height', innerHeight);
                    hoverRect.setAttribute('class', 'graph-element-clickable');
                    const dayVal = xData[i];
                    const count = yData[i];
                    const cumVal = cumData[i];
                    hoverRect.addEventListener('mouseenter', function(e) {{
                        let tooltip = document.querySelector('.prioritysieve-tooltip');
                        if (!tooltip) {{
                            tooltip = document.createElement('div');
                            tooltip.className = 'prioritysieve-tooltip graph-tooltip';
                            document.body.appendChild(tooltip);
                        }}
                        tooltip.innerHTML = `<div>${{dayVal}}日</div><div>追加: ${{count}}件</div><div>累計: ${{cumVal.toLocaleString()}}件</div>`;
                        tooltip.style.opacity = '1';
                    }});
                    hoverRect.addEventListener('mousemove', function(e) {{
                        const tooltip = document.querySelector('.prioritysieve-tooltip');
                        if (tooltip) {{
                            tooltip.style.left = (e.pageX + 10) + 'px';
                            tooltip.style.top = (e.pageY - 10) + 'px';
                        }}
                    }});
                    hoverRect.addEventListener('mouseleave', function() {{
                        const tooltip = document.querySelector('.prioritysieve-tooltip');
                        if (tooltip) tooltip.style.opacity = '0';
                    }});
                    hoverGroup.appendChild(hoverRect);
                }}
                svg.appendChild(hoverGroup);

                // Cumulative path
                if (cumData.length > 0) {{
                    const cumPath = document.createElementNS(svgNS, 'path');
                    cumPath.setAttribute('class', 'cumulative-overlay svelte-5v0l18');
                    let pathD = `M${{margin.left}},${{margin.top + innerHeight}}`;
                    for (let i = 0; i < cumData.length; i++) {{
                        const x = margin.left + i * totalBarWidth + barWidth / 2;
                        const y = margin.top + innerHeight - (cumData[i] / cumMax) * innerHeight;
                        pathD += `L${{x}},${{y}}`;
                    }}
                    pathD += `L${{margin.left + (cumData.length - 1) * totalBarWidth + barWidth / 2}},${{margin.top + innerHeight}}Z`;
                    cumPath.setAttribute('d', pathD);
                    svg.appendChild(cumPath);
                }}

                // X-axis
                const xTicksGroup = document.createElementNS(svgNS, 'g');
                xTicksGroup.setAttribute('class', 'x-ticks svelte-1mgreab');
                xTicksGroup.setAttribute('transform', `translate(0, ${{margin.top + innerHeight}})`);
                xTicksGroup.setAttribute('fill', 'none');
                xTicksGroup.setAttribute('font-size', '10');
                xTicksGroup.setAttribute('font-family', 'sans-serif');
                xTicksGroup.setAttribute('text-anchor', 'middle');
                const xDomain = document.createElementNS(svgNS, 'path');
                xDomain.setAttribute('class', 'domain');
                xDomain.setAttribute('stroke', 'currentColor');
                xDomain.setAttribute('d', `M${{margin.left}},0H${{width - margin.right}}`);
                xTicksGroup.appendChild(xDomain);
                const xTickInterval = xData.length <= 31 ? 5 : (xData.length <= 93 ? 10 : (xData.length <= 365 ? 30 : 100));
                for (let i = 0; i < xData.length; i++) {{
                    if (xData[i] % xTickInterval === 0) {{
                        const x = margin.left + i * totalBarWidth + barWidth / 2;
                        const tickG = document.createElementNS(svgNS, 'g');
                        tickG.setAttribute('class', 'tick');
                        tickG.setAttribute('transform', `translate(${{x}},0)`);
                        const line = document.createElementNS(svgNS, 'line');
                        line.setAttribute('stroke', 'currentColor');
                        line.setAttribute('y2', '6');
                        tickG.appendChild(line);
                        const text = document.createElementNS(svgNS, 'text');
                        text.setAttribute('fill', 'currentColor');
                        text.setAttribute('y', '9');
                        text.setAttribute('dy', '0.71em');
                        text.textContent = xData[i];
                        tickG.appendChild(text);
                        xTicksGroup.appendChild(tickG);
                    }}
                }}
                svg.appendChild(xTicksGroup);

                // Y-axis (left)
                const yTicksGroup = document.createElementNS(svgNS, 'g');
                yTicksGroup.setAttribute('class', 'y-ticks svelte-1mgreab');
                yTicksGroup.setAttribute('transform', `translate(${{margin.left}}, 0)`);
                yTicksGroup.setAttribute('fill', 'none');
                yTicksGroup.setAttribute('font-size', '10');
                yTicksGroup.setAttribute('font-family', 'sans-serif');
                yTicksGroup.setAttribute('text-anchor', 'end');
                const yDomain = document.createElementNS(svgNS, 'path');
                yDomain.setAttribute('class', 'domain');
                yDomain.setAttribute('stroke', 'currentColor');
                yDomain.setAttribute('d', `M0,${{margin.top + innerHeight}}V${{margin.top}}`);
                yTicksGroup.appendChild(yDomain);
                yTickInfo.ticks.forEach(val => {{
                    const y = margin.top + innerHeight - (val / yMax) * innerHeight;
                    const tickG = document.createElementNS(svgNS, 'g');
                    tickG.setAttribute('class', 'tick');
                    tickG.setAttribute('transform', `translate(0,${{y}})`);
                    const line = document.createElementNS(svgNS, 'line');
                    line.setAttribute('stroke', 'currentColor');
                    line.setAttribute('x2', '-6');
                    tickG.appendChild(line);
                    const text = document.createElementNS(svgNS, 'text');
                    text.setAttribute('fill', 'currentColor');
                    text.setAttribute('x', '-9');
                    text.setAttribute('dy', '0.32em');
                    text.textContent = val.toLocaleString();
                    tickG.appendChild(text);
                    yTicksGroup.appendChild(tickG);
                }});
                svg.appendChild(yTicksGroup);

                // Y2-axis (right)
                const y2TicksGroup = document.createElementNS(svgNS, 'g');
                y2TicksGroup.setAttribute('class', 'y2-ticks svelte-1mgreab');
                y2TicksGroup.setAttribute('transform', `translate(${{width - margin.right}}, 0)`);
                y2TicksGroup.setAttribute('fill', 'none');
                y2TicksGroup.setAttribute('font-size', '10');
                y2TicksGroup.setAttribute('font-family', 'sans-serif');
                y2TicksGroup.setAttribute('text-anchor', 'start');
                const y2Domain = document.createElementNS(svgNS, 'path');
                y2Domain.setAttribute('class', 'domain');
                y2Domain.setAttribute('stroke', 'currentColor');
                y2Domain.setAttribute('d', `M0,${{margin.top + innerHeight}}V${{margin.top}}`);
                y2TicksGroup.appendChild(y2Domain);
                cumTickInfo.ticks.forEach(val => {{
                    const y = margin.top + innerHeight - (val / cumMax) * innerHeight;
                    const tickG = document.createElementNS(svgNS, 'g');
                    tickG.setAttribute('class', 'tick');
                    tickG.setAttribute('transform', `translate(0,${{y}})`);
                    const line = document.createElementNS(svgNS, 'line');
                    line.setAttribute('stroke', 'currentColor');
                    line.setAttribute('x2', '6');
                    tickG.appendChild(line);
                    const text = document.createElementNS(svgNS, 'text');
                    text.setAttribute('fill', 'currentColor');
                    text.setAttribute('x', '9');
                    text.setAttribute('dy', '0.32em');
                    text.textContent = val.toLocaleString();
                    tickG.appendChild(text);
                    y2TicksGroup.appendChild(tickG);
                }});
                svg.appendChild(y2TicksGroup);

                svgContainer.innerHTML = '';
                svgContainer.appendChild(svg);

                tableWrapper.innerHTML = `
                    <table dir="ltr"><tbody>
                        <tr><td class="align-end svelte-1blhjzb">合計:</td><td class="align-start svelte-1blhjzb">${{totalEntries.toLocaleString()}}件</td></tr>
                        <tr><td class="align-end svelte-1blhjzb">平均:</td><td class="align-start svelte-1blhjzb">${{avgPerDay}}件 / 日</td></tr>
                    </tbody></table>
                `;
            }}

            // Styles
            if (!document.getElementById('prioritysieve-graph-styles')) {{
                const style = document.createElement('style');
                style.id = 'prioritysieve-graph-styles';
                style.textContent = `
                    .prioritysieve-tooltip {{
                        position: absolute;
                        background: var(--canvas-elevated, #333);
                        color: var(--fg, #fff);
                        padding: 8px 12px;
                        border-radius: 4px;
                        font-size: 12px;
                        pointer-events: none;
                        z-index: 10000;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        opacity: 0;
                        transition: opacity 0.15s;
                    }}
                    .graph-element-clickable {{
                        fill: transparent;
                        cursor: pointer;
                    }}
                    .graph-element-clickable:hover {{
                        fill: rgba(128,128,128,0.1);
                    }}
                `;
                document.head.appendChild(style);
            }}

            gridContainer.appendChild(container);
            renderGraph();
            return true;
        }}

        if (!injectGraph()) {{
            let retries = 0;
            const maxRetries = 10;
            const retryInterval = setInterval(function() {{
                retries++;
                if (injectGraph() || retries >= maxRetries) {{
                    clearInterval(retryInterval);
                }}
            }}, 200);
        }}
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
