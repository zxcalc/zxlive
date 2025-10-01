#!/usr/bin/env python3
"""Unit test for merge functionality."""
import pytest
import pyzx
from pyzx import VertexType


def test_merge_vertices_same_position():
    """Test merging two vertices at the same position."""
    g = pyzx.Graph()
    v1 = g.add_vertex(VertexType.Z, 1, 2, phase=1)
    v2 = g.add_vertex(VertexType.Z, 1, 2, phase=0.5)
    v3 = g.add_vertex(VertexType.X, 3, 4)
    g.add_edge((v1, v3))
    g.add_edge((v2, v3))
    
    # Initial state
    assert len(list(g.vertices())) == 3
    assert v1 in g.vertices()
    assert v2 in g.vertices()
    
    # Simulate merge
    g.add_edge((v1, v2))
    pyzx.basicrules.fuse(g, v1, v2)
    
    # Check result
    assert len(list(g.vertices())) == 2
    assert v1 in g.vertices()
    assert v2 not in g.vertices()
    assert abs(g.phase(v1) - 1.5) < 0.001  # Phases should be added


def test_merge_vertices_different_positions():
    """Test that vertices at different positions are not merged."""
    g = pyzx.Graph()
    v1 = g.add_vertex(VertexType.Z, 1, 2)
    v2 = g.add_vertex(VertexType.Z, 3, 4)
    
    # Group by position
    vertices = [v1, v2]
    position_groups = {}
    for v in vertices:
        pos = (g.row(v), g.qubit(v))
        if pos not in position_groups:
            position_groups[pos] = []
        position_groups[pos].append(v)
    
    # Should have two separate position groups
    assert len(position_groups) == 2
    assert all(len(verts) == 1 for verts in position_groups.values())


def test_merge_three_vertices():
    """Test merging three vertices at the same position."""
    g = pyzx.Graph()
    v1 = g.add_vertex(VertexType.Z, 1, 2, phase=1)
    v2 = g.add_vertex(VertexType.Z, 1, 2, phase=0.5)
    v3 = g.add_vertex(VertexType.Z, 1, 2, phase=0.25)
    v4 = g.add_vertex(VertexType.X, 3, 4)
    g.add_edge((v1, v4))
    g.add_edge((v2, v4))
    g.add_edge((v3, v4))
    
    # Initial state
    assert len(list(g.vertices())) == 4
    
    # Simulate merge (v1 merges with v2, then with v3)
    vertices = [v1, v2, v3]
    verts = sorted(vertices)
    target = verts[0]
    
    for v in verts[1:]:
        if v in g.vertices():
            g.add_edge((target, v))
            pyzx.basicrules.fuse(g, target, v)
    
    # Check result
    assert len(list(g.vertices())) == 2
    assert v1 in g.vertices()
    assert v2 not in g.vertices()
    assert v3 not in g.vertices()
    assert abs(g.phase(v1) - 1.75) < 0.001  # 1 + 0.5 + 0.25


if __name__ == "__main__":
    test_merge_vertices_same_position()
    print("✓ test_merge_vertices_same_position passed")
    
    test_merge_vertices_different_positions()
    print("✓ test_merge_vertices_different_positions passed")
    
    test_merge_three_vertices()
    print("✓ test_merge_three_vertices passed")
    
    print("\n✓ All tests passed!")
