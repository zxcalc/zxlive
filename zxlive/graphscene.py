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

from enum import Enum
from typing import Optional, Iterator, Iterable, Any, Dict

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QBrush, QColor, QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent

from pyzx.graph.base import VertexType, EdgeType

from .common import VT, ET, GraphT, SCALE
from .vitem import VItem, EITEM_Z, VITEM_SELECTED_Z, VITEM_UNSELECTED_Z, PHASE_ITEM_Z
from .eitem import EItem, EDragItem


class GraphScene(QGraphicsScene):
    """The main class responsible for drawing/editing graphs"""

    g: GraphT

    # Signals to handle double-clicking and moving of vertices.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_double_clicked = Signal(object)  # Actual type: VT
    vertices_moved = Signal(object)  # Actual type: list[tuple[VT, float, float]]

    # Triggers when a vertex is dragged onto or off of another vertex
    # Actual types: DragState, VT, VT
    vertex_dragged = Signal(object, object, object)

    # Triggers when a vertex is dropped onto another vertex. Actual types: VT, VT
    vertex_dropped_onto = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(-100, -100, 4000, 4000)
        self.setBackgroundBrush(QBrush(QColor(255, 255, 255)))
        self.vertex_map: Dict[VT, VItem] = {}
        self.edge_map: Dict[ET, EItem] = {}

    @property
    def selected_vertices(self) -> Iterator[VT]:
        """An iterator over all currently selected vertices."""
        return (it.v for it in self.selectedItems() if isinstance(it, VItem))

    @property
    def selected_edges(self) -> Iterator[ET]:
        return (it.e for it in self.selectedItems() if isinstance(it, EItem))

    def select_vertices(self, vs: Iterable[VT]) -> None:
        """Selects the given collection of vertices."""
        self.clearSelection()
        vs = set(vs)
        for it in self.items():
            if isinstance(it, VItem) and it.v in vs:
                it.setSelected(True)
                vs.remove(it.v)

    def set_graph(self, g: GraphT) -> None:
        """Set the PyZX graph for the scene

        If the scene already contains a graph, it will be replaced."""

        self.g = g
        # Stop all animations
        for it in self.items():
            if isinstance(it, VItem):
                for anim in it.active_animations.copy():
                    anim.stop()
        self.clear()
        self.add_items()
        self.invalidate()

    def add_items(self) -> None:
        """Add QGraphicsItem's for all vertices and edges in the graph"""
        self.vertex_map = {}
        for v in self.g.vertices():
            vi = VItem(self, v)
            self.vertex_map[v] = vi
            self.addItem(vi)  # add the vertex to the scene
            self.addItem(vi.phase_item)  # add the phase label to the scene
        
        self.edge_map = {}
        for e in self.g.edges():
            s, t = self.g.edge_st(e)
            ei = EItem(self.g, e, self.vertex_map[s], self.vertex_map[t])
            self.addItem(ei)
            self.addItem(ei.selection_node)
            self.edge_map[e] = ei

    def select_all(self) -> None:
        """Selects all vertices and edges in the scene."""
        for it in self.items():
            it.setSelected(True)

    def get_vitem(self, v: VT) -> VItem:
        """Returns the VItem corresponding to a vertex in the pyzx graph."""
        # TODO: We should save those in a dict
        return next(it for it in self.items() if isinstance(it, VItem) and it.v == v)


class EditGraphScene(GraphScene):
    """A graph scene tracking additional mouse events for graph editing."""

    # Signals to handle addition of vertices and edges.
    # Note that we have to set the argument types to `object`,
    # otherwise it doesn't work for some reason...
    vertex_added = Signal(object, object)  # Actual types: float, float
    edge_added = Signal(object, object)  # Actual types: VT, VT

    # Currently selected edge type for preview when dragging
    # to add a new edge
    curr_ety: EdgeType.Type

    # The vertex a right mouse button drag was initiated on
    _right_drag: Optional[EDragItem]

    def __init__(self) -> None:
        super().__init__()
        self.curr_ety = EdgeType.SIMPLE
        self._right_drag = None

    def mousePressEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        # Right-press on a vertex means the start of a drag for edge adding
        super().mousePressEvent(e)
        if e.button() == Qt.MouseButton.RightButton:
            if self.items(e.scenePos(), deviceTransform=QTransform()):
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    if isinstance(it, VItem):
                        self._right_drag = EDragItem(self.g, self.curr_ety, it, e.scenePos())
                        self.addItem(self._right_drag)
        else:
            e.ignore()

    def mouseMoveEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(e)
        if self._right_drag:
            self._right_drag.mouse_pos = e.scenePos()
            self._right_drag.refresh()
        else:
            e.ignore()

    def mouseReleaseEvent(self, e: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.RightButton:
            # It's either a drag to add an edge
            if self._right_drag:
                self.removeItem(self._right_drag)
                for it in self.items(e.scenePos(), deviceTransform=QTransform()):
                    # TODO: Think about if we want to allow self loops here?
                    #  For example, if had edge is selected this would mean that
                    #  right clicking adds pi to the phase...
                    if isinstance(it, VItem) and it != self._right_drag.start:
                        self.edge_added.emit(self._right_drag.start.v, it.v)
                self._right_drag = None
            # Or a click on a free spot to add a new vertex
            else:
                p = e.scenePos()
                self.vertex_added.emit(p.x() / SCALE, p.y() / SCALE)
        else:
            e.ignore()