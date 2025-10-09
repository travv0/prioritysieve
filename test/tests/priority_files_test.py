from __future__ import annotations

from types import SimpleNamespace

from prioritysieve import priority_files
from prioritysieve.priority_files import PRIORITY_HEADERS


def test_priority_files_helpers(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()

    mw_stub = SimpleNamespace(pm=SimpleNamespace(profileFolder=lambda: str(profile_dir)))
    monkeypatch.setattr("prioritysieve.priority_files.mw", mw_stub, raising=False)

    priority_files.ensure_directories()
    priority_dir = profile_dir / priority_files.prioritysieve_globals.PRIORITY_FILES_DIR_NAME
    known_dir = profile_dir / priority_files.KNOWN_ENTRIES_DIR
    assert priority_dir.is_dir()
    assert known_dir.is_dir()

    (priority_dir / "a.csv").write_text("Entry,Priority\nalpha,1\nbeta,2\n", encoding="utf-8")
    (priority_dir / "b.csv").write_text(
        "Entry,Reading,Priority\nalpha,reading,3\n", encoding="utf-8"
    )
    (priority_dir / "c.csv").write_text(
        "Entry,Reading,Priority\nテニス仲間,テニスナカマ,7\n",
        encoding="utf-8",
    )

    assert priority_files.available_priority_files() == ["a.csv", "b.csv", "c.csv"]

    priority_map = priority_files.load_priority_map(["a.csv", "b.csv", "c.csv"])
    assert priority_map[("alpha", "")] == 1
    assert priority_map[("alpha", "reading")] == 3
    assert priority_map[("テニス仲間", "てにすなかま")] == 7

    # ensure legacy header names are still accepted
    (priority_dir / "legacy.csv").write_text(
        "Morph-Lemma,Morph-Reading,%s\nalpha,alt,5\n" % PRIORITY_HEADERS[0],
        encoding="utf-8",
    )
    priority_map = priority_files.load_priority_map(["legacy.csv"])
    assert priority_map[("alpha", "alt")] == 5
