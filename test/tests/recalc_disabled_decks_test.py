from __future__ import annotations

from types import SimpleNamespace

import pytest
from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve.recalc.recalc_main import _should_skip_disabled_deck_card


def test_disabled_decks_config_loads() -> None:
    """Verify disabled_decks config loads as a list."""
    config = SimpleNamespace(disabled_decks=["Deck A", "Deck B"])

    assert isinstance(config.disabled_decks, list)
    assert len(config.disabled_decks) == 2
    assert "Deck A" in config.disabled_decks
    assert "Deck B" in config.disabled_decks


def test_disabled_decks_set_creation() -> None:
    """Verify disabled decks can be converted to set for efficient lookup."""
    disabled_decks = ["Deck A", "Deck B", "Deck C"]
    disabled_decks_set = set(disabled_decks)

    assert "Deck A" in disabled_decks_set
    assert "Deck B" in disabled_decks_set
    assert "Deck C" in disabled_decks_set
    assert "Deck D" not in disabled_decks_set


def test_disabled_deck_suspension_logic() -> None:
    """
    Test that auto_suspend flag is set when card is from disabled deck.

    In the actual recalc flow:
    1. Deck name is extracted from card's deck_id
    2. If deck_name is in disabled_decks_set, from_disabled_deck = True
    3. auto_suspend includes: base_auto_suspend OR (entry_reviewed and is_new_card) OR from_disabled_deck
    4. Cards with auto_suspend=True get:
       - desired_due = DEFAULT_REVIEW_DUE (100,000,000)
       - ps-suspended-automatically tag
       - ps-not-ready tag
       - suspended queue
    """
    # Base conditions
    base_auto_suspend = False  # Not missing from priority files
    entry_reviewed = False  # Entry not reviewed
    is_new_card = True  # Card is new

    # Test 1: Card from disabled deck should trigger auto_suspend
    from_disabled_deck = True
    auto_suspend = base_auto_suspend or (entry_reviewed and is_new_card) or from_disabled_deck
    assert auto_suspend is True

    # Test 2: Card from enabled deck should not trigger auto_suspend (in this scenario)
    from_disabled_deck = False
    auto_suspend = base_auto_suspend or (entry_reviewed and is_new_card) or from_disabled_deck
    assert auto_suspend is False

    # Test 3: Disabled deck overrides other conditions
    from_disabled_deck = True
    base_auto_suspend = False
    entry_reviewed = True  # Even if entry is reviewed
    is_new_card = False  # Even if card is not new
    auto_suspend = base_auto_suspend or (entry_reviewed and is_new_card) or from_disabled_deck
    assert auto_suspend is True


def test_disabled_decks_empty_list() -> None:
    """Verify empty disabled_decks list works correctly."""
    disabled_decks_set = set([])
    deck_name = "Any Deck"

    from_disabled_deck = deck_name in disabled_decks_set
    assert from_disabled_deck is False


def test_skip_disabled_deck_new_suspended_card() -> None:
    """New suspended cards in disabled decks are already suspended, skip them."""
    assert _should_skip_disabled_deck_card(is_new_card=True, queue=QUEUE_TYPE_SUSPENDED)


def test_skip_disabled_deck_non_new_non_suspended_card() -> None:
    """Non-new (review/learning) cards in disabled decks don't benefit from
    processing since auto_suspend only affects the new card code path."""
    assert _should_skip_disabled_deck_card(is_new_card=False, queue=QUEUE_TYPE_NEW)


def test_skip_disabled_deck_non_new_suspended_card() -> None:
    """Non-new suspended cards in disabled decks are already suspended, skip them."""
    assert _should_skip_disabled_deck_card(is_new_card=False, queue=QUEUE_TYPE_SUSPENDED)


def test_process_disabled_deck_new_non_suspended_card() -> None:
    """New non-suspended cards in disabled decks need processing to get auto-suspended."""
    assert not _should_skip_disabled_deck_card(is_new_card=True, queue=QUEUE_TYPE_NEW)
