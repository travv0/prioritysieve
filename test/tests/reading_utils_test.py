from ankimorphs.reading_utils import normalize_reading, parse_furigana_field


def test_parse_furigana_field_multiple_tokens() -> None:
    assert parse_furigana_field("繰[く]り 広[ひろ]げる") == ["くり", "ひろげる"]


def test_parse_furigana_field_single_token() -> None:
    assert parse_furigana_field("殺意[さつい]") == ["さつい"]


def test_parse_furigana_field_mixed_kana() -> None:
    assert parse_furigana_field("甘[あま]く 見[み]る") == ["あまく", "みる"]


def test_parse_furigana_without_space_separators() -> None:
    assert parse_furigana_field("入[い]り口[ぐち]") == ["いりぐち"]


def test_parse_furigana_mixed_with_plain_kana() -> None:
    assert parse_furigana_field("女[おんな]の子[こ]") == ["おんなのこ"]


def test_parse_furigana_with_empty_readings() -> None:
    assert parse_furigana_field("持[も]っ[　]て[　]行[い]く") == ["もっ", "て", "いく"]


def test_normalize_reading_katakana_to_hiragana() -> None:
    assert normalize_reading("タベルト") == "たべると"


def test_normalize_reading_none_returns_empty() -> None:
    assert normalize_reading(None) == ""
