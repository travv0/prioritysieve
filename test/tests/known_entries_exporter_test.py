from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch
from unittest.mock import MagicMock

from prioritysieve.entry import Entry
from prioritysieve.known_entries_exporter import KnownEntriesExporterDialog
from test.fake_configs import default_config_dict


def _collect_exported_rows(output_dir: Path) -> list[list[str]]:
    exported_files = sorted(output_dir.glob("known_entries-*.csv"))
    assert exported_files, "Expected exporter to create a CSV output"
    target = exported_files[-1]
    with target.open(encoding="utf-8") as handle:
        return [line.rstrip("\n").split(",") for line in handle]


def test_known_entries_exporter_writes_expected_columns(
    tmp_path: Path, monkeypatch: MonkeyPatch, qtbot: Any
) -> None:
    entries = [
        (Entry(text="犬", reading="いぬ", reviewed=True), 3),
        (Entry(text="猫", reading="", reviewed=True), 1),
    ]

    fake_db = MagicMock()
    fake_db.__enter__.return_value = fake_db
    fake_db.__exit__.return_value = False
    fake_db.get_entries_with_counts.return_value = entries

    monkeypatch.setattr(
        "prioritysieve.known_entries_exporter.EntryDB",
        lambda: fake_db,
    )

    class DummyProgress:
        def start(self, *args: object, **kwargs: object) -> None:  # noqa: D401
            return None

        def finish(self) -> None:  # noqa: D401
            return None

    mw_stub = SimpleNamespace(
        progress=DummyProgress(),
        pm=SimpleNamespace(profileFolder=lambda: str(tmp_path)),
        addonManager=SimpleNamespace(
            getConfig=lambda module: default_config_dict,
            addonFromModule=lambda module: "prioritysieve",
            addonConfigDefaults=lambda module: default_config_dict,
            writeConfig=lambda module, cfg: None,
        ),
    )

    monkeypatch.setattr("aqt.mw", mw_stub)
    monkeypatch.setattr("prioritysieve.known_entries_exporter.mw", mw_stub)
    monkeypatch.setattr("prioritysieve.entry_db.mw", mw_stub)
    monkeypatch.setattr(
        "prioritysieve.extra_settings.prioritysieve_extra_settings.mw", mw_stub
    )
    monkeypatch.setattr("prioritysieve.priority_files.mw", mw_stub)

    dialog = KnownEntriesExporterDialog()
    qtbot.addWidget(dialog)

    output_dir = tmp_path / "exports"
    output_dir.mkdir()

    dialog.ui.outputLineEdit.setText(str(output_dir))
    dialog.ui.includeReadingCheckBox.setChecked(True)
    dialog.ui.includeReviewedOnlyCheckBox.setChecked(True)
    dialog.ui.addOccurrencesColumnCheckBox.setChecked(True)

    dialog._background_export_known_entries()

    rows = _collect_exported_rows(output_dir)
    assert rows[0] == ["Entry", "Reading", "Occurrences"]
    assert rows[1] == ["犬", "いぬ", "3"]
    assert rows[2] == ["猫", "", "1"]
