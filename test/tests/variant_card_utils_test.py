from prioritysieve import prioritysieve_globals as ps_globals
from prioritysieve.__init__ import (
    _VariantCard,
    _collect_variant_card_ids,
    _entry_priority_due,
)
from prioritysieve.kanji_utils import extract_kanji_sequence


def _variant(card_id: int, text: str, reading: str, due: int = 0) -> _VariantCard:
    return _VariantCard(
        card_id=card_id,
        text=text,
        reading=reading,
        kanji_sequence=extract_kanji_sequence(text),
        due=due,
    )


def test_collect_variant_card_ids_with_okurigana() -> None:
    groups = {
        "いりぐち": [
            _variant(1, "入口", "いりぐち", due=5),
            _variant(2, "入り口", "いりぐち", due=10),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {2}


def test_collect_variant_card_ids_with_kanji_subset() -> None:
    groups = {
        "おもいだす": [
            _variant(1, "思い出す", "おもいだす", due=5),
            _variant(2, "思いだす", "おもいだす", due=20),
            _variant(3, "会う", "あう", due=5),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {2}


def test_collect_variant_card_ids_pure_kana_skipped() -> None:
    groups = {
        "あう": [
            _variant(1, "あう", "あう", due=10),
            _variant(2, "遭う", "あう", due=5),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {1}


def test_collect_variant_card_ids_all_kanji_ignored() -> None:
    groups = {
        "はね": [
            _variant(1, "羽", "はね"),
            _variant(2, "羽根", "はね"),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == set()


def test_entry_priority_due_prefers_exact_reading() -> None:
    priority_map = {("入口", "いりぐち"): 42, ("入口", ""): 99}

    due = _entry_priority_due("入口", "  いりぐち  ", priority_map)

    assert due == 42


def test_entry_priority_due_falls_back_to_text_only_entry() -> None:
    priority_map = {("入口", ""): 17}

    due = _entry_priority_due("入口", "いりぐち", priority_map)

    assert due == 17


def test_entry_priority_due_defaults_when_missing() -> None:
    due = _entry_priority_due("入口", "いりぐち", {})

    assert due == ps_globals.DEFAULT_REVIEW_DUE
