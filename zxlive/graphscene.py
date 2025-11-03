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

from __future__ import annotations

from typing import Optional, Iterator, Iterable

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QBrush, QColor, QTransform, QPainterPath
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsItem, QGraphicsSceneContextMenuEvent, QMenu

from pyzx.utils import EdgeType
from pyzx.graph.diff import GraphDiff


from .common import SCALE, VT, ET, GraphT, ToolType, pos_from_view, OFFSET_X, OFFSET_Y
from .vitem import VItem
from .eitem import EItem, EDragItem
from .settings import display_setting


class GraphScene(QGraphicsScene):
    """The main class responsible for drawing/editing graphs"""

    g: GraphT

    # Signals to handle double-clicking and moving of vertices.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_double_clicked = Signal(object)  # Actual type: VT
    vertices_moved = Signal(object)  # Actual type: list[tuple[VT, float, float]]

    # Triggers when a vertex is dragged onto or off of another vertex
    # Actual types: DragState, VT, VT
    vertex_dragged = Signal(object, object, object)

    # Triggers when a vertex is dropped onto another vertex. Actual types: VT, VT
    vertex_dropped_onto = Signal(object, object)

    # Triggers when an edge is dragged. Actual types: EItem, float (old curve_distance), float (new curve_distance)
    edge_dragged = Signal(object, object, object)
    edge_double_clicked = Signal(object)  # Actual type: ET

    selection_changed_custom = Signal()
    add_selection_as_pattern_signal = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(0, 0, 2 * OFFSET_X, 2 * OFFSET_Y)
        self.update_background_brush()
        self.vertex_map: dict[VT, VItem] = {}
        self.edge_map: dict[ET, dict[int, EItem]] = {}

    def update_background_brush(self) -> None:
        if display_setting.dark_mode:
            self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        else:
            self.setBackgroundBrush(QBrush(QColor(255, 255, 255)))

    @property
    def selected_vertices(self) -> Iterator[VT]:
        """An iterator over all currently selected vertices."""
        return (it.v for it in self.selectedItems() if isinstance(it, VItem))

    @property
    def selected_edges(self) -> Iterator[ET]:
        return (it.e for it in self.selectedItems() if isinstance(it, EItem))

    def select_vertices(self, vs: Iterable[VT]) -> None:
        """Selects the given collection of vertices."""
        self.clearSelection()
        vs = set(vs)
        for it in self.items():
            if isinstance(it, VItem) and it.v in vs:
                it.setSelected(True)
                vs.remove(it.v)
        self.selection_changed_custom.emit()

    def set_graph(self, g: GraphT) -> None:
        """Set the PyZX graph for the scene.
        If the scene already contains a graph, it will be replaced."""

        self.g = g
        # Stop all animations
        for it in self.items():
            if isinstance(it, VItem):
                for anim in it.active_animations.copy():
                    anim.stop()
        self.clear()
        self.add_items()
        self.invalidate()

    def update_graph(self, new: GraphT, select_new: bool = False) -> None:
        """Update the PyZX graph for the scene.
        This will update the scene to match the given graph. It will
        try to reuse existing QGraphicsItem's as much as possible.

        The selection is carried over to the updated graph.

        :param new: The new graph to update to.
        :param select_new: If True, add all new vertices to the selection set."""

        selected_vertices = set(self.selected_vertices)

        diff = GraphDiff(self.g, new)

        for v in diff.removed_verts:
            v_item = self.vertex_map[v]
            if v_item.phase_item:
                self.removeItem(v_item.phase_item)
            for anim_v in v_item.active_animations.copy():
                anim_v.stop()
            selected_vertices.discard(v)
            self.removeItem(v_item)
            del self.vertex_map[v]

        for e in diff.removed_edges:
            edge_idx = len(self.edge_map[e]) - 1
            e_item = self.edge_map[e][edge_idx]
            if e_item.selection_node:
                self.removeItem(e_item.selection_node)
            for anim_e in e_item.active_animations.copy():
                anim_e.stop()
            e_item.s_item.adj_items.remove(e_item)
            if e_item.s_item != e_item.t_item:
                e_item.t_item.adj_items.remove(e_item)
            self.removeItem(e_item)
            self.edge_map[e].pop(edge_idx)
            s, t = self.g.edge_st(e)
            self.update_edge_curves(s, t)
            if len(self.edge_map[e]) == 0:
                del self.edge_map[e]

        new_g = diff.apply_diff(self.g)
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert isinstance(new_g, GraphT)  # type: ignore
        self.g = new_g
        # g now contains the new graph,
        # but we still need to update the scene
        # However, the new vertices and edges automatically follow the new graph structure

        for v in diff.new_verts:
            v_item = VItem(self, v)
            self.vertex_map[v] = v_item
            self.addItem(v_item)
            self.addItem(v_item.phase_item)
            if select_new:
                selected_vertices.add(v)

        for (s, t), typ in diff.new_edges:
            e = (s, t, typ)
            if e not in self.edge_map:
                self.edge_map[e] = {}
            idx = len(self.edge_map[e])
            curve_distance = self.g.edata(e, f"curve_{idx}", 0.0)
            e_item = EItem(self, e, self.vertex_map[s], self.vertex_map[t], curve_distance, idx)
            self.edge_map[e][idx] = e_item
            self.update_edge_curves(s, t)
            self.addItem(e_item)
            self.addItem(e_item.selection_node)

        for v in diff.new_verts:
            self.vertex_map[v].set_vitem_rotation()

        for v in diff.changed_vertex_types:
            self.vertex_map[v].refresh()

        for v in diff.changed_phases:
            self.vertex_map[v].refresh()

        for v in diff.changed_vdata:
            self.vertex_map[v].refresh()

        for e in diff.changed_edata:
            for i in self.edge_map[e]:
                self.edge_map[e][i].refresh()

        for v in diff.changed_pos:
            v_item = self.vertex_map[v]
            for anim in v_item.active_animations.copy():
                anim.stop()
            v_item.set_pos_from_graph()
            v_item.set_vitem_rotation()

        for e in diff.changed_edge_types:
            for i in self.edge_map[e]:
                self.edge_map[e][i].reset_color()
                self.edge_map[e][i].refresh()

        self.select_vertices(selected_vertices)

    def update_edge_curves(self, s: VT, t: VT) -> None:
        edges = []
        for e in set(self.g.edges(s, t)):
            if e not in self.edge_map:
                continue
            for i in self.edge_map[e]:
                edges.append(self.edge_map[e][i])
        midpoint_index = 0.5 * (len(edges) - 1)
        for n, edge in enumerate(edges):
            edge.curve_distance = (n - midpoint_index) * 0.5
            edge.refresh()

    def update_colors(self) -> None:
        self.update_background_brush()
        for v in self.vertex_map.values():
            v.refresh()
        for e in self.edge_map.values():
            for ei in e.values():
                ei.reset_color()
                ei.refresh()

    def add_items(self) -> None:
        """Add QGraphicsItem's for all vertices and edges in the graph"""
        self.vertex_map = {}
        for v in self.g.vertices():
            vi = VItem(self, v)
            self.vertex_map[v] = vi
            self.addItem(vi)  # add the vertex to the scene
            self.addItem(vi.phase_item)  # add the phase label to the scene

        self.edge_map = {}
        for e in set(self.g.edges()):
            s, t = self.g.edge_st(e)
            self.edge_map[e] = {}
            for i in range(self.g.graph[s][t].get_edge_count(e[2])):
                curve_distance = self.g.edata(e, f"curve_{i}", 0.0)
                ei = EItem(self, e, self.vertex_map[s], self.vertex_map[t], curve_distance, i)
                self.addItem(ei)
                self.addItem(ei.selection_node)
                self.edge_map[e][i] = ei
        for e in self.g.edges():
            s, t = self.g.edge_st(e)
            self.update_edge_curves(s, t)

    def select_all(self) -> None:
        """Selects all vertices and edges in the scene."""
        for it in self.items():
            it.setSelected(True)
        self.selection_changed_custom.emit()


class EditGraphScene(GraphScene):
    """A graph scene tracking additional mouse events for graph editing."""

    # Signals to handle addition of vertices and edges.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_added = Signal(object, object, object)  # Actual types: float, float, list[EItem]
    edge_added = Signal(object, object, object)  # Actual types: VT, VT, list[VItem]

    # Currently selected edge type for preview when dragging
    # to add a new edge
    curr_ety: EdgeType
    curr_tool: ToolType

    # The vertex a right mouse button drag was initiated on
    _drag: Optional[EDragItem]

    def __init__(self) -> None:
        super().__init__()
        self.curr_ety = EdgeType.SIMPLE
        self.curr_tool = ToolType.SELECT
        self._drag = None
        self._is_dragging = False
        self._is_mouse_pressed = False

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        if e.button() == Qt.MouseButton.RightButton and self.selectedItems():
            return
        # Right-press on a vertex means the start of a drag for edge adding
        super().mousePressEvent(e)
        if (self.curr_tool == ToolType.EDGE) or \
                (self.curr_tool == ToolType.SELECT and e.button() == Qt.MouseButton.RightButton):
            if self.items(e.scenePos(), deviceTransform=QTransform()):
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    if isinstance(it, VItem):
                        self._drag = EDragItem(self.g, self.curr_ety, it, e.scenePos())
                        self._drag.start.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                        self.addItem(self._drag)
        else:
            e.ignore()
        self._is_mouse_pressed = True

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self._drag:
            self._drag.mouse_pos = e.scenePos()
            self._drag.refresh()
        else:
            e.ignore()
        if self._is_mouse_pressed:
            self._is_dragging = True

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        isRightClickOnSelectTool = (self.curr_tool == ToolType.SELECT and
                                    e.button() == Qt.MouseButton.RightButton)
        if self._drag and (self.curr_tool == ToolType.EDGE or isRightClickOnSelectTool):
            self._drag.start.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self.add_edge(e)
        elif not self._is_dragging and (self.curr_tool == ToolType.VERTEX or isRightClickOnSelectTool):
            self.add_vertex(e)
        else:
            e.ignore()
        self._is_mouse_pressed = False
        self._is_dragging = False

    def add_vertex(self, e: QGraphicsSceneMouseEvent) -> None:
        p = e.scenePos()
        # create a rectangle around the mouse position which will be used to check of edge intersections
        snap = display_setting.SNAP_DIVISION
        rect = QRectF(p.x() - SCALE / (2 * snap), p.y() - SCALE / (2 * snap), SCALE / snap, SCALE / snap)
        # edges under current mouse position
        edges: list[EItem] = [e for e in self.items(rect, deviceTransform=QTransform()) if isinstance(e, EItem)]
        self.vertex_added.emit(*pos_from_view(p.x(), p.y()), edges)

    def add_edge(self, e: QGraphicsSceneMouseEvent) -> None:
        assert self._drag is not None
        self.removeItem(self._drag)
        v1 = self._drag.start
        self._drag = None
        for it in self.items(e.scenePos(), deviceTransform=QTransform()):
            if isinstance(it, VItem):
                v2 = it
                break
        else:  # It wasn't actually dropped on a vertex
            e.ignore()
            return
        path = QPainterPath(v1.pos())
        path.lineTo(e.scenePos())
        colliding_verts = []
        for it in self.items(path, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, deviceTransform=QTransform()):
            if isinstance(it, VItem) and it not in (v1, v2):
                colliding_verts.append(it)
        self.edge_added.emit(v1.v, v2.v, colliding_verts)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        selected_items = self.selectedItems()
        if selected_items:
            menu = QMenu()
            add_pattern_action = menu.addAction("Add selection to patterns")
            action = menu.exec_(event.screenPos())
            if action == add_pattern_action:
                self.add_selection_as_pattern_signal.emit()
            event.accept()
            return
        super().contextMenuEvent(event)
