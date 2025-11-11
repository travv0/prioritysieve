from prioritysieve.__init__ import _VariantCard, _collect_variant_card_ids
from prioritysieve.kanji_utils import extract_kanji_sequence


def _variant(card_id: int, text: str, reading: str) -> _VariantCard:
    return _VariantCard(
        card_id=card_id,
        text=text,
        reading=reading,
        kanji_sequence=extract_kanji_sequence(text),
    )


def test_collect_variant_card_ids_with_okurigana() -> None:
    groups = {
        "いりぐち": [
            _variant(1, "入口", "いりぐち"),
            _variant(2, "入り口", "いりぐち"),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {1, 2}


def test_collect_variant_card_ids_with_kanji_subset() -> None:
    groups = {
        "おもいだす": [
            _variant(1, "思い出す", "おもいだす"),
            _variant(2, "思いだす", "おもいだす"),
            _variant(3, "会う", "あう"),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {1, 2}


def test_collect_variant_card_ids_pure_kana_skipped() -> None:
    groups = {
        "あう": [
            _variant(1, "あう", "あう"),
            _variant(2, "遭う", "あう"),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == {1, 2}


def test_collect_variant_card_ids_all_kanji_ignored() -> None:
    groups = {
        "はね": [
            _variant(1, "羽", "はね"),
            _variant(2, "羽根", "はね"),
        ]
    }

    card_ids = _collect_variant_card_ids(groups)

    assert card_ids == set()
