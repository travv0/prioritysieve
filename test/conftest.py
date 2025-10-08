from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QCoreApplication


@pytest.fixture
def qtbot() -> Iterator[object]:
    """Minimal subset of pytest-qt's qtbot fixture used in tests.

    Provides addWidget() so widgets are kept alive for the duration of a test.
    """

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
