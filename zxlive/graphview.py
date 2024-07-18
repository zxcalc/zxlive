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

from typing import Optional, TYPE_CHECKING
from pyzx.graph.scalar import Scalar

import math
import random
from PySide6.QtCore import QRect, QSize, QPointF, Signal, Qt, QRectF, QLineF, QObject, QTimerEvent
from PySide6.QtWidgets import QGraphicsView, QGraphicsPathItem, QRubberBand, QGraphicsEllipseItem, QGraphicsItem, QLabel
from PySide6.QtGui import (QPen, QColor, QPainter, QPainterPath, QTransform, 
                           QMouseEvent, QWheelEvent, QBrush, QShortcut, QKeySequence,
                           QKeyEvent)

from dataclasses import dataclass

from . import animations as anims
from .common import (GraphT, SCALE, OFFSET_X, OFFSET_Y, MIN_ZOOM, MAX_ZOOM,
                     get_settings_value, set_settings_value)
from .graphscene import GraphScene, VItem, EItem, EditGraphScene
from .settings import display_setting
from .vitem import PHASE_ITEM_Z

if TYPE_CHECKING:
    from .rule_panel import RulePanel


class GraphTool:
    Selection = 1
    MagicWand = 2


@dataclass
class WandTrace:
    start: QPointF
    end: QPointF
    shift: bool
    hit: dict[VItem | EItem, list[QPointF]]

    def __init__(self, start: QPointF, shift: bool = False) -> None:
        self.start = start
        self.hit = {}
        self.end = start
        self.shift = shift


WAND_COLOR = "#500050"
WAND_WIDTH = 3.0

ZOOMFACTOR = 0.002 # Specifies how sensitive zooming with the mousewheel is

GRID_SCALE = SCALE / 2


class GraphView(QGraphicsView):
    """QtWidget containing a graph

    This widget is the view associated with a graph. However, most of the
    interesting stuff happens in `GraphScene`.
    """

    wand_trace_finished = Signal(object)
    draw_background_lines = True

    def __init__(self, graph_scene: GraphScene) -> None:
        self.graph_scene = graph_scene
        self.tool = GraphTool.Selection

        super().__init__(self.graph_scene)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        #self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag) # This has to be enabled based on keyboard shortcuts
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground);
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate);

        # We implement the rubberband logic ourselves. Note that there is also
        # the option to set `self.setDragMode(QGraphicsView.RubberBandDrag)`,
        # but that doesn't seem to play nicely with selection in the GraphScene,
        # presumably because it uses the coordinate system from this QGraphicsView
        # and not the one from the GraphScene...
        self.rubberband = QRubberBand(QRubberBand.Shape.Rectangle, self)

        self.wand_trace: Optional[WandTrace] = None
        self.wand_path: Optional[QGraphicsPathItem] = None

        self.centerOn(OFFSET_X,OFFSET_Y)

        self.sparkles = Sparkles(self.graph_scene)
        QShortcut(QKeySequence("Ctrl+Shift+Alt+S"), self).activated.connect(self._toggle_sparkles)

    @property
    def sparkle_mode(self) -> bool:
        return get_settings_value("sparkle-mode", bool)

    @sparkle_mode.setter
    def sparkle_mode(self, value: bool) -> None:
        set_settings_value("sparkle-mode", value, bool)

    def _toggle_sparkles(self) -> None:
        self.sparkle_mode = not self.sparkle_mode

    def set_graph(self, g: GraphT) -> None:
        self.graph_scene.set_graph(g)

    def update_graph(self, g: GraphT, select_new: bool = False) -> None:
        self.graph_scene.update_graph(g, select_new)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if self.tool == GraphTool.Selection and Qt.KeyboardModifier.ShiftModifier & e.modifiers():
            e.setModifiers(e.modifiers() | Qt.KeyboardModifier.ControlModifier)
        super().mousePressEvent(e)

        if e.button() == Qt.MouseButton.LeftButton and not self.graph_scene.items(self.mapToScene(e.pos()), deviceTransform=QTransform()):
            if self.tool == GraphTool.Selection:
                self._rubberband_start = e.pos()
                self.rubberband.setGeometry(QRect(self._rubberband_start, QSize()))
                self.rubberband.show()
            elif self.tool == GraphTool.MagicWand:
                pos = self.mapToScene(e.pos())
                shift = e.modifiers() & Qt.KeyboardModifier.ShiftModifier
                self.wand_trace = WandTrace(pos, bool(shift))
                self.wand_path = QGraphicsPathItem()
                self.graph_scene.addItem(self.wand_path)
                pen = QPen(QColor(WAND_COLOR), WAND_WIDTH)
                self.wand_path.setPen(pen)
                path = QPainterPath()
                path.moveTo(pos)
                self.wand_path.setPath(path)
                self.wand_path.show()
                if self.sparkle_mode:
                    self.sparkles.emit_sparkles(pos, 10)
            else:
                e.ignore()
        else:
            e.ignore()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if Qt.KeyboardModifier.ControlModifier & e.modifiers():
            g = self.graph_scene.g
            if Qt.KeyboardModifier.ShiftModifier & e.modifiers():
                distance = 1 / get_settings_value("snap-granularity", int)
            else:
                distance = 0.5
            for v in self.graph_scene.selected_vertices:
                vitem = self.graph_scene.vertex_map[v]
                x = g.row(v)
                y = g.qubit(v)
                if e.key() == Qt.Key.Key_Up:
                    g.set_position(v, y - distance, x)
                elif e.key() == Qt.Key.Key_Down:
                    g.set_position(v, y + distance, x)
                elif e.key() == Qt.Key.Key_Left:
                    g.set_position(v, y, x - distance)
                elif e.key() == Qt.Key.Key_Right:
                    g.set_position(v, y, x + distance)
                vitem.set_pos_from_graph()
        else:
            super().keyPressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self.tool == GraphTool.Selection:
            if self.rubberband.isVisible():
                self.rubberband.setGeometry(QRect(self._rubberband_start, e.pos()).normalized())
        elif self.tool == GraphTool.MagicWand:
            if self.wand_trace is not None:
                if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.wand_trace.shift = False
                assert self.wand_path is not None
                pos = self.mapToScene(e.pos())
                prev = self.wand_trace.end
                self.wand_trace.end = pos
                path = self.wand_path.path()
                path.lineTo(pos)
                self.wand_path.setPath(path)
                for i in range(10):
                    t = i / 9
                    ipos = QPointF(pos * t + prev * (1.0 - t))
                    if self.sparkle_mode:
                        self.sparkles.emit_sparkles(ipos, 1)
                    items = self.graph_scene.items(ipos)
                    for item in items:
                        if isinstance(item, VItem) and item not in self.wand_trace.hit:
                            anims.anticipate_fuse(item)
                        if item is not self.wand_path and isinstance(item, (VItem, EItem)):
                            if item not in self.wand_trace.hit:
                                self.wand_trace.hit[item] = []
                            self.wand_trace.hit[item].append(ipos)
            else:
                e.ignore()
        else:
            e.ignore()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self.tool == GraphTool.Selection and Qt.KeyboardModifier.ShiftModifier & e.modifiers():
            e.setModifiers(e.modifiers() | Qt.KeyboardModifier.ControlModifier)
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            if self.tool == GraphTool.Selection:
                if self.rubberband.isVisible():
                    self.rubberband.hide()
                    key_modifiers = e.modifiers()
                    if not(Qt.KeyboardModifier.ShiftModifier & key_modifiers or Qt.KeyboardModifier.ControlModifier & key_modifiers):
                        self.graph_scene.clearSelection()
                    rect = self.rubberband.geometry()
                    items = [it for it in self.graph_scene.items(self.mapToScene(rect).boundingRect()) if isinstance(it, VItem)]
                    for it in items:
                        it.setSelected(not (len(items) == 1 or e.modifiers() & Qt.KeyboardModifier.ShiftModifier) or not it.isSelected())
                    self.graph_scene.selection_changed_custom.emit()
            elif self.tool == GraphTool.MagicWand:
                if self.wand_trace is not None:
                    if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                        self.wand_trace.shift = False
                    assert self.wand_path is not None
                    if self.sparkle_mode:
                        self.sparkles.stop()
                    for item in self.wand_trace.hit:
                        if isinstance(item, VItem):
                            anims.back_to_default(item)
                    self.wand_path.hide()
                    self.graph_scene.removeItem(self.wand_path)
                    self.wand_path = None
                    self.wand_trace_finished.emit(self.wand_trace)
                    self.wand_trace = None
                else:
                    e.ignore()
        else:
            e.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:
        # This event captures mousewheel scrolls
        # We do this to allow for zooming

        # If control is pressed, we want to zoom
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            ydelta = event.angleDelta().y()
            self.zoom(ydelta)
        else:
            super().wheelEvent(event)

    def zoom(self, ydelta: float) -> None:
        # Set Anchors
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        # Save the scene pos
        old_pos = self.mapToScene(self.viewport().rect().center())

        zoom_factor = 1.0
        if ydelta > 0:
            zoom_factor = 1 + ZOOMFACTOR * ydelta
        elif ydelta < 0:
            zoom_factor = 1/(1 - ZOOMFACTOR * ydelta)

        current_zoom = self.transform().m11()
        if current_zoom * zoom_factor < MIN_ZOOM:
            return
        elif current_zoom * zoom_factor > MAX_ZOOM:
            return
        self.scale(zoom_factor, zoom_factor)

        # Get the new position
        new_pos = self.mapToScene(self.viewport().rect().center())

        # Move scene to old position
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def zoom_out(self) -> None:
        self.zoom(-100)

    def zoom_in(self) -> None:
        self.zoom(100)

    def fit_view(self) -> None:
        self.fitInView(self.graph_scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        current_zoom = self.transform().m11()
        if current_zoom < MIN_ZOOM:
            self.scale(MIN_ZOOM / current_zoom, MIN_ZOOM / current_zoom)
        else:
            if current_zoom > MAX_ZOOM:
                self.scale(MAX_ZOOM / current_zoom, MAX_ZOOM / current_zoom)

    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        # First draw blank white background
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.drawRect(rect)
        if not self.draw_background_lines: return

        # Calculate grid lines
        lines, thick_lines = [], []
        for x in range(int(rect.left() / GRID_SCALE), math.ceil(rect.right() / GRID_SCALE) + 1):
            line = QLineF(x * GRID_SCALE, rect.top(), x * GRID_SCALE, rect.bottom())
            if x % 4 == 0:
                thick_lines.append(line)
            else:
                lines.append(line)
        for y in range(int(rect.top() / GRID_SCALE), math.ceil(rect.bottom() / GRID_SCALE) + 1):
            line = QLineF(rect.left(), y * GRID_SCALE, rect.right(), y * GRID_SCALE)
            if y % 4 == 0:
                thick_lines.append(line)
            else:
                lines.append(line)

        # Draw grid lines
        painter.setPen(QPen(QColor(240, 240, 240), 1, Qt.PenStyle.SolidLine))
        painter.drawLines(lines)
        painter.setPen(QPen(QColor(240, 240, 240), 2, Qt.PenStyle.SolidLine))
        painter.drawLines(thick_lines)

    def update_font(self) -> None:
        for i in self.graph_scene.items():
            if isinstance(i, VItem):
                i.update_font()

class ProofGraphView(GraphView):
    def __init__(self, graph_scene: GraphScene) -> None:
        super().__init__(graph_scene)
        self.scalar_label = QLabel(parent=self)
        self.scalar_label.move(10, 10)
        self.scalar_label.show()
        self.__update_scalar_label(Scalar())

    def set_graph(self, g: GraphT) -> None:
        super().set_graph(g)
        self.__update_scalar_label(g.scalar)

    def update_graph(self, g: GraphT, select_new: bool = False) -> None:
        super().update_graph(g, select_new)
        self.__update_scalar_label(g.scalar)

    def __update_scalar_label(self, scalar: Scalar) -> None:
        self.scalar = scalar
        scalar_string = f" Scalar: {scalar.polar_str()}"
        if scalar.is_zero:
            colour = "red"
            text = f"{scalar_string}, The global scalar is zero"
        else:
            colour = "black"
            text = f"{scalar_string}"

        self.scalar_label.setText(f"<span style='color:{colour}'>{text}</span>")
        font_metrics = self.scalar_label.fontMetrics().size(0, text, 0)
        self.scalar_label.setFixedWidth(font_metrics.width())
        self.scalar_label.setFixedHeight(font_metrics.height())

    def update_font(self) -> None:
        self.scalar_label.setFont(display_setting.font)
        self.__update_scalar_label(self.scalar)
        super().update_font()


class RuleEditGraphView(GraphView):
    def __init__(self, parent_panel: RulePanel, graph_scene: GraphScene) -> None:
        super().__init__(graph_scene)
        self.parent_panel = parent_panel

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self.parent_panel.graph_view = self
        assert isinstance(self.graph_scene, EditGraphScene)
        self.parent_panel.graph_scene = self.graph_scene
        super().mousePressEvent(e)


SPARKLE_COLOR = ["#900090", "#ff9999", "#3333ff", "#99ff99"]
SPARKLE_COUNT = 1
SPARKLE_MAX_SPEED = 100.0
SPARKLE_MIN_SPEED = 10.0
MAX_SPARKLES = 500
SPARKLE_STEPS = 60


class Sparkles(QObject):

    def __init__(self, graph_scene: GraphScene) -> None:
        super().__init__()
        self.graph_scene = graph_scene
        self.sparkle_index = 0
        self.sparkles: list[Sparkle] = []
        self.sparkle_deltas = []
        for _ in range(MAX_SPARKLES):
            angle = random.random() * 2 * math.pi
            speed = random.random() * (SPARKLE_MAX_SPEED - SPARKLE_MIN_SPEED) + SPARKLE_MIN_SPEED
            vx = speed * math.cos(angle) / SPARKLE_STEPS
            vy = speed * math.sin(angle) / SPARKLE_STEPS
            self.sparkle_deltas.append((vx, vy))
        self.timer_id: Optional[int] = None

    def emit_sparkles(self, pos: QPointF, mult: int) -> None:
        if not self.timer_id:
            self.timer_id = self.startTimer(int(1000 / SPARKLE_STEPS))

        for _ in range(mult * SPARKLE_COUNT):
            vx, vy = self.sparkle_deltas[self.sparkle_index]
            if len(self.sparkles) < MAX_SPARKLES:
                self.sparkles.append(Sparkle(pos.x(), pos.y(), vx, vy, self.graph_scene))
            else:
                self.sparkles[self.sparkle_index].reset(pos.x(), pos.y(), vx, vy)
            self.sparkle_index = (self.sparkle_index + 1) % MAX_SPARKLES

    def timerEvent(self, event: QTimerEvent) -> None:
        if event.timerId() != self.timer_id:
            event.ignore()
            return
        for sparkle in self.sparkles:
            sparkle.timer_step()

    def stop(self) -> None:
        assert self.timer_id is not None
        self.killTimer(self.timer_id)
        self.timer_id = None
        for sparkle in reversed(self.sparkles):
            self.graph_scene.removeItem(sparkle)
        self.sparkles = []


class Sparkle(QGraphicsEllipseItem):
    def __init__(self, x: float, y: float, vx: float, vy: float, scene: GraphScene) -> None:
        super().__init__(
            -0.05 * SCALE, -0.05 * SCALE, 0.1 * SCALE, 0.1 * SCALE
        )

        self.vx, self.vy = vx, vy
        self.vo = 1 / SPARKLE_STEPS

        self.setPos(x, y)
        self.setZValue(PHASE_ITEM_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False)
        col = SPARKLE_COLOR[random.randint(0,3)]
        self.setBrush(QBrush(QColor(col)))
        self.setPen(QPen(Qt.PenStyle.NoPen))

        scene.addItem(self)

        self.step = 0
        self.show()

    def reset(self, x: float, y: float, vx: float, vy: float) -> None:
        self.setPos(x, y)
        self.vx, self.vy = vx, vy
        self.setOpacity(1.0)

        self.step = 0
        self.show()

    def timer_step(self) -> None:
        self.step += 1
        if self.step == SPARKLE_STEPS:
            self.hide()
            return

        self.setX(self.x() + self.vx)
        self.setY(self.y() + self.vy)
        self.setOpacity(self.opacity() - self.vo)
