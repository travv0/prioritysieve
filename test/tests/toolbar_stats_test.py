from __future__ import annotations

from types import SimpleNamespace

from anki.consts import CARD_TYPE_NEW, CARD_TYPE_REV

from prioritysieve.entry_db import StoredCard
from prioritysieve.toolbar_stats import _compute_note_counts


def _config(
    *,
    auto_tag: str = "ps-auto-suspend",
    known_auto_tag: str = "ps-known-automatically",
    known_manual_tag: str = "ps-known-manually",
    exceptions: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        tag_suspended_automatically=auto_tag,
        tag_known_automatically=known_auto_tag,
        tag_known_manually=known_manual_tag,
        get_preprocess_ignore_suspended_unless_tag_list=lambda: exceptions or [],
    )


def test_counts_skip_auto_suspended_duplicates() -> None:
    config = _config()
    cards = [
        StoredCard(card_id=1, note_id=11, note_type_id=1, card_type=CARD_TYPE_NEW, tags=" ps-auto-suspend "),
        StoredCard(card_id=2, note_id=22, note_type_id=1, card_type=CARD_TYPE_REV, tags=""),
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
        )
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 1
    assert reviewed == 0


def test_counts_treat_known_tags_as_reviewed() -> None:
    config = _config()
    cards = [
        StoredCard(
            card_id=1,
            note_id=11,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags=" ps-known-automatically ",
        ),
        StoredCard(
            card_id=2,
            note_id=12,
            note_type_id=1,
            card_type=CARD_TYPE_NEW,
            tags=" ps-known-manually ",
        ),
    ]

    tracked, reviewed = _compute_note_counts(config, cards)

    assert tracked == 2
    assert reviewed == 2
