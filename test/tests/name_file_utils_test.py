from __future__ import annotations

from types import SimpleNamespace

from prioritysieve import prioritysieve_globals
from prioritysieve.name_file_utils import add_name_to_file, get_names_from_file


def test_name_file_utils_appends_and_caches(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    names_path = profile_dir / prioritysieve_globals.NAMES_TXT_FILE_NAME
    names_path.write_text("Existing\n", encoding="utf-8")

    mw_stub = SimpleNamespace(pm=SimpleNamespace(profileFolder=lambda: str(profile_dir)))
    monkeypatch.setattr("prioritysieve.name_file_utils.mw", mw_stub, raising=False)

    initial_names = get_names_from_file()
    assert initial_names == {"existing"}

    add_name_to_file("Alice Bob")
    updated_names = get_names_from_file()
    assert updated_names == {"existing", "alice", "bob"}

    # ensure duplicates are ignored when appended again
    add_name_to_file("Alice")
    assert get_names_from_file() == {"existing", "alice", "bob"}
