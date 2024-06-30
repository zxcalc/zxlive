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
from typing import Optional, Any, TYPE_CHECKING

from PySide6.QtCore import QPointF
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

        self.refresh()

    @property
    def g(self) -> GraphT:
        return self.graph_scene.g

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                     self.g.edge_type(self.e) != EdgeType.W_IO)
        # set color/style according to edge type
        pen = QPen()
        pen.setWidthF(3)
        if self.g.edge_type(self.e) == EdgeType.HADAMARD:
            pen.setColor(QColor(HAD_EDGE_BLUE))
            pen.setDashPattern([4.0, 2.0])
        else:
            pen.setColor(QColor("#000000"))
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



# TODO: This is essentially a clone of EItem. We should common it up!
class EDragItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge in construction during a drag"""

    def __init__(self, g: GraphT, ety: EdgeType.Type, start: VItem, mouse_pos: QPointF) -> None:
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

def calculate_control_point(source_pos: QPointF, target_pos: QPointF, curve_distance: float):
    """Calculate the control point for the curve"""
    perpendicular = compute_perpendicular_direction(source_pos, target_pos)
    midpoint = (source_pos + target_pos) / 2
    offset = perpendicular * curve_distance * SCALE
    control_point = midpoint + offset
    return control_point

def compute_perpendicular_direction(source_pos, target_pos):
    if source_pos == target_pos:
        return QPointF(0, -2/3)
    direction = target_pos - source_pos
    norm = sqrt(direction.x()**2 + direction.y()**2)
    direction = direction / norm
    perpendicular = QPointF(-direction.y(), direction.x())
    return perpendicular
