from anki.consts import CARD_TYPE_NEW, CARD_TYPE_REV, QUEUE_TYPE_SUSPENDED

from prioritysieve import card_filters


def test_filter_variant_shadowed_entries_removes_kanji_subset() -> None:
    entry_card_map = {
        ("入口", "いりぐち", "Japanese"): [1],
        ("口", "いりぐち", "Japanese"): [2],
    }
    suspended_cards_by_entry = {("口", "いりぐち", "Japanese"): [2]}
    card_status_lookup = {
        1: (0, "", CARD_TYPE_REV),  # active review card
        2: (QUEUE_TYPE_SUSPENDED, "", CARD_TYPE_NEW),  # suspended new card
    }

    filtered = card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=set(),
        merge_kana_variants=True,
        auto_suspend_variants=True,
        am_config=None,
    )

    assert filtered == {}


def test_filter_variant_shadowed_entries_respects_flag() -> None:
    entry_card_map = {
        ("食べる", "たべる", "Japanese"): [1],
        ("たべる", "たべる", "Japanese"): [2],
    }
    suspended_cards_by_entry = {("たべる", "たべる", "Japanese"): [2]}
    card_status_lookup = {
        1: (0, "", CARD_TYPE_REV),
        2: (QUEUE_TYPE_SUSPENDED, "", CARD_TYPE_NEW),
    }

    filtered = card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=set(),
        merge_kana_variants=True,
        auto_suspend_variants=False,
        am_config=None,
    )

    assert filtered == suspended_cards_by_entry


def test_filter_variant_shadowed_entries_merges_kana_scripts() -> None:
    entry_card_map = {
        ("カタカナ", "かたかな", "Japanese"): [1],
        ("かたかな", "かたかな", "Japanese"): [2],
    }
    suspended_cards_by_entry = {("かたかな", "かたかな", "Japanese"): [2]}
    card_status_lookup = {
        1: (0, "", CARD_TYPE_REV),
        2: (QUEUE_TYPE_SUSPENDED, "", CARD_TYPE_NEW),
    }

    filtered = card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=set(),
        merge_kana_variants=True,
        auto_suspend_variants=True,
        am_config=None,
    )

    assert filtered == {}


def test_filter_variant_shadowed_entries_respects_kana_setting_disabled() -> None:
    entry_card_map = {
        ("カタカナ", "かたかな", "Japanese"): [1],
        ("かたかな", "かたかな", "Japanese"): [2],
    }
    suspended_cards_by_entry = {("かたかな", "かたかな", "Japanese"): [2]}
    card_status_lookup = {
        1: (0, "", CARD_TYPE_REV),
        2: (QUEUE_TYPE_SUSPENDED, "", CARD_TYPE_NEW),
    }

    filtered = card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=set(),
        merge_kana_variants=False,
        auto_suspend_variants=True,
        am_config=None,
    )

    assert filtered == suspended_cards_by_entry
