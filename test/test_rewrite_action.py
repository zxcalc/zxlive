from __future__ import annotations

import base64
from fractions import Fraction
from typing import Any, cast

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from pyzx.rewrite import Rewrite
from pyzx.utils import EdgeType, VertexType

import zxlive.rewrite_action as rewrite_action_module
from zxlive.common import GraphT, new_graph
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteAction, RewriteActionTreeModel
from zxlive.rewrite_data import MATCH_DOUBLE, MATCH_SINGLE, rules_basic


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


class _OrderedDoubleRule(_DoubleRule):
    def __init__(self, matching_pair: tuple[int, int]) -> None:
        super().__init__(matching_pair)
        self.ordered_pair = matching_pair

    def is_match(self, _graph: object, v1: int, v2: int) -> bool:
        return (v1, v2) == self.ordered_pair

    def apply(self, _graph: object, v1: int, v2: int) -> bool:
        if (v1, v2) != self.ordered_pair:
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


def _make_chain_graph() -> tuple[GraphT, int, int, tuple[int, int, EdgeType], tuple[int, int, EdgeType]]:
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


@pytest.mark.parametrize("rule_name, picture", [
    ("id_simp", "remove_id.gif"),
    ("fuse_simp", "fuse_spiders.gif"),
    ("remove_self_loops", "remove_self_loops.svg"),
    ("hopf", "remove_parallel_edges.svg"),
    ("unfuse", "unfuse_spider.svg"),
    ("ocm", "save_positions.svg"),
    ("cc", "change_color_z.gif"),
    ("euler", "decompose_hadamard.gif"),
])
def test_basic_rule_tooltip_contains_preview(
        qapp: QApplication, monkeypatch: Any, rule_name: str, picture: str) -> None:
    monkeypatch.setattr(
        type(rewrite_action_module.display_setting),
        "previews_show",
        property(lambda _self: True),
    )
    action = RewriteAction.from_rewrite_data(rules_basic[rule_name])

    assert action.picture_path == picture
    tooltip = action.tooltip

    assert tooltip.startswith('<img src="data:image/png;base64,')
    assert tooltip.endswith(rules_basic[rule_name]["tooltip"])
    encoded = tooltip.split('base64,', 1)[1].split('"', 1)[0]
    pixmap = QPixmap()
    assert pixmap.loadFromData(base64.b64decode(encoded))
    assert pixmap.width() > 0 and pixmap.height() > 0


@pytest.mark.parametrize("rule_name, picture", [
    ("copy", "copy_pi.png"),
    ("bialgebra_op", "bialgebra.png"),
])
def test_existing_basic_rule_preview_is_unchanged(
        qapp: QApplication, monkeypatch: Any, rule_name: str, picture: str) -> None:
    monkeypatch.setattr(
        type(rewrite_action_module.display_setting),
        "previews_show",
        property(lambda _self: True),
    )
    action = RewriteAction.from_rewrite_data(rules_basic[rule_name])

    assert action.picture_path == picture
    assert action.tooltip.startswith('<img src="data:image/png;base64,')


def test_named_missing_previews_are_available_for_matching_graphs(qapp: QApplication) -> None:
    identity_graph = new_graph()
    left = identity_graph.add_vertex(VertexType.BOUNDARY, row=0, qubit=0)
    spider = identity_graph.add_vertex(VertexType.Z, row=1, qubit=0)
    right = identity_graph.add_vertex(VertexType.BOUNDARY, row=2, qubit=0)
    identity_graph.add_edge((left, spider))
    identity_graph.add_edge((spider, right))

    fuse_graph, _, _, _, _ = _make_chain_graph()

    loop_graph = new_graph()
    loop_vertex = loop_graph.add_vertex(VertexType.Z, row=1, qubit=0)
    loop_graph.add_edge((loop_vertex, loop_vertex))

    for name, graph in (
        ("id_simp", identity_graph),
        ("fuse_simp", fuse_graph),
        ("remove_self_loops", loop_graph),
    ):
        action = RewriteAction.from_rewrite_data(rules_basic[name])
        action.update_active(cast(GraphT, graph), [], [])
        assert action.enabled
        assert action.picture_path is not None


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


def test_do_rewrite_only_animates_applied_matches(monkeypatch: Any) -> None:
    g, z1, _, e_mid, _ = _make_chain_graph()
    _, z2 = g.edge_st(e_mid)

    class _FirstApplyOnlyRule(_SingleRule):
        """Matches z1 and z2, but applying the first match stops the second from applying."""
        def is_match(self, _graph: object, vertex: int) -> bool:
            return vertex in (z1, z2)

        def apply(self, _graph: object, vertex: int) -> bool:
            if self.applied_vertices:
                return False
            self.applied_vertices.append(vertex)
            return True

    action = RewriteAction("single", cast(Rewrite, _FirstApplyOnlyRule(z1)), MATCH_SINGLE, "")
    action.enabled = True
    panel = _Panel(g, [z1, z2], [])
    _patch_rewrite_side_effects(monkeypatch)
    animated_matches: list[list[Any]] = []
    def record_animation(_self: Any, _panel: Any, _g: Any, matches: list[Any], _rem: Any) -> tuple[None, None]:
        animated_matches.append(matches)
        return None, None

    monkeypatch.setattr(rewrite_action_module, "make_animation",
                        record_animation)

    action.do_rewrite(cast(Any, panel))

    assert animated_matches == [[z1]]


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


@pytest.mark.parametrize("reverse", [False, True])
def test_update_active_double_matches_either_edge_order(reverse: bool) -> None:
    g, _z1, _inp, e_mid, _ = _make_chain_graph()
    s, t = g.edge_st(e_mid)
    pair = (t, s) if reverse else (s, t)
    action = RewriteAction("double", cast(Rewrite, _OrderedDoubleRule(pair)), MATCH_DOUBLE, "")

    action.update_active(g, [], [e_mid])

    assert action.enabled


@pytest.mark.parametrize("reverse", [False, True])
def test_do_rewrite_double_applies_in_matching_order_once(monkeypatch: Any, reverse: bool) -> None:
    g, _z1, _inp, e_mid, _ = _make_chain_graph()
    s, t = g.edge_st(e_mid)
    pair = (t, s) if reverse else (s, t)
    rule = _OrderedDoubleRule(pair)
    action = RewriteAction("double", cast(Rewrite, rule), MATCH_DOUBLE, "")
    action.enabled = True
    panel = _Panel(g, [], [e_mid])
    _patch_rewrite_side_effects(monkeypatch)

    action.do_rewrite(cast(Any, panel))

    assert rule.applied_pairs == [pair]


@pytest.mark.parametrize("pauli, spider", [(1, 2), (2, 1)])
def test_push_pauli_matches_for_either_vertex_order(monkeypatch: Any, pauli: int, spider: int) -> None:
    g = new_graph()
    g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0, index=0)
    g.add_vertex(VertexType.X, qubit=0, row=1, phase=Fraction(1), index=pauli)
    g.add_vertex(VertexType.Z, qubit=0, row=2, phase=Fraction(1, 4), index=spider)
    g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3, index=3)
    g.add_vertex(VertexType.BOUNDARY, qubit=1, row=3, index=4)
    e = g.add_edge((pauli, spider))
    for v, w in ((0, pauli), (spider, 3), (spider, 4)):
        g.add_edge((v, w))
    action = RewriteAction.from_rewrite_data(rules_basic["pauli"])

    action.update_active(g, [], [e])
    assert action.enabled

    panel = _Panel(g, [], [e])
    _patch_rewrite_side_effects(monkeypatch)
    steps: list[dict[str, Any]] = []
    monkeypatch.setattr(rewrite_action_module, "AddRewriteStep", lambda **kwargs: steps.append(kwargs))
    action.do_rewrite(cast(Any, panel))

    assert panel.undo_stack.push_called
    assert pauli not in steps[0]["new_g"].vertices()


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
