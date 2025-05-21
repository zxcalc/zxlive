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
from math import sqrt
from typing import Optional, Any, TYPE_CHECKING, Union
from enum import Enum

from PySide6.QtCore import QPointF, QVariantAnimation, QAbstractAnimation
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, \
    QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem, QWidget, QStyle
from PySide6.QtGui import QPen, QPainter, QColor, QPainterPath

from pyzx import EdgeType

from .common import SCALE, ET, GraphT
from .vitem import VItem, EITEM_Z

if TYPE_CHECKING:
    from .graphscene import GraphScene

HAD_EDGE_BLUE = "#0077ff"

class EItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge"""

    # Set of animations that are currently running on this vertex
    active_animations: set[EItemAnimation]

    class Properties(Enum):
        """Properties of an EItem that can be animated."""
        Thickness = 1

    def __init__(self, graph_scene: GraphScene, e: ET, s_item: VItem, t_item: VItem, curve_distance: float = 0) -> None:
        super().__init__()
        self.setZValue(EITEM_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.graph_scene = graph_scene
        self.e = e
        self.s_item = s_item
        self.t_item = t_item
        self.curve_distance = curve_distance
        self.active_animations = set()
        s_item.adj_items.add(self)
        t_item.adj_items.add(self)
        self.selection_node = QGraphicsEllipseItem(-0.1 * SCALE, -0.1 * SCALE, 0.2 * SCALE, 0.2 * SCALE)
        pen = QPen()
        pen.setWidthF(4)
        pen.setColor(QColor('#0022FF'))
        self.selection_node.setPen(pen)
        self.selection_node.setOpacity(0.5)
        # self.selection_node.setVisible(False)
        self.is_mouse_pressed = False
        self.is_dragging = False
        self._old_pos: Optional[QPointF] = None
        self.thickness: float = 3

        self.refresh()

    @property
    def g(self) -> GraphT:
        return self.graph_scene.g

    @property
    def is_animated(self) -> bool:
        return len(self.active_animations) > 0

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                     self.g.edge_type(self.e) != EdgeType.W_IO)
        # set color/style according to edge type
        pen = QPen()
        pen.setWidthF(self.thickness)
        if self.g.edge_type(self.e) == EdgeType.HADAMARD:
            pen.setColor(QColor(HAD_EDGE_BLUE))
            pen.setDashPattern([4.0, 2.0])
        else:
            from .settings import display_setting
            pen.setColor(display_setting.effective_colors["edge"])
        self.setPen(QPen(pen))

        path = QPainterPath()
        if self.s_item == self.t_item: # self-loop
            cd = self.curve_distance
            cd = cd + 0.5 if cd >= 0 else cd - 0.5
            s_pos = self.s_item.pos()
            path.moveTo(s_pos)
            path.cubicTo(s_pos + QPointF(1, -1) * cd * SCALE,
                         s_pos + QPointF(-1, -1) * cd * SCALE,
                         s_pos)
            curve_midpoint = s_pos + QPointF(0, -0.75) * cd * SCALE
        else:
            control_point = calculate_control_point(self.s_item.pos(), self.t_item.pos(), self.curve_distance)
            path.moveTo(self.s_item.pos())
            path.quadTo(control_point, self.t_item.pos())
            curve_midpoint = self.s_item.pos() * 0.25 + control_point * 0.5 + self.t_item.pos() * 0.25
        self.setPath(path)
        self.selection_node.setPos(curve_midpoint.x(), curve_midpoint.y())
        self.selection_node.setVisible(self.isSelected())


    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        assert hasattr(option, "state")
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        # Intercept selection- and position-has-changed events to call `refresh`.
        # Note that the position and selected values are already updated when
        # this event fires.
        if change in (QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged):
            self.refresh()

        return super().itemChange(change, value)


    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        self.refresh()
        self._old_pos = e.pos()
        self._old_curve_distance = self.curve_distance
        self.is_mouse_pressed = True

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        if self.is_mouse_pressed and len(scene.selectedItems()) == 1 and self._old_pos is not None:
            self.is_dragging = True
            distance = e.pos() - self._old_pos
            perpendicular = compute_perpendicular_direction(self.s_item.pos(), self.t_item.pos())
            self.curve_distance += 2 * QPointF.dotProduct(distance, perpendicular) / SCALE
            self._old_pos = e.pos()
            self.refresh()
        e.ignore()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if self.is_dragging:
            self.graph_scene.edge_dragged.emit(self, self.curve_distance, self._old_curve_distance)
            self._old_pos = None
        self.is_dragging = False
        self.is_mouse_pressed = False
        self.graph_scene.selection_changed_custom.emit()

    def mouseDoubleClickEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(e)
        if self.is_animated:
            e.ignore()
            return
        scene = self.scene()
        if TYPE_CHECKING: assert isinstance(scene, GraphScene)
        scene.edge_double_clicked.emit(self.e)



# TODO: This is essentially a clone of EItem. We should common it up!
class EDragItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge in construction during a drag"""

    def __init__(self, g: GraphT, ety: EdgeType, start: VItem, mouse_pos: QPointF) -> None:
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

def calculate_control_point(source_pos: QPointF, target_pos: QPointF, curve_distance: float) -> QPointF:
    """Calculate the control point for the curve"""
    perpendicular = compute_perpendicular_direction(source_pos, target_pos)
    source_plus_target = source_pos + target_pos
    midpoint = QPointF(source_plus_target.x() / 2, source_plus_target.y() / 2)
    offset = perpendicular * curve_distance * SCALE
    control_point = midpoint + offset
    return control_point

def compute_perpendicular_direction(source_pos: QPointF, target_pos: QPointF) -> QPointF:
    if source_pos == target_pos:
        return QPointF(0, -2/3)
    direction = target_pos - source_pos
    norm = sqrt(direction.x()**2 + direction.y()**2)
    direction = QPointF(direction.x() / norm, direction.y() / norm)
    perpendicular = QPointF(-direction.y(), direction.x())
    return perpendicular


class EItemAnimation(QVariantAnimation):
    """Animator for edge graphics items.

    This animator lets the edge know that its being animated which stops any
    interaction with the user. Furthermore, this animator
    ensures that it's not garbage collected until the animation is finished, so there is
    no need to hold onto a reference of this class."""

    _it: Optional[EItem]
    prop: EItem.Properties
    refresh: bool  # Whether the item is refreshed at each frame

    e: Optional[ET]

    def __init__(self, item: Union[EItem, ET], property: EItem.Properties,
                 scene: Optional[GraphScene] = None, refresh: bool = False) -> None:
        super().__init__()
        self.e = None
        self._it = None
        self.scene: Optional[GraphScene] = None
        if isinstance(item, EItem):
            self._it = item
        elif scene is None:
            raise ValueError("Scene is required to obtain EItem from edge ET")
        else:
            self.e = item
            self.scene = scene
        self.prop = property
        self.refresh = refresh
        self.stateChanged.connect(self._on_state_changed)

    @property
    def it(self) -> EItem:
        if self._it is None and self.scene is not None and self.e is not None:
            self._it = self.scene.edge_map[self.e][0]
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

        if self.prop == EItem.Properties.Thickness:
            self.it.thickness = value

        if self.refresh:
            self.it.refresh()
