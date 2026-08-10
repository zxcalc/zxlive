import threading
import time
from types import SimpleNamespace
from typing import cast

import pytest
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget
from pytestqt.qtbot import QtBot

import zxlive.dialogs as dialogs
from zxlive.custom_rule import CustomRule


def test_run_in_thread_keeps_ui_responsive(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    main_thread = QThread.currentThread()
    timer_fired = False

    def mark_timer_fired() -> None:
        nonlocal timer_fired
        timer_fired = True

    def task() -> QThread:
        time.sleep(0.05)
        return QThread.currentThread()

    QTimer.singleShot(0, mark_timer_fired)
    completed, worker_thread = dialogs.run_in_thread(task, "Working...", "Abort", parent)

    assert completed
    assert timer_fired
    assert worker_thread is not main_thread


def test_run_in_thread_can_be_cancelled(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    release_worker = threading.Event()

    def task() -> None:
        release_worker.wait(timeout=2)

    def cancel_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QProgressDialog)
        dialog.cancel()

    QTimer.singleShot(10, cancel_dialog)
    completed, result = dialogs.run_in_thread(task, "Working...", "Abort", parent)
    release_worker.set()
    qtbot.waitUntil(lambda: not dialogs._running_threads)

    assert not completed
    assert result is None


def test_run_in_thread_reraises_errors(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    def fail() -> None:
        raise ValueError("bad matrix")

    with pytest.raises(ValueError, match="bad matrix"):
        dialogs.run_in_thread(fail, "Working...", "Abort", parent)


def test_rule_matrix_validation_can_be_skipped(
        monkeypatch: pytest.MonkeyPatch, qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    graph = SimpleNamespace(
        auto_detect_io=lambda: None,
        inputs=lambda: (),
        outputs=lambda: (),
        var_registry=SimpleNamespace(vars=lambda: ()),
    )
    rule = cast(CustomRule, SimpleNamespace(lhs_graph=graph, rhs_graph=graph))
    progress_arguments: list[tuple[str, str]] = []

    def skip(_task: object, message: str, cancel_text: str,
             _parent: QWidget) -> tuple[bool, None]:
        progress_arguments.append((message, cancel_text))
        return False, None

    monkeypatch.setattr(dialogs, "run_in_thread", skip)

    assert not dialogs.check_rule_with_progress(rule, parent)
    assert progress_arguments == [("Computing rule matrices...", "Skip validation")]
