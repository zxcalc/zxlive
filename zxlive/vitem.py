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
from enum import Enum

from typing import Optional, Set, Any, TYPE_CHECKING, Union

from PySide6.QtCore import Qt, QPointF, QVariantAnimation, QAbstractAnimation
from PySide6.QtGui import QPen, QBrush,  QPainter, QColor, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QGraphicsPathItem, QGraphicsTextItem, QGraphicsItem, \
     QStyle, QStyleOptionGraphicsItem, QGraphicsSceneMouseEvent



from pyzx.graph.base import VertexType
from pyzx.utils import phase_to_s

from .common import VT, ET, GraphT, SCALE, pos_to_view, pos_from_view

if TYPE_CHECKING:
    from .eitem import EItem
    from .graphscene import GraphScene


ZX_GREEN = "#ccffcc"
ZX_GREEN_PRESSED = "#64BC90"
ZX_RED = "#ff8888"
ZX_RED_PRESSED = "#bb0f0f"
H_YELLOW = "#ffff00"
H_YELLOW_PRESSED = "#f1c232"

# Z values for different items. We use those to make sure that edges
# are drawn below vertices and selected vertices above unselected
# vertices during movement. Phase items are drawn on the very top.
EITEM_Z = -1
VITEM_UNSELECTED_Z = 0
VITEM_SELECTED_Z = 1
PHASE_ITEM_Z = 2

class DragState(Enum):
        """A vertex can be dragged onto another vertex, or if it was dragged onto
         before, it can be dragged off of it again."""
        Onto = 0
        OffOf = 1


class VItem(QGraphicsPathItem):
    """A QGraphicsItem representing a single vertex"""

    v: VT
    phase_item: PhaseItem
    adj_items: Set[EItem]  # Connected edges
    graph_scene: GraphScene

    halftone = "1000100010001000" #QPixmap("images/halftone.png")

    # Set of animations that are currently running on this vertex
    active_animations: set[VItemAnimation]

    # Position before starting a drag-move
    _old_pos: Optional[QPointF]

    # Vertex we are currently dragged on top of
    _dragged_on: Optional[VItem]

    class Properties(Enum):
        """Properties of a VItem that can be animated."""
        Position = 0
        Scale = 1
        Rect = 2

    def __init__(self, graph_scene: GraphScene, v: VT) -> None:
        super().__init__()
        self.setZValue(VITEM_UNSELECTED_Z)

        self.graph_scene = graph_scene
        self.v = v
        self.setPos(*pos_to_view(self.g.row(v), self.g.qubit(v)))
        self.adj_items: Set[EItem] = set()
        self.phase_item = PhaseItem(self)
        self.active_animations = set()

        self._old_pos = None
        self._dragged_on = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        pen = QPen()
        pen.setWidthF(3)
        pen.setColor(QColor("black"))
        self.setPen(pen)

        path = QPainterPath()
        if self.g.type(self.v) == VertexType.H_BOX:
            path.addRect(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        elif self.g.type(self.v) == VertexType.W_OUTPUT:
            #draw a triangle
            path.moveTo(0, 0)
            path.lineTo(0.3 * SCALE, 0.3 * SCALE)
            path.lineTo(0.3 * SCALE, -0.3 * SCALE)
            path.lineTo(0, 0)
        elif self.g.type(self.v) == VertexType.W_INPUT:
            scale = 0.5 * SCALE
            path.addEllipse(-0.2 * scale, -0.2 * scale, 0.4 * scale, 0.4 * scale)
        else:
            path.addEllipse(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        self.setPath(path)
        self.refresh()

    @property
    def g(self) -> GraphT:
        return self.graph_scene.g

    @property
    def is_dragging(self) -> bool:
        return self._old_pos is not None

    @property
    def is_animated(self) -> bool:
        return len(self.active_animations) > 0

    def refresh(self) -> None:
        """Call this method whenever a vertex moves or its data changes"""
        if not self.isSelected():
            t = self.g.type(self.v)
            if t == VertexType.Z:
                self.setBrush(QBrush(QColor(ZX_GREEN)))
            elif t == VertexType.X:
                self.setBrush(QBrush(QColor(ZX_RED)))
            elif t == VertexType.H_BOX:
                self.setBrush(QBrush(QColor(H_YELLOW)))
            elif t == VertexType.W_INPUT:
                self.setBrush(QBrush(QColor("black")))
            elif t == VertexType.W_OUTPUT:
                self.setBrush(QBrush(QColor("black")))
            else:
                self.setBrush(QBrush(QColor("#000000")))
            pen = QPen()
            pen.setWidthF(3)
            pen.setColor(QColor("black"))
            self.setPen(pen)

        if self.isSelected():
            pen = QPen()
            pen.setWidthF(5)
            t = self.g.type(self.v)
            if t == VertexType.Z:
                brush = QBrush(QColor(ZX_GREEN_PRESSED))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.X:
                brush = QBrush(QColor(ZX_RED_PRESSED))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.H_BOX:
                brush = QBrush(QColor(H_YELLOW_PRESSED))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.W_INPUT:
                brush = QBrush(QColor("black"))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.W_OUTPUT:
                brush = QBrush(QColor("black"))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            else:
                brush = QBrush(QColor("#444444"))
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
                pen.setColor(QColor("#444444"))
            self.setPen(pen)

        if self.phase_item:
            self.phase_item.refresh()

        for e_item in self.adj_items:
            e_item.refresh()

    def set_pos_from_graph(self) -> None:
        self.setPos(*pos_to_view(self.g.row(self.v), self.g.qubit(self.v)))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        # Snap items to grid on movement by intercepting the position-change
        # event and returning a new position
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self.is_animated:
            assert isinstance(value, QPointF)
            grid_size = SCALE / 8
            x = round(value.x() / grid_size) * grid_size
            y = round(value.y() / grid_size) * grid_size
            return QPointF(x, y)

        # When selecting/deselecting items, we move them to the front/back
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            assert isinstance(value, int)  # 0 or 1
            self.setZValue(VITEM_SELECTED_Z if value else VITEM_UNSELECTED_Z)
            return value

        # Intercept selection- and position-has-changed events to call `refresh`.
        # Note that the position and selected values are already updated when
        # this event fires.
        if change in (QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged):
            # If we're being animated, the animation will decide for itself whether we
            # should be refreshed or not
            if not self.is_animated:
                self.refresh()

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(e)
        if self.is_animated:
            return
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        scene.vertex_double_clicked.emit(self.v)

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        if self.is_animated:
            return
        self._old_pos = self.pos()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self.is_animated:
            return
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        if self.is_dragging and len(scene.selectedItems()) == 1:
            reset = True
            for it in scene.items():
                if not it.sceneBoundingRect().intersects(self.sceneBoundingRect()):
                    continue
                if it == self._dragged_on:
                    reset = False
                elif isinstance(it, VItem) and it != self:
                    scene.vertex_dragged.emit(DragState.Onto, self.v, it.v)
                    # If we previously hovered over a vertex, notify the scene that we
                    # are no longer
                    if self._dragged_on is not None:
                        scene.vertex_dragged.emit(DragState.OffOf, self.v, self._dragged_on.v)
                    self._dragged_on = it
                    return
            if reset and self._dragged_on is not None:
                scene.vertex_dragged.emit(DragState.OffOf, self.v, self._dragged_on.v)
                self._dragged_on = None
        e.ignore()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        # Unfortunately, Qt does not provide a "MoveFinished" event, so we have to
        # manually detect mouse releases.
        super().mouseReleaseEvent(e)
        if self.is_animated:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._old_pos != self.pos():
                scene = self.scene()
                if TYPE_CHECKING: assert isinstance(scene, GraphScene)
                if self._dragged_on is not None and len(scene.selectedItems()) == 1:
                    scene.vertex_dropped_onto.emit(self.v, self._dragged_on.v)
                else:
                    scene.vertices_moved.emit([
                        (it.v, *pos_from_view(it.pos().x(),it.pos().y()))
                        for it in scene.selectedItems() if isinstance(it, VItem)
                    ])
                self._dragged_on = None
                self._old_pos = None
        else:
            e.ignore()


class VItemAnimation(QVariantAnimation):
    """Animator for vertex graphics items.

    This animator lets the vertex know that its being animated which stops any
    interaction with the user and disables grid snapping. Furthermore, this animator
    ensures that it's not garbage collected until the animation is finished, so there is
    no need to hold onto a reference of this class."""

    _it: Optional[VItem]
    prop: VItem.Properties
    refresh: bool  # Whether the item is refreshed at each frame

    v: Optional[VT]

    def __init__(self, item: Union[VItem, VT], property: VItem.Properties,
                 scene: Optional[GraphScene] = None, refresh: bool = False) -> None:
        super().__init__()
        self.v = None
        self._it = None
        self.scene: Optional[GraphScene] = None
        if refresh and property != VItem.Properties.Position:
            raise ValueError("Only position animations require refresh")
        if isinstance(item, VItem):
            self._it = item
        elif scene is None:
            raise ValueError("Scene is required to obtain VItem from vertex id")
        else:
            self.v = item
            self.scene = scene
        self.prop = property
        self.refresh = refresh
        self.stateChanged.connect(self._on_state_changed)

    @property
    def it(self) -> VItem:
        if self._it is None and self.scene is not None and self.v is not None:
            self._it = self.scene.vertex_map[self.v]
        assert self._it is not None
        return self._it

    def _on_state_changed(self, state: QAbstractAnimation.State) -> None:
        if state == QAbstractAnimation.State.Running and self not in self.it.active_animations:
            # Stop all animations that target the same property
            for anim in self.it.active_animations.copy():
                if anim.prop == self.prop:
                    anim.stop()
            self.it.active_animations.add(self)
        elif state == QAbstractAnimation.State.Stopped:
            self.it.active_animations.remove(self)
        elif state == QAbstractAnimation.State.Paused:
            # TODO: Once we use pausing, we should decide what to do here.
            #   Note that we cannot just remove ourselves from the set since the garbage
            #   collector will eat us in that case. We'll probably need something like
            #   `it.paused_animations`
            pass

    def updateCurrentValue(self, value: Any) -> None:
        if self.state() != QAbstractAnimation.State.Running:
            return

        if self.prop == VItem.Properties.Position:
            self.it.setPos(value)
        elif self.prop == VItem.Properties.Scale:
            self.it.setScale(value)
        elif self.prop == VItem.Properties.Rect:
            self.it.setPath(value)

        if self.refresh:
            self.it.refresh()


class PhaseItem(QGraphicsTextItem):
    """A QGraphicsItem representing a phase label"""

    def __init__(self, v_item: VItem) -> None:
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
        self.setPlainText(phase_to_s(phase, self.v_item.g.type(self.v_item.v)))
        if self.v_item.g.type(self.v_item.v) == VertexType.BOUNDARY:
            self.setPlainText(str(int(self.v_item.g.qubit(self.v_item.v))))
        p = self.v_item.pos()
        self.setPos(p.x(), p.y() - 0.6 * SCALE)
