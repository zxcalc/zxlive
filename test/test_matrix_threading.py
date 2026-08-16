import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog, QPushButton, QWidget
from pytestqt.qtbot import QtBot

import zxlive.matrix as matrix
from zxlive.common import GraphT
from zxlive.custom_rule import CustomRule


class _MatrixGraph:
    var_registry = SimpleNamespace(vars=lambda: ())

    def __init__(self, matrix: np.ndarray | None = None, *, return_pid: bool = False,
                 error: str | None = None, started_path: str | None = None,
                 release_path: str | None = None) -> None:
        self.matrix = matrix
        self.return_pid = return_pid
        self.error = error
        self.started_path = started_path
        self.release_path = release_path

    def auto_detect_io(self) -> None:
        pass

    def inputs(self) -> tuple[int]:
        return (0,)

    def outputs(self) -> tuple[int]:
        return (1,)

    def to_matrix(self) -> np.ndarray:
        if self.error is not None:
            raise ValueError(self.error)
        if self.return_pid:
            time.sleep(0.05)
            return np.array([[complex(os.getpid())]])
        if self.started_path is not None and self.release_path is not None:
            matrix = np.ones((1024, 1024), dtype=np.complex128)
            Path(self.started_path).touch()
            deadline = time.monotonic() + 10
            while not Path(self.release_path).exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            return matrix
        assert self.matrix is not None
        return self.matrix


def test_matrix_process_keeps_ui_responsive(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    timer_fired = False

    def mark_timer_fired() -> None:
        nonlocal timer_fired
        timer_fired = True

    QTimer.singleShot(0, mark_timer_fired)
    result = matrix.compute_matrix_with_progress(
        cast(GraphT, _MatrixGraph(return_pid=True)), parent)

    assert timer_fired
    assert result is not None
    assert int(result[0, 0].real) != os.getpid()
    assert not matrix._running_processes


def test_matrix_process_is_terminated_on_abort(qtbot: QtBot, tmp_path: Path) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    started_path = tmp_path / "matrix-started"
    release_path = tmp_path / "release-matrix"
    callback_errors: list[str] = []
    captured_processes: list[Any] = []
    deadline = time.monotonic() + 30

    def abort_when_started() -> None:
        dialog = QApplication.activeModalWidget()
        if started_path.exists():
            if matrix._running_processes:
                captured_processes.extend(matrix._running_processes)
            else:
                callback_errors.append("matrix process was not tracked")
            if not isinstance(dialog, QProgressDialog):
                callback_errors.append(f"unexpected modal widget: {dialog!r}")
                return
            button = next((b for b in dialog.findChildren(QPushButton)
                           if b.text() == "Abort"), None)
            if button is None:
                callback_errors.append("could not find the Abort button")
                dialog.cancel()
            else:
                button.click()
        elif time.monotonic() >= deadline:
            callback_errors.append("matrix process did not start in time")
            if isinstance(dialog, QProgressDialog):
                dialog.cancel()
        else:
            QTimer.singleShot(10, abort_when_started)

    QTimer.singleShot(10, abort_when_started)
    try:
        result = matrix.compute_matrix_with_progress(
            cast(GraphT, _MatrixGraph(
                started_path=str(started_path), release_path=str(release_path))),
            parent,
        )

        assert not callback_errors
        assert result is None
        assert started_path.exists()
        assert not release_path.exists()
        assert not matrix._running_processes
        assert len(captured_processes) == 1
        try:
            assert not captured_processes[0].is_alive()
        except ValueError:
            pass  # Closed process handles have necessarily already stopped.
    finally:
        release_path.touch()


def test_matrix_process_reraises_errors(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    with pytest.raises(ValueError, match="bad matrix"):
        matrix.compute_matrix_with_progress(
            cast(GraphT, _MatrixGraph(error="bad matrix")), parent)

    assert not matrix._running_processes


def test_rule_matrices_are_compared_in_process(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    identity = np.identity(2, dtype=np.complex128)
    rule = cast(CustomRule, SimpleNamespace(
        lhs_graph=_MatrixGraph(identity),
        rhs_graph=_MatrixGraph(identity.copy()),
    ))

    assert matrix.check_rule_with_progress(rule, parent)
    assert not matrix._running_processes


def test_rule_matrix_errors_are_returned_from_process(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    rule = cast(CustomRule, SimpleNamespace(
        lhs_graph=_MatrixGraph(np.identity(2, dtype=np.complex128)),
        rhs_graph=_MatrixGraph(np.diag([1, 2]).astype(np.complex128)),
    ))

    with pytest.raises(ValueError, match="different semantics"):
        matrix.check_rule_with_progress(rule, parent)

    assert not matrix._running_processes


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
    progress_arguments: list[tuple[str, str, str]] = []

    def skip(operation: str, _graphs: object, message: str, cancel_text: str,
             _parent: QWidget) -> tuple[bool, None]:
        progress_arguments.append((operation, message, cancel_text))
        return False, None

    monkeypatch.setattr(matrix, "_run_matrix_process", skip)

    assert not matrix.check_rule_with_progress(rule, parent)
    assert progress_arguments == [
        ("compare", "Computing rule matrices...", "Skip validation")]
