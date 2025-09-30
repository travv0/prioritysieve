from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aqt import mw

from . import prioritysieve_globals as ps_globals
from .exceptions import PriorityFileMalformedException, PriorityFileNotFoundException
from .prioritysieve_db import PrioritySieveDB
from .reading_utils import normalize_reading


@dataclass
class PriorityFileMeta:
    lemma_index: int
    reading_index: int | None
    priority_index: int | None


def get_priority_files() -> list[str]:
    assert mw is not None
    base_path = Path(mw.pm.profileFolder(), ps_globals.PRIORITY_FILES_DIR_NAME)
    return [file.name for file in base_path.glob('*.csv') if file.is_file()]


def get_morph_priority(
    am_db: PrioritySieveDB,
    morph_priority_selection: Iterable[str] | str,
) -> dict[tuple[str, str, str], int]:
    selections = _normalize_priority_selections(morph_priority_selection)

    merged_priorities: dict[tuple[str, str, str], int] = {}

    if ps_globals.COLLECTION_FREQUENCY_OPTION in selections:
        _merge_priorities(
            merged_priorities, am_db.get_morph_priorities_from_collection()
        )

    for selection in selections:
        if selection in (
            ps_globals.COLLECTION_FREQUENCY_OPTION,
            ps_globals.NONE_OPTION,
        ):
            continue

        file_priorities = _load_morph_priorities_from_file(selection)
        _merge_priorities(merged_priorities, file_priorities)

    return merged_priorities


def _normalize_priority_selections(
    morph_priority_selection: Iterable[str] | str,
) -> list[str]:
    if isinstance(morph_priority_selection, str):
        candidates = [morph_priority_selection]
    else:
        candidates = list(morph_priority_selection)

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        selection = candidate.strip()
        if not selection or selection == ps_globals.NONE_OPTION:
            continue
        if selection in seen:
            continue
        seen.add(selection)
        normalized.append(selection)

    return normalized


def _load_morph_priorities_from_file(
    priority_file_name: str,
) -> dict[tuple[str, str, str], int]:
    assert mw is not None
    priority_file_path = Path(
        mw.pm.profileFolder(),
        ps_globals.PRIORITY_FILES_DIR_NAME,
        priority_file_name,
    )

    try:
        with open(priority_file_path, encoding='utf-8') as csvfile:
            morph_reader = csv.reader(csvfile, delimiter=',')
            headers = next(morph_reader, None)
            meta = _parse_headers(priority_file_path, headers)
            return _extract_priorities(priority_file_path, morph_reader, meta)
    except FileNotFoundError as exc:
        raise PriorityFileNotFoundException(str(priority_file_path)) from exc


def _parse_headers(
    priority_file_path: Path,
    headers: list[str] | None,
) -> PriorityFileMeta:
    if not headers:
        raise PriorityFileMalformedException(
            path=str(priority_file_path),
            reason='Priority file does not have headers.',
        )

    if ps_globals.LEMMA_HEADER not in headers:
        raise PriorityFileMalformedException(
            path=str(priority_file_path),
            reason=f"Priority file is missing the '{ps_globals.LEMMA_HEADER}' header",
        )

    lemma_index = headers.index(ps_globals.LEMMA_HEADER)
    reading_index = (
        headers.index(ps_globals.READING_HEADER)
        if ps_globals.READING_HEADER in headers
        else None
    )
    priority_index = (
        headers.index(ps_globals.LEMMA_PRIORITY_HEADER)
        if ps_globals.LEMMA_PRIORITY_HEADER in headers
        else None
    )

    return PriorityFileMeta(
        lemma_index=lemma_index,
        reading_index=reading_index,
        priority_index=priority_index,
    )


def _extract_priorities(
    source_path: Path,
    morph_reader: Iterable[list[str]],
    meta: PriorityFileMeta,
) -> dict[tuple[str, str, str], int]:
    priorities: dict[tuple[str, str, str], int] = {}

    for index, row in enumerate(morph_reader):
        if meta.lemma_index >= len(row):
            raise PriorityFileMalformedException(
                path=str(source_path),
                reason='Row is missing lemma column.',
            )

        lemma = row[meta.lemma_index].strip()
        reading = ''
        if meta.reading_index is not None and meta.reading_index < len(row):
            reading = normalize_reading(row[meta.reading_index])

        if not lemma:
            continue

        if meta.priority_index is not None and meta.priority_index < len(row):
            priority_str = row[meta.priority_index].strip()
            if not priority_str:
                raise PriorityFileMalformedException(
                    path=str(source_path),
                    reason='Priority column contains an empty value.',
                )
            try:
                priority = int(priority_str)
            except ValueError as exc:
                raise PriorityFileMalformedException(
                    path=str(source_path),
                    reason=f"Priority '{priority_str}' is not an integer.",
                ) from exc
        else:
            priority = index

        key = (lemma, lemma, reading)
        existing = priorities.get(key)
        if existing is None or priority < existing:
            priorities[key] = priority

        if reading:
            fallback_key = (lemma, lemma, '')
            fallback_existing = priorities.get(fallback_key)
            if fallback_existing is None or priority < fallback_existing:
                priorities[fallback_key] = priority

    return priorities


def _merge_priorities(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, priority in source.items():
        existing = target.get(key)
        if existing is None or priority < existing:
            target[key] = priority
