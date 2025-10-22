from __future__ import annotations

from anki.consts import QUEUE_TYPE_SUSPENDED

from prioritysieve.card_filters import (
    counts_as_unsuspended,
    entry_keys_with_active_cards,
    find_suspended_only_entry_card_ids,
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


def test_find_suspended_only_entry_card_ids_filters_mixed_entries() -> None:
    entry_card_map = {
        ("manual-only", ""): [1, 2],
        ("has-active", ""): [3, 4],
        ("auto-suspended", ""): [5],
        ("exception-tag", ""): [6],
        ("mixed-suspended-exception", ""): [7, 8],
        ("case-insensitive-auto", ""): [9],
    }
    card_status_lookup = {
        1: (QUEUE_TYPE_SUSPENDED, " manual "),
        2: (QUEUE_TYPE_SUSPENDED, " "),
        3: (0, " manual "),
        4: (QUEUE_TYPE_SUSPENDED, " kanjicards_new "),
        5: (QUEUE_TYPE_SUSPENDED, " ps-suspended-automatically "),
        6: (QUEUE_TYPE_SUSPENDED, " kanjicards_new "),
        7: (QUEUE_TYPE_SUSPENDED, " "),
        8: (QUEUE_TYPE_SUSPENDED, " kanjicards_new "),
        9: (QUEUE_TYPE_SUSPENDED, " ps-suspended-automatically "),
    }

    result = find_suspended_only_entry_card_ids(
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags={"kanjicards_new"},
        auto_suspend_tag="PS-SUSPENDED-AUTOMATICALLY",
    )

    assert result == {
        ("manual-only", ""): [1, 2],
    }
