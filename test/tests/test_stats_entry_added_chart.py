from __future__ import annotations

import sys
import types
from datetime import datetime, timezone, timedelta

import pytest


def _install_fake_aqt(monkeypatch) -> None:
    """Provide minimal aqt / flask stubs so the module can import."""

    # aqt base
    aqt = types.ModuleType("aqt")
    aqt.mw = types.SimpleNamespace(col=None)

    class _SimpleHook:
        def __init__(self):
            self._callbacks = []

        def append(self, cb):
            self._callbacks.append(cb)

    aqt.gui_hooks = types.SimpleNamespace(
        webview_did_inject_style_into_page=_SimpleHook()
    )
    aqt.mediasrv = types.SimpleNamespace(post_handlers={})

    # aqt.webview
    webview = types.ModuleType("aqt.webview")

    class AnkiWebViewKind:
        DECK_STATS = "deck-stats"

    class AnkiWebView:
        def __init__(self, kind=None):
            self.kind = kind

        def eval(self, _js: str) -> None:  # pragma: no cover - not used
            pass

    webview.AnkiWebView = AnkiWebView
    webview.AnkiWebViewKind = AnkiWebViewKind

    sys.modules["aqt"] = aqt
    sys.modules["aqt.gui_hooks"] = aqt.gui_hooks
    sys.modules["aqt.mediasrv"] = aqt.mediasrv
    sys.modules["aqt.webview"] = webview

    # flask stub
    flask = types.ModuleType("flask")

    class Response:  # pragma: no cover - not used in these tests
        def __init__(self, *_args, **_kwargs):
            pass

    flask.Response = Response
    flask.request = types.SimpleNamespace(data=None)
    sys.modules["flask"] = flask

    # anki stubs
    anki = types.ModuleType("anki")
    consts = types.ModuleType("anki.consts")
    consts.CARD_TYPE_NEW = 0
    consts.QUEUE_TYPE_SUSPENDED = 3
    anki.consts = consts
    sys.modules["anki"] = anki
    sys.modules["anki.consts"] = consts


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    _install_fake_aqt(monkeypatch)
    yield
    # cleanup
    for name in ["aqt", "aqt.gui_hooks", "aqt.mediasrv", "aqt.webview", "flask"]:
        sys.modules.pop(name, None)


def _ms_for(day: datetime) -> int:
    return int(day.timestamp() * 1000)


def _load_module(monkeypatch):
    """Load stats_entry_added_chart without executing the real package __init__."""

    import importlib
    from pathlib import Path

    # Reset any existing modules for a clean import
    for name in list(sys.modules):
        if name == "prioritysieve" or name.startswith("prioritysieve."):
            sys.modules.pop(name, None)

    pkg_path = Path(__file__).resolve().parents[2] / "prioritysieve"
    pkg = types.ModuleType("prioritysieve")
    pkg.__path__ = [str(pkg_path)]
    sys.modules["prioritysieve"] = pkg

    return importlib.import_module("prioritysieve.stats_entry_added_chart")


def test_counts_all(monkeypatch):
    mod = _load_module(monkeypatch)

    # Fixed "today"
    fixed_today = datetime(2025, 1, 10, tzinfo=timezone.utc)

    class FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            return fixed_today.astimezone(tz)

        @classmethod
        def fromtimestamp(cls, ts, tz=None):
            return datetime.fromtimestamp(ts, tz)

    monkeypatch.setattr(mod, "datetime", FixedDatetime)
    monkeypatch.setattr(mod, "_local_tz", lambda: timezone.utc)

    # Build fake mw.col.find_cards
    today = fixed_today
    two_days_ago = today - timedelta(days=2)
    ids_today = [_ms_for(today)]
    ids_two_days = [_ms_for(two_days_ago)]
    card_search_ids = ids_today + ids_two_days + [123456]  # extra non-first id

    class FakeCol:
        timezone = timezone.utc

        @staticmethod
        def find_cards(_search, order=False):
            return card_search_ids

    mod.mw.col = FakeCol()

    # fake grouped entry cards
    grouped = {
        ("a", "a"): [ids_today[0], ids_today[0] + 1],
        ("b", "b"): [ids_two_days[0], ids_two_days[0] + 1],
        ("c", "c"): [999999],  # not in search
    }

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get_card_ids_grouped_by_entry(self):
            return grouped

    monkeypatch.setattr(mod, "EntryDB", FakeDB)

    result = mod._first_entry_counts(search="deck:current", days=None)

    assert result["total"] == 2
    assert len(result["bars"]) == 2
    counts_by_date = {b["date"]: b["count"] for b in result["bars"]}
    assert counts_by_date[str(two_days_ago.date())] == 1
    assert counts_by_date[str(today.date())] == 1


def test_counts_respect_days(monkeypatch):
    mod = _load_module(monkeypatch)

    fixed_today = datetime(2025, 1, 10, tzinfo=timezone.utc)

    class FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            return fixed_today.astimezone(tz)

        @classmethod
        def fromtimestamp(cls, ts, tz=None):
            return datetime.fromtimestamp(ts, tz)

    monkeypatch.setattr(mod, "datetime", FixedDatetime)
    monkeypatch.setattr(mod, "_local_tz", lambda: timezone.utc)

    today = fixed_today
    two_days_ago = today - timedelta(days=2)
    ids_today = [_ms_for(today)]
    ids_two_days = [_ms_for(two_days_ago)]
    card_search_ids = ids_today + ids_two_days

    class FakeCol:
        timezone = timezone.utc

        @staticmethod
        def find_cards(_search, order=False):
            return card_search_ids

    mod.mw.col = FakeCol()

    grouped = {("a", "a"): [ids_today[0]], ("b", "b"): [ids_two_days[0]]}

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get_card_ids_grouped_by_entry(self):
            return grouped

    monkeypatch.setattr(mod, "EntryDB", FakeDB)

    result = mod._first_entry_counts(search="deck:current", days=1)

    assert result["total"] == 1
    assert len(result["bars"]) == 1
    assert result["bars"][0]["date"] == str(today.date())
