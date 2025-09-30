from __future__ import annotations

import re

_KATAKANA_TO_HIRAGANA = str.maketrans(
    {chr(code_point): chr(code_point - 0x60) for code_point in range(ord("ァ"), ord("ヺ") + 1)}
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_reading(reading: str | None) -> str:
    if reading is None:
        return ""
    return reading.translate(_KATAKANA_TO_HIRAGANA)


def strip_furigana_token(token: str) -> str:
    """Convert a furigana token like 食[た]べる into its reading."""

    result: list[str] = []
    index = 0
    length = len(token)

    while index < length:
        char = token[index]

        if index + 1 < length and token[index + 1] == "[":
            closing_index = token.find("]", index + 2)
            if closing_index != -1:
                reading = token[index + 2 : closing_index]
                result.append(reading if reading else char)
                index = closing_index + 1
                continue

        if char not in "[]":
            result.append(char)
        index += 1

    return "".join(result)


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
