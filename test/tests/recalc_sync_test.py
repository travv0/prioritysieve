from __future__ import annotations

import json
from types import SimpleNamespace

import importlib

ps = importlib.import_module("prioritysieve.__init__")


class DummyExtraSettings:
    def __init__(self, state: str | None) -> None:
        self.collection_state = state

    def get_recalc_collection_state(self) -> str | None:
        return self.collection_state

    def set_recalc_collection_state(self, value: str | None) -> None:
        self.collection_state = value


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(recalc_after_sync=True)


def _state_snapshot(max_mod: int) -> list[dict[str, int | str]]:
    return [
        {
            "id": "Basic|inc:|exc:",
            "card_count": 1,
            "card_max_mod": max_mod,
            "card_max_id": 1,
            "note_count": 1,
            "note_max_mod": max_mod,
            "note_max_id": 1,
        }
    ]


def test_recalc_after_sync_skips_followup_sync(monkeypatch) -> None:
    baseline_state = json.dumps(_state_snapshot(1), sort_keys=True)
    post_state = _state_snapshot(2)
    post_state_json = json.dumps(post_state, sort_keys=True)

    extra_settings = DummyExtraSettings(baseline_state)

    monkeypatch.setattr(ps, "PrioritySieveExtraSettings", lambda: extra_settings)
    monkeypatch.setattr(ps, "PrioritySieveConfig", _make_config)
    callback_calls: list[object] = []
    monkeypatch.setattr(
        ps.recalc_main,
        "set_followup_sync_callback",
        lambda callback: callback_calls.append(callback),
    )
    recalc_calls: list[object] = []
    monkeypatch.setattr(ps.recalc_main, "recalc", lambda: recalc_calls.append(True))
    monkeypatch.setattr(
        ps.recalc_main, "compute_modify_filters_state", lambda: post_state
    )

    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_state, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", False, raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", True, raising=False)

    ps.recalc_after_sync(success=True)

    assert recalc_calls == []
    assert callback_calls and callback_calls[-1] is None
    assert ps._state_before_sync_recalc == post_state_json
    assert extra_settings.get_recalc_collection_state() == post_state_json
    assert not ps._pending_changes_before_sync
    assert not ps._last_sync_was_followup


def test_recalc_after_sync_runs_when_state_changes(monkeypatch) -> None:
    baseline_state = json.dumps(_state_snapshot(1), sort_keys=True)
    post_state = _state_snapshot(2)

    extra_settings = DummyExtraSettings("cached-state")

    monkeypatch.setattr(ps, "PrioritySieveExtraSettings", lambda: extra_settings)
    monkeypatch.setattr(ps, "PrioritySieveConfig", _make_config)
    callback_calls: list[object] = []

    def _record_callback(callback: object) -> None:
        callback_calls.append(callback)

    monkeypatch.setattr(ps.recalc_main, "set_followup_sync_callback", _record_callback)

    recalc_calls: list[object] = []
    monkeypatch.setattr(ps.recalc_main, "recalc", lambda: recalc_calls.append(True))
    monkeypatch.setattr(
        ps.recalc_main, "compute_modify_filters_state", lambda: post_state
    )

    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_state, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", False, raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", False, raising=False)

    ps.recalc_after_sync(success=True)

    assert recalc_calls == [True]
    assert len(callback_calls) >= 2
    assert callback_calls[0] is None
    assert callback_calls[-1] is ps._schedule_followup_sync
    assert ps._state_before_sync_recalc == "cached-state"
    assert not ps._pending_changes_before_sync
    assert not ps._last_sync_was_followup
