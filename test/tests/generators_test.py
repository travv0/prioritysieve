from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import csv

import pytest

from prioritysieve.generators import priority_file_generator, study_plan_generator
from prioritysieve.generators import generators_utils


class DummyOptions:
    def __init__(
        self,
        output_path: Path,
        include_reading: bool = True,
        include_occurrences_column: bool = True,
        comprehension_selected: bool = False,
        min_occurrence_threshold: int = 1,
        comprehension_threshold: int = 90,
    ) -> None:
        self.output_path = output_path
        self.include_reading = include_reading
        self.include_occurrences_column = include_occurrences_column
        self.comprehension_selected = comprehension_selected
        self.min_occurrence_threshold = min_occurrence_threshold
        self.comprehension_threshold = comprehension_threshold


def _write_csv(path: Path, rows: list[list[str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Entry", "Reading", "Occurrences"])
        writer.writerows(rows)


def _patch_progress(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    dummy_progress = SimpleNamespace(start=lambda *_, **__: None, finish=lambda: None)
    dummy_taskman = SimpleNamespace(run_on_main=lambda fn: fn())
    monkeypatch.setattr(module, "mw", SimpleNamespace(progress=dummy_progress, taskman=dummy_taskman), raising=False)


def test_priority_file_generator_combines_occurrences(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "source.csv"
    _write_csv(
        source,
        [
            ["犬", "いぬ", 3],
            ["猫", "", 1],
            ["犬", "いぬ", 2],
        ],
    )

    output_path = tmp_path / "priority.csv"
    options = DummyOptions(output_path=output_path)

    _patch_progress(monkeypatch, priority_file_generator)

    priority_file_generator.background_generate_priority_file(
        selected_output_options=options,
        input_dir_root=input_dir,
        input_files=[source],
    )

    with output_path.open(encoding="utf-8") as handle:
        reader = list(csv.reader(handle))

    assert reader[0] == ["Entry", "Reading", "Priority", "Occurrences"]
    assert reader[1] == ["犬", "いぬ", "0", "5"]
    assert reader[2] == ["猫", "", "1", "1"]


def test_study_plan_generator_outputs_status_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    first = input_dir / "first.csv"
    second = input_dir / "second.csv"

    _write_csv(
        first,
        [
            ["猫", "", 2],
            ["犬", "いぬ", 1],
        ],
    )
    _write_csv(
        second,
        [
            ["猫", "", 3],
            ["鳥", "とり", 1],
        ],
    )

    output_path = tmp_path / "study_plan.csv"
    options = DummyOptions(output_path=output_path)

    _patch_progress(monkeypatch, study_plan_generator)
    monkeypatch.setattr(
        generators_utils,
        "build_reviewed_lookup",
        lambda: {("犬", "いぬ"): True},
    )

    study_plan_generator.background_generate_study_plan(
        selected_output_options=options,
        input_dir_root=input_dir,
        input_files=[first, second],
    )

    with output_path.open(encoding="utf-8") as handle:
        reader = list(csv.reader(handle))

    assert reader[0] == ["Entry", "Reading", "Status", "Occurrences", "File"]
    assert reader[1] == ["猫", "", "unreviewed", "2", "first.csv"]
    assert reader[2] == ["犬", "いぬ", "reviewed", "1", "first.csv"]
    assert reader[3] == ["鳥", "とり", "unreviewed", "1", "second.csv"]
