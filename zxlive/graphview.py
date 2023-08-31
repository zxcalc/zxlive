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

from typing import Optional

import math
import random
from PySide6.QtCore import QRect, QSize, QPointF, Signal, Qt, QRectF, QLineF, QTimeLine
from PySide6.QtWidgets import QGraphicsView, QGraphicsPathItem, QRubberBand, QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath, QTransform, QMouseEvent, QWheelEvent, QBrush, QShortcut, QKeySequence

from .graphscene import GraphScene, VItem, EItem

from dataclasses import dataclass

from .common import  GraphT, SCALE, OFFSET_X, OFFSET_Y, MIN_ZOOM, MAX_ZOOM
from .vitem import PHASE_ITEM_Z
from . import animations as anims


class GraphTool:
    Selection = 1
    MagicWand = 2


@dataclass
class WandTrace:
    start: QPointF
    end: QPointF
    hit: dict[VItem | EItem, list[QPointF]]

    def __init__(self, start: QPointF) -> None:
        self.start = start
        self.hit = {}
        self.end = start


WAND_COLOR = "#500050"
WAND_WIDTH = 3.0

ZOOMFACTOR = 0.002 # Specifies how sensitive zooming with the mousewheel is

GRID_SCALE = SCALE / 2


class GraphView(QGraphicsView):
    """QtWidget containing a graph

    This widget is view associated with a graph. However, most of the
    interesting stuff happens in `GraphScene`.
    """

    wand_trace_finished = Signal(object)

    def __init__(self, graph_scene: GraphScene) -> None:
        self.graph_scene = graph_scene
        self.tool = GraphTool.Selection

        super().__init__(self.graph_scene)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        #self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag) # This has to be enabled based on keyboard shortcuts

        # We implement the rubberband logic ourselves. Note that there is also
        # the option to set `self.setDragMode(QGraphicsView.RubberBandDrag)`,
        # but that doesn't seem to play nicely with selection in the GraphScene,
        # presumably because it uses the coordinate system from this QGraphicsView
        # and not the one from the GraphScene...
        self.rubberband = QRubberBand(QRubberBand.Shape.Rectangle, self)

        self.wand_trace: Optional[WandTrace] = None
        self.wand_path: Optional[QGraphicsPathItem] = None

        self.centerOn(OFFSET_X,OFFSET_Y)

        self.sparkle_mode = False
        QShortcut(QKeySequence("Ctrl+Shift+Alt+S"), self).activated.connect(self._toggle_sparkles)

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
                self.wand_trace = WandTrace(pos)
                self.wand_path = QGraphicsPathItem()
                self.graph_scene.addItem(self.wand_path)
                pen = QPen(QColor(WAND_COLOR), WAND_WIDTH)
                self.wand_path.setPen(pen)
                path = QPainterPath()
                path.moveTo(pos)
                self.wand_path.setPath(path)
                self.wand_path.show()
                if self.sparkle_mode:
                    self._emit_sparkles(pos, 10)
        else:
            e.ignore()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self.tool == GraphTool.Selection:
            if self.rubberband.isVisible():
                self.rubberband.setGeometry(QRect(self._rubberband_start, e.pos()).normalized())
        elif self.tool == GraphTool.MagicWand:
            if self.wand_trace is not None:
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
                        self._emit_sparkles(ipos, 1)
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
            elif self.tool == GraphTool.MagicWand:
                if self.wand_trace is not None:
                    assert self.wand_path is not None
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
        print(current_zoom)
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

    def _emit_sparkles(self, pos: QPointF, mult: int) -> None:
        for _ in range(mult * SPARKLE_COUNT):
            angle = random.random() * 2 * math.pi
            speed = random.random() * (SPARKLE_MAX_SPEED - SPARKLE_MIN_SPEED) + SPARKLE_MIN_SPEED
            x = speed * math.cos(angle)
            y = speed * math.sin(angle)
            Sparkle(pos.x(), pos.y(), x, y, SPARKLE_FADE, self.graph_scene)


class RuleEditGraphView(GraphView):
    def __init__(self, parent_panel, graph_scene: GraphScene) -> None:
        super().__init__(graph_scene)
        self.parent_panel = parent_panel

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self.parent_panel.graph_view = self
        self.parent_panel.graph_scene = self.graph_scene
        super().mousePressEvent(e)


SPARKLE_COLOR = "#900090"
SPARKLE_COUNT = 1
SPARKLE_MAX_SPEED = 200.0
SPARKLE_MIN_SPEED = 100.0
SPARKLE_FADE = 20.0

class Sparkle(QGraphicsEllipseItem):
    def __init__(self, x: float, y: float, vx: float, vy: float, vo: float, scene: GraphScene) -> None:
        super().__init__(
            -0.05 * SCALE, -0.05 * SCALE, 0.1 * SCALE, 0.1 * SCALE
        )

        self.vx, self.vy, self.vo = vx, vy, vo
        self.prev_value = 0.0

        self.setPos(x, y)
        self.setZValue(PHASE_ITEM_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False)
        self.setBrush(QBrush(QColor(SPARKLE_COLOR)))
        self.setPen(QPen(Qt.PenStyle.NoPen))

        scene.addItem(self)

        self.timer = QTimeLine(1000)
        self.timer.valueChanged.connect(self._timer_step)
        self.timer.start()
        self.show()

    def _timer_step(self, value: float) -> None:
        dt = value - self.prev_value
        self.prev_value = value
        self.setX(self.x() + dt * self.vx)
        self.setY(self.y() + dt * self.vy)
        self.setOpacity(max(self.opacity() - dt * self.vo, 0.0))

        if value == 1.0:
            self.scene().removeItem(self)
