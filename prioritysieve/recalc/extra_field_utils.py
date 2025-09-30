from __future__ import annotations

from anki.models import FieldDict, ModelManager, NotetypeDict
from anki.notes import Note
from aqt import mw

from .. import prioritysieve_config
from .. import prioritysieve_globals as ps_globals
from ..prioritysieve_config import PrioritySieveConfigFilter
from ..reading_utils import normalize_reading
from ..morpheme import Morpheme


def new_extra_fields_are_selected() -> bool:
    assert mw is not None

    model_manager: ModelManager = mw.col.models
    modify_enabled_config_filters: list[PrioritySieveConfigFilter] = (
        prioritysieve_config.get_modify_enabled_filters()
    )

    for config_filter in modify_enabled_config_filters:
        if not config_filter.extra_reading_field:
            continue

        note_type_dict: NotetypeDict | None = mw.col.models.by_name(
            config_filter.note_type
        )
        if note_type_dict is None:
            continue

        existing_field_names = model_manager.field_names(note_type_dict)
        if ps_globals.EXTRA_FIELD_READING not in existing_field_names:
            return True

    return False


def potentially_add_extra_fields_to_note_type(
    model_manager: ModelManager,
    config_filter: PrioritySieveConfigFilter,
) -> NotetypeDict:
    note_type_dict: NotetypeDict | None = model_manager.by_name(config_filter.note_type)
    assert note_type_dict is not None

    if config_filter.extra_reading_field:
        existing_field_names = model_manager.field_names(note_type_dict)
        if ps_globals.EXTRA_FIELD_READING not in existing_field_names:
            new_field = model_manager.new_field(ps_globals.EXTRA_FIELD_READING)
            model_manager.add_field(note_type_dict, new_field)
            model_manager.update_dict(note_type_dict)

    note_type_dict = model_manager.by_name(config_filter.note_type)
    assert note_type_dict is not None
    return note_type_dict


def update_reading_field(
    field_name_dict: dict[str, tuple[int, FieldDict]],
    note: Note,
    morphs: list[Morpheme],
) -> None:
    index: int = field_name_dict[ps_globals.EXTRA_FIELD_READING][0]
    if not morphs:
        note.fields[index] = ""
        return

    # Use the first morph's lemma/reading pair (cards are treated as single morph tokens).
    morph = morphs[0]
    base = morph.lemma
    reading = normalize_reading(morph.reading)

    if reading:
        note.fields[index] = f"{base}[{reading}]"
    else:
        note.fields[index] = base
