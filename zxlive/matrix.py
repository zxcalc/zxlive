"""Cancellable matrix computation and rule-validation progress dialogs."""

from __future__ import annotations

import multiprocessing
import os
import tempfile
import traceback
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Literal, Optional

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QProgressDialog, QWidget

from .common import GraphT
from .custom_rule import CustomRule, check_rule, check_rule_matrices

_PROCESS_CONTEXT = multiprocessing.get_context("spawn")
_running_processes: set[BaseProcess] = set()
MatrixOperation = Literal["compute", "compare"]


def _matrix_process_worker(operation: MatrixOperation, graphs: tuple[GraphT, ...],
                           result_path: Optional[str], connection: Connection) -> None:
    """Perform a matrix job and send a small status response to the GUI process."""
    try:
        if operation == "compute":
            assert result_path is not None and len(graphs) == 1
            graph = graphs[0]
            graph.auto_detect_io()
            with open(result_path, "wb") as result_file:
                np.save(result_file, graph.to_matrix(), allow_pickle=False)
        else:
            assert operation == "compare" and result_path is None and len(graphs) == 2
            check_rule_matrices(*graphs)
    except BaseException as error:
        response: tuple[object, ...] = (
            "error", type(error).__module__, type(error).__qualname__,
            str(error), traceback.format_exc(),
        )
    else:
        response = ("ok",)

    try:
        connection.send(response)
    except OSError:
        pass  # Abort may close the one-use pipe while the child is exiting.
    finally:
        connection.close()


def _reap_process(process: BaseProcess, terminate: bool) -> None:
    """Stop and reap a matrix process without leaving a child or an open handle."""
    if terminate and process.is_alive():
        process.terminate()
    process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)
    if process.is_alive():
        raise RuntimeError("The matrix process could not be stopped.")


def _remote_process_error(message: tuple[object, ...]) -> Exception:
    if len(message) != 5 or message[0] != "error":
        return RuntimeError(f"Invalid response from the matrix process: {message!r}")

    module, qualname, text, remote_traceback = message[1:]
    known_errors: dict[str, type[Exception]] = {
        "AttributeError": AttributeError,
        "ValueError": ValueError,
    }
    error_type = (
        known_errors.get(qualname, RuntimeError)
        if module == "builtins" and isinstance(qualname, str)
        else RuntimeError
    )
    error = error_type(str(text))
    if remote_traceback:
        error.add_note(f"Matrix process traceback:\n{remote_traceback}")
    return error


def _run_matrix_process(operation: MatrixOperation, graphs: tuple[GraphT, ...],
                        message: str, cancel_text: str,
                        parent: QWidget) -> tuple[bool, Optional[np.ndarray]]:
    """Run a disposable matrix process while showing a cancellable dialog."""
    dialog = QProgressDialog(message, cancel_text, 0, 0, parent)
    dialog.setWindowTitle("ZXLive")
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    result_path: Optional[str] = None
    if operation == "compute":
        result_fd, result_path = tempfile.mkstemp(prefix="zxlive-matrix-", suffix=".npy")
        os.close(result_fd)

    try:
        receive_connection, send_connection = _PROCESS_CONTEXT.Pipe(duplex=False)
        process = _PROCESS_CONTEXT.Process(
            target=_matrix_process_worker,
            args=(operation, graphs, result_path, send_connection),
            daemon=True,
        )
        timer = QTimer(dialog)
        timer.setInterval(20)
        response: Optional[tuple[object, ...]] = None
        process_error: Optional[Exception] = None
        started = False
        accepted = False

        def finish(*, received: Optional[tuple[object, ...]] = None,
                   error: Optional[Exception] = None) -> None:
            nonlocal response, process_error
            response = received
            process_error = error
            timer.stop()
            dialog.accept()

        def receive_response() -> None:
            try:
                received = receive_connection.recv()
            except (EOFError, OSError) as error:
                finish(error=RuntimeError(f"The matrix process result pipe failed: {error}"))
            else:
                if isinstance(received, tuple):
                    finish(received=received)
                else:
                    finish(error=RuntimeError(
                        f"Invalid response from the matrix process: {received!r}"))

        def poll_process() -> None:
            try:
                if receive_connection.poll():
                    receive_response()
                elif not process.is_alive():
                    process.join(timeout=0)
                    if receive_connection.poll(0.01):
                        receive_response()
                    else:
                        finish(error=RuntimeError(
                            f"The matrix process exited unexpectedly with code {process.exitcode}."))
            except OSError as error:
                finish(error=RuntimeError(f"The matrix process result pipe failed: {error}"))

        timer.timeout.connect(poll_process)

        try:
            process.start()
            started = True
            _running_processes.add(process)
            send_connection.close()
            timer.start()
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            timer.stop()
            if started:
                try:
                    _reap_process(process, terminate=not accepted)
                finally:
                    _running_processes.discard(process)
            receive_connection.close()
            send_connection.close()
            if started and not process.is_alive():
                process.close()

        if not accepted:
            return False, None
        if process_error is not None:
            raise process_error
        if response is None:
            raise RuntimeError("The matrix process finished without a response.")
        if response != ("ok",):
            raise _remote_process_error(response)
        if result_path is None:
            return True, None
        return True, np.load(result_path, allow_pickle=False)
    finally:
        dialog.deleteLater()
        if result_path is not None:
            try:
                os.remove(result_path)
            except FileNotFoundError:
                pass


def compute_matrix_with_progress(graph: GraphT, parent: QWidget) -> Optional[np.ndarray]:
    completed, matrix = _run_matrix_process(
        "compute", (graph,), "Computing matrix...", "Abort", parent)
    return matrix if completed else None


def check_rule_with_progress(rule: CustomRule, parent: QWidget) -> bool:
    """Validate a rule, allowing expensive matrix validation to be skipped."""
    check_rule(rule, check_matrices=False)
    if len(rule.lhs_graph.var_registry.vars()) != 0 or len(rule.rhs_graph.var_registry.vars()) != 0:
        return True

    completed, _ = _run_matrix_process(
        "compare",
        (rule.lhs_graph, rule.rhs_graph),
        "Computing rule matrices...",
        "Skip validation",
        parent,
    )
    return completed
