from __future__ import annotations

from types import SimpleNamespace

from prioritysieve import prioritysieve_globals as am_globals
from prioritysieve.morpheme import Morpheme
from prioritysieve.recalc.caching import _assign_readings_to_morphs


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        preprocess_ignore_bracket_contents=False,
        preprocess_ignore_round_bracket_contents=False,
        preprocess_ignore_slim_round_bracket_contents=False,
        preprocess_ignore_angle_bracket_contents=False,
        preprocess_ignore_numbers=False,
        preprocess_ignore_custom_characters=False,
    )


def test_assign_readings_prefers_reading_when_configured() -> None:
    am_config = _make_config()
    morph = Morpheme(lemma="歩く", inflection="歩く")
    card_data = SimpleNamespace(
        furigana="歩[ある]く",
        reading="アルク",
        expression="歩く",
    )

    result = _assign_readings_to_morphs(
        am_config=am_config,
        card_data=card_data,
        processed_morphs=[morph],
        reading_priority=am_globals.READING_PRIORITY_READING_FIRST,
    )

    assert result[0].reading == "あるく"


def test_assign_readings_prefers_furigana_by_default() -> None:
    am_config = _make_config()
    morph = Morpheme(lemma="食べる", inflection="食べる")
    card_data = SimpleNamespace(
        furigana="食[た]べる",
        reading="タベル",
        expression="食べる",
    )

    result = _assign_readings_to_morphs(
        am_config=am_config,
        card_data=card_data,
        processed_morphs=[morph],
        reading_priority=am_globals.READING_PRIORITY_FURIGANA_FIRST,
    )

    assert result[0].reading == "たべる"


def test_assign_readings_falls_back_to_furigana_when_reading_missing() -> None:
    am_config = _make_config()
    morph = Morpheme(lemma="書く", inflection="書く")
    card_data = SimpleNamespace(
        furigana="書[か]く",
        reading="",
        expression="書く",
    )

    result = _assign_readings_to_morphs(
        am_config=am_config,
        card_data=card_data,
        processed_morphs=[morph],
        reading_priority=am_globals.READING_PRIORITY_READING_FIRST,
    )

    assert result[0].reading == "かく"

