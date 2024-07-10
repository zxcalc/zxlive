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
from enum import Enum
import math

from typing import Optional, Set, Any, TYPE_CHECKING, Union

from PySide6.QtCore import Qt, QPointF, QVariantAnimation, QAbstractAnimation
from PySide6.QtGui import QPen, QBrush,  QPainter, QColor, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QGraphicsPathItem, QGraphicsTextItem, QGraphicsItem, \
     QStyle, QStyleOptionGraphicsItem, QGraphicsSceneMouseEvent



from pyzx.utils import VertexType, phase_to_s, get_w_partner, vertex_is_w, get_z_box_label

from .common import VT, W_INPUT_OFFSET, GraphT, SCALE, pos_to_view, pos_from_view
from .settings import display_setting

if TYPE_CHECKING:
    from .eitem import EItem
    from .graphscene import GraphScene


BLACK = "#000000"

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

    _last_pos: Optional[QPointF]

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
        self._last_pos = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.refresh()

    @property
    def g(self) -> GraphT:
        return self.graph_scene.g

    @property
    def ty(self) -> VertexType:
        _ty: VertexType = self.g.type(self.v)
        return _ty

    @property
    def is_dragging(self) -> bool:
        return self._old_pos is not None

    @property
    def is_animated(self) -> bool:
        return len(self.active_animations) > 0

    def refresh(self) -> None:
        """Call this method whenever a vertex moves or its data changes"""
        self.update_shape()
        if not self.isSelected():
            t = self.ty
            if t == VertexType.Z or t == VertexType.Z_BOX:
                self.setBrush(QBrush(display_setting.colors["z_spider"]))
            elif t == VertexType.X:
                self.setBrush(QBrush(display_setting.colors["x_spider"]))
            elif t == VertexType.H_BOX:
                self.setBrush(QBrush(display_setting.colors["hadamard"]))
            elif t == VertexType.W_INPUT:
                self.setBrush(QBrush(display_setting.colors["w_input"]))
            elif t == VertexType.W_OUTPUT:
                self.setBrush(QBrush(display_setting.colors["w_output"]))
            else:
                self.setBrush(QBrush(display_setting.colors["boundary"]))
            pen = QPen()
            pen.setWidthF(3)
            pen.setColor(display_setting.colors["outline"])
            self.setPen(pen)

        if self.isSelected():
            pen = QPen()
            pen.setWidthF(5)
            t = self.ty
            if t == VertexType.Z or t == VertexType.Z_BOX:
                brush = QBrush(display_setting.colors["z_spider_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.X:
                brush = QBrush(display_setting.colors["x_spider_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.H_BOX:
                brush = QBrush(display_setting.colors["hadamard_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.W_INPUT:
                brush = QBrush(display_setting.colors["w_input_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            elif t == VertexType.W_OUTPUT:
                brush = QBrush(display_setting.colors["w_output_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
            else:
                brush = QBrush(display_setting.colors["boundary_pressed"])
                brush.setStyle(Qt.BrushStyle.Dense1Pattern)
                self.setBrush(brush)
                pen.setColor(display_setting.colors["boundary_pressed"])
            self.prepareGeometryChange()
            self.setPen(pen)

        if self.phase_item:
            self.phase_item.refresh()
        if self.ty == VertexType.W_INPUT:
            w_out = get_w_partner_vitem(self)
            if w_out:
                w_out.refresh()

        for e_item in self.adj_items:
            e_item.refresh()

    def update_shape(self) -> None:
        pen = QPen()
        pen.setWidthF(3)
        pen.setColor(display_setting.colors["outline"])
        self.setPen(pen)

        path = QPainterPath()
        if self.ty == VertexType.H_BOX or self.ty == VertexType.Z_BOX:
            path.addRect(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        elif self.ty == VertexType.W_OUTPUT:
            # draw a triangle
            path.moveTo(0, 0.2 * SCALE)
            path.lineTo(0.25 * SCALE, -0.15 * SCALE)
            path.lineTo(-0.25 * SCALE, -0.15 * SCALE)
            path.lineTo(0, 0.2 * SCALE)
        elif self.ty == VertexType.W_INPUT:
            scale = 0.3 * SCALE
            path.addEllipse(-0.2 * scale, -0.2 * scale, 0.4 * scale, 0.4 * scale)
        elif self.ty == VertexType.BOUNDARY:
            scale = 0.3 * SCALE
            path.addEllipse(-0.2 * scale, -0.2 * scale, 0.4 * scale, 0.4 * scale)
        else:
            path.addEllipse(-0.2 * SCALE, -0.2 * SCALE, 0.4 * SCALE, 0.4 * SCALE)
        self.setPath(path)
        self.set_vitem_rotation()

    def set_vitem_rotation(self) -> None:
        if self.ty == VertexType.W_OUTPUT:
            w_in = get_w_partner_vitem(self)
            if w_in:
                angle = math.atan2(self.pos().x() - w_in.pos().x(), w_in.pos().y() - self.pos().y())
                self.setRotation(math.degrees(angle))
        else:
            self.setRotation(0)

    def set_pos_from_graph(self) -> None:
        self.setPos(*pos_to_view(self.g.row(self.v), self.g.qubit(self.v)))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        assert hasattr(option, "state")
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        # Snap items to grid on movement by intercepting the position-change
        # event and returning a new position
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self.is_animated:
            assert isinstance(value, QPointF)
            if self.ty == VertexType.W_INPUT:
                x = value.x()
                y = value.y()
            else:
                x = round(value.x() / display_setting.SNAP) * display_setting.SNAP
                y = round(value.y() / display_setting.SNAP) * display_setting.SNAP
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
            e.ignore()
            return
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        scene.vertex_double_clicked.emit(self.v)

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        if self.is_animated:
            e.ignore()
            return
        self._old_pos = self.pos()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self.is_animated:
            e.ignore()
            return
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        if self.is_dragging and self.ty == VertexType.W_OUTPUT:
            w_in = get_w_partner_vitem(self)
            assert w_in is not None
            if self._last_pos is None:
                self._last_pos = self.pos()
            w_in.setPos(w_in.pos() + (self.pos() - self._last_pos))
            self._last_pos = self.pos()
        elif self.is_dragging and self.ty == VertexType.W_INPUT:
            w_out = get_w_partner_vitem(self)
            if w_out is None:
                e.ignore()
                return
            w_out.set_vitem_rotation()
        if self.is_dragging and len(scene.selectedItems()) == 1:
            reset = True
            for it in scene.items():
                if not it.sceneBoundingRect().intersects(self.sceneBoundingRect()):
                    continue
                if isinstance(it, VItem) and vertex_is_w(self.ty) and get_w_partner(self.g, self.v) == it.v:
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
            e.ignore()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._old_pos != self.pos():
                if self.ty == VertexType.W_INPUT:
                    # set the position of w_in to next to w_out at the same angle
                    w_out = get_w_partner_vitem(self)
                    assert w_out is not None
                    w_in_pos = w_out.pos() + QPointF(0, W_INPUT_OFFSET * SCALE)
                    w_in_pos = rotate_point(w_in_pos, w_out.pos(), w_out.rotation())
                    self.setPos(w_in_pos)
                scene = self.scene()
                if TYPE_CHECKING: assert isinstance(scene, GraphScene)
                if self._dragged_on is not None and len(scene.selectedItems()) == 1:
                    scene.vertex_dropped_onto.emit(self.v, self._dragged_on.v)
                else:
                    moved_vertices = []
                    for it in scene.selectedItems():
                        if not isinstance(it, VItem):
                            continue
                        moved_vertices.append(it)
                        if vertex_is_w(it.ty):
                            partner = get_w_partner_vitem(it)
                            if partner:
                                moved_vertices.append(partner)
                    scene.vertices_moved.emit([(it.v, *pos_from_view(it.pos().x(), it.pos().y())) for it in moved_vertices])
                self._dragged_on = None
                self._old_pos = None
            else:
                e.ignore()
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
        vertex_type = self.v_item.g.type(self.v_item.v)
        if vertex_type == VertexType.Z_BOX:
            self.setPlainText(str(get_z_box_label(self.v_item.g, self.v_item.v)))
        elif vertex_type != VertexType.BOUNDARY:
            phase = self.v_item.g.phase(self.v_item.v)
            self.setPlainText(phase_to_s(phase, vertex_type))
        p = self.v_item.pos()
        self.setPos(p.x(), p.y() - 0.6 * SCALE)


def rotate_point(p: QPointF, origin: QPointF, angle: float) -> QPointF:
    """Rotate a point around an origin by an angle in degrees."""
    angle = math.radians(angle)
    return QPointF(
        math.cos(angle) * (p.x() - origin.x()) - math.sin(angle) * (p.y() - origin.y()) + origin.x(),
        math.sin(angle) * (p.x() - origin.x()) + math.cos(angle) * (p.y() - origin.y()) + origin.y()
    )

def get_w_partner_vitem(vitem: VItem) -> Optional[VItem]:
    """Get the VItem of the partner of a w_in or w_out vertex."""
    assert vertex_is_w(vitem.ty)
    partner: int = get_w_partner(vitem.g, vitem.v)
    if partner not in vitem.graph_scene.vertex_map:
        return None
    return vitem.graph_scene.vertex_map[partner]
