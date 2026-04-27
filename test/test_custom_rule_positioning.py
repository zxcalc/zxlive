#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for custom rule vertex positioning (issue #171).

When a custom rule has only 2 boundary nodes, the polygon area is 0,
which previously caused the spring layout parameter k to be 0.  The fix
uses max inter-boundary distance instead.
"""

import math

import networkx as nx
import numpy as np
from pyzx.utils import EdgeType, VertexType

from zxlive.common import new_graph
from zxlive.custom_rule import get_vertex_positions


def _make_graph_with_positions(positions: list[tuple[float, float]]) -> tuple:
    """Create a graph with boundary vertices at the given (row, qubit) positions.

    Returns (graph, vertex_ids).
    """
    g = new_graph()
    verts = []
    for row, qubit in positions:
        v = g.add_vertex(VertexType.BOUNDARY, row=row, qubit=qubit)
        verts.append(v)
    return g, verts


def _make_rhs_graph(
    n_boundary: int, n_interior: int
) -> tuple[nx.MultiGraph, list[int], list[int]]:
    """Build a simple RHS networkx graph.

    Returns (rhs_graph, boundary_node_ids, interior_node_ids).
    Boundary nodes are connected to the first interior node;
    interior nodes are chained together.
    """
    G = nx.MultiGraph()
    boundary_ids = list(range(n_boundary))
    interior_ids = list(range(n_boundary, n_boundary + n_interior))

    for b in boundary_ids:
        G.add_node(b, type=VertexType.BOUNDARY, phase=0,
                   boundary_index=f"input_{b}")
    for i in interior_ids:
        G.add_node(i, type=VertexType.Z, phase=0)

    # Connect every boundary to the first interior node.
    if interior_ids:
        for b in boundary_ids:
            G.add_edge(b, interior_ids[0], type=EdgeType.SIMPLE)
        # Chain interior nodes together.
        for idx in range(len(interior_ids) - 1):
            G.add_edge(interior_ids[idx], interior_ids[idx + 1],
                       type=EdgeType.SIMPLE)

    return G, boundary_ids, interior_ids


def _assert_positions_finite(positions: dict) -> None:
    for v, (r, q) in positions.items():
        assert math.isfinite(r), f"vertex {v}: row {r} is not finite"
        assert math.isfinite(q), f"vertex {v}: qubit {q} is not finite"


def test_two_boundary_nodes_interior_between() -> None:
    """Interior nodes should be placed roughly between the 2 boundaries,
    not all collapsed to the same point."""
    graph, verts = _make_graph_with_positions([(0.0, 0.0), (10.0, 0.0)])
    rhs, b_ids, i_ids = _make_rhs_graph(n_boundary=2, n_interior=2)
    bv_map = {b_ids[0]: verts[0], b_ids[1]: verts[1]}

    positions = get_vertex_positions(graph, rhs, bv_map)

    # The two interior nodes should not be at the same position.
    p0 = np.array(positions[i_ids[0]])
    p1 = np.array(positions[i_ids[1]])
    assert float(np.linalg.norm(p0 - p1)) > 1e-6


def test_three_boundary_nodes_triangle() -> None:
    """3 boundary nodes forming a triangle should still work (non-zero area)."""
    graph, verts = _make_graph_with_positions(
        [(0.0, 0.0), (4.0, 0.0), (2.0, 3.0)]
    )
    rhs, b_ids, _ = _make_rhs_graph(n_boundary=3, n_interior=1)
    bv_map = {b_ids[i]: verts[i] for i in range(3)}

    positions = get_vertex_positions(graph, rhs, bv_map)

    assert len(positions) == 4
    _assert_positions_finite(positions)


def test_three_collinear_boundary_nodes() -> None:
    """3 boundary nodes in a line also have area 0 and should be handled."""
    graph, verts = _make_graph_with_positions(
        [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)]
    )
    rhs, b_ids, _ = _make_rhs_graph(n_boundary=3, n_interior=1)
    bv_map = {b_ids[i]: verts[i] for i in range(3)}

    positions = get_vertex_positions(graph, rhs, bv_map)
    _assert_positions_finite(positions)


def test_coincident_boundary_nodes() -> None:
    """All boundary nodes at the same position (distance = 0, area = 0)."""
    graph, verts = _make_graph_with_positions([(1.0, 1.0), (1.0, 1.0)])
    rhs, b_ids, _ = _make_rhs_graph(n_boundary=2, n_interior=1)
    bv_map = {b_ids[0]: verts[0], b_ids[1]: verts[1]}

    positions = get_vertex_positions(graph, rhs, bv_map)
    _assert_positions_finite(positions)


def test_no_boundary_nodes() -> None:
    """A custom rule with no boundary nodes should not raise."""
    graph, _ = _make_graph_with_positions([])
    rhs, _, _ = _make_rhs_graph(n_boundary=0, n_interior=2)
    bv_map: dict[int, int] = {}

    positions = get_vertex_positions(graph, rhs, bv_map)
    _assert_positions_finite(positions)


def test_empty_rhs_graph() -> None:
    """An empty RHS graph should return no positions and not raise."""
    graph, _ = _make_graph_with_positions([])
    rhs, _, _ = _make_rhs_graph(n_boundary=0, n_interior=0)
    bv_map: dict[int, int] = {}

    positions = get_vertex_positions(graph, rhs, bv_map)
    assert positions == {}
