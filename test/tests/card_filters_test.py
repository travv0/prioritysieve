from __future__ import annotations

from anki.consts import QUEUE_TYPE_SUSPENDED

from prioritysieve.card_filters import (
    counts_as_unsuspended,
    entry_keys_with_active_cards,
    find_leech_only_entry_card_ids,
    has_any_tag,
)


def test_has_any_tag_matches_normalized_values() -> None:
    assert has_any_tag(" foo bar ", {"bar"})
    assert not has_any_tag("foo", {"bar"})
    assert not has_any_tag("", {"bar"})
    assert not has_any_tag(" foo ", set())
    assert has_any_tag(None, {"bar"}) is False


def test_counts_as_unsuspended_respects_exception_tags() -> None:
    assert counts_as_unsuspended(queue=0, tags_text="", exception_tags=set())
    assert not counts_as_unsuspended(
        queue=QUEUE_TYPE_SUSPENDED,
        tags_text=" foo ",
        exception_tags=set(),
    )
    assert counts_as_unsuspended(
        queue=QUEUE_TYPE_SUSPENDED,
        tags_text=" special ",
        exception_tags={"special"},
    )


def test_entry_keys_with_active_cards_filters_using_status_lookup() -> None:
    entry_card_map = {
        ("has-active", ""): [1, 2],
        ("has-exception", ""): [3],
        ("inactive", ""): [4],
    }
    card_status_lookup = {
        1: (QUEUE_TYPE_SUSPENDED, " dormant "),
        2: (0, ""),
        3: (QUEUE_TYPE_SUSPENDED, " allowed "),
        4: (QUEUE_TYPE_SUSPENDED, " other "),
    }

    result = entry_keys_with_active_cards(
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags={"allowed"},
    )

    assert result == {("has-active", ""), ("has-exception", "")}


def test_find_leech_only_entry_card_ids_filters_mixed_entries() -> None:
    entry_card_map = {
        ("leech-only", ""): [1, 2],
        ("has-non-leech", ""): [3, 4],
        ("suspended-no-exception", ""): [5],
        ("suspended-exception", ""): [6],
    }
    card_status_lookup = {
        1: (0, " leech "),
        2: (2, " leech::extra "),
        3: (0, " leech "),
        4: (0, " other "),
        5: (QUEUE_TYPE_SUSPENDED, " leech "),
        6: (QUEUE_TYPE_SUSPENDED, " leech treat "),
    }

    result = find_leech_only_entry_card_ids(
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags={"treat"},
    )

    assert result == {
        ("leech-only", ""): [1, 2],
        ("suspended-exception", ""): [6],
    }
