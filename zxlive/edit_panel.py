from typing import Iterator

from PySide6.QtWidgets import QToolButton
from pyzx import EdgeType, VertexType
from pyzx.graph.base import BaseGraph, VT

from .base_panel import BasePanel, ToolbarSection
from .commands import AddEdge, AddNode, MoveNode
from .graphscene import EditGraphScene


class GraphEditPanel(BasePanel):
    """Panel for the edit mode of ZX live."""

    graph_scene: EditGraphScene

    _curr_ety: EdgeType = VertexType.Z
    _curr_vty: VertexType = EdgeType.SIMPLE

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = EditGraphScene(self._move_vert, self._add_vert, self._add_edge)
        super().__init__(graph, self.graph_scene)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        # Toolbar section for picking a vertex type
        select_z = QToolButton(self, text="Z Spider", checkable=True, checked=True)  # Selected by default
        select_x = QToolButton(self, text="X Spider", checkable=True)
        select_boundary = QToolButton(self, text="Boundary", checkable=True)
        select_z.clicked.connect(lambda _: self._select_vty(VertexType.Z))
        select_x.clicked.connect(lambda _: self._select_vty(VertexType.X))
        select_boundary.clicked.connect(lambda _: self._select_vty(VertexType.BOUNDARY))
        yield ToolbarSection(buttons=(select_z, select_x, select_boundary), exclusive=True)

        # Toolbar section for picking an edge type
        select_simple = QToolButton(self, text="Simple Edge", checkable=True, checked=True)  # Selected by default
        select_had = QToolButton(self, text="Had Edge", checkable=True)
        select_simple.clicked.connect(lambda _: self._select_ety(EdgeType.SIMPLE))
        select_had.clicked.connect(lambda _: self._select_ety(EdgeType.HADAMARD))
        yield ToolbarSection(buttons=(select_simple, select_had), exclusive=True)

        # Toolbar for global import/export/reset
        import_ = QToolButton(self, text="Import")
        export = QToolButton(self, text="Export")
        reset = QToolButton(self, text="Reset")
        yield ToolbarSection(buttons=(import_, export, reset))

    def _select_vty(self, vty: VertexType) -> None:
        self._curr_vty = vty

    def _select_ety(self, ety: EdgeType) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety

    def _add_vert(self, x: float, y: float) -> None:
        cmd = AddNode(self.graph_view, x, y, self._curr_vty)
        self.undo_stack.push(cmd)

    def _add_edge(self, u: VT, v: VT) -> None:
        cmd = AddEdge(self.graph_view, u, v, self._curr_ety)
        self.undo_stack.push(cmd)

    def _move_vert(self, v: VT, x: float, y: float):
        cmd = MoveNode(self.graph_view, v, x, y)
        self.undo_stack.push(cmd)

