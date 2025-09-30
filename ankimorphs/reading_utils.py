from __future__ import annotations

import re

_KATAKANA_TO_HIRAGANA = str.maketrans(
    {chr(code_point): chr(code_point - 0x60) for code_point in range(ord("ァ"), ord("ヺ") + 1)}
)

_WHITESPACE_RE = re.compile(r"\s+")


def _is_hiragana(char: str) -> bool:
    return "\u3041" <= char <= "\u309f"


def _is_katakana(char: str) -> bool:
    return ("\u30a0" <= char <= "\u30ff") or ("\uff66" <= char <= "\uff9f")


def _is_kanji(char: str) -> bool:
    return (
        "\u4e00" <= char <= "\u9fff"
        or "\u3400" <= char <= "\u4dbf"
        or char == "々"
    )


def _is_word_char(char: str) -> bool:
    return _is_hiragana(char) or _is_katakana(char) or _is_kanji(char) or char == "ー"


def normalize_reading(reading: str | None) -> str:
    if reading is None:
        return ""
    return reading.translate(_KATAKANA_TO_HIRAGANA)


def _only_hiragana(text: str) -> str:
    return "".join(ch for ch in text if _is_hiragana(ch) or ch == "ー")


def _split_prefix(prefix: str) -> tuple[str, str]:
    if not prefix:
        return "", ""

    end = len(prefix)
    start = end

    while start > 0 and _is_word_char(prefix[start - 1]):
        start -= 1

    chunk = prefix[start:]
    if not chunk:
        return prefix, ""

    first_kanji_index: int | None = None
    for idx, ch in enumerate(chunk):
        if _is_kanji(ch):
            first_kanji_index = idx
            break

    if first_kanji_index is not None:
        base_chunk = chunk[first_kanji_index:]
        prefix_to_keep = prefix[: start + first_kanji_index]
    else:
        base_chunk = chunk
        prefix_to_keep = prefix[:start]

    return prefix_to_keep, base_chunk


def strip_furigana_token(token: str) -> str:
    """Replace every base+reading pair such as 食[た] with the reading `た`."""

    result: list[str] = []
    index = 0
    length = len(token)

    while index < length:
        left_bracket = token.find("[", index)
        if left_bracket == -1:
            tail = token[index:]
            if tail:
                result.append(tail)
            break

        right_bracket = token.find("]", left_bracket + 1)
        if right_bracket == -1:
            result.append(token[index:])
            break

        prefix = token[index:left_bracket]
        prefix_to_keep, base_chunk = _split_prefix(prefix)

        if prefix_to_keep:
            result.append(prefix_to_keep)

        reading = token[left_bracket + 1 : right_bracket].strip()

        if reading:
            result.append(reading)
        else:
            result.append(base_chunk)

        index = right_bracket + 1

    return "".join(result)


def parse_furigana_field(field_text: str) -> list[str]:
    stripped_text = field_text.strip()
    if not stripped_text:
        return []

    tokens: list[str] = []
    current: list[str] = []
    depth = 0

    for char in stripped_text:
        if char == "[":
            depth += 1
            current.append(char)
            continue
        if char == "]":
            depth = max(depth - 1, 0)
            current.append(char)
            continue

        if char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue

        current.append(char)

    if current:
        tokens.append("".join(current))

    readings: list[str] = []
    for token in tokens:
        stripped = strip_furigana_token(token).strip()
        if not stripped:
            continue
        normalized = normalize_reading(stripped)
        normalized = _only_hiragana(normalized)
        if normalized:
            readings.append(normalized)

    return readings
