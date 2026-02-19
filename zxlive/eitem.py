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

from PySide6.QtCore import QPointF, QVariantAnimation, QAbstractAnimation, Qt
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, \
    QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem, QWidget, QStyle
from PySide6.QtGui import QPen, QPainter, QColor, QPainterPath, QPainterPathStroker

from pyzx.utils import EdgeType, VertexType

from .common import SCALE, ET, GraphT, get_settings_value
from .settings import display_setting
from .vitem import VItem, EITEM_Z

if TYPE_CHECKING:
    from .graphscene import GraphScene

HAD_EDGE_BLUE = "#0077ff"


class EItem(QGraphicsPathItem):
    """A QGraphicsItem representing an edge"""

    # Set of animations that are currently running on this vertex
    active_animations: set[EItemAnimation]

    # Diff highlight state for proof mode: None, "changed", "removed", or "added"
    _diff_highlight: Optional[str]

    class Properties(Enum):
        """Properties of an EItem that can be animated."""
        Thickness = 1

    def __init__(self, graph_scene: GraphScene, e: ET, s_item: VItem, t_item: VItem, curve_distance: float = 0, index: int = 0) -> None:
        super().__init__()
        self.setZValue(EITEM_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.graph_scene = graph_scene
        self.e = e
        self.s_item = s_item
        self.t_item = t_item
        self.curve_distance = curve_distance
        self.index = index
        self.active_animations = set()
        self._diff_highlight = None
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
        self.color: QColor = QColor()
        self.reset_color()

        self.refresh()

    @property
    def g(self) -> GraphT:
        return self.graph_scene.g

    @property
    def is_animated(self) -> bool:
        return len(self.active_animations) > 0

    def reset_color(self) -> None:
        """Reset the color of the edge to the default color."""
        if self.g.edge_type(self.e) == EdgeType.HADAMARD:
            self.color = QColor(HAD_EDGE_BLUE)
        else:
            if self.g.type(self.g.edge_s(self.e)) == VertexType.DUMMY or \
               self.g.type(self.g.edge_t(self.e)) == VertexType.DUMMY:
                self.color = display_setting.effective_colors["dummy_edge"]
            else:
                self.color = display_setting.effective_colors["edge"]

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                     self.g.edge_type(self.e) != EdgeType.W_IO)
        # set color/style according to edge type
        pen = QPen()
        pen.setWidthF(self.thickness)
        if self.g.edge_type(self.e) == EdgeType.HADAMARD:
            pen.setDashPattern([4.0, 2.0])
        pen.setColor(self.color)
        # Override color and thickness when diff-highlighted in proof mode
        if self._diff_highlight is not None:
            color_key = f"diff_{self._diff_highlight}"
            pen.setColor(display_setting.effective_colors[color_key])
            pen.setWidthF(self.thickness + 4)
        self.setPen(QPen(pen))

        if not self.is_dragging:
            self.curve_distance = self.g.edata(self.e, f"curve_{self.index}", self.curve_distance)

        path = QPainterPath()
        if self.s_item == self.t_item:  # self-loop
            cd = self.curve_distance
            cd = cd + 0.5 if cd >= 0 else cd - 0.5
            s_pos = self.s_item.pos()
            path.moveTo(s_pos)
            path.cubicTo(s_pos + QPointF(1, -1) * cd * SCALE,
                         s_pos + QPointF(-1, -1) * cd * SCALE,
                         s_pos)
            curve_midpoint = s_pos + QPointF(0, -0.75) * cd * SCALE

            # we don't care about half-paths for self loops, since they won't be colored
            self.half_path_left = None
            self.half_path_right = None
        else:
            control_point = calculate_control_point(self.s_item.pos(), self.t_item.pos(), self.curve_distance)
            path.moveTo(self.s_item.pos())
            path.quadTo(control_point, self.t_item.pos())
            curve_midpoint = self.s_item.pos() * 0.25 + control_point * 0.5 + self.t_item.pos() * 0.25

            half_path_left = QPainterPath()
            half_control_left = (self.s_item.pos() + control_point) * 0.5
            half_path_left.moveTo(self.s_item.pos())
            half_path_left.quadTo(half_control_left, curve_midpoint)
            self.half_path_left = half_path_left

            half_path_right = QPainterPath()
            half_control_right = (self.t_item.pos() + control_point) * 0.5
            half_path_right.moveTo(curve_midpoint)
            half_path_right.quadTo(half_control_right, self.t_item.pos())
            self.half_path_right = half_path_right

        self.setPath(path)
        self.selection_node.setPos(curve_midpoint.x(), curve_midpoint.y())
        self.selection_node.setVisible(self.isSelected())

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        # The type stub is missing the 'state' attribute, so there is a
        # false positive mypy error if we set the usual way.
        assert hasattr(option, "state")
        state = getattr(option, "state")
        setattr(option, "state", state & ~QStyle.StateFlag.State_Selected)

        webs: list[tuple[bool, bool, QColor]] = []

        swap = get_settings_value("swap-pauli-web-colors", bool)
        zweb0 = self.g.edata(self.e, "xweb0" if swap else "zweb0")
        zweb1 = self.g.edata(self.e, "xweb1" if swap else "zweb1")
        xweb0 = self.g.edata(self.e, "zweb0" if swap else "xweb0")
        xweb1 = self.g.edata(self.e, "zweb1" if swap else "xweb1")

        highlight = self.g.edata(self.e, "highlight")
        webs.append((highlight, highlight, QColor("#FFC107")))  # highlight web

        zcolor = display_setting.effective_colors["z_pauli_web"]
        xcolor = display_setting.effective_colors["x_pauli_web"]
        ycolor = display_setting.effective_colors["y_pauli_web"]

        # only draw y webs if the setting is enabled
        if get_settings_value("blue-y-pauli-web", bool):
            yweb0 = zweb0 and xweb0
            yweb1 = zweb1 and xweb1

            # if we're drawing y webs, we shouldn't draw the corresponding x and z webs
            zweb0 = zweb0 and not yweb0
            zweb1 = zweb1 and not yweb1
            xweb0 = xweb0 and not yweb0
            xweb1 = xweb1 and not yweb1

            webs.append((yweb0, yweb1, ycolor))

        webs.append((zweb0, zweb1, zcolor))
        webs.append((xweb0, xweb1, xcolor))

        # determine thicknesses for each web
        thicknesses: list[float] = []
        left_thickness = 2.5
        right_thickness = 2.5
        for left, right, _ in reversed(webs):
            if left and right:
                thickness = max(left_thickness, right_thickness)
                thicknesses.append(thickness)
                left_thickness = right_thickness = thickness + 1
            elif left:
                thicknesses.append(left_thickness)
                left_thickness += 1
            elif right:
                thicknesses.append(right_thickness)
                right_thickness += 1
            else:
                thicknesses.append(0)
        thicknesses.reverse()

        # draw webs from outermost to innermost
        for (left, right, color), thickness in zip(webs, thicknesses):
            self._paint_pauli_web(painter, option, widget, color, thickness, left=left, right=right)

        super().paint(painter, option, widget)

    def _paint_pauli_web(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget],
                         color: QColor, thickness: float, *, left: bool, right: bool) -> None:
        """Draws a colored Pauli web on the edge if specified by the flags."""

        if not (left or right):
            return

        old_path = self.path()
        old_pen = self.pen()

        path = old_path if left and right else (self.half_path_left if left else self.half_path_right)
        path = path or old_path  # fallback if half paths are not defined (self-loops)

        pen = QPen(old_pen)
        pen.setWidthF(self.thickness * thickness)
        pen.setColor(color)
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setPath(path)
        super().paint(painter, option, widget)
        self.setPen(old_pen)
        self.setPath(old_path)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        # Intercept selection- and position-has-changed events to call `refresh`.
        # Note that the position and selected values are already updated when
        # this event fires.
        if change in (QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged):
            self.refresh()

            if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
                self.graph_scene.selection_changed_custom.emit()

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
        if TYPE_CHECKING:
            assert isinstance(scene, GraphScene)
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
        if TYPE_CHECKING:
            assert isinstance(scene, GraphScene)
        scene.edge_double_clicked.emit(self.e)

    def shape(self) -> QPainterPath:
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.thickness, 8))  # 8 px is a reasonable clickable width
        return stroker.createStroke(path)


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
            pen.setColor(QColor(HAD_EDGE_BLUE))
            pen.setDashPattern([4.0, 2.0])
        elif self.start.ty == VertexType.DUMMY:
            pen.setColor(display_setting.effective_colors["dummy_edge"])
        else:
            pen.setColor(display_setting.effective_colors["edge"])
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
        return QPointF(0, -2 / 3)
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