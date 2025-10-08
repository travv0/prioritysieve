from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from anki.consts import CARD_TYPE_NEW
from aqt import mw

from ..entry import Entry
from ..entry_db import EntryDB
from ..priority_files import ensure_directories
from ..reading_utils import normalize_reading, parse_furigana_field
from ..text_preprocessing import get_processed_text
from ..prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from ..prioritysieve_globals import READING_PRIORITY_FURIGANA_FIRST
from .anki_data_utils import create_card_data_dict


def cache_entries(
    am_config: PrioritySieveConfig,
    filters: Iterable[PrioritySieveConfigFilter],
) -> None:
    """Collect cards for provided filters and rebuild the entry cache."""

    assert mw is not None

    entries: dict[int, Entry] = OrderedDict()
    cards_rows: dict[int, dict[str, object]] = OrderedDict()
    card_entry_rows: dict[int, tuple[str, str]] = OrderedDict()

    for config_filter in filters:
        card_data_dict = create_card_data_dict(am_config, config_filter)
        for card_id, card_data in card_data_dict.items():
            entry = _build_entry(am_config, config_filter, card_data)
            entries[card_id] = entry

            cards_rows[card_id] = {
                "card_id": card_id,
                "note_id": card_data.note_id,
                "note_type_id": card_data.note_type_id,
                "card_type": card_data.type,
                "tags": card_data.tags,
            }
            card_entry_rows[card_id] = entry.key()

    ensure_directories()
    with EntryDB() as db:
        entry_rows = _collapse_entries(entries.values())
        db.replace_data(
            entries=entry_rows,
            cards=cards_rows.values(),
            card_entries=(
                {
                    "card_id": card_id,
                    "entry_text": key[0],
                    "entry_reading": key[1],
                }
                for card_id, key in card_entry_rows.items()
            ),
        )


def _collapse_entries(entries: Iterable[Entry]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str], dict[str, object]] = {}
    for entry in entries:
        key = entry.key()
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = {
                "text": entry.text,
                "reading": entry.reading,
                "reviewed": int(entry.reviewed),
            }
        elif entry.reviewed and not existing["reviewed"]:
            existing["reviewed"] = 1
    return list(by_key.values())


def _build_entry(
    am_config: PrioritySieveConfig,
    config_filter: PrioritySieveConfigFilter,
    card_data,
) -> Entry:
    text = _normalise_expression(am_config, card_data.expression)
    reading = _extract_reading(am_config, config_filter, card_data)

    reviewed = (
        card_data.type != CARD_TYPE_NEW
        or card_data.automatically_known_tag
        or card_data.manually_known_tag
    )

    return Entry(text=text, reading=reading, reviewed=reviewed)


def _normalise_expression(am_config: PrioritySieveConfig, expression: str) -> str:
    processed = get_processed_text(am_config, expression).strip()
    return processed or expression.strip() or "<blank>"


def _extract_reading(
    am_config: PrioritySieveConfig,
    config_filter: PrioritySieveConfigFilter,
    card_data,
) -> str:
    def _normalise_reading_field(value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return ""

        parts = stripped.split()
        if not parts:
            parts = [stripped]

        normalised_parts: list[str] = []
        for part in parts:
            processed = get_processed_text(am_config, part.lower()).strip()
            if not processed:
                continue
            normalised = normalize_reading(processed)
            if normalised:
                normalised_parts.append(normalised)

        return " ".join(normalised_parts).strip()

    def _normalise_furigana_source(value: str) -> str:
        tokens = parse_furigana_field(value)
        if not tokens:
            return ""

        combined = "".join(tokens)
        if not combined:
            return ""

        combined = get_processed_text(am_config, combined.lower()).strip()
        if not combined:
            return ""

        return normalize_reading(combined)

    reading_candidates: list[str] = []
    if getattr(card_data, "reading", None):
        candidate = _normalise_reading_field(card_data.reading)
        if candidate:
            reading_candidates.append(candidate)

    furigana_candidates: list[str] = []

    primary_furigana_source = getattr(card_data, "furigana", None)
    if primary_furigana_source:
        candidate = _normalise_furigana_source(primary_furigana_source)
        if candidate:
            furigana_candidates.append(candidate)

    if not furigana_candidates and getattr(card_data, "expression", None):
        candidate = _normalise_furigana_source(card_data.expression)
        if candidate:
            furigana_candidates.append(candidate)

    if config_filter.reading_priority == READING_PRIORITY_FURIGANA_FIRST:
        ordered_candidates = furigana_candidates + reading_candidates
    else:
        ordered_candidates = reading_candidates + furigana_candidates

    for candidate in ordered_candidates:
        if candidate:
            return candidate.strip()

    return ""
