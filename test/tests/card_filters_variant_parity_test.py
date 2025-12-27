from anki.consts import CARD_TYPE_NEW, CARD_TYPE_REV, QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED

from prioritysieve import card_filters


def _filter(
    entry_card_map,
    suspended_cards_by_entry,
    *,
    merge_kana_variants=True,
    auto_suspend=True,
):
    am_config = type(
        "C",
        (),
        {
            "auto_suspend_variant_spellings": auto_suspend,
            "merge_kana_variant_spellings": merge_kana_variants,
            "tag_suspended_automatically": "ps-auto-suspend",
        },
    )()
    card_status_lookup = {}
    for ids in entry_card_map.values():
        for card_id in ids:
            # Default every card to suspended-new unless overwritten
            card_status_lookup[card_id] = (QUEUE_TYPE_SUSPENDED, "", CARD_TYPE_NEW)
    # First entry in each item treated as active review card
    for entry_ids in entry_card_map.values():
        if not entry_ids:
            continue
        active_id = entry_ids[0]
        card_status_lookup[active_id] = (QUEUE_TYPE_NEW, "", CARD_TYPE_REV)

    return card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=set(),
        merge_kana_variants=merge_kana_variants,
        auto_suspend_variants=auto_suspend,
        am_config=am_config,
    )


def test_non_new_superset_suspends_new_variant() -> None:
    entry_card_map = {("思い出す", "おもいだす", "Japanese"): [1], ("思いだす", "おもいだす", "Japanese"): [2]}
    suspended = {("思いだす", "おもいだす", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended)
    assert filtered == {}


def test_non_new_subset_keeps_new_variant() -> None:
    entry_card_map = {("思いだす", "おもいだす", "Japanese"): [1], ("思い出す", "おもいだす", "Japanese"): [2]}
    suspended = {("思い出す", "おもいだす", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended)
    assert filtered == suspended


def test_okurigana_variant_requires_setting() -> None:
    entry_card_map = {("入口", "いりぐち", "Japanese"): [1], ("入り口", "いりぐち", "Japanese"): [2]}
    suspended = {("入り口", "いりぐち", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, auto_suspend=False)
    assert filtered == suspended


def test_okurigana_variant_suspends_when_enabled() -> None:
    entry_card_map = {("入口", "いりぐち", "Japanese"): [1], ("入り口", "いりぐち", "Japanese"): [2]}
    suspended = {("入り口", "いりぐち", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, auto_suspend=True)
    assert filtered == {}


def test_kana_variant_requires_setting() -> None:
    entry_card_map = {("ゲーム", "げーむ", "Japanese"): [1], ("げーむ", "げーむ", "Japanese"): [2]}
    suspended = {("げーむ", "げーむ", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, merge_kana_variants=False)
    assert filtered == suspended


def test_kana_variant_suspends_when_enabled() -> None:
    entry_card_map = {("ゲーム", "げーむ", "Japanese"): [1], ("げーむ", "げーむ", "Japanese"): [2]}
    suspended = {("げーむ", "げーむ", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, merge_kana_variants=True)
    assert filtered == {}


def test_kana_vs_kanji_variant_suppressed() -> None:
    entry_card_map = {("嬉しい", "うれしい", "Japanese"): [1], ("うれしい", "うれしい", "Japanese"): [2]}
    suspended = {("うれしい", "うれしい", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, merge_kana_variants=False, auto_suspend=True)
    assert filtered == {}


def test_kanji_not_hidden_by_active_kana() -> None:
    entry_card_map = {("うれしい", "うれしい", "Japanese"): [1], ("嬉しい", "うれしい", "Japanese"): [2]}
    suspended = {("嬉しい", "うれしい", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, merge_kana_variants=True, auto_suspend=True)
    assert filtered == suspended


def test_kana_same_script_not_suspended() -> None:
    entry_card_map = {("げーむ", "げーむ", "Japanese"): [1], ("げーむ", "げーむ", "Japanese"): [2]}
    suspended = {("げーむ", "げーむ", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, merge_kana_variants=True)
    assert filtered == suspended


def test_pure_kanji_variants_not_suspended() -> None:
    entry_card_map = {("羽", "はね", "Japanese"): [1], ("羽根", "はね", "Japanese"): [2]}
    suspended = {("羽根", "はね", "Japanese"): [2]}
    filtered = _filter(entry_card_map, suspended, auto_suspend=True)
    assert filtered == suspended
