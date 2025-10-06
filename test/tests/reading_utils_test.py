from prioritysieve.reading_utils import (
    expand_long_vowel_variants,
    normalize_reading,
    parse_furigana_field,
)

def test_parse_furigana_field_multiple_tokens() -> None:
    assert parse_furigana_field("繰[く]り 広[ひろ]げる") == ["くり", "ひろげる"]

def test_parse_furigana_field_single_token() -> None:
    assert parse_furigana_field("殺意[さつい]") == ["さつい"]

def test_parse_furigana_field_okurigana_chain() -> None:
    assert parse_furigana_field("繰り返[くりかえ]す") == ["くりかえす"]

def test_parse_furigana_field_mixed_kana() -> None:
    assert parse_furigana_field("甘[あま]く 見[み]る") == ["あまく", "みる"]

def test_parse_furigana_without_space_separators() -> None:
    assert parse_furigana_field("入[い]り口[ぐち]") == ["いりぐち"]

def test_parse_furigana_mixed_with_plain_kana() -> None:
    assert parse_furigana_field("女[おんな]の子[こ]") == ["おんなのこ"]

def test_parse_furigana_with_empty_readings() -> None:
    assert parse_furigana_field("持[も]っ[　]て[　]行[い]く") == ["もっていく"]

def test_normalize_reading_katakana_to_hiragana() -> None:
    assert normalize_reading("タベルト") == "たべると"

def test_normalize_reading_none_returns_empty() -> None:
    assert normalize_reading(None) == ""

def test_parse_furigana_field_prefixed_kana_duplication() -> None:
    assert parse_furigana_field("そよ風[そよかぜ]") == ["そよかぜ"]

def test_parse_furigana_field_prefixed_kana_duplication_phrase() -> None:
    assert parse_furigana_field("あの世[あのよ]") == ["あのよ"]


def test_expand_long_vowel_variants_preserves_and_adds_matches() -> None:
    variants = expand_long_vowel_variants("ぎょーざ")
    assert "ぎょーざ" in variants
    assert "ぎょうざ" in variants
    assert "ぎょおざ" in variants


def test_expand_long_vowel_variants_handles_a_sound() -> None:
    variants = expand_long_vowel_variants("きゃー")
    assert "きゃー" in variants
    assert "きゃあ" in variants


def test_expand_long_vowel_variants_handles_i_sound() -> None:
    variants = expand_long_vowel_variants("きー")
    assert variants == {"きー", "きい"}


def test_expand_long_vowel_variants_handles_e_sound() -> None:
    variants = expand_long_vowel_variants("しぇー")
    assert "しぇー" in variants
    assert "しぇい" in variants
    assert "しぇえ" in variants


def test_expand_long_vowel_variants_handles_o_sound() -> None:
    variants = expand_long_vowel_variants("こー")
    assert "こー" in variants
    assert "こう" in variants
    assert "こお" in variants
