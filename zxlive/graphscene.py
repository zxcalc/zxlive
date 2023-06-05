#     zxlive - An interactive tool for the ZX calculus
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

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from typing import Optional, List, Set, Callable, Iterator

from pyzx.graph.base import BaseGraph, VT, ET, VertexType, EdgeType
from pyzx.utils import phase_to_s


SCALE = 60.0
ZX_GREEN = "#ccffcc"
ZX_GREEN_PRESSED = "#006600"
ZX_RED = "#ff8888"
ZX_RED_PRESSED = "#660000"


class VItem(QGraphicsEllipseItem):
    """A QGraphicsItem representing a single vertex"""

    def __init__(self, g: BaseGraph[VT, ET], v: VT):
        super().__init__(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        self.setZValue(1)  # draw vertices on top of edges but below phases

        self.g = g
        self.v = v
        self.setPos(g.row(v) * SCALE, g.qubit(v) * SCALE)
        self.adj_items: Set[EItem] = set()
        self.phase_item = PhaseItem(self)

        self.is_pressed = False

        pen = QPen()
        pen.setWidthF(3)
        pen.setColor(QColor("black"))
        self.setPen(pen)
        self.refresh()

    def refresh(self) -> None:
        """Call this method whenever a vertex moves or its data changes"""

        if not self.is_pressed:
            t = self.g.type(self.v)
            if t == VertexType.Z:
                self.setBrush(QBrush(QColor(ZX_GREEN)))
            elif t == VertexType.X:
                self.setBrush(QBrush(QColor(ZX_RED)))
            else:
                self.setBrush(QBrush(QColor("#000000")))

        if self.is_pressed:
            t = self.g.type(self.v)
            if t == VertexType.Z:
                self.setBrush(QBrush(QColor(ZX_GREEN_PRESSED)))
            elif t == VertexType.X:
                self.setBrush(QBrush(QColor(ZX_RED_PRESSED)))
            else:
                self.setBrush(QBrush(QColor("#000000")))

        if self.phase_item:
            self.phase_item.refresh()

        for e_item in self.adj_items:
            e_item.refresh()


class PhaseItem(QGraphicsTextItem):
    """A QGraphicsItem representing a phase label"""

    def __init__(self, v_item: VItem):
        super().__init__()
        self.setZValue(2)  # draw phase labels on top

        self.setDefaultTextColor(QColor("#006bb3"))
        self.setFont(QFont("monospace"))
        self.v_item = v_item
        self.refresh()

    def refresh(self) -> None:
        """Call this when a vertex moves or its phase changes"""

        phase = self.v_item.g.phase(self.v_item.v)
        # phase = self.v_item.v
        self.setPlainText(phase_to_s(phase))
        p = self.v_item.pos()
        self.setPos(p.x(), p.y() - 0.6 * SCALE)


class EItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge"""

    def __init__(self, g: BaseGraph[VT, ET], e: ET, s_item: VItem, t_item: VItem):
        super().__init__()
        self.setZValue(0)  # draw edges below vertices and phases
        self.g = g
        self.e = e
        self.s_item = s_item
        self.t_item = t_item
        s_item.adj_items.add(self)
        t_item.adj_items.add(self)

        self.refresh()

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        # set color/style according to edge type
        pen = QPen()
        pen.setWidthF(3)
        if self.g.edge_type(self.e) == EdgeType.HADAMARD:
            pen.setColor(QColor("#0077ff"))
            pen.setDashPattern([4.0, 2.0])
        else:
            pen.setColor(QColor("#000000"))
        self.setPen(QPen(pen))

        # set path as a straight line from source to target
        path = QPainterPath()
        path.moveTo(self.s_item.pos())
        path.lineTo(self.t_item.pos())
        self.setPath(path)


VertMovedEvent = Optional[Callable[[VT, float, float], None]]
VertDoubleClickedEvent = Optional[Callable[[VT], None]]


class GraphScene(QGraphicsScene):
    """The main class responsible for drawing/editing graphs"""

    g: BaseGraph[VT, ET]
    on_vertex_moved: VertMovedEvent = None
    on_vertex_double_clicked: VertDoubleClickedEvent = None

    _selected_items: list[VItem]
    _drag_start: QPointF
    _drag_items: List[tuple[QGraphicsItem, QPointF]]
    _is_moved: bool = False

    def __init__(self, on_vertex_moved: VertMovedEvent = None,
                 on_vertex_double_clicked: VertDoubleClickedEvent = None) -> None:
        super().__init__()
        self.on_vertex_moved = on_vertex_moved
        self.on_vertex_double_clicked = on_vertex_double_clicked
        self._selected_items = []
        self._drag_items = []
        self._drag_start = QPointF(0, 0)

        self.setSceneRect(-100, -100, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(255, 255, 255)))

    @property
    def selected_vertices(self) -> Iterator[VT]:
        """An iterator over all currently selected vertices."""
        return (it.v for it in self._selected_items)

    def clear_selection(self) -> None:
        """Unselects all selected vertices."""
        for it in self._selected_items:
            it.is_pressed = False
            it.refresh()
        self._selected_items = []

    def set_graph(self, g: BaseGraph[VT, ET]) -> None:
        """Set the PyZX graph for the scene

        If the scene already contains a graph, it will be replaced."""

        self.g = g
        self.clear()
        self.add_items()
        self.invalidate()

    def add_items(self) -> None:
        """Add QGraphicsItem's for all vertices and edges in the graph"""

        v_items = {}
        for v in self.g.vertices():
            vi = VItem(self.g, v)
            v_items[v] = vi
            self.addItem(vi)  # add the vertex to the scene
            self.addItem(vi.phase_item)  # add the phase label to the scene

        for e in self.g.edges():
            s, t = self.g.edge_st(e)
            self.addItem(EItem(self.g, e, v_items[s], v_items[t]))

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        if e.button() != Qt.LeftButton:
            return

        self._drag_start = e.scenePos()

        if not self.items(e.scenePos(), deviceTransform=QTransform()):
            for it in self._selected_items:
                it.is_pressed = False
                it.refresh()
            self._selected_items = []

        # TODO implement selecting/moving multiple items
        for it in self.items(e.scenePos(), deviceTransform=QTransform()):
            if it and isinstance(it, VItem):
                self._drag_items = [(it, it.scenePos())]
                if it.is_pressed:
                    self._selected_items.pop(-1)
                    it.is_pressed = False
                    it.refresh()
                    break
                else:
                    self._selected_items.append(it)
                    it.is_pressed = True
                    it.refresh()
                    break

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        p = e.scenePos()
        grid_size = SCALE / 8
        dx = round((p.x() - self._drag_start.x()) / grid_size) * grid_size
        dy = round((p.y() - self._drag_start.y()) / grid_size) * grid_size
        # move the items that have been dragged
        for it, pos in self._drag_items:
            self._is_moved = True
            it.setPos(QPointF(pos.x() + dx, pos.y() + dy))
            if isinstance(it, VItem):
                it.refresh()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                if it and isinstance(it, VItem) and self._is_moved:
                    it.is_pressed = False
                    if len(self._selected_items) == 0:
                        break
                    self._selected_items.pop(-1)
                    it.refresh()
                    if self.on_vertex_moved:
                        self.on_vertex_moved(it.v, it.x() / SCALE, it.y() / SCALE)
                    break

            self._drag_items = []
            self._is_moved = False

    def mouseDoubleClickEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        for it in self.items(e.scenePos(), deviceTransform=QTransform()):
            if isinstance(it, VItem):
                if self.on_vertex_double_clicked is not None:
                    self.on_vertex_double_clicked(it.v)
                return


# TODO: This is essentially a clone of EItem. We should common it up!
class EDragItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge in construction during a drag"""

    def __init__(self, g: BaseGraph[VT, ET], ety: EdgeType, start: VItem, mouse_pos: QPointF):
        super().__init__()
        self.setZValue(0)  # draw edges below vertices and phases
        self.g = g
        self.ety = ety
        self.start = start
        self.mouse_pos = mouse_pos
        self.refresh()

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        # set color/style according to edge type
        pen = QPen()
        pen.setWidthF(3)
        if self.ety == EdgeType.HADAMARD:
            pen.setColor(QColor("#0077ff"))
            pen.setDashPattern([4.0, 2.0])
        else:
            pen.setColor(QColor("#000000"))
        self.setPen(QPen(pen))

        # set path as a straight line from source to target
        path = QPainterPath()
        path.moveTo(self.start.pos())
        path.lineTo(self.mouse_pos)
        self.setPath(path)


AddVertEvent = Optional[Callable[[float, float], None]]
AddEdgeEvent = Optional[Callable[[VT, VT], None]]


class EditGraphScene(GraphScene):
    """A graph scene tracking additional mouse events for graph editing."""

    # Callbacks to handle addition of vertices and edges
    on_add_vert: AddVertEvent = None
    on_add_edge: AddEdgeEvent = None

    # Currently selected edge type for preview when dragging
    # to add a new edge
    curr_ety: EdgeType = EdgeType.SIMPLE

    # The vertex a right mouse button drag was initiated on
    _right_drag: Optional[EDragItem] = None

    def __init__(self, on_vertex_moved: VertMovedEvent = None,
                 on_vertex_double_clicked: VertDoubleClickedEvent = None,
                 on_add_vert: AddVertEvent = None,
                 on_add_edge: AddEdgeEvent = None):
        super().__init__(on_vertex_moved, on_vertex_double_clicked)
        self.on_add_vert = on_add_vert
        self.on_add_edge = on_add_edge

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        # Right-press on a vertex means the start of a drag for edge adding
        super().mousePressEvent(e)
        if e.button() == Qt.RightButton:
            if self.items(e.scenePos(), deviceTransform=QTransform()):
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    if isinstance(it, VItem):
                        self._right_drag = EDragItem(self.g, self.curr_ety, it, e.scenePos())
                        self.addItem(self._right_drag)

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self._right_drag:
            self._right_drag.mouse_pos = e.scenePos()
            self._right_drag.refresh()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if e.button() == Qt.RightButton:
            # It's either a drag to add an edge
            if self._right_drag:
                self.removeItem(self._right_drag)
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    # TODO: Think about if we want to allow self loops here?
                    #  For example, if had edge is selected this would mean that
                    #  right clicking adds pi to the phase...
                    if isinstance(it, VItem) and it != self._right_drag.start and self.on_add_edge:
                        self.on_add_edge(self._right_drag.start.v, it.v)
                self._right_drag = None
            # Or a click on a free spot to add a new vertex
            elif self.on_add_vert:
                p = e.scenePos()
                self.on_add_vert(p.x() / SCALE, p.y() / SCALE)
