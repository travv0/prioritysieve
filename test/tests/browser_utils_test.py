from __future__ import annotations

from types import SimpleNamespace

from prioritysieve.entry import Entry
from prioritysieve import browser_utils


class _LineEdit:
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def setText(self, text: str) -> None:
        self._sink.append(text)


class _SearchEdit:
    def __init__(self, sink: list[str]) -> None:
        self._line_edit = _LineEdit(sink)

    def lineEdit(self) -> _LineEdit:
        return self._line_edit


class _StubBrowser:
    def __init__(self, sink: list[str]) -> None:
        self.form = SimpleNamespace(searchEdit=_SearchEdit(sink))
        self._selected = [1]
        self.activated = False

    def selectedCards(self) -> list[int]:
        return self._selected.copy()

    def onSearchActivated(self) -> None:
        self.activated = True


def test_run_browse_entry_text_only(monkeypatch) -> None:
    queries: list[str] = []
    entry_calls: list[tuple[bool, bool]] = []

    class StubEntryDB:
        def __enter__(self) -> StubEntryDB:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
            return None

        def get_entry_for_card(self, card_id: int) -> Entry:
            assert card_id == 1
            return Entry(text="alpha", reading="reading2", language_name="Test", reviewed=False)

        def get_card_ids_for_entry(
            self, entry: Entry, include_reviewed: bool, text_only: bool
        ) -> list[int]:
            entry_calls.append((include_reviewed, text_only))
            return [1, 2]

    launcher_browser = _StubBrowser(queries)
    browser_utils.browser = launcher_browser

    def open_browser(name: str, mw) -> _StubBrowser:  # type: ignore[override]
        assert name == "Browser"
        new_browser = _StubBrowser(queries)
        browser_utils.browser = new_browser
        return new_browser

    monkeypatch.setattr(browser_utils, "dialogs", SimpleNamespace(open=open_browser))
    monkeypatch.setattr(browser_utils, "EntryDB", lambda: StubEntryDB())
    monkeypatch.setattr(
        browser_utils,
        "PrioritySieveConfig",
        lambda: SimpleNamespace(tag_ready="ready"),
    )
    monkeypatch.setattr(
        browser_utils.prioritysieve_config,
        "get_matching_read_filter",
        lambda note: object(),
    )

    mw_stub = SimpleNamespace(
        col=SimpleNamespace(
            get_card=lambda card_id: SimpleNamespace(
                id=card_id, note=lambda: SimpleNamespace()
            ),
            build_search_string=lambda node: "tag:ready",
        ),
        reviewer=None,
    )
    monkeypatch.setattr(browser_utils, "mw", mw_stub)

    tooltip_messages: list[str] = []
    monkeypatch.setattr(browser_utils, "tooltip", tooltip_messages.append)

    browser_utils.run_browse_entry(match_text_only=True)

    assert entry_calls == [(True, True)]
    assert queries
    assert queries[0].startswith("cid:")
    assert "1" in queries[0]
    assert "2" in queries[0]
    assert browser_utils.browser.activated  # type: ignore[attr-defined]
    assert not tooltip_messages


def test_run_browse_entry_unknowns_no_matches(monkeypatch) -> None:
    entry_calls: list[tuple[bool, bool]] = []

    class StubEntryDB:
        def __enter__(self) -> StubEntryDB:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get_entry_for_card(self, card_id: int) -> Entry:
            return Entry(text="alpha", reading="", language_name="Test", reviewed=False)

        def get_card_ids_for_entry(
            self, entry: Entry, include_reviewed: bool, text_only: bool
        ) -> list[int]:
            entry_calls.append((include_reviewed, text_only))
            return []

    initial_browser = _StubBrowser([])
    browser_utils.browser = initial_browser

    monkeypatch.setattr(browser_utils, "EntryDB", lambda: StubEntryDB())
    monkeypatch.setattr(
        browser_utils.prioritysieve_config,
        "get_matching_read_filter",
        lambda note: object(),
    )
    monkeypatch.setattr(
        browser_utils,
        "PrioritySieveConfig",
        lambda: SimpleNamespace(tag_ready="ready"),
    )

    mw_stub = SimpleNamespace(
        col=SimpleNamespace(
            get_card=lambda card_id: SimpleNamespace(
                id=card_id, note=lambda: SimpleNamespace()
            ),
            build_search_string=lambda node: "tag:ready",
        ),
        reviewer=None,
    )
    monkeypatch.setattr(browser_utils, "mw", mw_stub)

    tooltip_messages: list[str] = []
    monkeypatch.setattr(browser_utils, "tooltip", tooltip_messages.append)
    monkeypatch.setattr(
        browser_utils, "dialogs", SimpleNamespace(open=lambda name, mw: None)
    )

    browser_utils.run_browse_entry(search_unknowns=True)

    assert entry_calls == [(False, False)]
    assert tooltip_messages == ["No unknown entries"]
