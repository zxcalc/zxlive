from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtWidgets import QGraphicsSceneContextMenuEvent, QGraphicsSceneMouseEvent, QGraphicsView
import pytest
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

import zxlive.graphscene
from zxlive.common import SCALE, ToolType, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.graphscene import EditGraphScene


def _mouse_event(event_type: QEvent.Type, pos: QPointF) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(event_type)
    event.setScenePos(pos)
    event.setButton(Qt.MouseButton.LeftButton)
    return event


def _scene_with_vertex(qtbot: QtBot) -> tuple[EditGraphScene, QGraphicsView, int]:
    graph = new_graph()
    vertex = graph.add_vertex(VertexType.Z, qubit=0, row=0)
    scene = EditGraphScene()
    scene.curr_tool = ToolType.EDGE
    scene.set_graph(graph)
    view = QGraphicsView(scene)
    qtbot.addWidget(view)
    return scene, view, vertex


def test_edge_tool_single_click_does_not_create_self_loop(qtbot: QtBot) -> None:
    scene, _view, vertex = _scene_with_vertex(qtbot)
    pos = scene.vertex_map[vertex].pos()
    emitted: list[tuple[int, int]] = []
    scene.edge_added.connect(lambda source, target, _crossed: emitted.append((source, target)))

    scene.mousePressEvent(_mouse_event(QEvent.Type.GraphicsSceneMousePress, pos))
    scene.mouseReleaseEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseRelease, pos))

    assert emitted == []
    assert scene._drag is None


def test_edge_tool_double_click_edits_phase_without_self_loop(qtbot: QtBot) -> None:
    scene, _view, vertex = _scene_with_vertex(qtbot)
    pos = scene.vertex_map[vertex].pos()
    edges: list[tuple[int, int]] = []
    double_clicked: list[int] = []
    scene.edge_added.connect(lambda source, target, _crossed: edges.append((source, target)))
    scene.vertex_double_clicked.connect(double_clicked.append)

    scene.mousePressEvent(_mouse_event(QEvent.Type.GraphicsSceneMousePress, pos))
    scene.mouseReleaseEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseRelease, pos))
    scene.mouseDoubleClickEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseDoubleClick, pos))

    assert edges == []
    assert double_clicked == [vertex]


def test_edge_tool_drag_back_to_source_creates_self_loop(qtbot: QtBot) -> None:
    scene, _view, vertex = _scene_with_vertex(qtbot)
    pos = scene.vertex_map[vertex].pos()
    emitted: list[tuple[int, int]] = []
    scene.edge_added.connect(lambda source, target, _crossed: emitted.append((source, target)))

    scene.mousePressEvent(_mouse_event(QEvent.Type.GraphicsSceneMousePress, pos))
    scene.mouseMoveEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseMove, pos + QPointF(SCALE, 0)))
    scene.mouseMoveEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseMove, pos))
    scene.mouseReleaseEvent(_mouse_event(QEvent.Type.GraphicsSceneMouseRelease, pos))

    assert emitted == [(vertex, vertex)]


def test_pattern_context_menu_only_opens_on_selected_item(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    g = new_graph()
    selected = g.add_vertex(VertexType.Z, qubit=0, row=0)
    unselected = g.add_vertex(VertexType.Z, qubit=0, row=2)
    scene = EditGraphScene()
    scene.set_graph(g)
    scene.vertex_map[selected].setSelected(True)

    opened_at: list[QPoint] = []

    class Menu:
        def addAction(self, _text: str) -> object:
            return object()

        def exec_(self, pos: QPoint) -> None:
            opened_at.append(pos)

    monkeypatch.setattr(zxlive.graphscene, "QMenu", Menu)

    def open_context_menu(pos: QPointF) -> None:
        event = QGraphicsSceneContextMenuEvent(QEvent.Type.GraphicsSceneContextMenu)
        event.setScenePos(pos)
        event.setScreenPos(QPoint())
        scene.contextMenuEvent(event)

    open_context_menu(scene.vertex_map[unselected].pos())
    empty_pos = scene.vertex_map[selected].pos() + QPointF(2 * SCALE, 2 * SCALE)
    open_context_menu(empty_pos)
    assert opened_at == []

    open_context_menu(scene.vertex_map[selected].pos())
    assert opened_at == [QPoint()]


def test_right_click_empty_space_adds_vertex_with_existing_selection(qtbot: QtBot) -> None:
    g = new_graph()
    selected = g.add_vertex(VertexType.Z, qubit=0, row=0)
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    panel.resize(800, 600)
    panel.show()

    scene = panel.graph_scene
    scene.curr_tool = ToolType.SELECT
    scene.vertex_map[selected].setSelected(True)
    empty_pos = scene.vertex_map[selected].pos() + QPointF(2 * SCALE, 2 * SCALE)
    assert panel.graph.num_vertices() == 1

    qtbot.mouseClick(
        panel.graph_view.viewport(),
        Qt.MouseButton.RightButton,
        pos=panel.graph_view.mapFromScene(empty_pos),
    )

    new_vertices = set(panel.graph.vertices()) - {selected}
    assert len(new_vertices) == 1
    added = new_vertices.pop()
    assert (panel.graph.row(added), panel.graph.qubit(added)) == (2, 2)
