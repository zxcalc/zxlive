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


def test_fusion_like_change_highlights_local_region_only() -> None:
    g1 = new_graph()
    left = g1.add_vertex(VertexType.Z, row=0, qubit=0)
    mid = g1.add_vertex(VertexType.Z, row=1, qubit=0)
    right = g1.add_vertex(VertexType.Z, row=2, qubit=0)
    far = g1.add_vertex(VertexType.X, row=0, qubit=2)
    g1.add_edge((left, mid), EdgeType.SIMPLE)
    g1.add_edge((mid, right), EdgeType.SIMPLE)

    g2 = new_graph()
    left2 = g2.add_vertex(VertexType.Z, row=0, qubit=0)
    right2 = g2.add_vertex(VertexType.Z, row=2, qubit=0)
    far2 = g2.add_vertex(VertexType.X, row=0, qubit=2)
    g2.add_edge((left2, right2), EdgeType.SIMPLE)

    apply_step_difference_highlighting(g1, g2)

    assert g1.vdata(mid, "diff_highlight", False)
    assert g1.vdata(left, "diff_highlight", False)
    assert g1.vdata(right, "diff_highlight", False)
    assert not g1.vdata(far, "diff_highlight", False)

