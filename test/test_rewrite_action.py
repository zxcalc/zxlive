from __future__ import annotations

from typing import Any, cast

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from pyzx.rewrite import Rewrite
from pyzx.utils import EdgeType, VertexType

import zxlive.rewrite_action as rewrite_action_module
from zxlive.common import new_graph
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteAction, RewriteActionTreeModel
from zxlive.rewrite_data import MATCH_DOUBLE, MATCH_SINGLE


class _SingleRule:
    def __init__(self, matching_vertex: int) -> None:
        self.matching_vertex = matching_vertex
        self.applied_vertices: list[int] = []

    def is_match(self, _graph: object, vertex: int) -> bool:
        return vertex == self.matching_vertex

    def apply(self, _graph: object, vertex: int) -> bool:
        if vertex != self.matching_vertex:
            return False
        self.applied_vertices.append(vertex)
        return True


class _DoubleRule:
    def __init__(self, matching_pair: tuple[int, int]) -> None:
        self.matching_pair = frozenset(matching_pair)
        self.applied_pairs: list[tuple[int, int]] = []

    def is_match(self, _graph: object, v1: int, v2: int) -> bool:
        return frozenset((v1, v2)) == self.matching_pair

    def apply(self, _graph: object, v1: int, v2: int) -> bool:
        if frozenset((v1, v2)) != self.matching_pair:
            return False
        self.applied_pairs.append((v1, v2))
        return True


class _GraphScene:
    def __init__(self, graph: object) -> None:
        self.g = graph


class _UndoStack:
    def __init__(self) -> None:
        self.push_called = False

    def push(self, _cmd: object, *, anim_before: object, anim_after: object) -> None:
        self.push_called = True

class _RewriteActionTreeView:
    def __init__(self) -> None:
        self.refresh_rewrites_model = None

class _Panel:
    def __init__(self, graph: object, verts: list[int], edges: list[tuple[int, int, EdgeType]]) -> None:
        self.graph_scene = _GraphScene(graph)
        self.graph_view: object = object()
        self.step_view: object = object()
        self.undo_stack = _UndoStack()
        self._verts = verts
        self._edges = edges
        self.fault_equivalent_weight_value = None
        self.rewrites_panel = _RewriteActionTreeView()

    def parse_selection(self) -> tuple[list[int], list[tuple[int, int, EdgeType]]]:
        return self._verts.copy(), self._edges.copy()


def _patch_rewrite_side_effects(monkeypatch: Any) -> None:
    monkeypatch.setattr(rewrite_action_module, "AddRewriteStep", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(rewrite_action_module, "make_animation", lambda *_args, **_kwargs: (None, None))


def _make_chain_graph() -> tuple[object, int, int, tuple[int, int, EdgeType], tuple[int, int, EdgeType]]:
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    z1 = g.add_vertex(VertexType.Z, qubit=0, row=1)
    z2 = g.add_vertex(VertexType.Z, qubit=0, row=2)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    e_in = g.add_edge((inp, z1), EdgeType.SIMPLE)
    e_mid = g.add_edge((z1, z2), EdgeType.SIMPLE)
    g.add_edge((z2, out), EdgeType.SIMPLE)
    return g, z1, inp, e_mid, e_in


def test_update_active_single_treats_empty_selection_as_all_vertices() -> None:
    g, z1, inp, _, _ = _make_chain_graph()
    action = RewriteAction("single", cast(Rewrite, _SingleRule(z1)), MATCH_SINGLE, "")

    action.update_active(g, [], [])
    assert action.enabled

    action.update_active(g, [inp], [])
    assert not action.enabled


def test_update_active_double_treats_empty_selection_as_all_edges() -> None:
    g, z1, _inp, e_mid, e_in = _make_chain_graph()
    _, z2 = g.edge_st(e_mid)
    action = RewriteAction("double", cast(Rewrite, _DoubleRule((z1, z2))), MATCH_DOUBLE, "")

    action.update_active(g, [], [])
    assert action.enabled

    action.update_active(g, [], [e_in])
    assert not action.enabled


def test_custom_rule_tooltip_contains_graph_preview(
        qapp: QApplication, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        type(rewrite_action_module.display_setting),
        "previews_show",
        property(lambda _self: True),
    )
    graph = new_graph()
    graph.add_vertex(VertexType.Z, row=0, qubit=0)
    action = RewriteAction(
        "custom",
        cast(Rewrite, _SingleRule(0)),
        MATCH_SINGLE,
        "description",
        picture_path="custom",
        lhs_graph=graph,
        rhs_graph=graph,
    )

    tooltip = action.tooltip

    assert tooltip.startswith('<img src="data:image/png;base64,')
    assert tooltip.endswith("description")


def test_do_rewrite_single_treats_empty_selection_as_all_vertices(monkeypatch: Any) -> None:
    g, z1, _, _, _ = _make_chain_graph()
    rule = _SingleRule(z1)
    action = RewriteAction("single", cast(Rewrite, rule), MATCH_SINGLE, "")
    action.enabled = True
    panel = _Panel(g, [], [])
    _patch_rewrite_side_effects(monkeypatch)

    action.do_rewrite(cast(Any, panel))

    assert panel.undo_stack.push_called
    assert rule.applied_vertices == [z1]


def test_do_rewrite_double_treats_empty_selection_as_all_edges(monkeypatch: Any) -> None:
    g, z1, _, e_mid, _ = _make_chain_graph()
    _, z2 = g.edge_st(e_mid)
    rule = _DoubleRule((z1, z2))
    action = RewriteAction("double", cast(Rewrite, rule), MATCH_DOUBLE, "")
    action.enabled = True
    panel = _Panel(g, [], [])
    _patch_rewrite_side_effects(monkeypatch)

    action.do_rewrite(cast(Any, panel))

    assert panel.undo_stack.push_called
    assert len(rule.applied_pairs) == 1
    assert frozenset(rule.applied_pairs[0]) == frozenset((z1, z2))


def test_refreshing_reuses_the_model_and_its_worker(qtbot: QtBot, monkeypatch: Any) -> None:
    # A model per refresh would leak its worker thread and its selection_changed_custom connection.
    panel = ProofPanel(new_graph())
    qtbot.addWidget(panel)
    model = cast(RewriteActionTreeModel, panel.rewrites_panel.model())
    executor = model.executor
    submissions: list[object] = []
    monkeypatch.setattr(executor, "submit", lambda callback: submissions.append(callback))

    panel.rewrites_panel.refresh_rewrites_model()
    panel.rewrites_panel.refresh_rewrites_model()
    panel.graph_scene.selection_changed_custom.emit()

    assert panel.rewrites_panel.model() is model
    assert model.executor is executor
    assert submissions == [model.update_on_selection]
