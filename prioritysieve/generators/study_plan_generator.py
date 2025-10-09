from __future__ import annotations

import csv
from pathlib import Path

from aqt import mw

from ..prioritysieve_globals import PRIORITY_FILES_DIR_NAME
from . import generators_utils
from .generators_output_dialog import OutputOptions


def background_generate_study_plan(
    selected_output_options: OutputOptions,
    input_dir_root: Path,
    input_files: list[Path],
) -> None:
    assert mw is not None

    if not input_files:
        return

    mw.progress.start(label="Generating study plan")

    entries_by_file = generators_utils.read_entries_for_files(input_files)
    reviewed_lookup = generators_utils.build_reviewed_lookup()

    included: set[tuple[str, str]] = set()
    rows: list[list[str]] = []

    for file_path in input_files:
        aggregates_map = entries_by_file[file_path]
        sorted_aggregates = generators_utils.sort_aggregates_desc(aggregates_map)

        if selected_output_options.comprehension_selected:
            cutoff = generators_utils.comprehension_cutoff_index(
                sorted_aggregates,
                selected_output_options.comprehension_threshold,
            )
        else:
            cutoff = generators_utils.min_occurrence_cutoff_index(
                sorted_aggregates,
                selected_output_options.min_occurrence_threshold,
            )

        if cutoff > len(sorted_aggregates):
            cutoff = len(sorted_aggregates)

        for aggregate in sorted_aggregates[:cutoff]:
            key = aggregate.key()
            if key in included:
                continue
            included.add(key)

            status = "reviewed" if reviewed_lookup.get(key, False) else "unreviewed"
            row: list[str] = [aggregate.text]
            if selected_output_options.include_reading:
                row.append(aggregate.reading)
            row.append(status)
            if selected_output_options.include_occurrences_column:
                row.append(str(aggregate.occurrences))
            row.append(str(file_path.relative_to(input_dir_root)))
            rows.append(row)

    _write_study_plan(selected_output_options, rows)


def _write_study_plan(
    selected_output_options: OutputOptions,
    rows: list[list[str]],
) -> None:
    output_file: Path = selected_output_options.output_path
    if not output_file.name.endswith(".csv"):
        output_file = output_file.with_suffix(".csv")

    if not output_file.parent.is_absolute():
        assert mw is not None
        output_file = Path(mw.pm.profileFolder()) / PRIORITY_FILES_DIR_NAME / output_file.name

    output_file.parent.mkdir(parents=True, exist_ok=True)

    headers = ["Entry"]
    if selected_output_options.include_reading:
        headers.append("Reading")
    headers.append("Status")
    if selected_output_options.include_occurrences_column:
        headers.append("Occurrences")
    headers.append("File")

    with output_file.open(mode="w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
