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
from dataclasses import dataclass
from math import sqrt
from typing import Optional, Any, TYPE_CHECKING, Union
from enum import Enum

from PySide6.QtCore import QPointF, QVariantAnimation, QAbstractAnimation, Qt
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, \
    QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem, QWidget, QStyle
from PySide6.QtGui import QPen, QPainter, QColor, QPainterPath, QPainterPathStroker

from pyzx.utils import EdgeType, VertexType

from .common import SCALE, ET, GraphT
from .settings import display_setting
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
        Opacity = 2

    @dataclass
    class PauliWebData:
        left: bool
        right: bool
        color: QColor
        thickness: float
        
        def should_draw(self):
            return (self.left or self.right) and self.thickness > 0

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
        self.thickness: float = 3.0
        self.color: QColor = QColor()
        self.pauli_webs: list[EItem.PauliWebData] = []
        self.xweb_left: bool = False
        self.xweb_right: bool = False
        self.zweb_left: bool = False
        self.zweb_right: bool = False
        self.highlight: bool = False
        self.use_y_webs: bool = False
        self.pauli_pen: QPen = QPen(self.pen())
        self.pauli_pen.setStyle(Qt.PenStyle.SolidLine)
        self.pauli_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
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
        self.setPen(pen)

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

    def _add_pauli_web(self, left: bool, right: bool, color: QColor):
        self.pauli_webs.append(EItem.PauliWebData(
            left=left,
            right=right,
            color=color,
            thickness=0 # Temporary placeholder thickness; this should be set later
        ))

    def update_pauli_webs(
        self,
        *,
        xweb_left: bool | None = None,
        xweb_right: bool | None = None,
        zweb_left: bool | None = None,
        zweb_right: bool | None = None,
        highlight: bool | None = None,
        use_y_webs: bool | None = None
    ):
        """Updates the Pauli web data for this edge. Omitted parameters are unchanged."""

        # Default to cached values for any parameters which aren't provided
        # Additionally, cache the values for any parameters which are provided
        self.xweb_left = xweb_left = (self.xweb_left if xweb_left is None else xweb_left)
        self.xweb_right = xweb_right = (self.xweb_right if xweb_right is None else xweb_right)
        self.zweb_left = zweb_left = (self.zweb_left if zweb_left is None else zweb_left)
        self.zweb_right = zweb_right = (self.zweb_right if zweb_right is None else zweb_right)
        self.highlight = highlight = (self.highlight if highlight is None else highlight)
        self.use_y_webs = use_y_webs = (self.use_y_webs if use_y_webs is None else use_y_webs)

        # Webs are sorted from outer to inner
        # We use a temporary placeholder for the thickness
        self.pauli_webs.clear()
        self._add_pauli_web(highlight, highlight, display_setting.effective_colors["pauli_web_highlight"])

        zcolor = display_setting.effective_colors["z_pauli_web"]
        xcolor = display_setting.effective_colors["x_pauli_web"]
        ycolor = display_setting.effective_colors["y_pauli_web"]

        # Only draw Y-webs if the setting is enabled
        if self.use_y_webs:
            yweb0 = zweb_left and xweb_left
            yweb1 = zweb_right and xweb_right

            # If we're drawing Y-webs, we shouldn't draw the corresponding X- and Z-webs
            zweb_left &= not yweb0
            zweb_right &= not yweb1
            xweb_left &= not yweb0
            xweb_right &= not yweb1

            self._add_pauli_web(yweb0, yweb1, ycolor)

        self._add_pauli_web(zweb_left, zweb_right, zcolor)
        self._add_pauli_web(xweb_left, xweb_right, xcolor)

        # Determine thicknesses for each web
        left_thickness = 2.5
        right_thickness = 2.5
        for web in reversed(self.pauli_webs):
            if web.left and web.right:
                web.thickness = max(left_thickness, right_thickness)
                left_thickness = web.thickness + 1
                right_thickness = web.thickness + 1
            elif web.left:
                web.thickness = left_thickness
                left_thickness += 1
            elif web.right:
                web.thickness = right_thickness
                right_thickness += 1
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        # By default, Qt draws a dashed rectangle around selected items.
        # We have our own implementation to draw selected vertices, so
        # we intercept the selected option here.
        option.state &= ~QStyle.StateFlag.State_Selected

        # First, we draw any Pauli webs the edge has
        if self.pauli_webs:
            # Self-loops may not define half-paths, so we fall back to the full path
            full_path = self.path()
            left_path = self.half_path_left or full_path
            right_path = self.half_path_right or full_path

            painter.save()
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # Draw webs from outermost to innermost
            for web in self.pauli_webs:
                if not web.should_draw() <= 0:
                    continue

                # Choose the path to draw based on the web properties
                if web.left and web.right:
                    path = full_path
                elif web.left:
                    path = left_path
                else:
                    path = right_path

                # Set the painter and draw the web
                self.pauli_pen.setWidthF(self.thickness * web.thickness)
                self.pauli_pen.setColor(web.color)
                painter.setPen(self.pauli_pen)
                painter.drawPath(path)

            painter.restore()

        super().paint(painter, option, widget)

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
    """A QGraphicsItem representing edges in construction during a drag."""

    def __init__(self, g: GraphT, ety: EdgeType, start: VItem, mouse_pos: QPointF,
                 starts: Optional[list[VItem]] = None) -> None:
        super().__init__()
        self.setZValue(EITEM_Z)
        self.g = g
        self.ety = ety
        self.start = start
        self.starts = [start] if starts is None else starts
        self.mouse_pos = mouse_pos
        self._preview_paths: list[tuple[QPainterPath, QPen]] = []
        self.refresh()

    def _preview_pen(self, is_dummy: bool) -> QPen:
        """Return the pen for one group of preview paths."""
        pen = QPen()
        pen.setWidthF(3)
        if self.ety == EdgeType.HADAMARD:
            pen.setColor(QColor(HAD_EDGE_BLUE))
            pen.setDashPattern([4.0, 2.0])
        elif is_dummy:
            pen.setColor(display_setting.effective_colors["dummy_edge"])
        else:
            pen.setColor(display_setting.effective_colors["edge"])
        return pen

    def refresh(self) -> None:
        """Call whenever source or target moves or edge data changes"""

        # Apply the primary drag offset to every selected source.
        offset = self.mouse_pos - self.start.pos()
        path = QPainterPath()
        paths_by_style: dict[bool, QPainterPath] = {}
        for start in self.starts:
            subpath = QPainterPath(start.pos())
            subpath.lineTo(start.pos() + offset)
            path.addPath(subpath)

            # Hadamard styling takes precedence for every source. For other
            # edge types, dummy and ordinary previews need distinct colors.
            is_dummy = self.ety != EdgeType.HADAMARD and start.ty == VertexType.DUMMY
            paths_by_style.setdefault(is_dummy, QPainterPath()).addPath(subpath)

        primary_is_dummy = self.ety != EdgeType.HADAMARD and self.start.ty == VertexType.DUMMY
        # Qt uses the combined path and pen width to calculate the item's geometry;
        # paint() controls how the individual preview lines look.
        self.setPen(self._preview_pen(primary_is_dummy))
        self._preview_paths = [
            (style_path, self._preview_pen(is_dummy))
            for is_dummy, style_path in paths_by_style.items()
        ]
        self.setPath(path)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        """Paint preview subpaths with the pen for their source style."""
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for path, pen in self._preview_paths:
            painter.setPen(pen)
            painter.drawPath(path)
        painter.restore()


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
    def it(self) -> Optional[EItem]:
        # Returns ``None`` if the edge is no longer in the scene.
        if self._it is None and self.scene is not None and self.e is not None:
            if mapping := self.scene.edge_map.get(self.e):
                self._it = mapping[0]
        return self._it

    def _on_state_changed(self, state: QAbstractAnimation.State) -> None:
        if (item := self.it) is None:
            return
        if state == QAbstractAnimation.State.Running and self not in item.active_animations:
            # Stop all animations that target the same property
            for anim in item.active_animations.copy():
                if anim.prop == self.prop:
                    anim.stop()
            item.active_animations.add(self)
        elif state == QAbstractAnimation.State.Stopped:
            item.active_animations.discard(self)
        elif state == QAbstractAnimation.State.Paused:
            # TODO: Once we use pausing, we should decide what to do here.
            #   Note that we cannot just remove ourselves from the set since the garbage
            #   collector will eat us in that case. We'll probably need something like
            #   `it.paused_animations`
            pass

    def updateCurrentValue(self, value: Any) -> None:
        if self.state() != QAbstractAnimation.State.Running or (item := self.it) is None:
            return

        if self.prop == EItem.Properties.Thickness:
            item.thickness = value
        elif self.prop == EItem.Properties.Opacity:
            item.setOpacity(value)

        if self.refresh:
            item.refresh()
