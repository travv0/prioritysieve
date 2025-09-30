from __future__ import annotations

from pathlib import Path
from test.fake_configs import config_inflection_evaluation, config_lemma_evaluation
from test.fake_environment_module import (  # pylint:disable=unused-import
    FakeEnvironment,
    FakeEnvironmentParams,
    fake_environment_fixture,
)

import pytest

from prioritysieve import prioritysieve_globals as am_globals, debug_utils, morph_priority_utils
from prioritysieve.morph_priority_utils import (
    PriorityFile,
    PriorityFileFormat,
    PriorityFileType,
    _populate_priorities_with_lemmas_and_inflections_from_full_priority_file,
    _populate_priorities_with_lemmas_from_minimal_priority_file,
)
from prioritysieve.prioritysieve_config import PrioritySieveConfig
from prioritysieve.exceptions import PriorityFileMalformedException

# we don't need any special parameters for these tests
default_fake_environment_params = FakeEnvironmentParams()


@pytest.mark.parametrize(
    "fake_environment_fixture, csv_file_name, only_lemma_priorities, json_file_name",
    [
        (
            default_fake_environment_params,
            "ja_core_news_sm_freq_inflection_min_occurrence.csv",
            False,
            "ja_core_news_sm_freq_inflection_min_occurrence_inflection_priority.json",
        ),
        (
            default_fake_environment_params,
            "ja_core_news_sm_freq_inflection_min_occurrence.csv",
            True,
            "ja_core_news_sm_freq_inflection_min_occurrence_lemma_priority.json",
        ),
        (
            default_fake_environment_params,
            "ja_core_news_sm_freq_lemma_min_occurrence.csv",
            True,
            "ja_core_news_sm_freq_lemma_min_occurrence_lemma_priority.json",
        ),
        (
            default_fake_environment_params,
            "mecab_study_plan_lemma.csv",
            True,
            "mecab_study_plan_lemma_priority.json",
        ),
        (
            default_fake_environment_params,
            "mecab_study_plan_inflection.csv",
            False,
            "mecab_study_plan_inflection_priority.json",
        ),
    ],
    indirect=["fake_environment_fixture"],
)
def test_morph_priority_with_priority_file(  # pylint:disable=unused-argument
    fake_environment_fixture: FakeEnvironment | None,
    csv_file_name: str,
    only_lemma_priorities: bool,
    json_file_name: str,
) -> None:
    """
    Checks if morph priorities are loaded correctly from the priority files.
    Creating json files can be done with 'save_to_json_file' from 'debug_utils.py'
    """

    if fake_environment_fixture is None:
        pytest.xfail()

    morph_priorities = morph_priority_utils._load_morph_priorities_from_file(
        priority_file_name=csv_file_name, only_lemma_priorities=only_lemma_priorities
    )

    json_file_path = Path(
        fake_environment_fixture.mock_mw.pm.profileFolder(),
        fake_environment_fixture.priority_files_dir,
        json_file_name,
    )

    # debug_utils.save_to_json_file(json_file_path, morph_priorities)

    correct_morphs_priorities = debug_utils.load_dict_from_json_file(json_file_path)
    assert len(correct_morphs_priorities) > 0
    assert morph_priorities == correct_morphs_priorities


################################################################
#                  CASE: COLLECTION FREQUENCY
################################################################
# Get the respective morph priorities based on the collection
# frequencies.
################################################################
case_collection_frequency_lemma_params = FakeEnvironmentParams(
    actual_col="lemma_evaluation_lemma_extra_fields_collection",
    expected_col="lemma_evaluation_lemma_extra_fields_collection",
    config=config_lemma_evaluation,
    am_db="lemma_evaluation_lemma_extra_fields.db",
)

case_collection_frequency_inflection_params = FakeEnvironmentParams(
    actual_col="lemma_evaluation_lemma_extra_fields_collection",
    expected_col="lemma_evaluation_lemma_extra_fields_collection",
    config=config_inflection_evaluation,
    am_db="lemma_evaluation_lemma_extra_fields.db",
)


@pytest.mark.should_cause_exception
@pytest.mark.parametrize(
    "fake_environment_fixture, json_file_name",
    [
        (
            case_collection_frequency_lemma_params,
            "morph_priority_collection_frequency_lemma.json",
        ),
        (
            case_collection_frequency_inflection_params,
            "morph_priority_collection_frequency_inflection.json",
        ),
    ],
    indirect=["fake_environment_fixture"],
)
def test_morph_priority_with_collection_frequency(  # pylint:disable=unused-argument
    fake_environment_fixture: FakeEnvironment,
    json_file_name: str,
) -> None:
    am_config = PrioritySieveConfig()

    morph_priorities = morph_priority_utils.get_morph_priority(
        am_db=fake_environment_fixture.mock_db,
        only_lemma_priorities=am_config.evaluate_morph_lemma,
        morph_priority_selection=am_config.filters[0].morph_priority_selections,
    )

    json_file_path = Path(
        fake_environment_fixture.mock_mw.pm.profileFolder(),
        fake_environment_fixture.priority_files_dir,
        json_file_name,
    )

    correct_morphs_priorities = debug_utils.load_dict_from_json_file(json_file_path)
    assert len(correct_morphs_priorities) > 0
    assert morph_priorities == correct_morphs_priorities


################################################################
#                    CASE: NO HEADERS
################################################################
# The file 'frequency_file_no_headers.csv' has no headers and
# should raise an exception
################################################################
case_no_headers_params = FakeEnvironmentParams(
    priority_files_dir="wrong_inputs",
)


@pytest.mark.should_cause_exception
@pytest.mark.parametrize(
    "fake_environment_fixture, csv_file_name, only_lemma_priorities",
    [
        (case_no_headers_params, "priority_file_no_headers.csv", True),
        (
            default_fake_environment_params,
            "mecab_study_plan_inflection.csv",
            True,
        ),
        (
            default_fake_environment_params,
            "mecab_study_plan_lemma.csv",
            False,
        ),
        (
            default_fake_environment_params,
            "ja_core_news_sm_freq_lemma_min_occurrence.csv",
            False,
        ),
    ],
    indirect=["fake_environment_fixture"],
)
def test_morph_priority_with_invalid_priority_file(  # pylint:disable=unused-argument
    fake_environment_fixture: FakeEnvironment,
    csv_file_name: str,
    only_lemma_priorities: bool,
) -> None:
    try:
        morph_priority_utils._load_morph_priorities_from_file(
            priority_file_name=csv_file_name,
            only_lemma_priorities=only_lemma_priorities,
        )
    except PriorityFileMalformedException:
        pass
    else:
        assert False


def test_duplicate_entries_keep_lowest_priority_inflection() -> None:
    rows = [
        ["人", "人", "55", "55"],
        ["人", "人", "999", "22801"],
    ]

    priority_file = PriorityFile(
        file_type=PriorityFileType.PriorityFile,
        file_format=PriorityFileFormat.Full,
        lemma_header_index=0,
        inflection_header_index=1,
        lemma_priority_header_index=2,
        inflection_priority_header_index=3,
    )

    priorities: dict[tuple[str, str, str], int] = {}

    _populate_priorities_with_lemmas_and_inflections_from_full_priority_file(
        iter(rows), priority_file, priorities
    )

    assert priorities[("人", "人", "")] == 55


def test_duplicate_entries_keep_lowest_priority_minimal() -> None:
    rows = [["人"], ["人"], ["日"]]

    priority_file = PriorityFile(
        file_type=PriorityFileType.PriorityFile,
        file_format=PriorityFileFormat.Minimal,
        lemma_header_index=0,
    )

    priorities: dict[tuple[str, str, str], int] = {}

    _populate_priorities_with_lemmas_from_minimal_priority_file(
        iter(rows), priority_file, priorities
    )

    assert priorities[("人", "人", "")] == 0


def test_reading_column_creates_distinct_keys() -> None:
    rows = [
        ["人", "人", "じん", "10", "10"],
        ["人", "人", "にん", "20", "20"],
    ]

    priority_file = PriorityFile(
        file_type=PriorityFileType.PriorityFile,
        file_format=PriorityFileFormat.Full,
        lemma_header_index=0,
        inflection_header_index=1,
        reading_header_index=2,
        lemma_priority_header_index=3,
        inflection_priority_header_index=4,
    )

    priorities: dict[tuple[str, str, str], int] = {}

    _populate_priorities_with_lemmas_and_inflections_from_full_priority_file(
        iter(rows), priority_file, priorities
    )

    assert priorities[("人", "人", "じん")] == 10
    assert priorities[("人", "人", "にん")] == 20


def test_get_morph_priority_merges_multiple_sources(monkeypatch: pytest.MonkeyPatch) -> None:

    class DummyDB:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def get_morph_priorities_from_collection(
            self, only_lemma_priorities: bool
        ) -> dict[tuple[str, str, str], int]:
            self.calls.append(only_lemma_priorities)
            return {
                ("A", "A", ""): 10,
                ("B", "B", ""): 5,
                ("D", "D", ""): 7,
            }

    load_calls: dict[str, list[bool]] = {}

    def fake_loader(
        priority_file_name: str, only_lemma_priorities: bool
    ) -> dict[tuple[str, str, str], int]:
        load_calls.setdefault(priority_file_name, []).append(only_lemma_priorities)
        if priority_file_name == "file1.csv":
            return {
                ("A", "A", ""): 20,
                ("C", "C", ""): 1,
            }
        if priority_file_name == "file2.csv":
            return {
                ("A", "A", ""): 3,
                ("B", "B", ""): 9,
            }
        raise AssertionError("unexpected file request")

    monkeypatch.setattr(
        morph_priority_utils,
        "_load_morph_priorities_from_file",
        fake_loader,
    )

    am_db = DummyDB()

    priorities = morph_priority_utils.get_morph_priority(
        am_db=am_db,
        only_lemma_priorities=False,
        morph_priority_selection=[
            am_globals.COLLECTION_FREQUENCY_OPTION,
            "file1.csv",
            "file2.csv",
            "file1.csv",
        ],
    )

    assert priorities[("A", "A", "")] == 3
    assert priorities[("B", "B", "")] == 5
    assert priorities[("C", "C", "")] == 1
    assert priorities[("D", "D", "")] == 7
    assert len(priorities) == 4
    assert am_db.calls == [False]
    assert load_calls == {"file1.csv": [False], "file2.csv": [False]}
