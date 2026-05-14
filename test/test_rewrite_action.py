from __future__ import annotations

from typing import cast

from pyzx.rewrite import Rewrite
from pyzx.utils import EdgeType, VertexType

from zxlive.common import new_graph
from zxlive.rewrite_action import RewriteAction
from zxlive.rewrite_data import MATCH_DOUBLE, MATCH_SINGLE


class _SingleRule:
    def __init__(self, matching_vertex: int) -> None:
        self.matching_vertex = matching_vertex

    def is_match(self, _graph: object, vertex: int) -> bool:
        return vertex == self.matching_vertex


class _DoubleRule:
    def __init__(self, matching_pair: tuple[int, int]) -> None:
        self.matching_pair = frozenset(matching_pair)

    def is_match(self, _graph: object, v1: int, v2: int) -> bool:
        return frozenset((v1, v2)) == self.matching_pair


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
