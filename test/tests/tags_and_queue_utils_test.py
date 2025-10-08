from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.tags_and_queue_utils import ensure_tag_preserving_order


def _note(tags: list[str]) -> SimpleNamespace:
    return SimpleNamespace(tags=list(tags))


def test_ensure_tag_preserving_order_inserts_using_original_location() -> None:
    original_tags = ["am-ready", "ps-auto-suspend", "custom"]
    note = _note(["am-ready", "custom"])

    ensure_tag_preserving_order(note, "ps-auto-suspend", original_tags)

    assert note.tags == ["am-ready", "ps-auto-suspend", "custom"]


def test_ensure_tag_preserving_order_appends_when_missing_from_original() -> None:
    original_tags = ["am-ready", "ps-auto-suspend"]
    note = _note(["am-ready"])

    ensure_tag_preserving_order(note, "new-tag", original_tags)

    assert note.tags == ["am-ready", "new-tag"]


def test_ensure_tag_preserving_order_ignores_blank_values() -> None:
    original_tags = ["am-ready", "ps-auto-suspend"]
    note = _note(["am-ready"])

    ensure_tag_preserving_order(note, " ", original_tags)

    assert note.tags == ["am-ready"]
