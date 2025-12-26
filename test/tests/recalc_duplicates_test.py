from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve.prioritysieve_globals import DEFAULT_REVIEW_DUE
from prioritysieve.recalc.recalc_main import CardPlan, _apply_duplicate_rules


def _dummy_config() -> SimpleNamespace:
    return SimpleNamespace(
        tag_suspended_automatically="ps-auto-suspend",
        tag_ready="am-ready",
        tag_not_ready="am-not-ready",
        get_preprocess_ignore_suspended_unless_tag_list=lambda: ["kanjicards_unreviewed"],
    )


_card_sequence = 0
_note_sequence = 0


def _plan(
    *,
    entry_key: tuple[str, str],
    queue: int,
    card_type: int,
    due: int,
    auto_suspend: bool,
    is_new_card: bool,
    entry_reviewed: bool,
    deck_priority: int = 0,
    manually_suspended: bool = False,
    tags: list[str] | None = None,
    deck_id: int = 1,
    original_deck_id: int = 0,
    duplicate_sort_value: str | None = None,
    duplicate_sort_numeric: bool = False,
) -> CardPlan:
    global _card_sequence, _note_sequence
    _card_sequence += 1
    _note_sequence += 1
    base_tags = list(tags or [])
    return CardPlan(
        card_id=_card_sequence,
        note_id=_note_sequence,
        entry_key=entry_key,
        is_new_card=is_new_card,
        entry_reviewed=entry_reviewed,
        deck_priority=deck_priority,
        manually_suspended=manually_suspended,
        original_due=due,
        desired_due=due,
        original_queue=queue,
        desired_queue=queue,
        auto_suspend=auto_suspend,
        deck_id=deck_id,
        original_deck_id=original_deck_id,
        original_tags=list(base_tags),
        desired_tags=list(base_tags),
        extra_reading_field_index=None,
        desired_reading=None,
        duplicate_sort_value=duplicate_sort_value,
        duplicate_sort_numeric=duplicate_sort_numeric,
    )


def test_duplicate_rules_collapse_manual_exception_duplicates() -> None:
    am_config = _dummy_config()

    first_plan = _plan(
        entry_key=("雫", "しずく"),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=1111,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["kanjicards_unreviewed", "am-ready"],
        manually_suspended=True,
    )
    second_plan = _plan(
        entry_key=("雫", "しずく"),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=2222,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["kanjicards_unreviewed", "am-ready"],
        manually_suspended=True,
    )

    duplicates = defaultdict(list)
    duplicates[("雫", "しずく")] = [first_plan, second_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    active_candidates = [
        plan for plan in (first_plan, second_plan) if "kanjicards_unreviewed" in plan.desired_tags
    ]
    demoted_candidates = [
        plan for plan in (first_plan, second_plan) if "kanjicards_unreviewed" not in plan.desired_tags
    ]

    assert len(active_candidates) == 1, "Exactly one exception-tagged card should remain active"
    assert len(demoted_candidates) == 1, "Exactly one exception-tagged card should be demoted"
    assert all(plan.desired_queue == QUEUE_TYPE_SUSPENDED for plan in (first_plan, second_plan))
    assert demoted_candidates[0].desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in demoted_candidates[0].desired_tags
    assert "ps-auto-suspend" not in active_candidates[0].desired_tags


def test_duplicate_rules_leave_review_cards_untouched() -> None:
    am_config = _dummy_config()
    review_plan = _plan(
        entry_key=("ある", ""),
        queue=QUEUE_TYPE_NEW,
        card_type=2,
        due=17,
        auto_suspend=False,
        is_new_card=False,
        entry_reviewed=True,
        tags=["existing"],
    )
    new_plan = _plan(
        entry_key=("ある", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=True,
        is_new_card=True,
        entry_reviewed=True,
    )

    duplicates = defaultdict(list)
    duplicates[("ある", "")] = [review_plan, new_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert review_plan.desired_queue == QUEUE_TYPE_NEW
    assert review_plan.desired_tags == ["existing"]
    assert new_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert new_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in new_plan.desired_tags


def test_duplicate_rules_unsuspend_single_new_card_when_allowed() -> None:
    am_config = _dummy_config()
    first_plan = _plan(
        entry_key=("beta", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
    )
    second_plan = _plan(
        entry_key=("beta", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=1,
    )

    duplicates = defaultdict(list)
    duplicates[("beta", "")] = [first_plan, second_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert first_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in first_plan.desired_tags
    assert second_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert second_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in second_plan.desired_tags


def test_duplicate_rules_respect_distinct_readings() -> None:
    am_config = _dummy_config()
    reviewed_plan = _plan(
        entry_key=("側", "そば"),
        queue=QUEUE_TYPE_NEW,
        card_type=2,
        due=20,
        auto_suspend=False,
        is_new_card=False,
        entry_reviewed=True,
    )
    new_plan = _plan(
        entry_key=("側", "がわ"),
        queue=QUEUE_TYPE_NEW,
        card_type=CARD_TYPE_NEW,
        due=15,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
    )

    duplicates = defaultdict(list)
    duplicates[("側", "そば")] = [reviewed_plan]
    duplicates[("側", "がわ")] = [new_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
    assert new_plan.desired_due == 15
    assert "ps-auto-suspend" not in new_plan.desired_tags


def test_duplicate_rules_prefer_priority_deck() -> None:
    am_config = _dummy_config()
    high_priority_plan = _plan(
        entry_key=("語", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=50,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
    )
    low_priority_plan = _plan(
        entry_key=("語", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=5,
    )

    duplicates = defaultdict(list)
    duplicates[("語", "")] = [high_priority_plan, low_priority_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert high_priority_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in high_priority_plan.desired_tags
    assert low_priority_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert low_priority_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in low_priority_plan.desired_tags


def test_duplicate_rules_keep_manually_suspended_exception() -> None:
    am_config = _dummy_config()
    manual_plan = _plan(
        entry_key=("例", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=77,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["manual", "allow-recalc"],
        deck_priority=0,
        manually_suspended=True,
    )
    other_plan = _plan(
        entry_key=("例", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=1,
    )

    duplicates = defaultdict(list)
    duplicates[("例", "")] = [manual_plan, other_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert manual_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert manual_plan.desired_due == 77
    assert "ps-auto-suspend" not in manual_plan.desired_tags
    assert other_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert other_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in other_plan.desired_tags


def test_duplicate_rules_preserve_tag_order_with_auto_suspend() -> None:
    am_config = _dummy_config()
    base_tags = ["am-ready", "ps-auto-suspend", "matched20250511", "matched20250512"]
    base_plan = _plan(
        entry_key=("tag-order", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=True,
        is_new_card=True,
        entry_reviewed=False,
        tags=base_tags,
    )

    duplicates = defaultdict(list)
    duplicates[("tag-order", "")] = [base_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert base_plan.desired_tags == base_tags, "auto-suspend tag should remain in original position"


def test_duplicate_rules_prefer_newest_card_within_same_deck() -> None:
    am_config = _dummy_config()
    older_plan = _plan(
        entry_key=("新", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        deck_id=42,
    )
    newer_plan = _plan(
        entry_key=("新", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=0,
        deck_id=42,
    )

    duplicates = defaultdict(list)
    duplicates[("新", "")] = [older_plan, newer_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert newer_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in newer_plan.desired_tags
    assert older_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert older_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in older_plan.desired_tags


def test_duplicate_rules_sort_by_field_within_same_deck() -> None:
    """Cards with lower duplicate_sort_value should be preferred within same deck priority."""
    am_config = _dummy_config()
    # Card with higher sort value (should be suspended)
    high_rank_plan = _plan(
        entry_key=("順", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        duplicate_sort_value="B",
    )
    # Card with lower sort value (should stay unsuspended)
    low_rank_plan = _plan(
        entry_key=("順", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=0,
        duplicate_sort_value="A",
    )

    duplicates = defaultdict(list)
    duplicates[("順", "")] = [high_rank_plan, low_rank_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert low_rank_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in low_rank_plan.desired_tags
    assert high_rank_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert "ps-auto-suspend" in high_rank_plan.desired_tags


def test_duplicate_rules_deck_priority_beats_sort_field() -> None:
    """Deck priority should take precedence over duplicate_sort_value."""
    am_config = _dummy_config()
    # Higher deck priority but worse sort value - should still win
    high_priority_plan = _plan(
        entry_key=("優", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=50,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        duplicate_sort_value="Z",
    )
    # Lower deck priority but better sort value - should be suspended
    low_priority_plan = _plan(
        entry_key=("優", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=5,
        duplicate_sort_value="A",
    )

    duplicates = defaultdict(list)
    duplicates[("優", "")] = [high_priority_plan, low_priority_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert high_priority_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in high_priority_plan.desired_tags
    assert low_priority_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert "ps-auto-suspend" in low_priority_plan.desired_tags


def test_duplicate_rules_empty_sort_field_sorts_last() -> None:
    """Cards with no/empty duplicate_sort_value should sort after cards with values."""
    am_config = _dummy_config()
    # Card with no sort value (should be suspended)
    no_rank_plan = _plan(
        entry_key=("空", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        duplicate_sort_value=None,
    )
    # Card with sort value (should stay unsuspended)
    has_rank_plan = _plan(
        entry_key=("空", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=0,
        duplicate_sort_value="A",
    )

    duplicates = defaultdict(list)
    duplicates[("空", "")] = [no_rank_plan, has_rank_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert has_rank_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in has_rank_plan.desired_tags
    assert no_rank_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert "ps-auto-suspend" in no_rank_plan.desired_tags


def test_duplicate_rules_numeric_sort_field() -> None:
    """With numeric sorting, '2' should come before '10'."""
    am_config = _dummy_config()
    # Card with value "10" (should be suspended with numeric sort)
    ten_plan = _plan(
        entry_key=("数", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        duplicate_sort_value="10",
        duplicate_sort_numeric=True,
    )
    # Card with value "2" (should stay unsuspended with numeric sort)
    two_plan = _plan(
        entry_key=("数", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=0,
        duplicate_sort_value="2",
        duplicate_sort_numeric=True,
    )

    duplicates = defaultdict(list)
    duplicates[("数", "")] = [ten_plan, two_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert two_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in two_plan.desired_tags
    assert ten_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert "ps-auto-suspend" in ten_plan.desired_tags


def test_duplicate_rules_text_sort_field() -> None:
    """With text sorting (default), '10' should come before '2' alphabetically."""
    am_config = _dummy_config()
    # Card with value "10" (should stay unsuspended with text sort)
    ten_plan = _plan(
        entry_key=("文", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=5,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        tags=["ps-auto-suspend"],
        deck_priority=0,
        duplicate_sort_value="10",
        duplicate_sort_numeric=False,
    )
    # Card with value "2" (should be suspended with text sort)
    two_plan = _plan(
        entry_key=("文", ""),
        queue=QUEUE_TYPE_SUSPENDED,
        card_type=CARD_TYPE_NEW,
        due=10,
        auto_suspend=False,
        is_new_card=True,
        entry_reviewed=False,
        deck_priority=0,
        duplicate_sort_value="2",
        duplicate_sort_numeric=False,
    )

    duplicates = defaultdict(list)
    duplicates[("文", "")] = [ten_plan, two_plan]

    _apply_duplicate_rules(
        am_config,
        duplicates,
    )

    assert ten_plan.desired_queue == QUEUE_TYPE_NEW
    assert "ps-auto-suspend" not in ten_plan.desired_tags
    assert two_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert "ps-auto-suspend" in two_plan.desired_tags
