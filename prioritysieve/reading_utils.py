from __future__ import annotations

import re

_KATAKANA_TO_HIRAGANA = str.maketrans(
    {chr(code_point): chr(code_point - 0x60) for code_point in range(ord("ァ"), ord("ヺ") + 1)}
)

_WHITESPACE_RE = re.compile(r"\s+")

_HIRAGANA_VOWEL_MAP: dict[str, str] = {}


def _register_vowels(chars: str, vowel: str) -> None:
    for char in chars:
        _HIRAGANA_VOWEL_MAP[char] = vowel


_register_vowels("あかがさざただなはばぱまやゃらわぁゃゎゕゎ", "a")
_register_vowels("いきぎしじちぢにひびぴみりぃゐ", "i")
_register_vowels("うくぐすずつづぬふぶぷむゆゅるぅゔ", "u")
_register_vowels("えけげせぜてでねへべぺめれぇゑゖ", "e")
_register_vowels("おこごそぞとどのほぼぽもよょろをぉ", "o")


def _long_vowel_replacements_for_prefix(prefix: str) -> tuple[str, ...]:
    if not prefix:
        return ("ー",)

    vowel: str | None = None
    for char in reversed(prefix):
        vowel = _HIRAGANA_VOWEL_MAP.get(char)
        if vowel is not None:
            break
    if vowel is None:
        return ("ー",)

    replacements: list[str] = ["ー"]
    if vowel == "a":
        replacements.append("あ")
    elif vowel == "i":
        replacements.append("い")
    elif vowel == "u":
        replacements.append("う")
    elif vowel == "e":
        replacements.extend(["い", "え"])
    elif vowel == "o":
        replacements.extend(["う", "お"])

    # remove duplicates while keeping order
    return tuple(dict.fromkeys(replacements))


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


def _is_digit(char: str) -> bool:
    return char.isdigit()


def _is_latin_letter(char: str) -> bool:
    return (
        ("A" <= char <= "Z")
        or ("a" <= char <= "z")
        or ("\uff21" <= char <= "\uff3a")
        or ("\uff41" <= char <= "\uff5a")
    )


def _is_word_char(char: str) -> bool:
    return (
        _is_hiragana(char)
        or _is_katakana(char)
        or _is_kanji(char)
        or char == "ー"
        or _is_digit(char)
        or _is_latin_letter(char)
    )


def normalize_reading(reading: str | None) -> str:
    if reading is None:
        return ""
    return reading.translate(_KATAKANA_TO_HIRAGANA)


def expand_long_vowel_variants(reading: str) -> set[str]:
    """Return variants where long vowels may be written with kana instead of ー."""

    if not reading:
        return {""}

    variants: set[str] = {""}
    for char in reading:
        if char == "ー":
            replacement_options = None
        else:
            replacement_options = (char,)

        if replacement_options is None:
            replacements = []
            for prefix in variants:
                for repl in _long_vowel_replacements_for_prefix(prefix):
                    replacements.append(prefix + repl)
            variants = set(replacements)
            continue

        new_variants: set[str] = set()
        for prefix in variants:
            for replacement in replacement_options:
                new_variants.add(prefix + replacement)
        variants = new_variants

    return variants


def _extract_trailing_kana(text: str) -> str:
    """Return the trailing run of kana characters (and long vowels) in ``text``."""

    index = len(text)
    while index > 0:
        ch = text[index - 1]
        if _is_hiragana(ch) or _is_katakana(ch) or ch == "ー":
            index -= 1
            continue
        break
    return text[index:]


def _trim_duplicate_prefix(prefix: str, reading: str) -> str:
    """Remove kana duplicated between ``prefix`` and the start of ``reading``."""

    kana_suffix = _extract_trailing_kana(prefix)
    if not kana_suffix:
        return reading

    normalized_suffix = normalize_reading(kana_suffix)
    normalized_reading = normalize_reading(reading)

    if normalized_reading.startswith(normalized_suffix):
        return reading[len(normalized_suffix) :]

    return reading


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

    first_base_index: int | None = None
    for idx, ch in enumerate(chunk):
        if _is_kanji(ch) or _is_digit(ch) or _is_latin_letter(ch):
            first_base_index = idx
            break

    if first_base_index is not None:
        base_chunk = chunk[first_base_index:]
        prefix_to_keep = prefix[: start + first_base_index]
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
            trimmed_reading = _trim_duplicate_prefix(prefix_to_keep, reading)
            if trimmed_reading:
                result.append(trimmed_reading)
        else:
            result.append(base_chunk)

        index = right_bracket + 1

    return "".join(result)


def parse_furigana_field(field_text: str) -> list[str]:
    stripped_text = field_text.strip()
    if not stripped_text:
        return []

    if "[" not in stripped_text:
        return [normalize_reading(stripped_text)]

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
        readings.append(normalize_reading(stripped))

    return readings
