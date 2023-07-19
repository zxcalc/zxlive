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

from typing import Optional

import math
from PySide6.QtCore import QRect, QSize, QPointF, Signal, Qt, QRectF, QLineF
from PySide6.QtWidgets import QGraphicsView, QGraphicsPathItem, QRubberBand
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath, QTransform, QMouseEvent, QWheelEvent

from .graphscene import GraphScene, VItem

from dataclasses import dataclass

from .common import  GraphT, SCALE, OFFSET_X, OFFSET_Y


class GraphTool:
    Selection = 1
    MagicWand = 2


@dataclass
class WandTrace:
    start: QPointF
    end: QPointF
    hit: set[VItem]

    def __init__(self, start: QPointF) -> None:
        self.start = start
        self.hit = set()
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

    def set_graph(self, g: GraphT) -> None:
        self.graph_scene.set_graph(g)

    def update_graph(self, g: GraphT) -> None:
        self.graph_scene.update_graph(g)

    def mousePressEvent(self, e: QMouseEvent) -> None:
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
                self.wand_trace.end = pos
                path = self.wand_path.path()
                path.lineTo(pos)
                self.wand_path.setPath(path)
                items = self.graph_scene.items(pos)
                for item in items:
                    if item is not self.wand_path and isinstance(item, VItem):
                        self.wand_trace.hit.add(item)
                        break
        else:
            e.ignore()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            if self.tool == GraphTool.Selection:
                if self.rubberband.isVisible():
                    self.rubberband.hide()
                    self.graph_scene.clearSelection()
                    rect = self.rubberband.geometry()
                    for it in self.graph_scene.items(self.mapToScene(rect).boundingRect()):
                        if isinstance(it, VItem):
                            it.setSelected(True)
            elif self.tool == GraphTool.MagicWand:
                if self.wand_trace is not None:
                    assert self.wand_path is not None
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

        # Set Anchors
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        # Save the scene pos
        old_pos = self.mapToScene(event.position().toPoint())

        # Zoom
        ydelta = event.angleDelta().y()
        zoom_factor = 1.0
        if ydelta > 0:
            zoom_factor = 1 + ZOOMFACTOR * ydelta
        elif ydelta < 0:
            zoom_factor = 1/(1 - ZOOMFACTOR * ydelta)
        self.scale(zoom_factor, zoom_factor)

        # Get the new position
        new_pos = self.mapToScene(event.position().toPoint())

        # Move scene to old position
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        # First draw blank white background
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.setPen(QPen(Qt.NoPen))
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
        painter.setPen(QPen(QColor(240, 240, 240), 1, Qt.SolidLine))
        painter.drawLines(lines)
        painter.setPen(QPen(QColor(240, 240, 240), 2, Qt.SolidLine))
        painter.drawLines(thick_lines)
