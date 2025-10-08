from __future__ import annotations

from types import SimpleNamespace

import prioritysieve.recalc.recalc_main as recalc_main

def test_on_success_updates_toolbar_and_tooltip(monkeypatch):
    calls: list[str] = []

    original_mw = recalc_main.mw
    fake_toolbar = SimpleNamespace(draw=lambda: calls.append("draw"))
    recalc_main.mw = SimpleNamespace(toolbar=fake_toolbar)

    monkeypatch.setattr(recalc_main, "tooltip", lambda *args, **kwargs: calls.append("tooltip"))

    try:
        recalc_main._on_success()
    finally:
        recalc_main.mw = original_mw

    assert "draw" in calls
    assert "tooltip" in calls
