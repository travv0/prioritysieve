from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable as TypingIterable

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from .entry import Entry
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
                card_entries = (
                    db.get_card_entry_cache()
                    if config.deduplicate_toolbar_counts
                    else None
                )
        except TypeError:
            return
        except Exception:  # pragma: no cover - safeguard
            return

        tracked_count, reviewed_count = _compute_note_counts(
            config,
            cards,
            card_entries=card_entries,
            deduplicate=config.deduplicate_toolbar_counts,
        )
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


@dataclass(slots=True)
class _AggregatedState:
    active_any: bool
    active_non_new: bool


@dataclass(slots=True)
class _WordInfo:
    note_id: int
    reading: str
    entry_text: str
    kanji_sequence: str


def _compute_note_counts(
    config: PrioritySieveConfig,
    cards: TypingIterable[StoredCard],
    card_entries: dict[int, Entry] | None = None,
    deduplicate: bool = False,
) -> tuple[int, int]:
    """Return (tracked_notes, reviewed_notes) counts."""

    exception_tags = {
        tag.strip()
        for tag in config.get_preprocess_ignore_suspended_unless_tag_list()
        if isinstance(tag, str) and tag.strip()
    }

    note_states: dict[int, _NoteState] = {}
    note_word_infos: dict[int, _WordInfo] = {}

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
        if (
            deduplicate
            and card_entries
            and card.note_id not in note_word_infos
        ):
            entry = card_entries.get(card.card_id)
            if entry is not None:
                note_word_infos[card.note_id] = _WordInfo(
                    note_id=card.note_id,
                    reading=(entry.reading or "").strip(),
                    entry_text=entry.text or "",
                    kanji_sequence=_extract_kanji_sequence(entry.text or ""),
                )

    if not deduplicate or not card_entries or not note_word_infos:
        tracked_notes = sum(1 for state in note_states.values() if state.active_any)
        reviewed_notes = sum(1 for state in note_states.values() if state.active_non_new)
        return tracked_notes, reviewed_notes

    aggregated_states = _aggregate_word_states(note_states, note_word_infos)
    tracked_notes = sum(1 for state in aggregated_states if state.active_any)
    reviewed_notes = sum(1 for state in aggregated_states if state.active_non_new)
    return tracked_notes, reviewed_notes


def _aggregate_word_states(
    note_states: dict[int, _NoteState],
    note_word_infos: dict[int, _WordInfo],
) -> list[_AggregatedState]:
    """Merge note states that represent the same lexical entry."""
    aggregated: list[_AggregatedState] = []
    reading_groups: dict[str, list[_WordInfo]] = {}

    for note_id, state in note_states.items():
        info = note_word_infos.get(note_id)
        if info is None or not info.reading:
            aggregated.append(_AggregatedState(state.active_any, state.active_non_new))
            continue
        reading_groups.setdefault(info.reading, []).append(info)

    for infos in reading_groups.values():
        aggregated.extend(_aggregate_clusters_for_reading(infos, note_states))

    return aggregated


def _aggregate_clusters_for_reading(
    word_infos: list[_WordInfo],
    note_states: dict[int, _NoteState],
) -> list[_AggregatedState]:
    """
    Group variants that share a reading.

    Kanji sequences that are subsequences of each other (differing only by
    removed kanji or okurigana) share a cluster. Pure kana spellings only join
    a cluster when that reading has a single unambiguous kanji cluster.
    """
    non_empty_sequences: dict[str, list[_WordInfo]] = {}
    empty_sequences: list[_WordInfo] = []

    for info in word_infos:
        if info.kanji_sequence:
            non_empty_sequences.setdefault(info.kanji_sequence, []).append(info)
        else:
            empty_sequences.append(info)

    cluster_note_ids: list[list[int]] = []

    if non_empty_sequences:
        seq_to_cluster = _cluster_kanji_sequences(list(non_empty_sequences.keys()))
        cluster_map: dict[int, list[int]] = {}
        for seq, infos in non_empty_sequences.items():
            cluster_id = seq_to_cluster[seq]
            bucket = cluster_map.setdefault(cluster_id, [])
            bucket.extend(info.note_id for info in infos)

        non_empty_clusters = list(cluster_map.values())
        cluster_note_ids.extend(non_empty_clusters)

        if empty_sequences:
            if len(non_empty_clusters) == 1:
                non_empty_clusters[0].extend(info.note_id for info in empty_sequences)
            else:
                cluster_note_ids.extend(
                    [info.note_id for info in group]
                    for group in _group_infos_by_text(empty_sequences)
                )
    elif empty_sequences:
        cluster_note_ids.extend(
            [info.note_id for info in group]
            for group in _group_infos_by_text(empty_sequences)
        )

    aggregated = [
        _aggregate_note_states(note_ids, note_states) for note_ids in cluster_note_ids
    ]
    return aggregated


def _aggregate_note_states(
    note_ids: list[int],
    note_states: dict[int, _NoteState],
) -> _AggregatedState:
    active_any = False
    active_non_new = False

    for note_id in note_ids:
        state = note_states.get(note_id)
        if state is None:
            continue
        if state.active_any:
            active_any = True
        if state.active_non_new:
            active_non_new = True

    return _AggregatedState(active_any=active_any, active_non_new=active_non_new)


def _group_infos_by_text(word_infos: list[_WordInfo]) -> list[list[_WordInfo]]:
    grouped: dict[str, list[_WordInfo]] = {}
    for info in word_infos:
        key = info.entry_text or ""
        grouped.setdefault(key, []).append(info)
    return list(grouped.values())


def _cluster_kanji_sequences(sequences: list[str]) -> dict[str, int]:
    """Return a mapping of kanji sequence to a cluster id."""
    if not sequences:
        return {}

    parent = list(range(len(sequences)))

    def _find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def _union(left: int, right: int) -> None:
        root_left = _find(left)
        root_right = _find(right)
        if root_left == root_right:
            return
        parent[root_right] = root_left

    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            if _has_subsequence_relation(sequences[i], sequences[j]):
                _union(i, j)

    root_to_cluster: dict[int, int] = {}
    seq_to_cluster: dict[str, int] = {}
    next_cluster = 0

    for idx, seq in enumerate(sequences):
        root = _find(idx)
        cluster_id = root_to_cluster.get(root)
        if cluster_id is None:
            cluster_id = next_cluster
            next_cluster += 1
            root_to_cluster[root] = cluster_id
        seq_to_cluster[seq] = cluster_id

    return seq_to_cluster


def _has_subsequence_relation(seq_a: str, seq_b: str) -> bool:
    """True when seq_a and seq_b only differ by removing kanji."""
    return _is_subsequence(seq_a, seq_b) or _is_subsequence(seq_b, seq_a)


def _is_subsequence(candidate: str, target: str) -> bool:
    if len(candidate) > len(target):
        return False
    if not candidate:
        return True

    index = 0
    for char in target:
        if char == candidate[index]:
            index += 1
            if index == len(candidate):
                return True
    return index == len(candidate)


def _extract_kanji_sequence(text: str) -> str:
    """Return only the kanji characters from text, preserving order."""
    return "".join(char for char in text if _is_kanji(char))


def _is_kanji(char: str) -> bool:
    return (
        "\u4e00" <= char <= "\u9fff"
        or "\u3400" <= char <= "\u4dbf"
        or char == "々"
    )
