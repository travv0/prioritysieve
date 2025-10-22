from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from anki.consts import QUEUE_TYPE_SUSPENDED


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
