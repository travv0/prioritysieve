from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from types import SimpleNamespace
from test.fake_configs import (
    config_big_japanese_collection,
    config_default_behavior,
    config_default_field,
    config_default_morph_priority,
    config_default_morphemizer,
    config_default_note_type,
    config_ignore_names_txt_enabled,
    config_known_morphs_enabled,
    config_lemma_evaluation_lemma_extra_fields,
    config_max_morph_priority,
    config_offset_inflection_enabled,
    config_wrong_field_name,
    config_wrong_morph_priority,
    config_wrong_morphemizer_description,
    config_wrong_note_type,
)
from test.fake_environment_module import (  # pylint:disable=unused-import
    FakeEnvironment,
    FakeEnvironmentParams,
    fake_environment_fixture,
)

import pytest

from prioritysieve import prioritysieve_config
from prioritysieve import prioritysieve_globals as am_globals
from prioritysieve import tags_and_queue_utils
from prioritysieve import text_preprocessing
from prioritysieve.prioritysieve_config import PrioritySieveConfig, RawConfigFilterKeys
from prioritysieve.prioritysieve_db import PrioritySieveDB
from prioritysieve.exceptions import (
    AnkiFieldNotFound,
    AnkiNoteTypeNotFound,
    DefaultSettingsException,
    KnownMorphsFileMalformedException,
    MorphemizerNotFoundException,
    PriorityFileNotFoundException,
)
from prioritysieve.recalc import recalc_main
from prioritysieve.recalc.card_score import _MAX_SCORE
from prioritysieve.recalc.card_morphs_metrics import CardMorphsMetrics

# these have to be placed here to avoid cyclical imports
from anki.cards import Card, CardId  # isort:skip  pylint:disable=wrong-import-order
from anki.models import (  # isort:skip pylint:disable=wrong-import-order
    ModelManager,
    NotetypeDict,
)
from anki.notes import Note  # isort:skip  pylint:disable=wrong-import-order


test_cases_with_success = [
    ################################################################
    #             CASE: SAME INFLECTION AND LEMMA SCORES
    ################################################################
    # Config contains "lemma priority", therefore we check that all
    # the inflections are given the same score as their respective
    # lemmas.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="lemma_evaluation_lemma_extra_fields_collection",
            expected_col="lemma_evaluation_lemma_extra_fields_collection",
            config=config_lemma_evaluation_lemma_extra_fields,
        ),
        id="same_lemma_and_inflection_scores",
    ),
    ################################################################
    #                 CASE: INFLECTIONS ARE KNOWN
    ################################################################
    # Same as case 1, but at least one card of each lemma has been
    # studied. This checks the following:
    # 1. all inflections are set to "known"
    # 2. the 'ps-fresh-entries' tag are set
    # 3. the 'ps-study-morph' field has a value
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="some_studied_lemmas_collection",
            expected_col="some_studied_lemmas_collection",
            config=config_lemma_evaluation_lemma_extra_fields,
        ),
        id="inflections_are_known",
    ),
    ################################################################
    #               CASE: KNOWN MORPHS ENABLED
    ################################################################
    # Config contains "read_known_morphs_folder": true,
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="known_morphs_collection",
            expected_col="known_morphs_collection",
            config=config_known_morphs_enabled,
        ),
        id="known_morphs_enabled",
    ),
    ################################################################
    #               CASE: IGNORE NAMES ENABLED
    ################################################################
    # Config contains "preprocess_ignore_names_textfile": true,
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="ignore_names_txt_collection",
            expected_col="ignore_names_txt_collection",
            config=config_ignore_names_txt_enabled,
        ),
        id="ignore_names_txt_enabled",
    ),
    ################################################################
    #               CASE: BIG JAPANESE COLLECTION
    ################################################################
    # Monolithic collection, used for catching weird and unexpected
    # edge cases.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="big_japanese_collection",
            expected_col="big_japanese_collection",
            config=config_big_japanese_collection,
        ),
        id="big_japanese_collection",
    ),
    ################################################################
    #               CASE: MAX MORPH PRIORITY
    ################################################################
    # This collection uses the `ja_core_news_sm_freq_inflection_min_occurrence.csv`
    # priority file, and checks if morphs not contained in that file
    # are given the max morph priority.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="max_morph_priority_collection",
            expected_col="max_morph_priority_collection",
            config=config_max_morph_priority,
        ),
        id="max_morph_priority",
    ),
    ################################################################
    #        CASE: SUSPEND NEW CARDS WITH ONLY KNOWN ENTRIES
    ################################################################
    # Checks if cards are correctly suspended whenever all of their
    # entries are already known
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            actual_col="card_handling_collection",
            expected_col="suspend_morphs_known_or_fresh",
            config=config_default_behavior,
        ),
        id="suspend_known_entries",
    ),
]


# "Using the indirect=True parameter when parametrizing a test allows to parametrize a
# test with a fixture receiving the values before passing them to a test"
# - https://docs.pytest.org/en/7.1.x/example/parametrize.html#indirect-parametrization
# This means that we run the fixture AND the test function for each parameter.
@pytest.mark.external_morphemizers
@pytest.mark.parametrize(
    "fake_environment_fixture",
    test_cases_with_success,
    indirect=True,
)
def test_recalc(  # pylint:disable=too-many-locals
    fake_environment_fixture: FakeEnvironment | None,
) -> None:
    if fake_environment_fixture is None:
        pytest.xfail()

    text_preprocessing.update_translation_table()  # updates custom characters to ignore

    actual_collection = fake_environment_fixture.mock_mw.col
    expected_collection = fake_environment_fixture.expected_collection

    model_manager: ModelManager = ModelManager(actual_collection)
    note_type_dict: NotetypeDict | None = model_manager.by_name(
        fake_environment_fixture.config["filters"][0]["note_type"]
    )
    assert note_type_dict is not None
    field_name_dict = model_manager.field_map(note_type_dict)

    field_indices = {
        RawConfigFilterKeys.EXTRA_ALL_MORPHS: am_globals.EXTRA_FIELD_ALL_MORPHS,
        RawConfigFilterKeys.EXTRA_ALL_MORPHS_COUNT: am_globals.EXTRA_FIELD_ALL_MORPHS_COUNT,
        RawConfigFilterKeys.EXTRA_UNKNOWN_MORPHS: am_globals.EXTRA_FIELD_UNKNOWN_MORPHS,
        RawConfigFilterKeys.EXTRA_UNKNOWN_MORPHS_COUNT: am_globals.EXTRA_FIELD_UNKNOWN_MORPHS_COUNT,
        RawConfigFilterKeys.EXTRA_HIGHLIGHTED: am_globals.EXTRA_FIELD_HIGHLIGHTED,
        RawConfigFilterKeys.EXTRA_SCORE: am_globals.EXTRA_FIELD_SCORE,
        RawConfigFilterKeys.EXTRA_SCORE_TERMS: am_globals.EXTRA_FIELD_SCORE_TERMS,
        RawConfigFilterKeys.EXTRA_STUDY_MORPHS: am_globals.EXTRA_FIELD_STUDY_MORPHS,
    }
    field_positions = {
        key: field_name_dict[value][0] for key, value in field_indices.items()
    }

    read_enabled_config_filters = prioritysieve_config.get_read_enabled_filters()
    modify_enabled_config_filters = prioritysieve_config.get_modify_enabled_filters()

    recalc_main._recalc_background_op(
        read_enabled_config_filters=read_enabled_config_filters,
        modify_enabled_config_filters=modify_enabled_config_filters,
    )

    # print("config:")
    # pprint(fake_environment_fixture.config)
    # print()

    expected_collection_cards: Sequence[int] = expected_collection.find_cards("")
    actual_collection_cards: Sequence[int] = actual_collection.find_cards("")
    assert len(expected_collection_cards) > 0
    assert len(expected_collection_cards) == len(actual_collection_cards)

    for card_id in expected_collection_cards:
        # print(f"card_id: {card_id}")
        card_id = CardId(card_id)

        actual_card: Card = actual_collection.get_card(card_id)
        actual_note: Note = actual_card.note()

        expected_card: Card = expected_collection.get_card(card_id)
        expected_note: Note = expected_card.note()

        # for field, pos in field_positions.items():
        #     print()
        #     print(f"field: {field}")
        #     print(f"actual_note: {actual_note.fields[pos]}")
        #     print(f"expected_note: {expected_note.fields[pos]}")

        # print(f"actual_card.due: {actual_card.due}")
        # print(f"expected_card.due: {expected_card.due}")
        # print(f"actual_note.tags: {actual_note.tags}")
        # print(f"expected_note.tags: {expected_note.tags}")

        assert card_id == actual_card.id
        assert actual_card.due == expected_card.due
        assert actual_note.tags == expected_note.tags

        for pos in field_positions.values():
            # note.fields[pos]: the content of the field
            assert actual_note.fields[pos] == expected_note.fields[pos]


@pytest.mark.external_morphemizers
@pytest.mark.parametrize(
    "fake_environment_fixture",
    [
        pytest.param(
            FakeEnvironmentParams(
                actual_col="offset_new_cards_inflection_collection",
                config=config_offset_inflection_enabled,
            ),
            id="auto_suspend_duplicate_cards",
        )
    ],
    indirect=True,
)
def test_recalc_auto_suspends_duplicate_cards(
    fake_environment_fixture: FakeEnvironment | None,
) -> None:
    if fake_environment_fixture is None:
        pytest.xfail()

    text_preprocessing.update_translation_table()

    read_enabled_config_filters = prioritysieve_config.get_read_enabled_filters()
    modify_enabled_config_filters = prioritysieve_config.get_modify_enabled_filters()

    recalc_main._recalc_background_op(
        read_enabled_config_filters=read_enabled_config_filters,
        modify_enabled_config_filters=modify_enabled_config_filters,
    )

    am_config = PrioritySieveConfig()
    auto_tag = am_config.tag_suspended_automatically

    am_db = PrioritySieveDB()
    try:
        card_morph_map_cache = am_db.get_card_morph_map_cache()
    finally:
        am_db.con.close()

    assert card_morph_map_cache

    collection = fake_environment_fixture.actual_collection

    morph_to_cards: dict[tuple[str, str, str], list[int]] = {}
    for card_id in card_morph_map_cache:
        unknown_keys = CardMorphsMetrics.get_unknown_morph_keys(
            card_morph_map_cache=card_morph_map_cache,
            card_id=card_id,
        )
        if len(unknown_keys) != 1:
            continue
        key = next(iter(unknown_keys))
        morph_to_cards.setdefault(key, []).append(card_id)

    assert any(len(card_ids) > 1 for card_ids in morph_to_cards.values())

    for card_ids in morph_to_cards.values():
        if len(card_ids) < 2:
            continue

        active_cards: list[int] = []
        for card_id in card_ids:
            card = collection.get_card(card_id)
            note = card.note()
            if card.queue == tags_and_queue_utils.suspended:
                assert auto_tag in note.tags
            else:
                active_cards.append(card_id)
                assert auto_tag not in note.tags

        assert len(active_cards) == 1

test_cases_with_immediate_exceptions = [
    ################################################################
    #                  CASE: WRONG NOTE TYPE
    ################################################################
    # Checks if "AnkiNoteTypeNotFound" exception is raised correctly
    # when we supply an invalid note type in the config.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_wrong_note_type,
        ),
        AnkiNoteTypeNotFound,
        id="wrong_note_type",
    ),
    ################################################################
    #                  CASE: WRONG FIELD NAME
    ################################################################
    # Checks if "AnkiFieldNotFound" exception is raised correctly
    # when we supply an invalid field name in the config.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_wrong_field_name,
        ),
        AnkiFieldNotFound,
        id="wrong_field_name",
    ),
    ################################################################
    #                CASE: WRONG MORPH PRIORITY
    ################################################################
    # Checks if "PriorityFileNotFoundException" exception is raised
    # correctly when we supply an invalid priority file in the config.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_wrong_morph_priority,
        ),
        PriorityFileNotFoundException,
        id="wrong_morph_priority",
    ),
    ################################################################
    #            CASE: WRONG MORPHEMIZER DESCRIPTION
    ################################################################
    # Checks if "MorphemizerNotFoundException" exception is raised
    # correctly when we supply an invalid morphemizer description
    # in the config.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_wrong_morphemizer_description,
        ),
        MorphemizerNotFoundException,
        id="wrong_morphemizer_description",
    ),
    ################################################################
    #            CASES: DEFAULT NOTE FILTER SETTINGS
    ################################################################
    # Checks if "DefaultSettingsException" exception is raised
    # when any note filters contain the default `(none)` selection.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_default_note_type,
        ),
        DefaultSettingsException,
        id="default_note_type",
    ),
    pytest.param(
        FakeEnvironmentParams(
            config=config_default_field,
        ),
        DefaultSettingsException,
        id="default_field",
    ),
    pytest.param(
        FakeEnvironmentParams(
            config=config_default_morph_priority,
        ),
        DefaultSettingsException,
        id="default_morph_priority",
    ),
]


@pytest.mark.should_cause_exception
@pytest.mark.parametrize(
    "fake_environment_fixture, expected_exception",
    test_cases_with_immediate_exceptions,
    indirect=["fake_environment_fixture"],
)
def test_recalc_with_default_settings(  # pylint:disable=unused-argument
    fake_environment_fixture: FakeEnvironment, expected_exception: type[Exception]
) -> None:
    read_enabled_config_filters = prioritysieve_config.get_read_enabled_filters()
    modify_enabled_config_filters = prioritysieve_config.get_modify_enabled_filters()

    settings_error: Exception | None = recalc_main._check_selected_settings_for_errors(
        read_enabled_config_filters, modify_enabled_config_filters
    )
    assert isinstance(settings_error, expected_exception)


@pytest.mark.parametrize(
    "fake_environment_fixture",
    [
        pytest.param(
            FakeEnvironmentParams(
                config=config_default_morphemizer,
            ),
            id="default_morphemizer_allowed",
        )
    ],
    indirect=True,
)
def test_recalc_allows_none_morphemizer(
    fake_environment_fixture: FakeEnvironment | None,
) -> None:
    assert fake_environment_fixture is not None

    read_enabled_config_filters = prioritysieve_config.get_read_enabled_filters()
    modify_enabled_config_filters = prioritysieve_config.get_modify_enabled_filters()

    settings_error: Exception | None = recalc_main._check_selected_settings_for_errors(
        read_enabled_config_filters, modify_enabled_config_filters
    )

    assert settings_error is None


test_cases_with_delayed_exceptions = [
    ################################################################
    #        CASES: INVALID/MALFORMED KNOWN MORPHS FILE
    ################################################################
    # Checks if "KnownMorphsFileMalformedException" exception is raised
    # when a file is malformed.
    # Collection choice is arbitrary.
    # Database choice is arbitrary.
    ################################################################
    pytest.param(
        FakeEnvironmentParams(
            config=config_known_morphs_enabled,
            known_morphs_dir="known-morphs-invalid",
        ),
        KnownMorphsFileMalformedException,
        id="invalid_known_morphs_file",
    ),
]


@pytest.mark.should_cause_exception
@pytest.mark.parametrize(
    "fake_environment_fixture, expected_exception",
    test_cases_with_delayed_exceptions,
    indirect=["fake_environment_fixture"],
)
def test_recalc_with_invalid_known_morphs_file(  # pylint:disable=unused-argument
    fake_environment_fixture: FakeEnvironment, expected_exception: type[Exception]
) -> None:
    read_enabled_config_filters = prioritysieve_config.get_read_enabled_filters()
    modify_enabled_config_filters = prioritysieve_config.get_modify_enabled_filters()

    with pytest.raises(expected_exception):
        recalc_main._recalc_background_op(
            read_enabled_config_filters=read_enabled_config_filters,
            modify_enabled_config_filters=modify_enabled_config_filters,
        )


def test_add_offsets_priority_deck(monkeypatch: pytest.MonkeyPatch) -> None:
    cards = {
        1: SimpleNamespace(id=1, did=10, nid=101, due=10, queue=0),
        2: SimpleNamespace(id=2, did=20, nid=102, due=50, queue=0),
        3: SimpleNamespace(id=3, did=30, nid=103, due=20, queue=0),
    }
    notes = {
        101: SimpleNamespace(id=101, fields=[""], tags=[]),
        102: SimpleNamespace(id=102, fields=[""], tags=[]),
        103: SimpleNamespace(id=103, fields=[""], tags=[]),
    }
    deck_map = {
        10: {"name": "OtherDeck"},
        20: {"name": "PriorityDeck"},
        30: {"name": "OtherDeck2"},
    }

    class FakeDecks:
        def __init__(self, decks_dict: dict[int, dict[str, str]]):
            self._decks_dict = decks_dict

        def get(self, did: int, default: dict[str, str] | None = None) -> dict[str, str] | None:
            return self._decks_dict.get(did, default)

    fake_col = SimpleNamespace(
        get_card=lambda card_id: cards[card_id],
        get_note=lambda note_id: notes[note_id],
        decks=FakeDecks(deck_map),
    )
    fake_mw = SimpleNamespace(col=fake_col)

    monkeypatch.setattr(recalc_main, "mw", fake_mw)
    monkeypatch.setattr(
        recalc_main.progress_utils,
        "background_update_progress_potentially_cancel",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        recalc_main.progress_utils,
        "background_update_progress",
        lambda *args, **kwargs: None,
    )

    def _fake_unknowns(_card_morph_map_cache: dict[int, object], card_id: int) -> set[str]:
        return {"shared-morph"} if card_id in cards else set()

    monkeypatch.setattr(
        recalc_main.CardMorphsMetrics,
        "get_unknown_morph_keys",
        _fake_unknowns,
    )

    auto_tag = "auto-tag"
    am_config = SimpleNamespace(
        recalc_offset_priority_decks=["PriorityDeck"],
        tag_suspended_automatically=auto_tag,
    )

    handled_cards = OrderedDict((card_id, None) for card_id in cards)
    modified_notes: dict[int, object] = {}
    note_original_state: dict[int, tuple[list[str], list[str]]] = {}

    recalc_main._add_offsets_to_new_cards(
        am_config=am_config,
        card_morph_map_cache={},
        already_modified_cards={},
        handled_cards=handled_cards,
        modified_notes=modified_notes,
        note_original_state=note_original_state,
    )

    assert cards[2].queue != tags_and_queue_utils.suspended
    assert notes[102].tags == []

    for loser_id in (1, 3):
        card = cards[loser_id]
        note = notes[card.nid]
        assert card.queue == tags_and_queue_utils.suspended
        assert auto_tag in note.tags
        assert card.due == _MAX_SCORE


def test_add_offsets_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    cards = {
        1: SimpleNamespace(id=1, did=10, nid=101, due=0, queue=0),
        2: SimpleNamespace(id=2, did=10, nid=102, due=0, queue=0),
        3: SimpleNamespace(id=3, did=10, nid=103, due=0, queue=0),
    }
    notes = {
        101: SimpleNamespace(id=101, fields=[""], tags=[]),
        102: SimpleNamespace(id=102, fields=[""], tags=[]),
        103: SimpleNamespace(id=103, fields=[""], tags=[]),
    }

    fake_col = SimpleNamespace(
        get_card=lambda card_id: cards[card_id],
        get_note=lambda note_id: notes[note_id],
        decks=SimpleNamespace(get=lambda *_args, **_kwargs: None),
    )
    fake_mw = SimpleNamespace(col=fake_col)

    monkeypatch.setattr(recalc_main, "mw", fake_mw)
    monkeypatch.setattr(
        recalc_main.progress_utils,
        "background_update_progress_potentially_cancel",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        recalc_main.progress_utils,
        "background_update_progress",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        recalc_main.CardMorphsMetrics,
        "get_unknown_morph_keys",
        lambda _cache, card_id: {"shared-morph"} if card_id in cards else set(),
    )

    auto_tag = "auto-tag"
    am_config = SimpleNamespace(
        recalc_offset_priority_decks=[],
        tag_suspended_automatically=auto_tag,
    )

    handled_cards = OrderedDict((card_id, None) for card_id in cards)
    modified_notes: dict[int, object] = {}
    note_original_state: dict[int, tuple[list[str], list[str]]] = {}

    recalc_main._add_offsets_to_new_cards(
        am_config=am_config,
        card_morph_map_cache={},
        already_modified_cards={},
        handled_cards=handled_cards,
        modified_notes=modified_notes,
        note_original_state=note_original_state,
    )

    for card_id in (2, 3):
        card = cards[card_id]
        note = notes[card.nid]
        assert card.queue == tags_and_queue_utils.suspended
        assert auto_tag in note.tags
        assert card.due == _MAX_SCORE

    handled_cards_second = OrderedDict((card_id, None) for card_id in cards)
    modified_notes_second: dict[int, object] = {}
    note_original_state_second: dict[int, tuple[list[str], list[str]]] = {}

    result_second = recalc_main._add_offsets_to_new_cards(
        am_config=am_config,
        card_morph_map_cache={},
        already_modified_cards={},
        handled_cards=handled_cards_second,
        modified_notes=modified_notes_second,
        note_original_state=note_original_state_second,
    )

    assert result_second == {}
    assert modified_notes_second == {}


def test_update_tags_auto_suspend_override() -> None:
    am_config = SimpleNamespace(
        tag_ready="ready",
        tag_not_ready="not-ready",
        tag_known_automatically="known-auto",
        tag_known_manually="known-manual",
        tag_fresh="fresh",
        tag_suspended_automatically="auto-tag",
    )

    note = SimpleNamespace(id=1, tags=["ready"])
    card = SimpleNamespace(queue=0, nid=note.id, due=42)

    tags_and_queue_utils.update_tags_and_queue_of_new_card(
        am_config=am_config,
        note=note,
        card=card,
        unknowns=1,
        has_learning_morphs=False,
        force_auto_suspend=True,
    )

    assert card.queue == tags_and_queue_utils.suspended
    assert "auto-tag" in note.tags
    assert "ready" not in note.tags
    assert "not-ready" in note.tags
    assert card.due == _MAX_SCORE


def test_force_auto_suspend_survives_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    auto_tag = "auto-tag"
    card = SimpleNamespace(
        id=1,
        nid=1,
        did=10,
        due=_MAX_SCORE,
        queue=tags_and_queue_utils.suspended,
    )
    note = SimpleNamespace(id=1, tags=[auto_tag], fields=[])

    class FakeCol:
        @staticmethod
        def get_card(card_id: int) -> SimpleNamespace:
            assert card_id == card.id
            return card

        @staticmethod
        def get_note(note_id: int) -> SimpleNamespace:
            assert note_id == note.id
            return note

        class Decks:
            @staticmethod
            def get(_did: int, default=None):
                return default

        decks = Decks()

    monkeypatch.setattr(recalc_main, "mw", SimpleNamespace(col=FakeCol()))

    am_config = SimpleNamespace(tag_suspended_automatically=auto_tag)
    already_modified = {card.id: card}
    earliest = {("m", "m", ""): card}
    cards_with = {("m", "m", ""): {card.id}}
    modified_notes = {note.id: note}
    note_original_state = {note.id: (list(note.fields), list(note.tags))}

    recalc_main._apply_offsets(
        am_config=am_config,
        already_modified_cards=already_modified,
        earliest_due_card_for_unknown_morph=earliest,
        cards_with_morph=cards_with,
        modified_notes=modified_notes,
        note_original_state=note_original_state,
    )

    assert card.queue == tags_and_queue_utils.suspended
    assert card.due == _MAX_SCORE
    assert auto_tag in note.tags


def test_update_tags_of_review_cards_removes_auto_tag() -> None:
    am_config = SimpleNamespace(
        tag_ready="ready",
        tag_not_ready="not-ready",
        tag_fresh="fresh",
        tag_suspended_automatically="auto-tag",
    )

    note = SimpleNamespace(tags=["auto-tag", "ready"], id=1)

    tags_and_queue_utils.update_tags_of_review_cards(
        am_config=am_config,
        note=note,
        has_learning_morphs=False,
    )

    assert "auto-tag" not in note.tags
    assert "ready" not in note.tags
