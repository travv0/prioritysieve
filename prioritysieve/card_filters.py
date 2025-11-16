from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from .kanji_utils import (
    contains_hiragana,
    contains_kana,
    contains_katakana,
    extract_kanji_sequence,
    is_kanji_subsequence,
)
from .reading_utils import normalize_reading


def _normalize_tags(tags_text: str | None) -> set[str]:
    """Return a normalized tag set from the stored Anki tag text."""

    if not isinstance(tags_text, str):
        return set()

    # Anki stores tags as a space-separated string with a trailing space.
    stripped = tags_text.strip()
    if not stripped:
        return set()

    normalized = {tag for tag in stripped.split() if tag}
    return normalized


def has_any_tag(tags_text: str | None, candidate_tags: Collection[str]) -> bool:
    """Return True when ``tags_text`` contains at least one tag from ``candidate_tags``."""

    if not candidate_tags:
        return False

    normalized_candidates = {tag for tag in candidate_tags if isinstance(tag, str) and tag}
    if not normalized_candidates:
        return False

    note_tags = _normalize_tags(tags_text)
    return any(tag in note_tags for tag in normalized_candidates)


def counts_as_unsuspended(queue: int, tags_text: str | None, exception_tags: Collection[str]) -> bool:
    """Return True when the card should be treated as unsuspended for PrioritySieve tools."""

    if queue != QUEUE_TYPE_SUSPENDED:
        return True

    return has_any_tag(tags_text, exception_tags)


def entry_keys_with_active_cards(
    entry_card_map: Mapping[tuple[str, str], Iterable[int]],
    card_status_lookup: Mapping[int, tuple[int, str | None]],
    exception_tags: Collection[str],
) -> set[tuple[str, str]]:
    """Return entry keys that have at least one card treated as unsuspended."""

    active_keys: set[tuple[str, str]] = set()
    for entry_key, card_ids in entry_card_map.items():
        for card_id in card_ids:
            status = card_status_lookup.get(card_id)
            if status is None:
                continue
            queue, tags_text = status
            if counts_as_unsuspended(queue, tags_text, exception_tags):
                active_keys.add(entry_key)
                break
    return active_keys


def find_suspended_only_entry_card_ids(
    entry_card_map: Mapping[tuple[str, str], Iterable[int]],
    card_status_lookup: Mapping[int, tuple[int, str | None]],
    exception_tags: Collection[str],
    auto_suspend_tag: str | None,
) -> dict[tuple[str, str], list[int]]:
    """Return card ids grouped by entry when every card is suspended without exception tags."""

    sanitized_exception_lowers = {
        tag.strip().lower()
        for tag in exception_tags
        if isinstance(tag, str) and tag.strip()
    }
    normalized_auto_tag = auto_suspend_tag.strip() if isinstance(auto_suspend_tag, str) else ""
    normalized_auto_tag_lower = normalized_auto_tag.lower() if normalized_auto_tag else ""

    suspended_cards_by_entry: dict[tuple[str, str], list[int]] = {}

    for entry_key, card_ids in entry_card_map.items():
        suspended_ids: list[int] = []
        disqualify_entry = False

        for card_id in card_ids:
            status = card_status_lookup.get(card_id)
            if status is None:
                continue

            queue, tags_text = status
            if queue != QUEUE_TYPE_SUSPENDED:
                disqualify_entry = True
                break

            normalized_tags = _normalize_tags(tags_text)
            normalized_tags_lower = {tag.lower() for tag in normalized_tags}

            if normalized_auto_tag_lower and normalized_auto_tag_lower in normalized_tags_lower:
                disqualify_entry = True
                break

            if sanitized_exception_lowers and sanitized_exception_lowers.intersection(normalized_tags_lower):
                disqualify_entry = True
                break

            suspended_ids.append(int(card_id))

        if not disqualify_entry and suspended_ids:
            suspended_cards_by_entry[entry_key] = suspended_ids

    return suspended_cards_by_entry


# Variant helpers -----------------------------------------------------------

_HIRAGANA_SCRIPT = "hiragana"
_KATAKANA_SCRIPT = "katakana"


def _has_both_scripts(scripts: Collection[str]) -> bool:
    return (_HIRAGANA_SCRIPT in scripts) and (_KATAKANA_SCRIPT in scripts)


def _pure_kana_variant_info(text: str) -> tuple[str, frozenset[str]] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    normalized = normalize_reading(stripped)
    if not normalized:
        return None
    scripts: set[str] = set()
    if contains_hiragana(stripped):
        scripts.add(_HIRAGANA_SCRIPT)
    if contains_katakana(stripped):
        scripts.add(_KATAKANA_SCRIPT)
    if not scripts:
        return None
    return (normalized, frozenset(scripts))


def _active_non_new_by_reading(
    entry_card_map: Mapping[tuple[str, str], Iterable[int]],
    card_status_lookup: Mapping[int, tuple[int, str | None, int]],
    exception_tags: Collection[str],
) -> dict[str, list[tuple[str, str, tuple[str, frozenset[str]] | None]]]:
    """
    Return mapping of normalized reading to tuples of (text, sequence, pure_kana_info).
    Only cards treated as unsuspended and not new are included.
    """
    active: dict[str, list[tuple[str, str, tuple[str, frozenset[str]] | None]]] = defaultdict(list)
    for (text, reading), card_ids in entry_card_map.items():
        normalized_reading = normalize_reading(reading or "")
        if not normalized_reading:
            continue
        sequence = extract_kanji_sequence(text or "")
        pure_info = _pure_kana_variant_info(text)
        for card_id in card_ids:
            status = card_status_lookup.get(card_id)
            if status is None:
                continue
            queue, tags_text, card_type = status
            if counts_as_unsuspended(queue, tags_text, exception_tags) and card_type != CARD_TYPE_NEW:
                active[normalized_reading].append((text or "", sequence, pure_info))
                break
    return active


def _would_be_variant_suspended(
    entry_key: tuple[str, str],
    card_ids: Iterable[int],
    card_status_lookup: Mapping[int, tuple[int, str | None, int]],
    active_by_reading: Mapping[str, list[tuple[str, str, tuple[str, frozenset[str]] | None]]],
    merge_kana_variants: bool,
) -> bool:
    text, reading = entry_key
    normalized_reading = normalize_reading(reading or "")
    if not normalized_reading:
        return False

    anchors = active_by_reading.get(normalized_reading)
    if not anchors:
        return False

    # Only new cards are auto-suspended as variants
    has_new_card = any(
        (card_status_lookup.get(card_id) or (None, None, None))[2] == CARD_TYPE_NEW
        for card_id in card_ids
    )
    if not has_new_card:
        return False

    sequence = extract_kanji_sequence(text or "")
    if sequence:
        for anchor_text, anchor_sequence, _ in anchors:
            if not anchor_sequence:
                continue
            if sequence != anchor_sequence and is_kanji_subsequence(sequence, anchor_sequence):
                return True
            if sequence == anchor_sequence and (contains_kana(text) or contains_kana(anchor_text)):
                return True
        return False

    if not merge_kana_variants:
        return False

    candidate_info = _pure_kana_variant_info(text)
    if candidate_info is None:
        return False

    candidate_key, candidate_scripts = candidate_info
    for _, _, anchor_info in anchors:
        if anchor_info is None:
            continue
        anchor_key, anchor_scripts = anchor_info
        if anchor_key != candidate_key:
            continue
        combined = set(candidate_scripts)
        combined.update(anchor_scripts)
        if _has_both_scripts(combined):
            return True
    return False


def filter_variant_shadowed_entries(
    suspended_cards_by_entry: Mapping[tuple[str, str], list[int]],
    entry_card_map: Mapping[tuple[str, str], Iterable[int]],
    card_status_lookup: Mapping[int, tuple[int, str | None, int]],
    exception_tags: Collection[str],
    merge_kana_variants: bool,
    auto_suspend_variants: bool,
) -> dict[tuple[str, str], list[int]]:
    """
    Drop entries whose suspended cards would be auto-suspended as variant spellings.
    """
    if not auto_suspend_variants:
        return dict(suspended_cards_by_entry)

    active_by_reading = _active_non_new_by_reading(
        entry_card_map, card_status_lookup, exception_tags
    )

    filtered: dict[tuple[str, str], list[int]] = {}
    for entry_key, card_ids in suspended_cards_by_entry.items():
        if not _would_be_variant_suspended(
            entry_key,
            card_ids,
            card_status_lookup,
            active_by_reading,
            merge_kana_variants,
        ):
            filtered[entry_key] = card_ids
    return filtered
