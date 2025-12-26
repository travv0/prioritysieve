from __future__ import annotations

from types import SimpleNamespace

from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve.prioritysieve_globals import DEFAULT_REVIEW_DUE
from prioritysieve.recalc.recalc_main import CardPlan, _apply_kanji_subset_auto_suspend

_CARD_SEQUENCE = 0
_NOTE_SEQUENCE = 0


def _config(
    enabled: bool = True,
    kana_variants: bool = False,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    # Global config with tags
    am_config = SimpleNamespace(
        tag_ready="ps-ready",
        tag_not_ready="ps-not-ready",
        tag_suspended_automatically="ps-auto-suspend",
    )
    # Per-language config with variant settings
    lang_config = SimpleNamespace(
        auto_suspend_variant_spellings=enabled,
        merge_kana_variant_spellings=kana_variants,
    )
    return am_config, lang_config


def _plan(
    *,
    text: str,
    reading: str,
    is_new: bool,
    due: int,
    queue: int = QUEUE_TYPE_NEW,
    auto_suspend: bool = False,
) -> CardPlan:
    global _CARD_SEQUENCE, _NOTE_SEQUENCE
    _CARD_SEQUENCE += 1
    _NOTE_SEQUENCE += 1
    tags = ["ps-ready"] if queue == QUEUE_TYPE_NEW else ["ps-not-ready"]
    return CardPlan(
        card_id=_CARD_SEQUENCE,
        note_id=_NOTE_SEQUENCE,
        entry_key=(text, reading),
        is_new_card=is_new,
        entry_reviewed=not is_new,
        deck_priority=0,
        manually_suspended=False,
        original_due=due,
        desired_due=due,
        original_queue=queue,
        desired_queue=queue,
        auto_suspend=auto_suspend,
        deck_id=1,
        original_deck_id=1,
        original_tags=list(tags),
        desired_tags=list(tags),
        extra_reading_field_index=None,
        desired_reading=None,
        duplicate_sort_value=None,
        duplicate_sort_numeric=False,
    )


def test_non_new_superset_suspends_new_variant() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="思い出す",
        reading="おもいだす",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="思いだす",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert new_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in new_plan.desired_tags
    assert "ps-ready" not in new_plan.desired_tags


def test_non_new_subset_does_not_suspend_new_variant() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="思いだす",
        reading="おもいだす",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="思い出す",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
    assert new_plan.desired_due == 10


def test_long_vowel_reading_variants_share_group() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="焼き餃子",
        reading="ぎょーざ",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="餃子",
        reading="ぎょうざ",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert new_plan.desired_due == DEFAULT_REVIEW_DUE


def test_pure_kanji_subset_does_not_suspend() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="焼餃子",
        reading="ぎょーざ",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="餃子",
        reading="ぎょうざ",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
    assert new_plan.desired_due == 10


def test_due_order_prefers_kanji_superset_variant() -> None:
    am_config, lang_config = _config()
    early_plan = _plan(
        text="思い出す",
        reading="おもいだす",
        is_new=True,
        due=5,
    )
    late_plan = _plan(
        text="思いだす",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert early_plan.desired_queue == QUEUE_TYPE_NEW
    assert late_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert late_plan.desired_due == DEFAULT_REVIEW_DUE
    assert late_plan.auto_suspend is True


def test_due_rule_ignored_when_setting_disabled() -> None:
    am_config, lang_config = _config(enabled=False)
    early_plan = _plan(
        text="思い出す",
        reading="おもいだす",
        is_new=True,
        due=5,
    )
    late_plan = _plan(
        text="思いだす",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert late_plan.desired_queue == QUEUE_TYPE_NEW
    assert late_plan.desired_due == 10


def test_due_rule_skips_superset_that_is_already_suspended() -> None:
    am_config, lang_config = _config()
    early_plan = _plan(
        text="思い出す",
        reading="おもいだす",
        is_new=True,
        due=5,
        queue=QUEUE_TYPE_SUSPENDED,
        auto_suspend=True,
    )
    late_plan = _plan(
        text="思いだす",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert late_plan.desired_queue == QUEUE_TYPE_NEW


def test_okurigana_variant_requires_setting() -> None:
    am_config, lang_config = _config(enabled=False)
    review_plan = _plan(
        text="入口",
        reading="いりぐち",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="入り口",
        reading="いりぐち",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
    assert new_plan.desired_due == 10




def test_okurigana_variant_suspends_when_enabled() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="入口",
        reading="いりぐち",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="入り口",
        reading="いりぐち",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert new_plan.desired_due == DEFAULT_REVIEW_DUE
    assert "ps-auto-suspend" in new_plan.desired_tags


def test_okurigana_variant_due_rule() -> None:
    am_config, lang_config = _config()
    early_plan = _plan(
        text="入口",
        reading="いりぐち",
        is_new=True,
        due=5,
    )
    late_plan = _plan(
        text="入り口",
        reading="いりぐち",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert early_plan.desired_queue == QUEUE_TYPE_NEW
    assert late_plan.desired_queue == QUEUE_TYPE_SUSPENDED


def test_okurigana_variant_ignored_for_pure_kana() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="おもいだす",
        reading="おもいだす",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="おもぃだす",
        reading="おもいだす",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW


def test_kana_variant_non_new_suspends_new() -> None:
    am_config, lang_config = _config(kana_variants=True)
    review_plan = _plan(
        text="ゲーム",
        reading="げーむ",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="げーむ",
        reading="げーむ",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_SUSPENDED
    assert new_plan.desired_due == DEFAULT_REVIEW_DUE


def test_kana_variant_non_new_requires_setting() -> None:
    am_config, lang_config = _config(kana_variants=False)
    review_plan = _plan(
        text="ゲーム",
        reading="げーむ",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="げーむ",
        reading="げーむ",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
    assert new_plan.desired_due == 10


def test_kana_variant_due_prefers_earlier_new_card() -> None:
    am_config, lang_config = _config(kana_variants=True)
    early_plan = _plan(
        text="ゲーム",
        reading="げーむ",
        is_new=True,
        due=5,
    )
    late_plan = _plan(
        text="げーむ",
        reading="げーむ",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert early_plan.desired_queue == QUEUE_TYPE_NEW
    assert late_plan.desired_queue == QUEUE_TYPE_SUSPENDED


def test_kana_variant_same_script_not_suspended() -> None:
    am_config, lang_config = _config(kana_variants=True)
    early_plan = _plan(
        text="げーむ",
        reading="げーむ",
        is_new=True,
        due=5,
    )
    late_plan = _plan(
        text="げーむ",
        reading="げーむ",
        is_new=True,
        due=10,
    )

    plans = {early_plan.card_id: early_plan, late_plan.card_id: late_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert early_plan.desired_queue == QUEUE_TYPE_NEW
    assert late_plan.desired_queue == QUEUE_TYPE_NEW


def test_pure_kanji_variants_not_suspended() -> None:
    am_config, lang_config = _config()
    review_plan = _plan(
        text="羽",
        reading="はね",
        is_new=False,
        due=5,
        queue=QUEUE_TYPE_NEW,
    )
    new_plan = _plan(
        text="羽根",
        reading="はね",
        is_new=True,
        due=10,
    )

    plans = {review_plan.card_id: review_plan, new_plan.card_id: new_plan}
    _apply_kanji_subset_auto_suspend(am_config, lang_config, plans)

    assert new_plan.desired_queue == QUEUE_TYPE_NEW
