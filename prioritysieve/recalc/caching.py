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
    candidates: list[str] = []

    if card_data.reading:
        processed = get_processed_text(am_config, card_data.reading).strip()
        if processed:
            candidates.append(processed)

    if card_data.furigana:
        tokens = parse_furigana_field(card_data.furigana)
        if tokens:
            candidates.append("".join(tokens))

    if config_filter.reading_priority != READING_PRIORITY_FURIGANA_FIRST:
        candidates = list(reversed(candidates))

    for candidate in candidates:
        normalised = normalize_reading(candidate.strip())
        if normalised:
            return normalised

    return ""
