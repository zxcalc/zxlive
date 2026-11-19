"""Regression tests for selection parsing and asynchronous rewrite availability."""
from __future__ import annotations

import gc
import copy
import weakref
from concurrent.futures import Future
from threading import Event, get_ident
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from pytestqt.qtbot import QtBot
from pyzx.rewrite import RewriteSingleVertex
from pyzx.utils import EdgeType, VertexType

from zxlive.common import GraphT, new_graph
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteAction, RewriteActionTree, RewriteActionTreeModel, _match_selection
from zxlive.rewrite_data import MATCH_SINGLE


@pytest.fixture
def panel(qtbot: QtBot) -> Iterator[ProofPanel]:
    graph = new_graph()
    for v in range(4):
        graph.add_vertex(VertexType.Z, row=v, qubit=0)
    for v in range(3):
        graph.add_edge((v, v + 1))
    widget = ProofPanel(graph)
    qtbot.addWidget(widget)
    yield widget
    widget.release_resources()


def _model(panel: ProofPanel) -> RewriteActionTreeModel:
    return cast(RewriteActionTreeModel, panel.rewrites_panel.model())


def _install_rule(model: RewriteActionTreeModel, matcher: Any = None) -> RewriteAction:
    if matcher is None:
        def matcher(g: GraphT, v: int) -> bool:
            return g.phase(v) == 0
    action = RewriteAction("test", RewriteSingleVertex(matcher, lambda g, v: True), MATCH_SINGLE, "")
    root = RewriteActionTree("root", None, [], None)
    root.append_child(RewriteActionTree("test", action, [], root))
    model.set_root(root)
    return action


def _capture_jobs(model: RewriteActionTreeModel, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    jobs: list[Any] = []

    def submit(callback: Any, *args: Any) -> Future[list[bool]]:
        future: Future[list[bool]] = Future()
        future.set_running_or_notify_cancel()
        jobs.append((callback, args, future))
        return future

    monkeypatch.setattr(model.executor, "submit", submit)
    return jobs


@pytest.mark.parametrize("vertices, explicit, expected", [
    ([], [], set()),
    ([2, 1], [], {(1, 2, EdgeType.SIMPLE), (1, 2, EdgeType.HADAMARD), (1, 1, EdgeType.SIMPLE)}),
    ([], [(3, 4, EdgeType.SIMPLE)], {(3, 4, EdgeType.SIMPLE)}),
    ([2, 1], [(3, 4, EdgeType.SIMPLE)], {
        (1, 2, EdgeType.SIMPLE), (1, 2, EdgeType.HADAMARD), (1, 1, EdgeType.SIMPLE), (3, 4, EdgeType.SIMPLE)}),
    ([1], [], {(1, 1, EdgeType.SIMPLE)}),
    ([4], [], set()),
])
def test_parse_selection_preserves_order_and_edge_semantics(vertices: list[int], explicit: list[Any],
                                                          expected: set[Any]) -> None:
    graph = new_graph()
    for _ in range(5):
        graph.add_vertex(VertexType.Z)
    for edge in [(1, 2), (1, 2), (1, 1), (3, 4)]:
        graph.add_edge(edge)
    graph.add_edge((1, 2), EdgeType.HADAMARD)
    snapshot = SimpleNamespace(graph_scene=SimpleNamespace(
        g=graph, selected_vertices=iter(vertices), selected_edges=iter(explicit)))

    selected, edges = ProofPanel.parse_selection(snapshot)

    assert selected == vertices
    assert set(edges) == expected


def test_select_all_coalesces_to_one_snapshot(panel: ProofPanel, qtbot: QtBot,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    jobs = _capture_jobs(model, monkeypatch)
    graph = new_graph()
    for v in range(300):
        graph.add_vertex(VertexType.Z, row=v, qubit=0)
    panel.graph_scene.set_graph(graph)
    panel.graph_scene.select_all_vertices()

    assert jobs == []
    qtbot.waitUntil(lambda: len(jobs) == 1)
    _, (_, vertices, _, _, _), _ = jobs[0]
    assert set(vertices) == set(graph.vertices())


def test_busy_worker_keeps_only_latest_selection(panel: ProofPanel, qtbot: QtBot,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    action = _install_rule(model)
    jobs = _capture_jobs(model, monkeypatch)
    panel.graph_scene.select_vertices([0])
    qtbot.waitUntil(lambda: len(jobs) == 1)
    for v in (1, 2, 3):
        panel.graph_scene.select_vertices([v])
        model._update_on_timer()
    assert len(jobs) == 1
    assert jobs[0][1][-1].is_set()  # Superseded work can stop between matchers.

    jobs[0][2].set_result([True])
    model._update_on_timer()

    assert not action.enabled  # The old selection's result was discarded.
    assert len(jobs) == 2
    assert jobs[1][1][1] == [3]
    jobs[1][2].set_result([True])
    model._update_on_timer()
    assert action.enabled
    assert model.flags(model.index(0, 0)) == Qt.ItemFlag.ItemIsEnabled


def test_matching_snapshots_graph_rules_and_ui_thread(panel: ProofPanel, qtbot: QtBot,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    action = _install_rule(model)
    jobs = _capture_jobs(model, monkeypatch)
    gui_thread = get_ident()
    parse = panel.parse_selection

    def parse_on_gui() -> Any:
        assert get_ident() == gui_thread
        return parse()

    monkeypatch.setattr(panel, "parse_selection", parse_on_gui)
    panel.graph_scene.select_vertices([1])
    qtbot.waitUntil(lambda: len(jobs) == 1)
    callback, args, future = jobs[0]
    graph, vertices, _, actions, _ = args
    assert graph is not panel.graph
    assert actions[0] is not action
    assert actions[0].rule is not action.rule
    panel.graph.set_phase(1, 1)
    assert graph.phase(1) == 0
    assert vertices == [1]
    future.set_result(callback(*args))
    assert not action.enabled  # Only the GUI completion handler publishes results.
    model._update_on_timer()
    assert action.enabled


def test_refresh_discards_old_tree_results(panel: ProofPanel, qtbot: QtBot,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    old_action = _install_rule(model)
    jobs = _capture_jobs(model, monkeypatch)
    qtbot.waitUntil(lambda: len(jobs) == 1)
    new_action = _install_rule(model)
    new_action.disabled_by_fe_mode = True
    jobs[0][2].set_result([True])
    model._update_on_timer()

    assert not old_action.enabled
    assert not new_action.enabled
    assert len(jobs) == 2
    callback, args, future = jobs[1]
    future.set_result(callback(*args))
    model._update_on_timer()
    assert not new_action.enabled


def test_graph_edit_discards_old_applicability(panel: ProofPanel, qtbot: QtBot,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    action = _install_rule(model)
    jobs = _capture_jobs(model, monkeypatch)
    panel.graph_scene.select_vertices([1])
    qtbot.waitUntil(lambda: len(jobs) == 1)

    edited = copy.deepcopy(panel.graph)
    edited.set_phase(1, 1)
    panel.graph_scene.update_graph(edited)
    jobs[0][2].set_result([True])
    model._update_on_timer()

    assert not action.enabled
    assert len(jobs) == 2
    callback, args, future = jobs[1]
    assert args[0].phase(1) == 1
    future.set_result(callback(*args))
    model._update_on_timer()
    assert not action.enabled
    assert not model._matching_pending()


def test_pending_results_cannot_apply_a_rewrite(panel: ProofPanel, qtbot: QtBot,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    action = _install_rule(model)
    action.enabled = True
    jobs = _capture_jobs(model, monkeypatch)
    applied: list[bool] = []
    monkeypatch.setattr(action, "do_rewrite", lambda _: applied.append(True))

    model.do_rewrite(model.index(0, 0))
    qtbot.waitUntil(lambda: len(jobs) == 1)
    model.do_rewrite(model.index(0, 0))
    assert not applied
    assert model.flags(model.index(0, 0)) == Qt.ItemFlag.NoItemFlags
    jobs[0][2].set_result([True])
    model._update_on_timer()
    model.do_rewrite(model.index(0, 0))
    assert applied == [True]


def test_matcher_error_disables_only_that_action(panel: ProofPanel, qtbot: QtBot,
                                               caplog: pytest.LogCaptureFixture) -> None:
    model = _model(panel)
    gui_thread = get_ident()
    worker_threads: list[int] = []

    def fail(_g: GraphT, _v: int) -> bool:
        worker_threads.append(get_ident())
        raise ValueError("broken matcher")

    bad = _install_rule(model, fail)
    good = RewriteAction("good", RewriteSingleVertex(lambda g, v: True, lambda g, v: True), MATCH_SINGLE, "")
    model.root_item.append_child(RewriteActionTree("good", good, [], model.root_item))
    updates: list[int] = []
    model.layoutChanged.connect(lambda: updates.append(get_ident()))
    qtbot.waitUntil(lambda: good.enabled)

    assert not bad.enabled
    assert "broken matcher" in caplog.text
    assert worker_threads and all(thread != gui_thread for thread in worker_threads)
    assert updates and set(updates) == {gui_thread}


def test_close_before_dispatch_cancels_timer(panel: ProofPanel, qtbot: QtBot,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model(panel)
    jobs = _capture_jobs(model, monkeypatch)
    panel.graph_scene.select_all_vertices()
    panel.release_resources()
    model.schedule_selection_update()
    model._update_on_timer()
    assert not model._update_timer.isActive()
    assert jobs == []


def test_close_does_not_wait_for_or_retain_running_matcher(qtbot: QtBot) -> None:
    started, unblock, finished = Event(), Event(), Event()

    def slow(_g: GraphT, _v: int) -> bool:
        started.set()
        unblock.wait(5)
        finished.set()
        return True

    graph = new_graph()
    graph.add_vertex(VertexType.Z)
    panel = ProofPanel(graph)
    model = _model(panel)
    _install_rule(model, slow)
    try:
        qtbot.waitUntil(started.is_set)
        future = model._future
        panel_ref = weakref.ref(panel)
        panel.release_resources()
        assert not finished.is_set()
        panel.deleteLater()
        del panel, model
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        assert panel_ref() is None
    finally:
        unblock.set()
    assert future is not None
    future.result(timeout=2)
    qtbot.wait(20)  # There must be no callback into the deleted Qt objects.
