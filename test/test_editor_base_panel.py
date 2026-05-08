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


import pytest
from PySide6.QtCore import QPointF
from pyzx.utils import EdgeType, VertexType
from pytestqt.qtbot import QtBot

from zxlive.common import GraphT, SCALE, ToolType, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.editor_base_panel import string_to_complex
from zxlive.graphscene import EditGraphScene, EdgeDragSpec


def _edge_count(g: GraphT, u: int, v: int, ety: EdgeType = EdgeType.SIMPLE) -> int:
    expected = tuple(sorted((u, v)))
    count = 0
    for edge in g.edges():
        s, t = g.edge_st(edge)
        if tuple(sorted((s, t))) == expected and g.edge_type(edge) == ety:
            count += 1
    return count


def _parallel_graph() -> tuple[GraphT, int, int, int, int]:
    g = new_graph()
    left_top = g.add_vertex(VertexType.Z, qubit=0, row=0)
    left_bottom = g.add_vertex(VertexType.Z, qubit=1, row=0)
    right_top = g.add_vertex(VertexType.Z, qubit=0, row=2)
    right_bottom = g.add_vertex(VertexType.Z, qubit=1, row=2)
    return g, left_top, left_bottom, right_top, right_bottom


def test_string_to_complex() -> None:
    # Test empty input clears the phase.
    assert string_to_complex('') == 0

    # Test a complex input.
    assert string_to_complex('-123+456j') == -123 + 456j

    # Test complex phase specified with variables (not supported).
    with pytest.raises(ValueError):
        string_to_complex('a+bj')

    # Test bad input.
    with pytest.raises(ValueError):
        string_to_complex('bad input')


def test_parallel_edge_specs_match_targets_by_drag_offset(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(g)
    scene.select_vertices([left_top, left_bottom])

    sources = [scene.vertex_map[left_top], scene.vertex_map[left_bottom]]
    specs = scene._build_parallel_edge_specs(scene.vertex_map[left_top], scene.vertex_map[right_top], sources)

    assert [(spec.source, spec.target) for spec in specs] == [
        (left_top, right_top),
        (left_bottom, right_bottom),
    ]


def test_parallel_edge_specs_skip_missing_targets(qtbot: QtBot) -> None:
    g = new_graph()
    left_top = g.add_vertex(VertexType.Z, qubit=0, row=0)
    left_bottom = g.add_vertex(VertexType.Z, qubit=1, row=0)
    right_top = g.add_vertex(VertexType.Z, qubit=0, row=2)
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(g)
    scene.select_vertices([left_top, left_bottom])

    sources = [scene.vertex_map[left_top], scene.vertex_map[left_bottom]]
    specs = scene._build_parallel_edge_specs(scene.vertex_map[left_top], scene.vertex_map[right_top], sources)

    assert [(spec.source, spec.target) for spec in specs] == [(left_top, right_top)]


def test_parallel_edge_specs_keep_path_vertices_without_targets(qtbot: QtBot) -> None:
    g = new_graph()
    left_top = g.add_vertex(VertexType.Z, qubit=0, row=0)
    left_bottom = g.add_vertex(VertexType.Z, qubit=1, row=0)
    middle_top = g.add_vertex(VertexType.Z, qubit=0, row=1)
    middle_bottom = g.add_vertex(VertexType.Z, qubit=1, row=1)
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(g)
    scene.select_vertices([left_top, left_bottom])

    sources = [scene.vertex_map[left_top], scene.vertex_map[left_bottom]]
    end_pos = scene.vertex_map[left_top].pos() + QPointF(2 * SCALE, 0)
    specs = scene._build_parallel_edge_specs_to_pos(scene.vertex_map[left_top], end_pos, sources)

    assert [(spec.source, spec.target, [vitem.v for vitem in spec.colliding_verts]) for spec in specs] == [
        (left_top, None, [middle_top]),
        (left_bottom, None, [middle_bottom]),
    ]


def test_drag_sources_fall_back_to_single_when_not_multi_edge(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, _ = _parallel_graph()
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(g)

    assert scene._drag_sources_for_press(scene.vertex_map[right_top], {left_top, left_bottom}) == [
        scene.vertex_map[right_top]
    ]
    assert scene._drag_sources_for_press(scene.vertex_map[left_top], {left_top}) == [scene.vertex_map[left_top]]


def test_add_edges_adds_parallel_edges_as_one_undo_step(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False
    scene = panel.graph_scene
    scene.select_vertices([left_top, left_bottom])

    sources = [scene.vertex_map[left_top], scene.vertex_map[left_bottom]]
    specs = scene._build_parallel_edge_specs(scene.vertex_map[left_top], scene.vertex_map[right_top], sources)
    panel.add_edges(specs)

    assert panel.undo_stack.count() == 1
    assert _edge_count(scene.g, left_top, right_top) == 1
    assert _edge_count(scene.g, left_bottom, right_bottom) == 1

    panel.undo_stack.undo()
    assert _edge_count(scene.g, left_top, right_top) == 0
    assert _edge_count(scene.g, left_bottom, right_bottom) == 0


def test_add_edges_snap_chains_each_parallel_edge(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    middle_top = g.add_vertex(VertexType.Z, qubit=0, row=1)
    middle_bottom = g.add_vertex(VertexType.Z, qubit=1, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene
    scene.select_vertices([left_top, left_bottom])

    sources = [scene.vertex_map[left_top], scene.vertex_map[left_bottom]]
    specs = scene._build_parallel_edge_specs(scene.vertex_map[left_top], scene.vertex_map[right_top], sources)
    panel.add_edges(specs)

    assert _edge_count(scene.g, left_top, middle_top) == 1
    assert _edge_count(scene.g, middle_top, right_top) == 1
    assert _edge_count(scene.g, left_bottom, middle_bottom) == 1
    assert _edge_count(scene.g, middle_bottom, right_bottom) == 1
    assert _edge_count(scene.g, left_top, right_top) == 0
    assert _edge_count(scene.g, left_bottom, right_bottom) == 0


def test_add_edges_snap_chains_without_terminal_targets(qtbot: QtBot) -> None:
    g = new_graph()
    left_top = g.add_vertex(VertexType.Z, qubit=0, row=0)
    left_bottom = g.add_vertex(VertexType.Z, qubit=1, row=0)
    middle_top = g.add_vertex(VertexType.Z, qubit=0, row=1)
    middle_bottom = g.add_vertex(VertexType.Z, qubit=1, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene

    panel.add_edges([
        EdgeDragSpec(left_top, None, [scene.vertex_map[middle_top]]),
        EdgeDragSpec(left_bottom, None, [scene.vertex_map[middle_bottom]]),
    ])

    assert panel.undo_stack.count() == 1
    assert _edge_count(scene.g, left_top, middle_top) == 1
    assert _edge_count(scene.g, left_bottom, middle_bottom) == 1


def test_add_edges_without_terminal_target_needs_snap_enabled(qtbot: QtBot) -> None:
    g = new_graph()
    left = g.add_vertex(VertexType.Z, qubit=0, row=0)
    middle = g.add_vertex(VertexType.Z, qubit=0, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False
    scene = panel.graph_scene

    panel.add_edges([EdgeDragSpec(left, None, [scene.vertex_map[middle]])])

    assert panel.undo_stack.count() == 0
    assert _edge_count(scene.g, left, middle) == 0


def test_add_edges_without_terminal_target_skips_invalid_snap_chain(qtbot: QtBot) -> None:
    g = new_graph()
    dummy = g.add_vertex(VertexType.DUMMY, qubit=0, row=0)
    spider = g.add_vertex(VertexType.Z, qubit=0, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene

    panel.add_edges([EdgeDragSpec(dummy, None, [scene.vertex_map[spider]])])

    assert panel.undo_stack.count() == 0
    assert _edge_count(scene.g, dummy, spider) == 0


def test_add_edges_skips_invalid_pairs_without_blocking_valid_pairs(qtbot: QtBot) -> None:
    g = new_graph()
    dummy_source = g.add_vertex(VertexType.DUMMY, qubit=0, row=0)
    valid_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    invalid_target = g.add_vertex(VertexType.Z, qubit=0, row=2)
    valid_target = g.add_vertex(VertexType.Z, qubit=1, row=2)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False
    scene = panel.graph_scene
    scene.select_vertices([dummy_source, valid_source])

    sources = [scene.vertex_map[dummy_source], scene.vertex_map[valid_source]]
    specs = scene._build_parallel_edge_specs(scene.vertex_map[dummy_source], scene.vertex_map[invalid_target], sources)
    panel.add_edges(specs)

    assert _edge_count(scene.g, dummy_source, invalid_target) == 0
    assert _edge_count(scene.g, valid_source, valid_target) == 1
