from __future__ import annotations


def is_kanji(char: str) -> bool:
    """Return True when ``char`` is a CJK ideograph (incl. iteration mark)."""

    return (
        "\u4e00" <= char <= "\u9fff"
        or "\u3400" <= char <= "\u4dbf"
        or char == "々"
    )


def extract_kanji_sequence(text: str) -> str:
    """Return a string containing only the kanji characters from ``text``."""

    return "".join(char for char in text if is_kanji(char))


def is_kanji_subsequence(candidate: str, target: str) -> bool:
    """Return True when ``candidate`` is a subsequence of ``target``."""

    if len(candidate) > len(target):
        return False
    if not candidate:
        return True

    index = 0
    for char in target:
        if char == candidate[index]:
            index += 1
            if index == len(candidate):
                return True
    return index == len(candidate)


def has_kanji_subsequence_relation(left: str, right: str) -> bool:
    """Return True when ``left`` and ``right`` share a subsequence relation."""

    return is_kanji_subsequence(left, right) or is_kanji_subsequence(right, left)


def contains_hiragana(text: str) -> bool:
    """Return True when ``text`` contains any hiragana characters."""

    return any("ぁ" <= char <= "ゖ" for char in text)


def contains_katakana(text: str) -> bool:
    """Return True when ``text`` contains any katakana characters."""

    return any(("ァ" <= char <= "ヺ") or ("\uff66" <= char <= "\uff9f") for char in text)


def contains_kana(text: str) -> bool:
    """Return True when ``text`` contains at least one kana character."""

    return contains_hiragana(text) or contains_katakana(text)
