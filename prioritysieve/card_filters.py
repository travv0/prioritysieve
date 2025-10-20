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


def _has_leech_tag(tags_text: str | None) -> bool:
    """Return True when the note tags include Anki's leech marker."""

    tags = _normalize_tags(tags_text)
    for tag in tags:
        lowered = tag.lower()
        if lowered == "leech" or lowered.startswith("leech::"):
            return True
    return False


def find_leech_only_entry_card_ids(
    entry_card_map: Mapping[tuple[str, str], Iterable[int]],
    card_status_lookup: Mapping[int, tuple[int, str | None]],
    exception_tags: Collection[str],
) -> dict[tuple[str, str], list[int]]:
    """Return card ids grouped by entry when only leech-tagged active cards remain."""

    leech_cards_by_entry: dict[tuple[str, str], list[int]] = {}

    for entry_key, card_ids in entry_card_map.items():
        active_leech_ids: list[int] = []
        has_active_non_leech = False

        for card_id in card_ids:
            status = card_status_lookup.get(card_id)
            if status is None:
                continue

            queue, tags_text = status
            if not counts_as_unsuspended(queue, tags_text, exception_tags):
                continue

            if _has_leech_tag(tags_text):
                active_leech_ids.append(int(card_id))
            else:
                has_active_non_leech = True
                break

        if not has_active_non_leech and active_leech_ids:
            leech_cards_by_entry[entry_key] = active_leech_ids

    return leech_cards_by_entry
