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


def _per_lang_state_snapshot(max_mod: int) -> dict[str, list[dict[str, int | str]]]:
    """Return per-language state format used by compute_per_language_filters_state."""
    return {"Japanese": _state_snapshot(max_mod)}


def test_recalc_after_sync_skips_followup_sync(monkeypatch) -> None:
    # Per-language format: dict of lang_name -> JSON-encoded state list
    baseline_per_lang = {"Japanese": json.dumps(_state_snapshot(1), sort_keys=True)}
    post_per_lang_state = _per_lang_state_snapshot(2)
    post_per_lang = {
        lang: json.dumps(state, sort_keys=True)
        for lang, state in post_per_lang_state.items()
    }
    post_state_json = json.dumps(post_per_lang, sort_keys=True)

    # Extra settings stores JSON-encoded dict of per-language states
    extra_settings = DummyExtraSettings(json.dumps(baseline_per_lang, sort_keys=True))

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
        ps.recalc_main,
        "recalc_languages",
        lambda langs: recalc_calls.append(langs),
    )
    monkeypatch.setattr(
        ps.recalc_main,
        "compute_per_language_filters_state",
        lambda: post_per_lang_state,
    )

    # Set per-language baseline state (dict format)
    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_per_lang, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", set(), raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", True, raising=False)

    ps.recalc_after_sync(success=True)

    assert recalc_calls == []
    assert callback_calls and callback_calls[-1] is None
    assert ps._state_before_sync_recalc == post_per_lang
    assert extra_settings.get_recalc_collection_state() == post_state_json
    assert ps._pending_changes_before_sync == set()
    assert not ps._last_sync_was_followup


def test_recalc_after_sync_runs_when_state_changes(monkeypatch) -> None:
    # Per-language format
    baseline_per_lang = {"Japanese": json.dumps(_state_snapshot(1), sort_keys=True)}
    post_per_lang_state = _per_lang_state_snapshot(2)

    # Extra settings stores cached state
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
        ps.recalc_main,
        "recalc_languages",
        lambda langs: recalc_calls.append(langs),
    )
    monkeypatch.setattr(
        ps.recalc_main,
        "compute_per_language_filters_state",
        lambda: post_per_lang_state,
    )

    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_per_lang, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", set(), raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", False, raising=False)

    ps.recalc_after_sync(success=True)

    # Should call recalc_languages with the set of changed languages
    assert len(recalc_calls) == 1
    assert recalc_calls[0] == {"Japanese"}
    assert len(callback_calls) >= 2
    assert callback_calls[0] is None
    assert callback_calls[-1] is ps._schedule_followup_sync
    # State is updated from extra_settings after recalc
    assert ps._pending_changes_before_sync == set()
    assert not ps._last_sync_was_followup


def test_recalc_after_sync_only_recalcs_changed_languages(monkeypatch) -> None:
    """Test that only languages with changes are recalculated."""
    # Baseline has two languages
    baseline_per_lang = {
        "Japanese": json.dumps(_state_snapshot(1), sort_keys=True),
        "Chinese": json.dumps(_state_snapshot(1), sort_keys=True),
    }
    # Post-sync: only Japanese changed
    post_per_lang_state = {
        "Japanese": _state_snapshot(2),  # changed
        "Chinese": _state_snapshot(1),   # unchanged
    }

    extra_settings = DummyExtraSettings(json.dumps(baseline_per_lang, sort_keys=True))

    monkeypatch.setattr(ps, "PrioritySieveExtraSettings", lambda: extra_settings)
    monkeypatch.setattr(ps, "PrioritySieveConfig", _make_config)
    callback_calls: list[object] = []
    monkeypatch.setattr(
        ps.recalc_main,
        "set_followup_sync_callback",
        lambda callback: callback_calls.append(callback),
    )

    recalc_calls: list[object] = []
    monkeypatch.setattr(ps.recalc_main, "recalc", lambda: recalc_calls.append("full"))
    monkeypatch.setattr(
        ps.recalc_main,
        "recalc_languages",
        lambda langs: recalc_calls.append(langs),
    )
    monkeypatch.setattr(
        ps.recalc_main,
        "compute_per_language_filters_state",
        lambda: post_per_lang_state,
    )

    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_per_lang, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", set(), raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", False, raising=False)

    ps.recalc_after_sync(success=True)

    # Should only recalc Japanese, not Chinese
    assert len(recalc_calls) == 1
    assert recalc_calls[0] == {"Japanese"}


def test_recalc_after_sync_skips_when_no_changes(monkeypatch) -> None:
    """Test that recalc is skipped when no languages have changes."""
    # Same state before and after
    baseline_per_lang = {"Japanese": json.dumps(_state_snapshot(1), sort_keys=True)}
    post_per_lang_state = {"Japanese": _state_snapshot(1)}  # same as baseline

    extra_settings = DummyExtraSettings(json.dumps(baseline_per_lang, sort_keys=True))

    monkeypatch.setattr(ps, "PrioritySieveExtraSettings", lambda: extra_settings)
    monkeypatch.setattr(ps, "PrioritySieveConfig", _make_config)
    callback_calls: list[object] = []
    monkeypatch.setattr(
        ps.recalc_main,
        "set_followup_sync_callback",
        lambda callback: callback_calls.append(callback),
    )

    recalc_calls: list[object] = []
    monkeypatch.setattr(ps.recalc_main, "recalc", lambda: recalc_calls.append("full"))
    monkeypatch.setattr(
        ps.recalc_main,
        "recalc_languages",
        lambda langs: recalc_calls.append(langs),
    )
    monkeypatch.setattr(
        ps.recalc_main,
        "compute_per_language_filters_state",
        lambda: post_per_lang_state,
    )

    monkeypatch.setattr(
        ps, "_state_before_sync_recalc", baseline_per_lang, raising=False
    )
    monkeypatch.setattr(ps, "_pending_changes_before_sync", set(), raising=False)
    monkeypatch.setattr(ps, "_last_sync_was_followup", False, raising=False)

    ps.recalc_after_sync(success=True)

    # Should not recalc anything
    assert recalc_calls == []
    assert callback_calls and callback_calls[-1] is None
