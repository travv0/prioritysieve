from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from aqt import mw

from .. import prioritysieve_globals as am_globals
from .. import progress_utils
from ..prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from ..prioritysieve_db import PrioritySieveDB
from ..exceptions import CancelledOperationException, KnownMorphsFileMalformedException
from ..morphemizers import morphemizer_utils
from ..reading_utils import normalize_reading, parse_furigana_field
from ..text_preprocessing import get_processed_text
from . import anki_data_utils
from .anki_data_utils import AnkiCardData


def cache_anki_data(  # pylint:disable=too-many-locals, too-many-branches, too-many-statements
    am_config: PrioritySieveConfig,
    read_enabled_config_filters: list[PrioritySieveConfigFilter],
) -> None:
    # Extracting morphs from cards is expensive, so caching them yields a significant
    # performance gain.
    #
    # Note: this function is a monstrosity, but at some point it's better to have
    # most of the logic in the same function in a way that gives a better overview
    # of all the things that are happening. Refactoring this into even smaller pieces
    # will in effect lead to spaghetti code.

    assert mw is not None

    # Rebuilding the entire prioritysieve db every time is faster and much simpler than
    # updating it since we can bulk queries to the anki db.
    am_db = PrioritySieveDB()
    am_db.drop_all_tables()
    am_db.create_all_tables()

    # These lists contain data that will be inserted into prioritysieve.db
    card_table_data: list[dict[str, Any]] = []
    morph_table_data: list[dict[str, Any]] = []
    card_morph_map_table_data: list[dict[str, Any]] = []

    # We only want to cache the morphs on the note-filters that have 'read' enabled
    for config_filter in read_enabled_config_filters:
        cards_data_dict: dict[int, AnkiCardData] = (
            anki_data_utils.create_card_data_dict(
                am_config,
                config_filter,
            )
        )
        card_amount = len(cards_data_dict)

        # Batching the text makes spacy much faster, so we flatten the data into the all_text list.
        # To get back to the card_id for every entry in the all_text list, we create a separate list with the keys.
        # These two lists have to be synchronized, i.e., the indexes align, that way they can be used for lookup later.
        all_text: list[str] = []
        all_keys: list[int] = []

        for key, _card_data in cards_data_dict.items():
            # Some spaCy models label all capitalized words as proper nouns,
            # which is pretty bad. To prevent this, we lower case everything.
            # This in turn makes some models not label proper nouns correctly,
            # but this is preferable because we also have the 'Mark as Name'
            # feature that can be used in that case.
            expression = get_processed_text(am_config, _card_data.expression.lower())
            all_text.append(expression)
            all_keys.append(key)

        morphemizer = morphemizer_utils.get_morphemizer_by_description(
            config_filter.morphemizer_description
        )
        assert morphemizer is not None

        for index, processed_morphs in enumerate(
            morphemizer.get_processed_morphs(am_config, all_text)
        ):
            progress_utils.background_update_progress_potentially_cancel(
                label=f"Extracting morphs from<br>{config_filter.note_type} cards<br>card: {index} of {card_amount}",
                counter=index,
                max_value=card_amount,
            )
            key = all_keys[index]
            morphs_with_readings = _assign_readings_to_morphs(
                am_config=am_config,
                card_data=cards_data_dict[key],
                processed_morphs=processed_morphs,
            )
            cards_data_dict[key].morphs = set(morphs_with_readings)

        for counter, card_id in enumerate(cards_data_dict):
            progress_utils.background_update_progress_potentially_cancel(
                label=f"Caching {config_filter.note_type} cards<br>card: {counter} of {card_amount}",
                counter=counter,
                max_value=card_amount,
            )
            card_data: AnkiCardData = cards_data_dict[card_id]

            if card_data.automatically_known_tag or card_data.manually_known_tag:
                highest_interval = am_config.interval_for_known_morphs
            elif card_data.type == 1:  # 1: learning
                # cards in the 'learning' state have an interval of zero, but we don't
                # want to treat them as 'unknown', so we change the value manually.
                highest_interval = 1
            else:
                highest_interval = card_data.interval

            card_table_data.append(
                {
                    "card_id": card_id,
                    "note_id": card_data.note_id,
                    "note_type_id": card_data.note_type_id,
                    "card_type": card_data.type,
                    "tags": card_data.tags,
                }
            )

            if card_data.morphs is None:
                continue

            for morph in card_data.morphs:
                morph_table_data.append(
                    {
                        "lemma": morph.lemma,
                        "inflection": morph.inflection,
                        "reading": normalize_reading(morph.reading),
                        "highest_lemma_learning_interval": None,  # updates later
                        "highest_inflection_learning_interval": highest_interval,
                    }
                )
                card_morph_map_table_data.append(
                    {
                        "card_id": card_id,
                        "morph_lemma": morph.lemma,
                        "morph_inflection": morph.inflection,
                        "morph_reading": normalize_reading(morph.reading),
                    }
                )

    if am_config.read_known_morphs_folder is True:
        progress_utils.background_update_progress(label="Importing known morphs")
        morph_table_data += _get_morphs_from_files(am_config)

    progress_utils.background_update_progress(label="Updating learning intervals")
    _update_learning_intervals(am_config, morph_table_data)

    progress_utils.background_update_progress(label="Saving to prioritysieve.db")
    am_db.insert_many_into_morph_table(morph_table_data)
    am_db.insert_many_into_card_table(card_table_data)
    am_db.insert_many_into_card_morph_map_table(card_morph_map_table_data)
    # am_db.print_table("Morphs")
    am_db.con.close()


def _assign_readings_to_morphs(
    am_config: PrioritySieveConfig,
    card_data: AnkiCardData,
    processed_morphs: list[Morpheme],
) -> list[Morpheme]:
    if not processed_morphs:
        return processed_morphs

    furigana_tokens = (
        parse_furigana_field(card_data.furigana)
        if card_data.furigana
        else []
    )

    combined_furigana = "".join(furigana_tokens)
    if combined_furigana:
        combined_furigana = combined_furigana.lower()
        combined_furigana = get_processed_text(am_config, combined_furigana)
        combined_furigana = normalize_reading(combined_furigana.strip())
        furigana_tokens = [combined_furigana] if combined_furigana else []
    else:
        furigana_tokens = []

    raw_reading_tokens: list[str] = []
    if card_data.reading:
        stripped = card_data.reading.strip()
        if stripped:
            parts = stripped.split()
            if not parts:
                parts = [stripped]
            raw_reading_tokens = [
                get_processed_text(am_config, part.lower()) for part in parts
            ]
            raw_reading_tokens = [normalize_reading(token) for token in raw_reading_tokens]
            raw_reading_tokens = [token for token in raw_reading_tokens if token]

    tokens = furigana_tokens if furigana_tokens else raw_reading_tokens

    if not tokens:
        if len(processed_morphs) == 1 and card_data.expression:
            fallback = get_processed_text(
                am_config, card_data.expression.lower()
            ).strip()
            if fallback:
                tokens = [fallback]

    if not tokens:
        return processed_morphs

    if len(tokens) == len(processed_morphs):
        pairs = zip(processed_morphs, tokens)
    elif len(tokens) == 1:
        pairs = ((morph, tokens[0]) for morph in processed_morphs)
    else:
        if len(processed_morphs) == 1:
            joined = "".join(tokens)
            pairs = ((processed_morphs[0], joined),)
        else:
            pairs = zip(processed_morphs, tokens)

    for morph, reading in pairs:
        normalized = normalize_reading(reading)
        if not normalized:
            continue

        existing = normalize_reading(morph.reading)
        if existing and normalized.startswith(existing) and len(normalized) > len(existing):
            continue

        morph.reading = normalized

    return processed_morphs


def _get_morphs_from_files(am_config: PrioritySieveConfig) -> list[dict[str, Any]]:
    assert mw is not None

    morphs_from_files: list[dict[str, Any]] = []
    input_files: list[Path] = _get_known_morphs_files()

    for input_file in input_files:
        if mw.progress.want_cancel():  # user clicked 'x'
            raise CancelledOperationException

        progress_utils.background_update_progress(
            label=f"Importing known morphs from file:<br>{input_file.name}",
        )

        with open(input_file, encoding="utf-8") as csvfile:
            morph_reader = csv.reader(csvfile, delimiter=",")
            headers: list[str] | None = next(morph_reader, None)

            lemma_column_index, inflection_column_index, reading_column_index = (
                _get_lemma_and_inflection_columns(
                    input_file_path=input_file, headers=headers
                )
            )

            if inflection_column_index == -1:
                morphs_from_files += _get_morphs_from_minimum_format(
                    am_config,
                    morph_reader,
                    lemma_column=lemma_column_index,
                    reading_column=reading_column_index,
                )
            else:
                morphs_from_files += _get_morphs_from_full_format(
                    am_config,
                    morph_reader,
                    lemma_column=lemma_column_index,
                    inflection_column=inflection_column_index,
                    reading_column=reading_column_index,
                )

    return morphs_from_files


def _get_known_morphs_files() -> list[Path]:
    assert mw is not None
    input_files: list[Path] = []
    known_morphs_dir_path: Path = Path(
        mw.pm.profileFolder(), am_globals.KNOWN_MORPHS_DIR_NAME
    )
    for path in known_morphs_dir_path.rglob("*.csv"):
        input_files.append(path)
    return input_files


def _get_lemma_and_inflection_columns(
    input_file_path: Path, headers: list[str] | None
) -> tuple[int, int, int | None]:
    if headers is None:
        raise KnownMorphsFileMalformedException(input_file_path)

    # we lower case the headers to make it backwards
    # compatible with 'known morphs' files from PrioritySieve v2
    headers_lower = [header.lower() for header in headers]

    if am_globals.LEMMA_HEADER.lower() not in headers_lower:
        raise KnownMorphsFileMalformedException(input_file_path)

    lemma_column_index: int = headers_lower.index(am_globals.LEMMA_HEADER.lower())
    inflection_column_index: int = -1

    try:
        inflection_column_index = headers_lower.index(
            am_globals.INFLECTION_HEADER.lower()
        )
    except ValueError:
        # ValueError just means it's not a full format file, which
        # we handle later, so this can safely be ignored.
        pass

    reading_column_index: int | None = None
    try:
        reading_column_index = headers_lower.index(am_globals.READING_HEADER.lower())
    except ValueError:
        pass

    return lemma_column_index, inflection_column_index, reading_column_index


def _get_morphs_from_minimum_format(
    am_config: PrioritySieveConfig,
    morph_reader: Any,
    lemma_column: int,
    reading_column: int | None,
) -> list[dict[str, Any]]:
    morphs_from_files: list[dict[str, Any]] = []

    for row in morph_reader:
        lemma: str = row[lemma_column]
        reading = normalize_reading(
            row[reading_column] if reading_column is not None and reading_column < len(row) else None
        )
        morphs_from_files.append(
            {
                "lemma": lemma,
                "inflection": lemma,
                "reading": reading,
                "highest_lemma_learning_interval": am_config.interval_for_known_morphs,
                "highest_inflection_learning_interval": am_config.interval_for_known_morphs,
            }
        )
    return morphs_from_files


def _get_morphs_from_full_format(
    am_config: PrioritySieveConfig,
    morph_reader: Any,
    lemma_column: int,
    inflection_column: int,
    reading_column: int | None,
) -> list[dict[str, Any]]:
    morphs_from_files: list[dict[str, Any]] = []

    for row in morph_reader:
        lemma: str = row[lemma_column]
        inflection: str = row[inflection_column]
        reading = normalize_reading(
            row[reading_column] if reading_column is not None and reading_column < len(row) else None
        )
        morphs_from_files.append(
            {
                "lemma": lemma,
                "inflection": inflection,
                "reading": reading,
                "highest_lemma_learning_interval": am_config.interval_for_known_morphs,
                "highest_inflection_learning_interval": am_config.interval_for_known_morphs,
            }
        )
    return morphs_from_files


def _update_learning_intervals(
    am_config: PrioritySieveConfig, morph_table_data: list[dict[str, Any]]
) -> None:
    learning_intervals_of_lemmas: dict[tuple[str, str], int] = (
        _get_learning_intervals_of_lemmas(morph_table_data)
    )

    if am_config.evaluate_morph_lemma:
        # update both the lemma and inflection intervals
        for morph_data_dict in morph_table_data:
            lemma = morph_data_dict["lemma"]
            reading_key = normalize_reading(morph_data_dict.get("reading"))
            interval = learning_intervals_of_lemmas.get((lemma, reading_key))
            if interval is None and reading_key:
                interval = learning_intervals_of_lemmas.get((lemma, ""))
            if interval is None:
                interval = 0
            morph_data_dict["highest_lemma_learning_interval"] = interval
            morph_data_dict["highest_inflection_learning_interval"] = interval
    else:
        # only update lemma intervals
        for morph_data_dict in morph_table_data:
            lemma = morph_data_dict["lemma"]
            reading_key = normalize_reading(morph_data_dict.get("reading"))
            interval = learning_intervals_of_lemmas.get((lemma, reading_key))
            if interval is None and reading_key:
                interval = learning_intervals_of_lemmas.get((lemma, ""))
            if interval is None:
                interval = 0
            morph_data_dict["highest_lemma_learning_interval"] = interval


def _get_learning_intervals_of_lemmas(
    morph_table_data: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    learning_intervals_of_lemmas: dict[tuple[str, str], int] = {}

    for morph_data_dict in morph_table_data:
        lemma = morph_data_dict["lemma"]
        inflection_interval = morph_data_dict["highest_inflection_learning_interval"]
        reading_key = normalize_reading(morph_data_dict.get("reading"))
        key = (lemma, reading_key)

        existing = learning_intervals_of_lemmas.get(key)
        if existing is None or inflection_interval > existing:
            learning_intervals_of_lemmas[key] = inflection_interval

        if reading_key:
            fallback_key = (lemma, "")
            fallback_existing = learning_intervals_of_lemmas.get(fallback_key)
            if fallback_existing is None or inflection_interval > fallback_existing:
                learning_intervals_of_lemmas[fallback_key] = inflection_interval

    return learning_intervals_of_lemmas
