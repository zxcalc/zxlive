import multiprocessing
import os
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
import pyzx as zx
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog, QPushButton, QWidget
from pytestqt.qtbot import QtBot

import zxlive.matrix as matrix
from zxlive.common import GraphT
from zxlive.custom_rule import CustomRule, check_rule_matrices


class _MatrixGraph:
    var_registry = SimpleNamespace(vars=lambda: ())

    def __init__(self, matrix: np.ndarray | None = None, *, return_pid: bool = False,
                 error: str | None = None, exit_code: int | None = None,
                 started_path: str | None = None, release_path: str | None = None) -> None:
        self.matrix = matrix
        self.return_pid = return_pid
        self.error = error
        self.exit_code = exit_code
        self.started_path = started_path
        self.release_path = release_path

    def auto_detect_io(self) -> None:
        pass

    def inputs(self) -> tuple[int]:
        return (0,)

    def outputs(self) -> tuple[int]:
        return (1,)

    def to_matrix(self) -> np.ndarray:
        if self.exit_code is not None:
            os._exit(self.exit_code)
        if self.error is not None:
            raise ValueError(self.error)
        if self.return_pid:
            time.sleep(0.05)
            return np.array([[complex(os.getpid())]])
        if self.started_path is not None and self.release_path is not None:
            # Write the worker's PID atomically so the test never reads a half-written file.
            Path(self.started_path + ".tmp").write_text(str(os.getpid()))
            os.replace(self.started_path + ".tmp", self.started_path)
            deadline = time.monotonic() + 10
            while not Path(self.release_path).exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            return np.ones((1024, 1024), dtype=np.complex128)
        assert self.matrix is not None
        return self.matrix


@pytest.fixture(autouse=True)
def stop_matrix_worker(qtbot: QtBot) -> Iterator[None]:
    yield
    # Progress dialogs still pending deletion crash the os._exit in conftest.
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    matrix.shutdown_matrix_worker()


@pytest.fixture
def parent(qtbot: QtBot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


def _worker_pid(parent: QWidget) -> int:
    result = matrix.compute_matrix_with_progress(
        cast(GraphT, _MatrixGraph(return_pid=True)), parent)
    assert result is not None
    return int(result[0, 0].real)


def _child_pids() -> set[int]:
    return {p.pid for p in multiprocessing.active_children() if p.pid is not None}


def test_matrix_job_keeps_ui_responsive(parent: QWidget) -> None:
    timer_fired = False

    def mark_timer_fired() -> None:
        nonlocal timer_fired
        timer_fired = True

    QTimer.singleShot(0, mark_timer_fired)
    pid = _worker_pid(parent)

    assert timer_fired
    assert pid != os.getpid()


def test_worker_is_reused_between_jobs(parent: QWidget) -> None:
    assert _worker_pid(parent) == _worker_pid(parent)


def test_job_error_keeps_worker(parent: QWidget) -> None:
    pid = _worker_pid(parent)

    with pytest.raises(ValueError, match="bad matrix"):
        matrix.compute_matrix_with_progress(
            cast(GraphT, _MatrixGraph(error="bad matrix")), parent)

    assert _worker_pid(parent) == pid


def test_worker_crash_is_reported_and_replaced(parent: QWidget) -> None:
    pid = _worker_pid(parent)

    with pytest.raises(RuntimeError, match="exited unexpectedly"):
        matrix.compute_matrix_with_progress(
            cast(GraphT, _MatrixGraph(exit_code=3)), parent)

    assert _worker_pid(parent) != pid


def test_abort_kills_worker_and_warms_replacement(
        parent: QWidget, qtbot: QtBot, tmp_path: Path) -> None:
    started_path = tmp_path / "matrix-started"
    release_path = tmp_path / "release-matrix"
    callback_errors: list[str] = []
    deadline = time.monotonic() + 30

    def abort_when_started() -> None:
        dialog = QApplication.activeModalWidget()
        if started_path.exists():
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
            callback_errors.append("matrix worker did not start in time")
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
        assert not release_path.exists()
        aborted_pid = int(started_path.read_text())
        qtbot.waitUntil(lambda: aborted_pid not in _child_pids())
        assert _child_pids(), "a replacement worker should already be starting"
        assert _worker_pid(parent) != aborted_pid
    finally:
        release_path.touch()


def test_shutdown_stops_worker(parent: QWidget) -> None:
    pid = _worker_pid(parent)

    matrix.shutdown_matrix_worker()

    assert pid not in _child_pids()


def test_real_graph_matrix_and_rule(parent: QWidget) -> None:
    circuit = zx.Circuit(2)
    circuit.add_gate("CNOT", 0, 1)
    circuit.add_gate("HAD", 0)
    graph = circuit.to_graph(backend="multigraph")

    result = matrix.compute_matrix_with_progress(cast(GraphT, graph), parent)

    assert result is not None
    assert np.allclose(result, graph.to_matrix())
    rule = cast(CustomRule, SimpleNamespace(lhs_graph=graph, rhs_graph=graph.copy()))
    matrix.check_rule_with_progress(rule, parent)


def test_rule_matrix_errors_are_returned_from_worker(parent: QWidget) -> None:
    rule = cast(CustomRule, SimpleNamespace(
        lhs_graph=_MatrixGraph(np.identity(2, dtype=np.complex128)),
        rhs_graph=_MatrixGraph(np.diag([1, 2]).astype(np.complex128)),
    ))

    with pytest.raises(ValueError, match="different semantics"):
        matrix.check_rule_with_progress(rule, parent)


def test_rule_matrix_validation_can_be_skipped(
        monkeypatch: pytest.MonkeyPatch, parent: QWidget) -> None:
    rule = cast(CustomRule, SimpleNamespace(lhs_graph=_MatrixGraph(), rhs_graph=_MatrixGraph()))
    progress_arguments: list[tuple[object, str, str]] = []

    def skip(function: object, _args: object, message: str, cancel_text: str,
             _parent: QWidget) -> None:
        progress_arguments.append((function, message, cancel_text))

    monkeypatch.setattr(matrix, "_run_with_progress", skip)

    matrix.check_rule_with_progress(rule, parent)
    assert progress_arguments == [
        (check_rule_matrices, "Computing rule matrices...", "Skip validation")]
