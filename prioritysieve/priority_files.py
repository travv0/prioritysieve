from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from aqt import mw

from . import prioritysieve_globals
from .reading_utils import expand_long_vowel_variants, normalize_reading

DEFAULT_PRIORITY_DIR = "prioritysieve-priority-files"
KNOWN_ENTRIES_DIR = "prioritysieve-known-entries"

ENTRY_HEADERS = ("Entry", "Lemma", "Morph-Lemma")
READING_HEADERS = ("Reading", "Lemma-Reading", "Morph-Reading")
PRIORITY_HEADERS = ("Priority", "Entry-Priority", "Lemma-Priority")


def ensure_directories() -> None:
    assert mw is not None
    base = Path(mw.pm.profileFolder())
    (base / prioritysieve_globals.PRIORITY_FILES_DIR_NAME).mkdir(exist_ok=True)
    (base / KNOWN_ENTRIES_DIR).mkdir(exist_ok=True)


def available_priority_files() -> list[str]:
    assert mw is not None
    directory = Path(mw.pm.profileFolder()) / prioritysieve_globals.PRIORITY_FILES_DIR_NAME
    if not directory.exists():
        return []
    return sorted(file.name for file in directory.glob("*.csv"))


def load_priority_map(priority_files: Iterable[str]) -> dict[tuple[str, str], int]:
    assert mw is not None
    directory = Path(mw.pm.profileFolder()) / prioritysieve_globals.PRIORITY_FILES_DIR_NAME
    merged: dict[tuple[str, str], int] = {}

    for name in priority_files:
        sanitized = name.strip()
        if not sanitized:
            continue
        path = directory / sanitized
        if not path.is_file():
            continue
        for key, value in _read_priority_file(path):
            text, reading = key
            for variant in expand_long_vowel_variants(reading):
                variant_key = (text, variant)
                existing = merged.get(variant_key)
                if existing is None or value < existing:
                    merged[variant_key] = value

    return merged


def _read_priority_file(path: Path) -> Iterable[tuple[tuple[str, str], int]]:
    with path.open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        headers = next(reader, [])
        text_index = _find_header(headers, ENTRY_HEADERS)
        if text_index is None:
            raise ValueError(f"Priority file {path} has no entry column")
        reading_index = _find_header(headers, READING_HEADERS)
        priority_index = _find_header(headers, PRIORITY_HEADERS)

        for idx, row in enumerate(reader):
            if text_index >= len(row):
                continue
            text = row[text_index].strip()
            if not text:
                continue
            reading: str = ""
            if reading_index is not None and reading_index < len(row):
                reading = normalize_reading(row[reading_index].strip())
            if priority_index is not None and priority_index < len(row):
                priority_str = row[priority_index].strip()
                try:
                    priority = int(priority_str)
                except ValueError:
                    priority = idx
            else:
                priority = idx
            yield (text, reading), priority


def _find_header(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    lower = {header.strip().lower(): i for i, header in enumerate(headers)}
    for candidate in candidates:
        match = lower.get(candidate.lower())
        if match is not None:
            return match
    return None
