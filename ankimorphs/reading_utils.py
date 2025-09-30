from __future__ import annotations

import re

_KATAKANA_TO_HIRAGANA = str.maketrans(
    {chr(code_point): chr(code_point - 0x60) for code_point in range(ord("ァ"), ord("ヺ") + 1)}
)

_WHITESPACE_RE = re.compile(r"\s+")
_FURIGANA_PAIR_RE = re.compile(r"([^\[\]]+)\[([^\]]*)\]")


def normalize_reading(reading: str | None) -> str:
    if reading is None:
        return ""
    return reading.translate(_KATAKANA_TO_HIRAGANA)


def strip_furigana_token(token: str) -> str:
    """Replace every base+reading pair such as 食[た] with the reading `た`."""

    def _replace(match: re.Match[str]) -> str:
        reading = match.group(2)
        return reading if reading else match.group(1)

    stripped = _FURIGANA_PAIR_RE.sub(_replace, token)
    return stripped.replace("[", "").replace("]", "")


def parse_furigana_field(field_text: str) -> list[str]:
    stripped_text = field_text.strip()
    if not stripped_text:
        return []

    readings: list[str] = []
    for token in _WHITESPACE_RE.split(stripped_text):
        if token == "":
            continue
        stripped = strip_furigana_token(token)
        readings.append(normalize_reading(stripped))

    return readings
