from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtWidgets import QGraphicsSceneContextMenuEvent
import pytest
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

import zxlive.graphscene
from zxlive.common import SCALE, ToolType, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.graphscene import EditGraphScene


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
