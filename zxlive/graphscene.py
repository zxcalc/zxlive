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

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from typing import Optional, Set, Iterator, Iterable, Any

from pyzx.graph.base import BaseGraph, VT, ET, VertexType, EdgeType
from pyzx.utils import phase_to_s


SCALE = 60.0
ZX_GREEN = "#ccffcc"
ZX_GREEN_PRESSED = "#006600"
ZX_RED = "#ff8888"
ZX_RED_PRESSED = "#660000"


# Z values for different items. We use those to make sure that edges
# are drawn below vertices and selected vertices above unselected
# vertices during movement. Phase items are drawn on the very top.
EITEM_Z = -1
VITEM_UNSELECTED_Z = 0
VITEM_SELECTED_Z = 1
PHASE_ITEM_Z = 2


class VItem(QGraphicsEllipseItem):
    """A QGraphicsItem representing a single vertex"""

    v: VT
    phase_item: PhaseItem
    adj_items: Set[EItem]  # Connected edges
    graph_scene: GraphScene

    # Position before starting a drag-move
    _old_pos: Optional[QPointF]

    # Vertex we are currently dragged on top of
    _dragged_on: Optional[VItem]

    _highlighted: bool

    def __init__(self, graph_scene: GraphScene, v: VT):
        super().__init__(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        self.setZValue(VITEM_UNSELECTED_Z)

        self.graph_scene = graph_scene
        self.v = v
        self.setPos(self.g.row(v) * SCALE, self.g.qubit(v) * SCALE)
        self.adj_items: Set[EItem] = set()
        self.phase_item = PhaseItem(self)

        self._old_pos = None
        self._dragged_on = None
        self._highlighted = False

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        pen = QPen()
        pen.setWidthF(3)
        pen.setColor(QColor("black"))
        self.setPen(pen)
        self.refresh()

    @property
    def g(self) -> BaseGraph[VT, ET]:
        return self.graph_scene.g

    @property
    def is_dragging(self) -> bool:
        return self._old_pos is not None

    def set_highlighted(self, value: bool) -> None:
        self._highlighted = value
        self.refresh()

    def refresh(self) -> None:
        """Call this method whenever a vertex moves or its data changes"""

        self.setScale(1.25 if self._highlighted else 1)

        if not self.isSelected():
            t = self.g.type(self.v)
            if t == VertexType.Z:
                self.setBrush(QBrush(QColor(ZX_GREEN)))
            elif t == VertexType.X:
                self.setBrush(QBrush(QColor(ZX_RED)))
            else:
                self.setBrush(QBrush(QColor("#000000")))

        if self.isSelected():
            t = self.g.type(self.v)
            if t == VertexType.Z:
                self.setBrush(QBrush(QColor(ZX_GREEN_PRESSED)))
            elif t == VertexType.X:
                self.setBrush(QBrush(QColor(ZX_RED_PRESSED)))
            else:
                self.setBrush(QBrush(QColor("#444444")))

        if self.phase_item:
            self.phase_item.refresh()

        for e_item in self.adj_items:
            e_item.refresh()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        option.state &= ~QStyle.State_Selected
        super().paint(painter, option, widget)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        # Snap items to grid on movement by intercepting the position-change
        # event and returning a new position
        if change == QGraphicsItem.ItemPositionChange:
            assert isinstance(value, QPointF)
            grid_size = SCALE / 8
            x = round(value.x() / grid_size) * grid_size
            y = round(value.y() / grid_size) * grid_size
            return QPointF(x, y)

        # When selecting/deselecting items, we move them the front/back
        if change == QGraphicsItem.ItemSelectedChange:
            assert isinstance(value, int)  # 0 or 1
            self.setZValue(VITEM_SELECTED_Z if value else VITEM_UNSELECTED_Z)
            return value

        # Intercept selection- and position-has-changed events to call `refresh`.
        # Note that the position and selected values are already updated when
        # this event fires.
        if change in (QGraphicsItem.ItemSelectedHasChanged, QGraphicsItem.ItemPositionHasChanged):
            self.refresh()

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(e)
        scene = self.scene()
        assert isinstance(scene, GraphScene)
        scene.vertex_double_clicked.emit(self.v)

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        self._old_pos = self.pos()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        scene = self.scene()
        assert isinstance(scene, GraphScene)
        if self.is_dragging and len(scene.selectedItems()) == 1:
            reset = True
            for it in scene.items():
                if not it.sceneBoundingRect().intersects(self.sceneBoundingRect()):
                    continue
                if it == self._dragged_on:
                    reset = False
                elif isinstance(it, VItem) and it != self:
                    scene.vertex_dragged_onto.emit(self.v, it.v)
                    # Try to un-highlight the previously hovered over vertex
                    if self._dragged_on is not None:
                        self._dragged_on.set_highlighted(False)
                    self._dragged_on = it
                    return
            if reset and self._dragged_on is not None:
                self._dragged_on.set_highlighted(False)
                self._dragged_on = None
        e.ignore()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        # Unfortunately, Qt does not provide a "MoveFinished" event, so we have to
        # manually detect mouse releases.
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton:
            if self._old_pos != self.pos():
                scene = self.scene()
                assert isinstance(scene, GraphScene)
                if self._dragged_on is not None and self._dragged_on._highlighted and len(scene.selectedItems()) == 1:
                    scene.vertex_dropped_onto.emit(self.v, self._dragged_on.v)
                else:
                    scene.vertices_moved.emit([
                        (it.v,  it.pos().x() / SCALE, it.pos().y() / SCALE)
                        for it in scene.selectedItems() if isinstance(it, VItem)
                    ])
                self._dragged_on = None
                self._old_pos = None
        else:
            e.ignore()


class PhaseItem(QGraphicsTextItem):
    """A QGraphicsItem representing a phase label"""

    def __init__(self, v_item: VItem):
        super().__init__()
        self.setZValue(PHASE_ITEM_Z)

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
        self.setZValue(EITEM_Z)
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


class GraphScene(QGraphicsScene):
    """The main class responsible for drawing/editing graphs"""

    g: BaseGraph[VT, ET]

    # Signals to handle double-clicking and moving of vertices.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_double_clicked = Signal(object)  # Actual type: VT
    vertices_moved = Signal(object)  # Actual type: list[tuple[VT, float, float]]
    vertex_dragged_onto = Signal(object, object)  # Actual types: VT, VT
    vertex_dropped_onto = Signal(object, object)  # Actual types: VT, VT

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(-100, -100, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(255, 255, 255)))

    @property
    def selected_vertices(self) -> Iterator[VT]:
        """An iterator over all currently selected vertices."""
        return (it.v for it in self.selectedItems() if isinstance(it, VItem))

    def select_vertices(self, vs: Iterable[VT]) -> None:
        """Selects the given collection of vertices."""
        self.clearSelection()
        vs = set(vs)
        for it in self.items():
            if isinstance(it, VItem) and it.v in vs:
                it.setSelected(True)
                vs.remove(it.v)

    def highlight_vertex(self, v: VT) -> None:
        for it in self.items():
            if isinstance(it, VItem) and it.v == v:
                it.set_highlighted(True)
                return

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
            vi = VItem(self, v)
            v_items[v] = vi
            self.addItem(vi)  # add the vertex to the scene
            self.addItem(vi.phase_item)  # add the phase label to the scene

        for e in self.g.edges():
            s, t = self.g.edge_st(e)
            self.addItem(EItem(self.g, e, v_items[s], v_items[t]))


# TODO: This is essentially a clone of EItem. We should common it up!
class EDragItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge in construction during a drag"""

    def __init__(self, g: BaseGraph[VT, ET], ety: EdgeType, start: VItem, mouse_pos: QPointF):
        super().__init__()
        self.setZValue(EITEM_Z)
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


class EditGraphScene(GraphScene):
    """A graph scene tracking additional mouse events for graph editing."""

    # Signals to handle addition of vertices and edges.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_added = Signal(object, object)  # Actual types: float, float
    edge_added = Signal(object, object)  # Actual types: VT, VT

    # Currently selected edge type for preview when dragging
    # to add a new edge
    curr_ety: EdgeType

    # The vertex a right mouse button drag was initiated on
    _right_drag: Optional[EDragItem]

    def __init__(self):
        super().__init__()
        self.curr_ety = EdgeType.SIMPLE
        self._right_drag = None

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        # Right-press on a vertex means the start of a drag for edge adding
        super().mousePressEvent(e)
        if e.button() == Qt.RightButton:
            if self.items(e.scenePos(), deviceTransform=QTransform()):
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    if isinstance(it, VItem):
                        self._right_drag = EDragItem(self.g, self.curr_ety, it, e.scenePos())
                        self.addItem(self._right_drag)
        else:
            e.ignore()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self._right_drag:
            self._right_drag.mouse_pos = e.scenePos()
            self._right_drag.refresh()
        else:
            e.ignore()

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
                    if isinstance(it, VItem) and it != self._right_drag.start:
                        self.edge_added.emit(self._right_drag.start.v, it.v)
                self._right_drag = None
            # Or a click on a free spot to add a new vertex
            else:
                p = e.scenePos()
                self.vertex_added.emit(p.x() / SCALE, p.y() / SCALE)
        else:
            e.ignore()
