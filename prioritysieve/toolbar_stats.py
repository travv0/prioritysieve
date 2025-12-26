from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Iterable as TypingIterable

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from aqt import mw

from .entry import Entry
from .entry_db import EntryDB, StoredCard
from .kanji_utils import (
    contains_hiragana,
    contains_kana,
    contains_katakana,
    extract_kanji_sequence,
    is_kanji_subsequence,
)
from .prioritysieve_config import (
    PrioritySieveConfig,
    PrioritySieveLanguageConfig,
)
from .reading_utils import normalize_reading
from .recalc import recalc_main

_COUNTER_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("tracked", "Tracked"),
    ("reviewed", "Reviewed"),
    ("pending", "Pending"),
)
_LAST_KNOWN_VALUES: dict[str, int] | None = None
_LAST_KNOWN_LANGUAGE_VALUES: dict[str, dict[str, int]] | None = None
_HIRAGANA_SCRIPT = "hiragana"
_KATAKANA_SCRIPT = "katakana"


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


@dataclass(slots=True)
class LanguageStats:
    """Stats for a single language."""

    language_name: str
    prefix: str
    tracked: int
    reviewed: int
    pending: int
    hide_recalc_toolbar: bool
    hide_reviewed_counter: bool
    hide_tracked_counter: bool
    hide_pending_counter: bool

    @property
    def label(self) -> str:
        """Return label in format 'PREFIX: reviewed/tracked', respecting visibility settings."""
        parts: list[str] = []
        if not self.hide_reviewed_counter:
            parts.append(str(self.reviewed))
        if not self.hide_tracked_counter:
            parts.append(str(self.tracked))

        if not parts:
            # Both counters hidden - shouldn't reach here if is_visible is checked first
            return ""

        stats_text = "/".join(parts)
        if self.prefix:
            return f"{self.prefix}: {stats_text}"
        return stats_text

    @property
    def tooltip(self) -> str:
        """Return tooltip text, respecting visibility settings."""
        parts: list[str] = []
        if not self.hide_reviewed_counter:
            parts.append(f"{self.reviewed} reviewed")
        if not self.hide_tracked_counter:
            parts.append(f"{self.tracked} tracked")

        if not parts:
            return self.language_name

        return f"{self.language_name}: {' / '.join(parts)}"

    @property
    def is_visible(self) -> bool:
        """Return True if this language's stats should be shown.

        Stats are hidden only when both reviewed and tracked counters are hidden.
        hide_recalc_toolbar only affects the Recalc button, not the stats display.
        """
        return not (self.hide_reviewed_counter and self.hide_tracked_counter)


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
        self._language_stats: list[LanguageStats] = []
        self.update_stats()

    @property
    def counters(self) -> list[ToolbarCounter]:
        return self._counters

    @property
    def language_stats(self) -> list[LanguageStats]:
        return self._language_stats

    def get_counter(self, key: str) -> ToolbarCounter | None:
        return self._counter_map.get(key)

    def update_stats(self) -> None:
        if recalc_main.recalc_in_progress():
            return

        config = PrioritySieveConfig()
        try:
            with EntryDB() as db:
                all_cards = db.get_cards()
                card_entries = db.get_card_entry_cache()
        except TypeError:
            return
        except Exception:  # pragma: no cover - safeguard
            return

        # Build note type ID to language mapping
        note_type_id_to_lang: dict[int, PrioritySieveLanguageConfig] = {}
        if mw is not None and mw.col is not None:
            for lang in config.languages:
                for flt in lang.filters:
                    note_type_id = mw.col.models.id_for_name(flt.note_type)
                    if note_type_id is not None:
                        note_type_id_to_lang[note_type_id] = lang

        # Group cards by language
        cards_by_lang: dict[str, list[StoredCard]] = {}
        for card in all_cards:
            lang = note_type_id_to_lang.get(card.note_type_id)
            if lang is not None:
                cards_by_lang.setdefault(lang.name, []).append(card)

        # Compute stats for each language
        global _LAST_KNOWN_LANGUAGE_VALUES
        _LAST_KNOWN_LANGUAGE_VALUES = {}
        language_stats_list: list[LanguageStats] = []

        for lang in config.languages:
            lang_cards = cards_by_lang.get(lang.name, [])
            # Deduplicate is per-language (depends on variant spelling logic)
            use_dedupe = lang.deduplicate_toolbar_counts
            filter_okuri = lang.auto_suspend_variant_spellings and use_dedupe

            tracked_count, reviewed_count = _compute_note_counts(
                config,
                lang_cards,
                card_entries=card_entries if use_dedupe else None,
                deduplicate=use_dedupe,
                filter_okurigana=filter_okuri,
                exception_tags=set(lang.get_preprocess_ignore_suspended_unless_tag_list()),
            )
            pending_count = max(tracked_count - reviewed_count, 0)

            _LAST_KNOWN_LANGUAGE_VALUES[lang.name] = {
                "tracked": tracked_count,
                "reviewed": reviewed_count,
                "pending": pending_count,
            }

            language_stats_list.append(
                LanguageStats(
                    language_name=lang.name,
                    prefix=lang.prefix,
                    tracked=tracked_count,
                    reviewed=reviewed_count,
                    pending=pending_count,
                    hide_recalc_toolbar=config.hide_recalc_toolbar,
                    hide_reviewed_counter=config.hide_reviewed_counter,
                    hide_tracked_counter=config.hide_tracked_counter,
                    hide_pending_counter=False,  # Pending is no longer shown
                )
            )

        self._language_stats = language_stats_list

        # Also update legacy counters for backward compatibility
        total_tracked = sum(s.tracked for s in language_stats_list)
        total_reviewed = sum(s.reviewed for s in language_stats_list)
        total_pending = max(total_tracked - total_reviewed, 0)

        global _LAST_KNOWN_VALUES
        _LAST_KNOWN_VALUES = {
            "tracked": total_tracked,
            "reviewed": total_reviewed,
            "pending": total_pending,
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
    filter_okurigana: bool = False,
    exception_tags: set[str] | None = None,
) -> tuple[int, int]:
    """Return (tracked_notes, reviewed_notes) counts."""

    if exception_tags is None:
        exception_tags = {
            tag.strip()
            for tag in config.get_preprocess_ignore_suspended_unless_tag_list()
            if isinstance(tag, str) and tag.strip()
        }

    note_states: dict[int, _NoteState] = {}
    note_word_infos: dict[int, _WordInfo] = {}
    collect_word_infos = deduplicate and card_entries is not None

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
        if collect_word_infos and card.note_id not in note_word_infos:
            entry = card_entries.get(card.card_id) if card_entries else None
            if entry is not None:
                note_word_infos[card.note_id] = _WordInfo(
                    note_id=card.note_id,
                    reading=(entry.reading or "").strip(),
                    entry_text=entry.text or "",
                    kanji_sequence=extract_kanji_sequence(entry.text or ""),
                )

    merge_kana_variants = (
        getattr(config, "merge_kana_variant_spellings", False)
        if (collect_word_infos and note_word_infos)
        else False
    )
    should_aggregate = collect_word_infos and note_word_infos
    if should_aggregate:
        aggregated_states = _aggregate_word_states(
            note_states=note_states,
            note_word_infos=note_word_infos,
            merge_supersets=deduplicate,
            merge_same_sequence=deduplicate or filter_okurigana,
            merge_kana_variants=merge_kana_variants,
        )
        tracked_notes = sum(1 for state in aggregated_states if state.active_any)
        reviewed_notes = sum(1 for state in aggregated_states if state.active_non_new)
        return tracked_notes, reviewed_notes

    tracked_notes = sum(1 for state in note_states.values() if state.active_any)
    reviewed_notes = sum(1 for state in note_states.values() if state.active_non_new)
    return tracked_notes, reviewed_notes


def _aggregate_word_states(
    note_states: dict[int, _NoteState],
    note_word_infos: dict[int, _WordInfo],
    merge_supersets: bool,
    merge_same_sequence: bool,
    merge_kana_variants: bool,
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
        aggregated.extend(
            _aggregate_clusters_for_reading(
                infos,
                note_states,
                merge_supersets=merge_supersets,
                merge_same_sequence=merge_same_sequence,
                merge_kana_variants=merge_kana_variants,
            )
        )

    return aggregated


def _aggregate_clusters_for_reading(
    word_infos: list[_WordInfo],
    note_states: dict[int, _NoteState],
    merge_supersets: bool,
    merge_same_sequence: bool,
    merge_kana_variants: bool,
) -> list[_AggregatedState]:
    """
    Group variants that share a reading.

    Kanji sequences that are subsequences of each other (differing only by
    removed kanji or okurigana) share a cluster when ``merge_supersets`` is True.
    When ``merge_same_sequence`` is True, spellings that use the exact same
    kanji (but differ in surrounding okurigana) are also collapsed. Pure kana
    spellings join a cluster when the reading has a single unambiguous
    kanji spelling or when the same word appears in both hiragana and katakana.
    """
    non_empty_sequences: dict[str, list[_WordInfo]] = {}
    sequence_has_kana: dict[str, bool] = {}
    empty_sequences: list[_WordInfo] = []

    for info in word_infos:
        if info.kanji_sequence:
            non_empty_sequences.setdefault(info.kanji_sequence, []).append(info)
            if contains_kana(info.entry_text):
                sequence_has_kana[info.kanji_sequence] = True
            else:
                sequence_has_kana.setdefault(info.kanji_sequence, False)
        else:
            empty_sequences.append(info)

    cluster_note_ids: list[list[int]] = []

    grouping_fn = _group_pure_kana_infos if merge_kana_variants else _group_infos_by_text

    if non_empty_sequences:
        sequence_list = list(non_empty_sequences.keys())
        sequence_flags = [sequence_has_kana.get(seq, False) for seq in sequence_list]
        seq_to_cluster = _cluster_kanji_sequences(
            sequence_list,
            merge_supersets=merge_supersets,
            merge_same_sequence=merge_same_sequence,
            sequence_flags=sequence_flags,
        )
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
                    for group in grouping_fn(empty_sequences)
                )
    elif empty_sequences:
        cluster_note_ids.extend(
            [info.note_id for info in group]
            for group in grouping_fn(empty_sequences)
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


def _group_pure_kana_infos(word_infos: list[_WordInfo]) -> list[list[_WordInfo]]:
    grouped_by_text = _group_infos_by_text(word_infos)
    normalized_groups: dict[str, list[list[_WordInfo]]] = {}
    script_presence: dict[str, set[str]] = {}
    order_markers: list[tuple[str, str | list[_WordInfo]]] = []

    for group in grouped_by_text:
        if not group:
            continue
        text = group[0].entry_text or ""
        stripped = text.strip()
        normalized = normalize_reading(stripped) if stripped else ""
        has_hiragana = contains_hiragana(stripped)
        has_katakana = contains_katakana(stripped)
        if normalized and (has_hiragana or has_katakana):
            if normalized not in normalized_groups:
                normalized_groups[normalized] = []
            normalized_groups[normalized].append(group)
            scripts = script_presence.setdefault(normalized, set())
            if has_hiragana:
                scripts.add(_HIRAGANA_SCRIPT)
            if has_katakana:
                scripts.add(_KATAKANA_SCRIPT)
            order_markers.append(("normalized", normalized))
        else:
            order_markers.append(("group", group))

    merged: list[list[_WordInfo]] = []
    processed_normals: set[str] = set()

    for marker, value in order_markers:
        if marker == "group":
            assert isinstance(value, list)
            merged.append(value)
            continue
        normalized = value
        if not isinstance(normalized, str):
            continue
        if normalized in processed_normals:
            continue
        processed_normals.add(normalized)
        groups = normalized_groups.get(normalized, [])
        scripts = script_presence.get(normalized, set())
        if len(groups) >= 2 and _has_both_scripts(scripts):
            combined: list[_WordInfo] = []
            for group in groups:
                combined.extend(group)
            merged.append(combined)
        else:
            merged.extend(groups)

    return merged


def _cluster_kanji_sequences(
    sequences: list[str],
    merge_supersets: bool,
    merge_same_sequence: bool,
    sequence_flags: list[bool],
) -> dict[str, int]:
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
            seq_i = sequences[i]
            seq_j = sequences[j]
            should_merge = False
            if (
                merge_same_sequence
                and seq_i
                and seq_i == seq_j
                and sequence_flags[i]
            ):
                should_merge = True
            elif merge_supersets and _has_strict_subsequence_relation(seq_i, seq_j):
                if sequence_flags[i] or sequence_flags[j]:
                    should_merge = True

            if should_merge:
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


def _has_both_scripts(scripts: Collection[str]) -> bool:
    return (_HIRAGANA_SCRIPT in scripts) and (_KATAKANA_SCRIPT in scripts)


def _has_strict_subsequence_relation(seq_a: str, seq_b: str) -> bool:
    if seq_a == seq_b:
        return False
    return is_kanji_subsequence(seq_a, seq_b) or is_kanji_subsequence(seq_b, seq_a)
