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


def _split_prefix(prefix: str) -> tuple[str, str]:
    if not prefix:
        return "", ""

    replace_start = len(prefix)
    while replace_start > 0:
        char = prefix[replace_start - 1]
        if _is_replaced_char(char):
            replace_start -= 1
        else:
            break

    if replace_start == len(prefix):
        return prefix, ""

    return prefix[:replace_start], prefix[replace_start:]


def _is_replaced_char(char: str) -> bool:
    if char.isspace():
        return False
    return not (
        "\u3041" <= char <= "\u309f"  # hiragana
        or "\uff65" <= char <= "\uff9f"  # half-width katakana
    )


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
        if normalized:
            readings.append(normalized)

    return readings
