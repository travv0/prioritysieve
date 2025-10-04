from __future__ import annotations

import pytest

from prioritysieve import priority_gap_utils
from prioritysieve.morpheme import Morpheme


class DummyDB:
    def __init__(self, morphs: dict[int, list[Morpheme]]) -> None:
        self._morphs = morphs

    def get_card_morph_map_cache(self) -> dict[int, list[Morpheme]]:
        return self._morphs


@pytest.fixture
def dummy_db() -> DummyDB:
    card_morphs = {
        1: [Morpheme(lemma="known", inflection="known", reading=None)],
        2: [Morpheme(lemma="lemmaOnly", inflection="lemmaOnly", reading="テスト")],
    }
    return DummyDB(card_morphs)


def test_find_missing_priority_entries_respects_priority_order(monkeypatch: pytest.MonkeyPatch, dummy_db: DummyDB) -> None:
    priorities: dict[tuple[str, str, str], int] = {
        ("known", "known", ""): 1,
        ("missing", "missing", ""): 5,
        ("missingExact", "missingExact", "abc"): 2,
        ("lemmaOnly", "lemmaOnly", ""): 3,
        ("kana", "kana", ""): 4,
        ("kana", "kana", "kana"): 4,
    }

    monkeypatch.setattr(
        priority_gap_utils,
        "get_morph_priority",
        lambda am_db, morph_priority_selection: priorities,
        raising=False,
    )

    missing = priority_gap_utils.find_missing_priority_entries(
        am_db=dummy_db,
        morph_priority_selection=["ignored"],
    )

    assert missing == [
        ("missingExact", "abc", 2),
        ("kana", "", 4),
        ("missing", "", 5),
    ]
