from __future__ import annotations

from types import SimpleNamespace

from anki.consts import QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve.recalc.recalc_main import _should_skip_card


def _note(tags: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(tags=list(tags or []))


def _card(queue: int) -> SimpleNamespace:
    return SimpleNamespace(queue=queue)


def test_skip_manual_suspension_without_auto_tag() -> None:
    auto_tag = "ps-auto"
    card = _card(QUEUE_TYPE_SUSPENDED)
    note = _note(tags=["manual-suspended"])

    assert _should_skip_card(card, note, auto_tag, set())


def test_keep_suspended_when_auto_tag_present() -> None:
    auto_tag = "ps-auto"
    card = _card(QUEUE_TYPE_SUSPENDED)
    note = _note(tags=["manual", auto_tag])

    assert not _should_skip_card(card, note, auto_tag, set())


def test_do_not_skip_active_cards() -> None:
    auto_tag = "ps-auto"
    card = _card(QUEUE_TYPE_NEW)
    note = _note(tags=[])

    assert not _should_skip_card(card, note, auto_tag, set())


def test_keep_suspended_when_exception_tag_present() -> None:
    auto_tag = "ps-auto"
    exception_tags = {"kanjicards_new"}
    card = _card(QUEUE_TYPE_SUSPENDED)
    note = _note(tags=["manual", "kanjicards_new"])

    assert not _should_skip_card(card, note, auto_tag, exception_tags)
