from __future__ import annotations

from collections.abc import Iterator

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import QCoreApplication
except ImportError:  # pragma: no cover - fallback for headless test envs
    QApplication = None
    QWidget = None
    QCoreApplication = None


@pytest.fixture
def qtbot() -> Iterator[object]:
    """Minimal subset of pytest-qt's qtbot fixture used in tests.

    Provides addWidget() so widgets are kept alive for the duration of a test.
    """

    if QApplication is None:
        # When Qt libs are unavailable, provide a no-op stub so non-Qt tests run.
        class _QtBot:  # pragma: no cover - trivial stub
            def addWidget(self, _widget) -> None:
                return None

        yield _QtBot()
        return

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    widgets: list[QWidget] = []

    class _QtBot:
        def addWidget(self, widget: QWidget) -> None:
            widgets.append(widget)

    yield _QtBot()

    for widget in widgets:
        widget.deleteLater()
    QCoreApplication.processEvents()
