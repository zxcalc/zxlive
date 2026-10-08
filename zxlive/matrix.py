"""Cancellable matrix computation and rule-validation progress dialogs."""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Callable, Optional

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QProgressDialog, QWidget

from .common import GraphT
from .custom_rule import CustomRule, check_rule, check_rule_matrices

_executor: Optional[ProcessPoolExecutor] = None


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        # Spawn, since forking a process that runs Qt is unsafe.
        _executor = ProcessPoolExecutor(
            max_workers=1, mp_context=multiprocessing.get_context("spawn"))
    return _executor


def kill_matrix_worker() -> None:
    """Kill the matrix worker process, including any running job."""
    global _executor
    executor, _executor = _executor, None
    if executor is None:
        return
    if hasattr(executor, "kill_workers"):
        executor.kill_workers()
    else:  # Python < 3.14
        processes = list((executor._processes or {}).values())
        executor.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            process.kill()


def _compute_matrix(graph: GraphT) -> np.ndarray:
    graph.auto_detect_io()
    matrix: np.ndarray = graph.to_matrix()
    return matrix


def _wait_with_dialog(future: Future[Any], message: str, cancel_text: str,
                      parent: QWidget) -> bool:
    """Show a progress dialog until the future is done. Returns False if cancelled."""
    dialog = QProgressDialog(message, cancel_text, 0, 0, parent)
    dialog.setWindowTitle("ZXLive")
    dialog.setMinimumDuration(0)

    def accept_when_done() -> None:
        if future.done():
            dialog.accept()

    timer = QTimer(dialog)
    timer.timeout.connect(accept_when_done)
    timer.start(20)
    try:
        return dialog.exec() == QDialog.DialogCode.Accepted
    finally:
        timer.stop()
        dialog.deleteLater()


def _run_with_progress(function: Callable[..., Any], args: tuple[Any, ...], message: str,
                       cancel_text: str, parent: QWidget) -> Any:
    """Run function(*args) in the worker process. Returns None if cancelled or killed."""
    executor = _get_executor()
    try:
        future = executor.submit(function, *args)
        if not _wait_with_dialog(future, message, cancel_text, parent):
            if _executor is executor:  # Cancelled by the user, not by the app quitting.
                kill_matrix_worker()
                _get_executor().submit(os.getpid)  # Warm up a replacement so the next job starts quickly.
            return None
        return future.result()
    except BrokenProcessPool as error:
        if _executor is not executor:
            return None  # Killed by kill_matrix_worker, e.g. because the app is quitting.
        kill_matrix_worker()
        raise RuntimeError("The matrix process exited unexpectedly.") from error


def compute_matrix_with_progress(graph: GraphT, parent: QWidget) -> Optional[np.ndarray]:
    """Compute the graph's matrix, or return None if the user aborts."""
    matrix: Optional[np.ndarray] = _run_with_progress(
        _compute_matrix, (graph,), "Computing matrix...", "Abort", parent)
    return matrix


def check_rule_with_progress(rule: CustomRule, parent: QWidget) -> bool:
    """Validate a rule, returning False if the matrix comparison was skipped."""
    validated = True

    def compare_matrices(lhs_graph: GraphT, rhs_graph: GraphT) -> None:
        nonlocal validated
        result = _run_with_progress(check_rule_matrices, (lhs_graph, rhs_graph),
                                    "Computing rule matrices...", "Skip validation", parent)
        if result is not True:
            validated = False

    check_rule(rule, compare_matrices)
    return validated
