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
from PySide2.QtCore import Qt, QPointF
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from typing import Optional, List, Set, Tuple

from pyzx.graph.base import BaseGraph, VT, ET, VertexType, EdgeType
from pyzx.utils import phase_to_s

SCALE = 60.0
ZX_GREEN = '#ccffcc'
ZX_RED = '#ff8888'


class VItem(QGraphicsEllipseItem):
    def __init__(self, g: BaseGraph[VT,ET], v: VT):
        super().__init__(-0.1 * SCALE, -0.1 * SCALE, 0.2 * SCALE, 0.2 * SCALE)
        self.g = g
        self.v = v
        self.setPos(g.row(v) * SCALE, g.qubit(v) * SCALE)
        self.setZValue(1)
        self.adj_items: Set[EItem] = set()
        self.phase_item: Optional[PhaseItem] = None

        pen = QPen()
        pen.setWidthF(1.5)
        pen.setColor(QColor('black'))
        self.setPen(pen)

        t = g.type(v)
        if t == VertexType.Z:
            self.setBrush(QBrush(QColor(ZX_GREEN)))
        elif t == VertexType.X:
            self.setBrush(QBrush(QColor(ZX_RED)))
        else:
            self.setBrush(QBrush(QColor('#000000')))

    def refresh(self) -> None:
        if self.phase_item:
            self.phase_item.refresh()

        for e_item in self.adj_items:
            e_item.refresh()

class PhaseItem(QGraphicsTextItem):
    def __init__(self, v_item: VItem, phase: str):
        super().__init__(phase)
        self.setDefaultTextColor(QColor('blue'))
        self.setFont(QFont('monospace'))
        self.phase = phase
        self.v_item = v_item
        self.setZValue(2)
        self.refresh()

    def refresh(self) -> None:
        p = self.v_item.pos()
        self.setPos(p.x(), p.y() - 0.5*SCALE)

class EItem(QGraphicsPathItem):
    def __init__(self, g: BaseGraph[VT,ET], e: ET, s_item: VItem, t_item: VItem):
        super().__init__()
        self.setZValue(0)
        self.s_item = s_item
        self.t_item = t_item
        s_item.adj_items.add(self)
        t_item.adj_items.add(self)
        pen = QPen()
        pen.setWidthF(1.5)
        if g.edge_type(e) == EdgeType.HADAMARD:
            pen.setColor(QColor('#0077ff'))
            pen.setDashPattern([4.0, 2.0])
        else:
            pen.setColor(QColor('#000000'))
        self.setPen(QPen(pen))

        self.refresh()

    def refresh(self) -> None:
        path = QPainterPath()
        path.moveTo(self.s_item.pos())
        path.lineTo(self.t_item.pos())
        self.setPath(path)


class GraphScene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.undo_stack = QUndoStack(self)

        self.setSceneRect(-100, -100, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(255,255,255)))
        self.drag_start = QPointF(0,0)
        self.drag_items: List[Tuple[QGraphicsItem, QPointF]] = []

    def set_graph(self, g: BaseGraph[VT,ET]) -> None:
        self.g = g
        self.clear()
        self.add_items()
        self.invalidate()

    def add_items(self) -> None:
        v_items = {}
        for v in self.g.vertices():
            vi = VItem(self.g, v)
            v_items[v] = vi
            self.addItem(vi)
            phase = self.g.phase(v)
            if phase != 0:
                vi.phase_item = PhaseItem(vi, phase_to_s(phase))
                self.addItem(vi.phase_item)

        for e in self.g.edges():
            s,t = self.g.edge_st(e)
            self.addItem(EItem(self.g, e, v_items[s], v_items[t]))



    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(e)
        
        self.drag_start = e.scenePos()

        # TODO implement selecting/moving multiple items
        for it in self.items(e.scenePos(), deviceTransform=QTransform()):
            if it and isinstance(it, VItem):
                self.drag_items = [(it, it.scenePos())]
                break

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        p = e.scenePos()
        grid_size = SCALE / 8
        dx = round((p.x() - self.drag_start.x())/grid_size) * grid_size
        dy = round((p.y() - self.drag_start.y())/grid_size) * grid_size

        # move the items that have been dragged
        for it,pos in self.drag_items:
            it.setPos(QPointF(pos.x() + dx, pos.y() + dy))
            if isinstance(it, VItem): it.refresh()

    def mouseReleaseEvent(self, _: QGraphicsSceneMouseEvent) -> None:
        self.drag_items = []

