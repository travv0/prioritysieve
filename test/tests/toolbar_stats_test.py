from __future__ import annotations

from types import SimpleNamespace

from anki.consts import (
    CARD_TYPE_NEW,
    CARD_TYPE_REV,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_SUSPENDED,
)

from prioritysieve.entry import Entry
from prioritysieve.entry_db import StoredCard
from prioritysieve.toolbar_stats import _compute_note_counts, LanguageStats


# --------------------------------------------------------------------------
# LanguageStats visibility tests
# --------------------------------------------------------------------------


def _make_language_stats(
    *,
    hide_reviewed: bool = False,
    hide_tracked: bool = False,
    hide_pending: bool = False,
    hide_recalc: bool = False,
    prefix: str = "JP",
    name: str = "Japanese",
    reviewed: int = 50,
    tracked: int = 100,
    pending: int = 50,
) -> LanguageStats:
    return LanguageStats(
        language_name=name,
        prefix=prefix,
        tracked=tracked,
        reviewed=reviewed,
        pending=pending,
        hide_recalc_toolbar=hide_recalc,
        hide_reviewed_counter=hide_reviewed,
        hide_tracked_counter=hide_tracked,
        hide_pending_counter=hide_pending,
    )


def test_language_stats_label_shows_both_counters_by_default() -> None:
    stats = _make_language_stats()
    assert stats.label == "JP: 50/100"


def test_language_stats_label_hides_reviewed_counter() -> None:
    stats = _make_language_stats(hide_reviewed=True)
    assert stats.label == "JP: 100"


def test_language_stats_label_hides_tracked_counter() -> None:
    stats = _make_language_stats(hide_tracked=True)
    assert stats.label == "JP: 50"


def test_language_stats_label_without_prefix() -> None:
    stats = _make_language_stats(prefix="")
    assert stats.label == "50/100"


def test_language_stats_label_without_prefix_hides_reviewed() -> None:
    stats = _make_language_stats(prefix="", hide_reviewed=True)
    assert stats.label == "100"


def test_language_stats_tooltip_shows_both_counters_by_default() -> None:
    stats = _make_language_stats()
    assert stats.tooltip == "Japanese: 50 reviewed / 100 tracked"


def test_language_stats_tooltip_hides_reviewed_counter() -> None:
    stats = _make_language_stats(hide_reviewed=True)
    assert stats.tooltip == "Japanese: 100 tracked"


def test_language_stats_tooltip_hides_tracked_counter() -> None:
    stats = _make_language_stats(hide_tracked=True)
    assert stats.tooltip == "Japanese: 50 reviewed"


def test_language_stats_is_visible_when_both_counters_shown() -> None:
    stats = _make_language_stats()
    assert stats.is_visible is True


def test_language_stats_is_visible_when_reviewed_hidden() -> None:
    stats = _make_language_stats(hide_reviewed=True)
    assert stats.is_visible is True


def test_language_stats_is_visible_when_tracked_hidden() -> None:
    stats = _make_language_stats(hide_tracked=True)
    assert stats.is_visible is True


def test_language_stats_not_visible_when_both_counters_hidden() -> None:
    stats = _make_language_stats(hide_reviewed=True, hide_tracked=True)
    assert stats.is_visible is False


def test_language_stats_is_visible_independent_of_hide_recalc() -> None:
    """hide_recalc_toolbar should only affect Recalc button, not stats visibility."""
    stats = _make_language_stats(hide_recalc=True)
    assert stats.is_visible is True


def test_language_stats_hide_recalc_does_not_hide_stats() -> None:
    """Regression test: hide_recalc_toolbar should not hide per-language stats."""
    stats = _make_language_stats(hide_recalc=True, hide_reviewed=False, hide_tracked=False)
    assert stats.is_visible is True
    assert stats.label == "JP: 50/100"


def _config(
    *,
    auto_tag: str = "ps-auto-suspend",
    known_manual_tag: str = "ps-known-manually",
    exceptions: list[str] | None = None,
    okurigana_filter: bool = False,
    kana_variants: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        tag_suspended_automatically=auto_tag,
        tag_known_manually=known_manual_tag,
        get_preprocess_ignore_suspended_unless_tag_list=lambda: exceptions or [],
        auto_suspend_variant_spellings=okurigana_filter,
        merge_kana_variant_spellings=kana_variants,
    )


def test_counts_skip_auto_suspended_duplicates() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags=" ps-auto-suspend ",
            card_queue=QUEUE_TYPE_SUSPENDED,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 1
    assert reviewed == 1


def test_counts_include_exception_tagged_suspended_cards() -> None:
    config = _config(exceptions=["keep-active"])
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags=" ps-auto-suspend keep-active ",
            card_queue=QUEUE_TYPE_SUSPENDED,
        )
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 1
    assert reviewed == 0


def test_counts_ignore_notes_with_all_suspended_cards() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_SUSPENDED,
        )
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 0
    assert reviewed == 0


def test_counts_include_active_new_and_review_cards_per_note() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
        StoredCard(
            card_id=2,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_merges_spelling_variants_for_omoi_dasu() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=3,
            note_id=33,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=4,
            note_id=44,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
    ]
    card_entries = {
        1: Entry(text="思い出す", reading="おもいだす", reviewed=False),
        2: Entry(text="思いだす", reading="おもいだす", reviewed=False),
        3: Entry(text="おもい出す", reading="おもいだす", reviewed=False),
        4: Entry(text="おもいだす", reading="おもいだす", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_keeps_public_vs_regret_separate() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="公開", reading="こうかい", reviewed=False),
        2: Entry(text="後悔", reading="こうかい", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 2
    assert reviewed == 2


def test_deduplicate_counts_keeps_homophone_au_variants_separate() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=3,
            note_id=33,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="会う", reading="あう", reviewed=False),
        2: Entry(text="逢う", reading="あう", reviewed=False),
        3: Entry(text="遭う", reading="あう", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 3
    assert reviewed == 3


def test_deduplicate_counts_merges_unambiguous_wakaru_variants() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
    ]
    card_entries = {
        1: Entry(text="分る", reading="わかる", reviewed=False),
        2: Entry(text="わかる", reading="わかる", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_merges_iriguchi_okurigana_variants() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
    ]
    card_entries = {
        1: Entry(text="入口", reading="いりぐち", reviewed=False),
        2: Entry(text="入り口", reading="いりぐち", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_keeps_ambiguous_all_kana_separate() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=3,
            note_id=33,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
    ]
    card_entries = {
        1: Entry(text="公開", reading="こうかい", reviewed=False),
        2: Entry(text="後悔", reading="こうかい", reviewed=False),
        3: Entry(text="こうかい", reading="こうかい", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 3
    assert reviewed == 2


def test_deduplicate_counts_merge_hiragana_katakana_variants() -> None:
    config = _config(kana_variants=True)
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="げーむ", reading="げーむ", reviewed=False),
        2: Entry(text="ゲーム", reading="げーむ", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_kana_variants_respect_setting() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="げーむ", reading="げーむ", reviewed=False),
        2: Entry(text="ゲーム", reading="げーむ", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 2
    assert reviewed == 2


def test_deduplicate_counts_require_both_kana_scripts() -> None:
    config = _config(kana_variants=True)
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="げーむ", reading="げーむ", reviewed=False),
        2: Entry(text="げえむ", reading="げーむ", reviewed=False),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
    )

    assert tracked == 2
    assert reviewed == 2


def test_okurigana_filter_without_full_dedup() -> None:
    config = _config(okurigana_filter=True)
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {}

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=None,
        deduplicate=False,
        filter_okurigana=False,
    )

    assert tracked == 2
    assert reviewed == 1


def test_okurigana_filter_applies_with_dedup() -> None:
    config = _config(okurigana_filter=True)
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="入口", reading="いりぐち", reviewed=False),
        2: Entry(text="入り口", reading="いりぐち", reviewed=True),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
        filter_okurigana=True,
    )

    assert tracked == 1
    assert reviewed == 1


def test_deduplicate_counts_ignore_pure_kanji_same_sequence() -> None:
    config = _config(okurigana_filter=True)
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags="",
            card_queue=QUEUE_TYPE_NEW,
        ),
        StoredCard(
            card_id=2,
            note_id=22,
            note_type_id=1,
            card_type=CARD_TYPE_REV,
            tags="",
            card_queue=QUEUE_TYPE_REV,
        ),
    ]
    card_entries = {
        1: Entry(text="羽", reading="はね", reviewed=False),
        2: Entry(text="羽根", reading="はね", reviewed=True),
    }

    tracked, reviewed = _compute_note_counts(
        config,
        cards,
        card_entries=card_entries,
        deduplicate=True,
        filter_okurigana=True,
    )

    assert tracked == 2
    assert reviewed == 1
