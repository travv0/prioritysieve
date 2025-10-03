from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.recalc import recalc_main


def _empty_tags() -> dict[str, list[str]]:
    return {"include": [], "exclude": []}


def test_filters_requiring_state_snapshot_includes_read_only(monkeypatch) -> None:
    read_only_filter = SimpleNamespace(note_type="Basic", tags=_empty_tags())

    monkeypatch.setattr(
        recalc_main.prioritysieve_config,
        "get_modify_enabled_filters",
        lambda: [],
    )
    monkeypatch.setattr(
        recalc_main.prioritysieve_config,
        "get_read_enabled_filters",
        lambda: [read_only_filter],
    )

    filters = recalc_main._filters_requiring_state_snapshot()

    assert filters == [read_only_filter]


def test_filters_requiring_state_snapshot_deduplicates(monkeypatch) -> None:
    modify_filter = SimpleNamespace(note_type="Basic", tags=_empty_tags())
    read_filter = SimpleNamespace(note_type="Basic", tags=_empty_tags())

    monkeypatch.setattr(
        recalc_main.prioritysieve_config,
        "get_modify_enabled_filters",
        lambda: [modify_filter],
    )
    monkeypatch.setattr(
        recalc_main.prioritysieve_config,
        "get_read_enabled_filters",
        lambda: [read_filter],
    )

    filters = recalc_main._filters_requiring_state_snapshot()

    assert filters == [modify_filter]
