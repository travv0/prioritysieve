from __future__ import annotations

import pytest

import importlib

priority_gap_utils = importlib.import_module("prioritysieve.priority_gap_utils")
Entry = importlib.import_module("prioritysieve.entry").Entry


def test_find_missing_priority_entries_respects_priority_order(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        Entry(text="known", reading="", language_name="Japanese", reviewed=True),
        Entry(text="lemmaOnly", reading="テスト", language_name="Japanese", reviewed=False),
    ]

    priorities: dict[tuple[str, str], int] = {
        ("known", ""): 1,
        ("missing", ""): 5,
        ("missingExact", "abc"): 2,
        ("lemmaOnly", ""): 3,
        ("kana", ""): 4,
        ("kana", "kana"): 4,
        ("kanji", ""): 6,
        ("kanji", "かな"): 3,
    }

    monkeypatch.setattr(
        priority_gap_utils,
        "load_priority_map",
        lambda files: priorities,
        raising=False,
    )

    missing = priority_gap_utils.find_missing_priority_entries(
        entries=entries,
        priority_files=["ignored"],
    )

    assert missing == [
        ("missingExact", "abc", 2),
        ("kanji", "かな", 3),
        ("kana", "", 4),
        ("missing", "", 5),
    ]


def test_find_missing_priority_entries_suppresses_fallback_when_readings_present(monkeypatch: pytest.MonkeyPatch) -> None:
    entries: list[Entry] = []
    priorities: dict[tuple[str, str], int] = {
        ("word", ""): 10,
        ("word", "かな"): 5,
    }

    monkeypatch.setattr(
        priority_gap_utils,
        "load_priority_map",
        lambda files: priorities,
        raising=False,
    )

    missing = priority_gap_utils.find_missing_priority_entries(
        entries=entries,
        priority_files=["ignored"],
    )

    assert missing == [("word", "かな", 5)]


def test_find_missing_priority_entries_includes_fallback_when_no_readings(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [Entry(text="covered", reading="", language_name="Japanese", reviewed=False)]
    priorities: dict[tuple[str, str], int] = {
        ("covered", ""): 3,
        ("unused", ""): 4,
    }

    monkeypatch.setattr(
        priority_gap_utils,
        "load_priority_map",
        lambda files: priorities,
        raising=False,
    )

    missing = priority_gap_utils.find_missing_priority_entries(
        entries=entries,
        priority_files=["ignored"],
    )

    assert missing == [("unused", "", 4)]
