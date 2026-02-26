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


from pyzx.utils import EdgeType, VertexType

from zxlive.common import new_graph
from zxlive.proof import apply_step_difference_highlighting


def test_highlight_removed_edge_and_incident_vertices() -> None:
    g1 = new_graph()
    v0 = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    v1 = g1.add_vertex(VertexType.X, row=1, qubit=0)
    g1.add_edge((v0, v1), EdgeType.SIMPLE)
    e = g1.edge(v0, v1)

    g2 = g1.copy()
    e2 = g2.edge(v0, v1)
    g2.remove_edge(e2)

    apply_step_difference_highlighting(g1, g2)

    assert g1.edata(e, "diff_highlight", False)
    assert g1.vdata(v0, "diff_highlight", False)
    assert g1.vdata(v1, "diff_highlight", False)


def test_highlight_clears_when_no_next_step() -> None:
    g = new_graph()
    v0 = g.add_vertex(VertexType.Z, row=0, qubit=0)
    g.set_vdata(v0, "diff_highlight", True)

    apply_step_difference_highlighting(g, None)

    assert not g.vdata(v0, "diff_highlight", False)

def test_highlight_vertices_for_new_edge_in_next_step() -> None:
    g1 = new_graph()
    v0 = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    v1 = g1.add_vertex(VertexType.X, row=1, qubit=0)

    g2 = g1.copy()
    g2.add_edge((v0, v1), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    assert g1.vdata(v0, "diff_highlight", False)
    assert g1.vdata(v1, "diff_highlight", False)


def test_ignores_existing_diff_metadata_when_computing_diff() -> None:
    g1 = new_graph()
    v0 = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    v1 = g1.add_vertex(VertexType.X, row=1, qubit=0)
    g1.add_edge((v0, v1), EdgeType.SIMPLE)
    e = g1.edge(v0, v1)

    g2 = g1.copy()

    # Simulate stale transient metadata from a previous selection.
    g1.set_vdata(v0, "diff_highlight", True)
    g1.set_vdata(v1, "diff_highlight", True)
    g1.set_edata(e, "diff_highlight", True)

    apply_step_difference_highlighting(g1, g2)

    assert not g1.vdata(v0, "diff_highlight", False)
    assert not g1.vdata(v1, "diff_highlight", False)
    assert not g1.edata(e, "diff_highlight", False)


def test_position_only_changes_are_not_highlighted() -> None:
    g1 = new_graph()
    v0 = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    v1 = g1.add_vertex(VertexType.X, row=1, qubit=0)
    g1.add_edge((v0, v1), EdgeType.SIMPLE)
    e = g1.edge(v0, v1)

    g2 = g1.copy()
    g2.set_row(v0, 0.5)
    g2.set_qubit(v1, 0.5)

    apply_step_difference_highlighting(g1, g2)

    assert not g1.vdata(v0, "diff_highlight", False)
    assert not g1.vdata(v1, "diff_highlight", False)
    assert not g1.edata(e, "diff_highlight", False)


def test_vdata_only_changes_are_not_highlighted() -> None:
    g1 = new_graph()
    v0 = g1.add_vertex(VertexType.DUMMY, row=0, qubit=0)

    g2 = g1.copy()
    g2.set_vdata(v0, "text", "changed-label")

    apply_step_difference_highlighting(g1, g2)

    assert not g1.vdata(v0, "diff_highlight", False)

def test_identical_geometry_with_different_vertex_ids_is_not_highlighted() -> None:
    g1 = new_graph()
    a = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    b = g1.add_vertex(VertexType.X, row=1, qubit=0)
    c = g1.add_vertex(VertexType.Z, row=2, qubit=0)
    g1.add_edge((a, b), EdgeType.SIMPLE)
    g1.add_edge((b, c), EdgeType.SIMPLE)

    # Rebuild equivalent graph in a different insertion order (different vertex ids).
    g2 = new_graph()
    c2 = g2.add_vertex(VertexType.Z, row=2, qubit=0)
    a2 = g2.add_vertex(VertexType.Z, row=0, qubit=0)
    b2 = g2.add_vertex(VertexType.X, row=1, qubit=0)
    g2.add_edge((a2, b2), EdgeType.SIMPLE)
    g2.add_edge((b2, c2), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    for v in g1.vertices():
        assert not g1.vdata(v, "diff_highlight", False)
    for e in g1.edges():
        assert not g1.edata(e, "diff_highlight", False)


def test_fusion_highlights_only_fused_spiders_and_connecting_edge() -> None:
    g1 = new_graph()
    left = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    right = g1.add_vertex(VertexType.Z, row=1, qubit=0)
    neighbor = g1.add_vertex(VertexType.X, row=0, qubit=1)
    far = g1.add_vertex(VertexType.X, row=5, qubit=5)
    g1.add_edge((left, right), EdgeType.SIMPLE)
    g1.add_edge((left, neighbor), EdgeType.SIMPLE)
    g1.add_edge((far, far), EdgeType.SIMPLE)

    e_fuse = g1.edge(left, right)
    e_transferred = g1.edge(left, neighbor)
    e_far = g1.edge(far, far)

    g2 = new_graph()
    right2 = g2.add_vertex(VertexType.Z, row=1, qubit=0)
    neighbor2 = g2.add_vertex(VertexType.X, row=0, qubit=1)
    far2 = g2.add_vertex(VertexType.X, row=5, qubit=5)
    g2.add_edge((right2, neighbor2), EdgeType.SIMPLE)
    g2.add_edge((far2, far2), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    assert g1.vdata(left, "diff_highlight", False)
    assert g1.vdata(right, "diff_highlight", False)
    assert not g1.vdata(neighbor, "diff_highlight", False)
    assert not g1.vdata(far, "diff_highlight", False)

    assert g1.edata(e_fuse, "diff_highlight", False)
    assert not g1.edata(e_transferred, "diff_highlight", False)
    assert not g1.edata(e_far, "diff_highlight", False)


def test_fusion_highlights_partner_even_if_type_changes() -> None:
    g1 = new_graph()
    left = g1.add_vertex(VertexType.X, row=0, qubit=0)
    right = g1.add_vertex(VertexType.Z, row=1, qubit=0)
    far = g1.add_vertex(VertexType.Z, row=5, qubit=5)
    g1.add_edge((left, right), EdgeType.SIMPLE)
    g1.add_edge((far, far), EdgeType.SIMPLE)

    e_fuse = g1.edge(left, right)
    e_far = g1.edge(far, far)

    g2 = new_graph()
    right2 = g2.add_vertex(VertexType.Z, row=1, qubit=0)
    far2 = g2.add_vertex(VertexType.Z, row=5, qubit=5)
    g2.add_edge((far2, far2), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    assert g1.vdata(left, "diff_highlight", False)
    assert g1.vdata(right, "diff_highlight", False)
    assert g1.edata(e_fuse, "diff_highlight", False)

    assert not g1.vdata(far, "diff_highlight", False)
    assert not g1.edata(e_far, "diff_highlight", False)


def test_fusion_highlights_neighbor_when_survivor_phase_changes() -> None:
    g1 = new_graph()
    removed = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    survivor = g1.add_vertex(VertexType.Z, row=1, qubit=0)
    far = g1.add_vertex(VertexType.X, row=5, qubit=5)
    g1.add_edge((removed, survivor), EdgeType.SIMPLE)
    g1.add_edge((far, far), EdgeType.SIMPLE)
    e_fuse = g1.edge(removed, survivor)

    g2 = new_graph()
    survivor2 = g2.add_vertex(VertexType.Z, row=1, qubit=0)
    # Simulate phase accumulation on fusion so key-based mapping changes.
    g2.set_phase(survivor2, 1)
    far2 = g2.add_vertex(VertexType.X, row=5, qubit=5)
    g2.add_edge((far2, far2), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    assert g1.vdata(removed, "diff_highlight", False)
    assert g1.vdata(survivor, "diff_highlight", False)
    assert g1.edata(e_fuse, "diff_highlight", False)

def test_explicit_fuse_hint_highlights_exact_vertices_and_edge() -> None:
    g1 = new_graph()
    v = g1.add_vertex(VertexType.X, row=0, qubit=0)
    w = g1.add_vertex(VertexType.Z, row=1, qubit=0)
    far = g1.add_vertex(VertexType.Z, row=3, qubit=3)
    g1.add_edge((v, w), EdgeType.SIMPLE)
    g1.add_edge((far, far), EdgeType.SIMPLE)

    e_vw = g1.edge(v, w)
    e_far = g1.edge(far, far)

    g2 = g1.copy()
    g2.remove_vertex(v)

    apply_step_difference_highlighting(g1, g2, {"vertices": [v, w], "edge_pairs": [(min(v, w), max(v, w))]})

    assert g1.vdata(v, "diff_highlight", False)
    assert g1.vdata(w, "diff_highlight", False)
    assert not g1.vdata(far, "diff_highlight", False)
    assert g1.edata(e_vw, "diff_highlight", False)
    assert not g1.edata(e_far, "diff_highlight", False)


def test_vertex_only_hint_highlights_only_that_spider() -> None:
    g1 = new_graph()
    v = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    other = g1.add_vertex(VertexType.X, row=1, qubit=0)
    g1.add_edge((v, other), EdgeType.SIMPLE)
    e = g1.edge(v, other)

    g2 = g1.copy()
    g2.set_type(v, VertexType.X)

    apply_step_difference_highlighting(g1, g2, {"vertices": [v], "edge_pairs": []})

    assert g1.vdata(v, "diff_highlight", False)
    assert not g1.vdata(other, "diff_highlight", False)
    assert not g1.edata(e, "diff_highlight", False)


def test_removed_vertex_hint_highlights_only_removed_spider() -> None:
    g1 = new_graph()
    v = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    a = g1.add_vertex(VertexType.BOUNDARY, row=-1, qubit=0)
    b = g1.add_vertex(VertexType.BOUNDARY, row=1, qubit=0)
    g1.add_edge((a, v), EdgeType.SIMPLE)
    g1.add_edge((v, b), EdgeType.SIMPLE)

    g2 = g1.copy()
    g2.remove_vertex(v)
    g2.add_edge((a, b), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2, {"vertices": [v], "edge_pairs": []})

    assert g1.vdata(v, "diff_highlight", False)
    assert not g1.vdata(a, "diff_highlight", False)
    assert not g1.vdata(b, "diff_highlight", False)

