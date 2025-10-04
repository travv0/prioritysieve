from __future__ import annotations

from typing import Any

from aqt import mw
from aqt.operations import on_op_finished


def notify_op_execution(result: Any, *, initiator: object | None = None) -> None:
    """Run Anki's post-operation hooks on the main thread."""

    if mw is None or result is None:
        return

    main_window = mw

    def _finish() -> None:
        on_op_finished(main_window, result, initiator)

    if main_window.taskman is not None:
        main_window.taskman.run_on_main(_finish)
    else:
        _finish()
