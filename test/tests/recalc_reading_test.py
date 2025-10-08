from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.prioritysieve_globals import (
    READING_PRIORITY_FURIGANA_FIRST,
    READING_PRIORITY_READING_FIRST,
)
from prioritysieve.recalc.caching import _extract_reading


def _dummy_config() -> SimpleNamespace:
    return SimpleNamespace(
        preprocess_ignore_bracket_contents=False,
        preprocess_ignore_round_bracket_contents=False,
        preprocess_ignore_slim_round_bracket_contents=False,
        preprocess_ignore_angle_bracket_contents=False,
        preprocess_ignore_numbers=False,
        preprocess_ignore_custom_characters=False,
        preprocess_custom_characters_to_ignore="",
    )


def test_extract_reading_prefers_reading_field_when_configured() -> None:
    am_config = _dummy_config()
    config_filter = SimpleNamespace(reading_priority=READING_PRIORITY_READING_FIRST)
    card_data = SimpleNamespace(
        reading="ソバ ガワ",
        furigana="側[そば]",
        expression="側[がわ]",
    )

    reading = _extract_reading(am_config, config_filter, card_data)

    assert reading == "そば がわ"


def test_extract_reading_prefers_furigana_by_default() -> None:
    am_config = _dummy_config()
    config_filter = SimpleNamespace(reading_priority=READING_PRIORITY_FURIGANA_FIRST)
    card_data = SimpleNamespace(
        reading="ソバ",
        furigana="側[そば]",
        expression="側[がわ]",
    )

    reading = _extract_reading(am_config, config_filter, card_data)

    assert reading == "そば"


def test_extract_reading_falls_back_to_furigana_field() -> None:
    am_config = _dummy_config()
    config_filter = SimpleNamespace(reading_priority=READING_PRIORITY_FURIGANA_FIRST)
    card_data = SimpleNamespace(
        reading="",
        furigana="側[がわ]",
        expression="側",
    )

    reading = _extract_reading(am_config, config_filter, card_data)

    assert reading == "がわ"


def test_extract_reading_uses_expression_when_no_furigana_field() -> None:
    am_config = _dummy_config()
    config_filter = SimpleNamespace(reading_priority=READING_PRIORITY_FURIGANA_FIRST)
    card_data = SimpleNamespace(
        reading="",
        furigana="",
        expression="側[そば]",
    )

    reading = _extract_reading(am_config, config_filter, card_data)

    assert reading == "そば"
