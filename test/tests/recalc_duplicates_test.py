from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve.prioritysieve_globals import DEFAULT_REVIEW_DUE
from prioritysieve.recalc.recalc_main import DuplicateCandidate, _apply_duplicate_rules


def _dummy_config() -> SimpleNamespace:
    return SimpleNamespace(tag_suspended_automatically="ps-auto-suspend")


_card_sequence = 0


def _card(queue: int, card_type: int, due: int = 42) -> SimpleNamespace:
    global _card_sequence
    _card_sequence += 1
    return SimpleNamespace(queue=queue, type=card_type, due=due, id=_card_sequence)


def _note(tags: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(tags=list(tags or []))


def test_duplicate_rules_leave_review_cards_untouched() -> None:
    am_config = _dummy_config()
    review_card = _card(queue=QUEUE_TYPE_NEW, card_type=2, due=17)
    review_note = _note(tags=["existing"])
    new_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=10)
    new_note = _note()

    duplicates = defaultdict(list)
    duplicates[("ある", "")] = [
        DuplicateCandidate(
            card=review_card,
            note=review_note,
            due=100,
            auto_suspend=False,
            is_new_card=False,
            entry_reviewed=True,
            deck_priority=0,
            manually_suspended=False,
        ),
        DuplicateCandidate(
            card=new_card,
            note=new_note,
            due=10,
            auto_suspend=True,
            is_new_card=True,
            entry_reviewed=True,
            deck_priority=0,
            manually_suspended=False,
        ),
    ]

    _apply_duplicate_rules(am_config, duplicates)

    assert review_card.queue == QUEUE_TYPE_NEW
    assert review_note.tags == ["existing"]
    assert new_card.queue == QUEUE_TYPE_SUSPENDED
    assert new_card.due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in new_note.tags


def test_duplicate_rules_unsuspend_single_new_card_when_allowed() -> None:
    am_config = _dummy_config()
    first_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=9)
    first_note = _note(tags=["ps-auto-suspend"])
    second_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=11)
    second_note = _note()

    duplicates = defaultdict(list)
    duplicates[("beta", "")] = [
        DuplicateCandidate(
            card=first_card,
            note=first_note,
            due=5,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=0,
            manually_suspended=False,
        ),
        DuplicateCandidate(
            card=second_card,
            note=second_note,
            due=10,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=1,
            manually_suspended=False,
        ),
    ]

    _apply_duplicate_rules(am_config, duplicates)

    assert first_card.queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in first_note.tags
    assert second_card.queue == QUEUE_TYPE_SUSPENDED
    assert second_card.due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in second_note.tags


def test_duplicate_rules_respect_distinct_readings() -> None:
    am_config = _dummy_config()
    reviewed_card = _card(queue=QUEUE_TYPE_NEW, card_type=2, due=25)
    reviewed_note = _note()
    new_card = _card(queue=QUEUE_TYPE_NEW, card_type=CARD_TYPE_NEW, due=5)
    new_note = _note(tags=["ps-auto-suspend"])

    duplicates = defaultdict(list)
    duplicates[("側", "そば")] = [
        DuplicateCandidate(
            card=reviewed_card,
            note=reviewed_note,
            due=20,
            auto_suspend=False,
            is_new_card=False,
            entry_reviewed=True,
            deck_priority=0,
            manually_suspended=False,
        )
    ]
    duplicates[("側", "がわ")] = [
        DuplicateCandidate(
            card=new_card,
            note=new_note,
            due=15,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=0,
            manually_suspended=False,
        )
    ]

    _apply_duplicate_rules(am_config, duplicates)

    assert new_card.queue == QUEUE_TYPE_NEW
    assert new_card.due == 5
    assert "ps-auto-suspend" not in new_note.tags


def test_duplicate_rules_prefer_priority_deck() -> None:
    am_config = _dummy_config()
    high_priority_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=50)
    high_priority_note = _note(tags=["ps-auto-suspend"])
    low_priority_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=10)
    low_priority_note = _note()

    duplicates = defaultdict(list)
    duplicates[("語", "")] = [
        DuplicateCandidate(
            card=high_priority_card,
            note=high_priority_note,
            due=50,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=0,
            manually_suspended=False,
        ),
        DuplicateCandidate(
            card=low_priority_card,
            note=low_priority_note,
            due=10,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=5,
            manually_suspended=False,
        ),
    ]

    _apply_duplicate_rules(am_config, duplicates)

    assert high_priority_card.queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in high_priority_note.tags
    assert low_priority_card.queue == QUEUE_TYPE_SUSPENDED
    assert low_priority_card.due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in low_priority_note.tags


def test_duplicate_rules_keep_manually_suspended_exception() -> None:
    am_config = _dummy_config()
    manual_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=77)
    manual_note = _note(tags=["manual", "allow-recalc"])
    other_card = _card(queue=QUEUE_TYPE_SUSPENDED, card_type=CARD_TYPE_NEW, due=10)
    other_note = _note()

    duplicates = defaultdict(list)
    duplicates[("例", "")] = [
        DuplicateCandidate(
            card=manual_card,
            note=manual_note,
            due=77,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=0,
            manually_suspended=True,
        ),
        DuplicateCandidate(
            card=other_card,
            note=other_note,
            due=10,
            auto_suspend=False,
            is_new_card=True,
            entry_reviewed=False,
            deck_priority=1,
            manually_suspended=False,
        )
    ]

    _apply_duplicate_rules(am_config, duplicates)

    assert manual_card.queue == QUEUE_TYPE_SUSPENDED
    assert manual_card.due == 77
    assert "ps-auto-suspend" not in manual_note.tags
    assert other_card.queue == QUEUE_TYPE_SUSPENDED
    assert other_card.due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in other_note.tags
