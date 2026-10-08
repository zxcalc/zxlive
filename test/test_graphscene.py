from pathlib import Path
from fractions import Fraction

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QGraphicsSceneContextMenuEvent, QGraphicsSceneMouseEvent, QGraphicsView
import pytest
from pytestqt.qtbot import QtBot
from pyzx.utils import EdgeType, VertexType

import zxlive.graphscene
import zxlive.editor_base_panel
from zxlive.common import SCALE, ToolType, new_graph, pos_to_view
from zxlive.edit_panel import GraphEditPanel
from zxlive.graphscene import EditGraphScene
from zxlive.rule_panel import RulePanel


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


def test_empty_graph_starts_with_small_scene_rect_at_origin(qtbot: QtBot) -> None:
    scene = EditGraphScene()
    scene.set_graph(new_graph())

    origin = QPointF(*pos_to_view(0, 0))
    assert scene.sceneRect().center() == origin
    assert scene.sceneRect().width() == pytest.approx(20 * SCALE)
    assert scene.sceneRect().height() == pytest.approx(20 * SCALE)


def test_initial_scene_rect_follows_far_away_graph(qtbot: QtBot) -> None:
    graph = new_graph()
    graph.add_vertex(VertexType.Z, qubit=-100, row=100)
    scene = EditGraphScene()
    scene.set_graph(graph)

    item_bounds = scene.itemsBoundingRect()
    assert scene.sceneRect().contains(item_bounds)
    assert scene.sceneRect().width() == pytest.approx(item_bounds.width() + 20 * SCALE)
    assert scene.sceneRect().height() == pytest.approx(item_bounds.height() + 20 * SCALE)
    assert not scene.sceneRect().contains(QPointF(*pos_to_view(0, 0)))


def test_scene_rect_grows_but_does_not_shrink_on_graph_updates(qtbot: QtBot) -> None:
    graph = new_graph()
    graph.add_vertex(VertexType.Z, qubit=0, row=0)
    scene = EditGraphScene()
    scene.set_graph(graph)
    initial_rect = scene.sceneRect()

    outward_graph = new_graph()
    outward_graph.add_vertex(VertexType.Z, qubit=-100, row=100)
    scene.update_graph(outward_graph)
    expanded_rect = scene.sceneRect()
    assert expanded_rect.top() < initial_rect.top()
    assert expanded_rect.right() > initial_rect.right()

    scene.update_graph(new_graph())
    assert scene.sceneRect() == expanded_rect


def test_scene_rect_grows_while_vertex_is_moved(qtbot: QtBot) -> None:
    scene, _view, vertex = _scene_with_vertex(qtbot)
    initial_rect = scene.sceneRect()

    scene.vertex_map[vertex].setPos(initial_rect.right() + SCALE, initial_rect.bottom() + SCALE)

    assert scene.sceneRect().right() > initial_rect.right()
    assert scene.sceneRect().bottom() > initial_rect.bottom()


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


@pytest.fixture
def pattern_panel(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphEditPanel:
    pattern = new_graph()
    source = pattern.add_vertex(VertexType.Z, row=10, qubit=-3, phase=Fraction(1, 2))
    target = pattern.add_vertex(VertexType.X, row=11, qubit=-2)
    pattern.add_edge((source, target), EdgeType.HADAMARD)
    (tmp_path / "example.zxg").write_text(pattern.to_json(), encoding="utf-8")
    monkeypatch.setattr(zxlive.editor_base_panel, "get_settings_value", lambda _key, _type: str(tmp_path))
    graph = new_graph()
    graph.add_vertex(VertexType.Z, row=0, qubit=0)
    panel = GraphEditPanel(graph)
    qtbot.addWidget(panel)
    panel.resize(800, 600)
    panel.show()
    panel.patterns_list.setCurrentRow(0)
    return panel


@pytest.mark.parametrize("on_vertex, selected", [(False, False), (False, True), (True, False)])
def test_right_click_inserts_pattern_at_cursor_with_undo(
    qtbot: QtBot, pattern_panel: GraphEditPanel, on_vertex: bool, selected: bool
) -> None:
    panel = pattern_panel
    original = next(iter(panel.graph.vertices()))
    panel.graph_scene.vertex_map[original].setSelected(selected)
    position = (0, 0) if on_vertex else (2, 3)
    qtbot.mouseClick(panel.graph_view.viewport(), Qt.MouseButton.RightButton,
                     pos=panel.graph_view.mapFromScene(QPointF(*pos_to_view(*position))))

    added = set(panel.graph.vertices()) - {original}
    assert len(added) == 2
    assert {(panel.graph.row(v), panel.graph.qubit(v)) for v in added} == {
        position, (position[0] + 1, position[1] + 1)
    }
    assert {panel.graph.type(v) for v in added} == {VertexType.Z, VertexType.X}
    assert sorted(float(panel.graph.phase(v)) for v in added) == [0, 0.5]
    assert panel.graph.num_edges() == 1
    assert panel.graph.edge_type(next(iter(panel.graph.edges()))) == EdgeType.HADAMARD
    assert set(panel.graph_scene.selected_vertices) == added
    assert panel.graph_scene._drag is None
    assert panel.undo_stack.count() == 1

    panel.undo_stack.undo()
    assert set(panel.graph.vertices()) == {original}
    panel.undo_stack.redo()
    assert set(panel.graph.vertices()) == added | {original}

    # Deselect the inserted pattern before placing another copy at the same position.
    panel.graph_scene.clearSelection()
    qtbot.mouseClick(panel.graph_view.viewport(), Qt.MouseButton.RightButton,
                     pos=panel.graph_view.mapFromScene(QPointF(*pos_to_view(*position))))
    assert panel.graph.num_vertices() == 5
    assert panel.graph.num_edges() == 2


@pytest.mark.parametrize("palette", ["vertex", "edge"])
def test_palette_click_restores_vertex_creation(
    qtbot: QtBot, pattern_panel: GraphEditPanel, palette: str
) -> None:
    panel = pattern_panel
    widget = panel.vertex_list if palette == "vertex" else panel.edge_list
    qtbot.mouseClick(widget.viewport(), Qt.MouseButton.LeftButton,
                     pos=widget.visualItemRect(widget.item(0)).center())
    assert not panel.patterns_list.selectedItems()
    qtbot.mouseClick(panel.graph_view.viewport(), Qt.MouseButton.RightButton,
                     pos=panel.graph_view.mapFromScene(QPointF(*pos_to_view(2, 3))))
    assert panel.graph.num_vertices() == 2


def test_filtering_clears_active_pattern(pattern_panel: GraphEditPanel) -> None:
    pattern_panel.patterns_list.filter_patterns("missing")
    assert not pattern_panel.patterns_list.selectedItems()


def test_selected_pattern_preserves_selection_context_menu(
    qtbot: QtBot, pattern_panel: GraphEditPanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = pattern_panel.graph_scene
    vertex = next(iter(scene.g.vertices()))
    scene.vertex_map[vertex].setSelected(True)

    emitted: list[bool] = []
    scene.add_selection_as_pattern_signal.disconnect(pattern_panel.add_selection_as_pattern)
    scene.add_selection_as_pattern_signal.connect(lambda: emitted.append(True))

    class Menu:
        def addAction(self, text: str) -> str:
            assert text == "Add selection to patterns"
            return text

        def exec_(self, _pos: QPoint) -> str:
            return "Add selection to patterns"

    monkeypatch.setattr(zxlive.graphscene, "QMenu", Menu)
    pos = pattern_panel.graph_view.mapFromScene(scene.vertex_map[vertex].pos())
    qtbot.mouseClick(pattern_panel.graph_view.viewport(), Qt.MouseButton.RightButton, pos=pos)
    assert scene.g.num_vertices() == 1
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                             pattern_panel.graph_view.mapFromScene(scene.vertex_map[vertex].pos()), QPoint())
    event.setAccepted(False)
    QApplication.sendEvent(pattern_panel.graph_view.viewport(), event)
    assert event.isAccepted()
    assert emitted
    assert scene.g.num_vertices() == 1


def test_inserting_pattern_does_not_open_selection_context_menu(
    qtbot: QtBot, pattern_panel: GraphEditPanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_menu() -> None:
        pytest.fail("Inserting a pattern should not also open its selection context menu")

    monkeypatch.setattr(zxlive.graphscene, "QMenu", unexpected_menu)
    pos = pattern_panel.graph_view.mapFromScene(QPointF(*pos_to_view(2, 3)))
    qtbot.mouseClick(pattern_panel.graph_view.viewport(), Qt.MouseButton.RightButton, pos=pos)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, QPoint())
    QApplication.sendEvent(pattern_panel.graph_view.viewport(), event)
    assert event.isAccepted()
    assert pattern_panel.graph.num_vertices() == 3


def test_pattern_selection_does_not_override_vertex_tool(qtbot: QtBot, pattern_panel: GraphEditPanel) -> None:
    panel = pattern_panel
    panel._tool_clicked(ToolType.VERTEX)
    qtbot.mouseClick(panel.graph_view.viewport(), Qt.MouseButton.LeftButton,
                     pos=panel.graph_view.mapFromScene(QPointF(*pos_to_view(2, 3))))
    assert panel.graph.num_vertices() == 2


def test_pattern_double_click_keeps_existing_insertion_position(pattern_panel: GraphEditPanel) -> None:
    panel = pattern_panel
    panel.patterns_list.itemDoubleClicked.emit(panel.patterns_list.item(0))
    added = set(panel.graph.vertices()) - {0}
    assert {(panel.graph.row(v), panel.graph.qubit(v)) for v in added} == {(10.5, -2.5), (11.5, -1.5)}


def test_selected_pattern_inserts_into_both_rule_canvases(qtbot: QtBot, pattern_panel: GraphEditPanel) -> None:
    panel = RulePanel(new_graph(), new_graph(), "", "")
    qtbot.addWidget(panel)
    panel.resize(1000, 600)
    panel.show()
    panel.patterns_list.setCurrentRow(0)
    for view in (panel.graph_view_left, panel.graph_view_right):
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.RightButton,
                         pos=view.mapFromScene(QPointF(*pos_to_view(0, 0))))
        assert view.graph_scene.g.num_vertices() == 2
    panel._vty_clicked(VertexType.Z)
    assert not panel.patterns_list.selectedItems()


@pytest.mark.parametrize("rule_editor", [False, True])
def test_drag_pattern_to_canvas(
    qtbot: QtBot, pattern_panel: GraphEditPanel, rule_editor: bool
) -> None:
    panel = RulePanel(new_graph(), new_graph(), "", "") if rule_editor else pattern_panel
    if rule_editor:
        qtbot.addWidget(panel)
        panel.resize(1000, 600)
        panel.show()
    mime = panel.patterns_list.mimeData([panel.patterns_list.item(0)])
    # The payload survives clearing the sidebar selection during a drag.
    panel.patterns_list.clearSelection()
    assert panel.patterns_list.dragEnabled()
    views = (panel.graph_view_left, panel.graph_view_right) if isinstance(panel, RulePanel) else (panel.graph_view,)
    for view in views:
        before = set(view.graph_scene.g.vertices())
        pos = view.mapFromScene(QPointF(*pos_to_view(1, 2)))
        for event in (QDragEnterEvent(pos, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                                      Qt.KeyboardModifier.NoModifier),
                      QDragMoveEvent(pos, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                                     Qt.KeyboardModifier.NoModifier),
                      QDropEvent(QPointF(pos), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier)):
            QApplication.sendEvent(view.viewport(), event)
            assert event.isAccepted()
            assert event.dropAction() == Qt.DropAction.CopyAction
        added = set(view.graph_scene.g.vertices()) - before
        assert len(added) == 2
        assert {(view.graph_scene.g.row(v), view.graph_scene.g.qubit(v)) for v in added} == {(1, 2), (2, 3)}
    panel.undo_stack.undo()
    assert set(views[-1].graph_scene.g.vertices()) == before


def test_canvas_rejects_unrelated_drag_data(pattern_panel: GraphEditPanel) -> None:
    mime = QMimeData()
    mime.setText("unrelated text")
    event = QDragEnterEvent(QPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(pattern_panel.graph_view.viewport(), event)
    assert not event.isAccepted()
    assert pattern_panel.graph.num_vertices() == 1
