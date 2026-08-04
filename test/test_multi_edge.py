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


from PySide6.QtCore import QEvent, QPointF
from PySide6.QtWidgets import QGraphicsSceneMouseEvent
from pyzx.utils import EdgeType, VertexType
from pytestqt.qtbot import QtBot

from zxlive.common import GraphT, SCALE, ToolType, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.eitem import EDragItem
from zxlive.graphscene import EditGraphScene, EdgeDragSpec
from zxlive.proof_panel import ProofPanel


def _edge_count(g: GraphT, u: int, v: int, ety: EdgeType = EdgeType.SIMPLE) -> int:
    endpoints = tuple(sorted((u, v)))
    return sum(
        tuple(sorted(g.edge_st(edge))) == endpoints and g.edge_type(edge) == ety
        for edge in g.edges()
    )


def _parallel_graph() -> tuple[GraphT, int, int, int, int]:
    g = new_graph()
    left_top = g.add_vertex(VertexType.Z, qubit=0, row=0)
    left_bottom = g.add_vertex(VertexType.Z, qubit=1, row=0)
    right_top = g.add_vertex(VertexType.Z, qubit=0, row=2)
    right_bottom = g.add_vertex(VertexType.Z, qubit=1, row=2)
    return g, left_top, left_bottom, right_top, right_bottom


def _release_multi_drag(scene: EditGraphScene, sources: list[int],
                        pos: QPointF) -> tuple[list[list[EdgeDragSpec]], bool]:
    source_items = [scene.vertex_map[source] for source in sources]
    drag = EDragItem(scene.g, EdgeType.SIMPLE, source_items[0], source_items[0].pos(), starts=source_items)
    scene._drag = drag
    scene.addItem(drag)
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    event.setScenePos(pos)
    emitted: list[list[EdgeDragSpec]] = []
    scene.edges_added.connect(emitted.append)
    scene.add_edge(event)
    return emitted, event.isAccepted()


def test_multi_edge_drag_uses_target_centres(qtbot: QtBot) -> None:
    """An off-centre drag previews and commits the same centred translation."""
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    parallel_source = g.add_vertex(VertexType.DUMMY, qubit=1, row=0)
    target = g.add_vertex(VertexType.Z, qubit=0, row=2)
    parallel_target = g.add_vertex(VertexType.DUMMY, qubit=1, row=2)
    scene = EditGraphScene()
    scene.set_graph(g)

    source_items = [scene.vertex_map[source], scene.vertex_map[parallel_source]]
    drag = EDragItem(scene.g, EdgeType.SIMPLE, source_items[0], source_items[0].pos(), starts=source_items)
    scene._drag = drag
    scene.addItem(drag)
    cursor_pos = scene.vertex_map[target].pos() + QPointF(0.1 * SCALE, 0)

    move_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
    move_event.setScenePos(cursor_pos)
    scene.mouseMoveEvent(move_event)

    preview = drag.path()
    primary_end = preview.elementAt(1)
    parallel_end = preview.elementAt(3)
    assert QPointF(primary_end.x, primary_end.y) == scene.vertex_map[target].pos()
    assert QPointF(parallel_end.x, parallel_end.y) == scene.vertex_map[parallel_target].pos()

    release_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release_event.setScenePos(cursor_pos)
    emitted: list[list[EdgeDragSpec]] = []
    scene.edges_added.connect(emitted.append)
    scene.add_edge(release_event)

    specs = emitted[0]
    assert [(spec.source, spec.target) for spec in specs] == [
        (source, target),
        (parallel_source, parallel_target),
    ]


def test_multi_edge_drag_to_empty_space_uses_collisions(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    parallel_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    crossed = g.add_vertex(VertexType.Z, qubit=0, row=1.5)
    parallel_crossed = g.add_vertex(VertexType.Z, qubit=1, row=1.5)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene

    emitted, _ = _release_multi_drag(
        scene,
        [source, parallel_source],
        scene.vertex_map[source].pos() + QPointF(2 * SCALE, 0),
    )

    specs = emitted[0]
    assert [
        (spec.source, spec.target, [item.v for item in spec.colliding_verts])
        for spec in specs
    ] == [
        (source, None, [crossed]),
        (parallel_source, None, [parallel_crossed]),
    ]
    assert panel.undo_stack.count() == 1
    assert _edge_count(panel.graph, source, crossed) == 1
    assert _edge_count(panel.graph, parallel_source, parallel_crossed) == 1


def test_multi_edge_drag_mixes_target_and_collision(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    parallel_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    target = g.add_vertex(VertexType.Z, qubit=0, row=2)
    parallel_crossed = g.add_vertex(VertexType.Z, qubit=1, row=1.5)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)

    emitted, _ = _release_multi_drag(
        panel.graph_scene,
        [source, parallel_source],
        panel.graph_scene.vertex_map[target].pos(),
    )

    specs = emitted[0]
    assert [
        (spec.source, spec.target, [item.v for item in spec.colliding_verts])
        for spec in specs
    ] == [
        (source, target, []),
        (parallel_source, None, [parallel_crossed]),
    ]
    assert panel.undo_stack.count() == 1
    assert _edge_count(panel.graph, source, target) == 1
    assert _edge_count(panel.graph, parallel_source, parallel_crossed) == 1


def test_multi_edge_drag_to_empty_space_without_collisions_is_ignored(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    parallel_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    scene = EditGraphScene()
    scene.set_graph(g)

    emitted, accepted = _release_multi_drag(
        scene,
        [source, parallel_source],
        scene.vertex_map[source].pos() + QPointF(2 * SCALE, 0),
    )

    assert emitted == []
    assert not accepted


def test_multi_edge_drag_primary_miss_cancels_secondary_hit(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    parallel_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    parallel_target = g.add_vertex(VertexType.Z, qubit=1, row=2)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)

    emitted, accepted = _release_multi_drag(
        panel.graph_scene,
        [source, parallel_source],
        panel.graph_scene.vertex_map[source].pos() + QPointF(2 * SCALE, 0),
    )

    assert emitted == []
    assert not accepted
    assert panel.undo_stack.count() == 0
    assert _edge_count(panel.graph, parallel_source, parallel_target) == 0


def test_multi_edge_specs_skip_missing_parallel_target(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    unmatched_source = g.add_vertex(VertexType.Z, qubit=1, row=0)
    target = g.add_vertex(VertexType.Z, qubit=0, row=2)
    scene = EditGraphScene()
    scene.set_graph(g)

    specs = scene._build_edge_specs(
        scene.vertex_map[source],
        scene.vertex_map[target].pos(),
        [scene.vertex_map[source], scene.vertex_map[unmatched_source]],
    )

    assert [(spec.source, spec.target) for spec in specs] == [(source, target)]


def test_drag_sources_put_pressed_vertex_first(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, _ = _parallel_graph()
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(g)

    sources = scene._drag_sources_for_press(
        scene.vertex_map[left_bottom], {left_top, left_bottom}
    )
    assert sources == [scene.vertex_map[left_bottom], scene.vertex_map[left_top]]
    assert scene._drag_sources_for_press(
        scene.vertex_map[right_top], {left_top, left_bottom}
    ) == [scene.vertex_map[right_top]]


def test_add_edges_is_one_undo_step(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    g.add_edge((left_top, right_top))
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False

    panel.add_edges([
        EdgeDragSpec(left_top, right_top, []),
        EdgeDragSpec(left_bottom, right_bottom, []),
    ])

    assert panel.undo_stack.count() == 1
    assert _edge_count(panel.graph, left_top, right_top) == 2
    assert _edge_count(panel.graph, left_bottom, right_bottom) == 1
    panel.undo_stack.undo()
    assert _edge_count(panel.graph, left_top, right_top) == 1
    assert _edge_count(panel.graph, left_bottom, right_bottom) == 0
    panel.undo_stack.redo()
    assert _edge_count(panel.graph, left_top, right_top) == 2
    assert _edge_count(panel.graph, left_bottom, right_bottom) == 1


def test_add_edges_snaps_each_parallel_path(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    middle_top = g.add_vertex(VertexType.Z, qubit=0, row=1)
    middle_bottom = g.add_vertex(VertexType.Z, qubit=1, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene

    panel.add_edges([
        EdgeDragSpec(left_top, right_top, [scene.vertex_map[middle_top]]),
        EdgeDragSpec(left_bottom, right_bottom, [scene.vertex_map[middle_bottom]]),
    ])

    assert _edge_count(panel.graph, left_top, middle_top) == 1
    assert _edge_count(panel.graph, middle_top, right_top) == 1
    assert _edge_count(panel.graph, left_bottom, middle_bottom) == 1
    assert _edge_count(panel.graph, middle_bottom, right_bottom) == 1


def test_edge_drags_reject_invalid_snap_path(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.DUMMY, qubit=0, row=0)
    crossed = g.add_vertex(VertexType.Z, qubit=0, row=1)
    target = g.add_vertex(VertexType.DUMMY, qubit=0, row=2)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)

    panel.add_edge(source, target, [panel.graph_scene.vertex_map[crossed]])
    panel.add_edges([EdgeDragSpec(source, target, [panel.graph_scene.vertex_map[crossed]])])
    panel.add_edges([EdgeDragSpec(source, None, [panel.graph_scene.vertex_map[crossed]])])

    assert panel.undo_stack.count() == 0
    assert list(panel.graph.edges()) == []


def test_collision_ended_edges_require_snap_enabled(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    crossed = g.add_vertex(VertexType.Z, qubit=0, row=1)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False

    panel.add_edges([EdgeDragSpec(source, None, [panel.graph_scene.vertex_map[crossed]])])

    assert panel.undo_stack.count() == 0
    assert _edge_count(panel.graph, source, crossed) == 0


def test_add_edges_respects_w_input_degree_across_batch(qtbot: QtBot) -> None:
    g = new_graph()
    source = g.add_vertex(VertexType.Z, qubit=0, row=0)
    w_input = g.add_vertex(VertexType.W_INPUT, qubit=0, row=1)
    w_output = g.add_vertex(VertexType.W_OUTPUT, qubit=0, row=1.3)
    target = g.add_vertex(VertexType.Z, qubit=0, row=2)
    g.add_edge((w_input, w_output), EdgeType.W_IO)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.snap_vertex_edge = False

    panel.add_edges([
        EdgeDragSpec(source, w_input, []),
        EdgeDragSpec(w_input, target, []),
    ])

    assert _edge_count(panel.graph, source, w_input) == 1
    assert _edge_count(panel.graph, w_input, target) == 0


def test_proof_panel_adds_dummy_edges_as_one_undo_step(qtbot: QtBot) -> None:
    g, left_top, left_bottom, right_top, right_bottom = _parallel_graph()
    for vertex in g.vertices():
        g.set_type(vertex, VertexType.DUMMY)
    panel = ProofPanel(g)
    qtbot.addWidget(panel)
    panel.graph_scene.curr_tool = ToolType.EDGE

    panel.graph_scene.edges_added.emit([
        EdgeDragSpec(left_top, right_top, []),
        EdgeDragSpec(left_bottom, right_bottom, []),
    ])

    assert panel.undo_stack.count() == 1
    assert _edge_count(panel.graph, left_top, right_top) == 1
    assert _edge_count(panel.graph, left_bottom, right_bottom) == 1
