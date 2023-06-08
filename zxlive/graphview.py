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

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from pyzx.graph.base import BaseGraph, VT, ET
from .graphscene import GraphScene, VItem


class GraphView(QGraphicsView):
    """QtWidget containing a graph

    This widget is view associated with a graph. However, most of the
    interesting stuff happens in `GraphScene`.
    """

    def __init__(self, graph_scene: GraphScene) -> None:
        self.graph_scene = graph_scene
        super().__init__(self.graph_scene)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # We implement the rubberband logic ourselves. Note that there is also
        # the option to set `self.setDragMode(QGraphicsView.RubberBandDrag)`,
        # but that doesn't seem to play nicely with selection in the GraphScene,
        # presumably because it uses the coordinate system from this QGraphicsView
        # and not the one from the GraphScene...
        self.rubberband = QRubberBand(QRubberBand.Rectangle, self)

    def set_graph(self, g: BaseGraph[VT, ET]) -> None:
        self.graph_scene.set_graph(g)
        self.centerOn(0, 0)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        super().mousePressEvent(e)
        if e.button() == Qt.LeftButton and all(not isinstance(it, VItem) for it in self.graph_scene.items(self.mapToScene(e.pos()), deviceTransform=QTransform())):
            self._rubberband_start = e.pos()
            self.rubberband.setGeometry(QRect(self._rubberband_start, QSize()))
            self.rubberband.show()
        else:
            e.ignore()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self.rubberband.isVisible():
            self.rubberband.setGeometry(QRect(self._rubberband_start, e.pos()).normalized())
        else:
            e.ignore()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton and self.rubberband.isVisible():
            self.rubberband.hide()
            self.graph_scene.clearSelection()
            rect = self.rubberband.geometry()
            for it in self.graph_scene.items(self.mapToScene(rect).boundingRect()):
                if isinstance(it, VItem):
                    it.setSelected(True)
        else:
            e.ignore()
