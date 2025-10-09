from __future__ import annotations

from types import SimpleNamespace

import prioritysieve.recalc.recalc_main as recalc_main

def test_on_success_updates_toolbar_and_tooltip(monkeypatch):
    calls: list[str] = []

    original_mw = recalc_main.mw
    fake_toolbar = SimpleNamespace(draw=lambda: calls.append("draw"))
    recalc_main.mw = SimpleNamespace(toolbar=fake_toolbar)

    monkeypatch.setattr(
        recalc_main,
        "compute_modify_filters_state",
        lambda: [{"id": "dummy", "card_count": 0}],
    )

    class _FakeSettings:
        def set_recalc_collection_state(self, *_args, **_kwargs) -> None:
            calls.append("set_recalc_collection_state")

        def set_recalc_settings_state(self, *_args, **_kwargs) -> None:
            calls.append("set_recalc_settings_state")

        def sync(self) -> None:
            calls.append("sync")

    monkeypatch.setattr(
        recalc_main, "PrioritySieveExtraSettings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        recalc_main.prioritysieve_config,
        "get_config_dict",
        lambda: {"mock": "config"},
    )

    monkeypatch.setattr(recalc_main, "tooltip", lambda *args, **kwargs: calls.append("tooltip"))

    try:
        recalc_main._on_success()
    finally:
        recalc_main.mw = original_mw

    assert "draw" in calls
    assert "tooltip" in calls
