from __future__ import annotations

import csv
from pathlib import Path

from aqt import mw

from ..prioritysieve_globals import PRIORITY_FILES_DIR_NAME
from . import generators_utils
from .generators_output_dialog import OutputOptions


def background_generate_priority_file(
    selected_output_options: OutputOptions,
    input_dir_root: Path,
    input_files: list[Path],
) -> None:
    assert mw is not None

    if not input_files:
        return

    mw.progress.start(label="Generating priority file")

    entries_by_file = generators_utils.read_entries_for_files(input_files)
    combined = generators_utils.build_global_aggregates(entries_by_file)
    sorted_aggregates = generators_utils.sort_aggregates_desc(combined)

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

    entries_to_write = sorted_aggregates[:cutoff]
    _write_priority_file(selected_output_options, entries_to_write)


def _write_priority_file(
    selected_output_options: OutputOptions,
    aggregates: list[generators_utils.EntryAggregate],
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
    headers.append("Priority")
    if selected_output_options.include_occurrences_column:
        headers.append("Occurrences")

    with output_file.open(mode="w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)

        for priority, aggregate in enumerate(aggregates):
            row: list[str | int] = [aggregate.text]
            if selected_output_options.include_reading:
                row.append(aggregate.reading)
            row.append(priority)
            if selected_output_options.include_occurrences_column:
                row.append(aggregate.occurrences)
            writer.writerow(row)
