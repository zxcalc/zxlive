from fractions import Fraction
from typing import Iterator

from PySide6.QtWidgets import QToolButton, QInputDialog
from pyzx import EdgeType, VertexType
from pyzx.graph.base import BaseGraph, VT

from .base_panel import BasePanel, ToolbarSection
from .commands import AddEdge, AddNode, MoveNode, SetGraph, ChangePhase, ChangeNodeColor
from .dialogs import import_diagram_dialog, export_diagram_dialog, show_error_msg
from .graphscene import EditGraphScene


class GraphEditPanel(BasePanel):
    """Panel for the edit mode of ZX live."""

    graph_scene: EditGraphScene

    _curr_ety: EdgeType = VertexType.Z
    _curr_vty: VertexType = EdgeType.SIMPLE

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = EditGraphScene(self._vert_moved, self._vert_double_clicked,
                                          self._add_vert, self._add_edge)
        super().__init__(graph, self.graph_scene)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        # Toolbar section for picking a vertex type
        select_z = QToolButton(self, text="Z Spider", checkable=True, checked=True)  # Selected by default
        select_x = QToolButton(self, text="X Spider", checkable=True)
        select_boundary = QToolButton(self, text="Boundary", checkable=True)
        select_z.clicked.connect(lambda: self._vty_clicked(VertexType.Z))
        select_x.clicked.connect(lambda: self._vty_clicked(VertexType.X))
        select_boundary.clicked.connect(lambda: self._vty_clicked(VertexType.BOUNDARY))
        yield ToolbarSection(select_z, select_x, select_boundary, exclusive=True)

        # Toolbar section for picking an edge type
        select_simple = QToolButton(self, text="Simple Edge", checkable=True, checked=True)  # Selected by default
        select_had = QToolButton(self, text="Had Edge", checkable=True)
        select_simple.clicked.connect(lambda _: self._ety_clicked(EdgeType.SIMPLE))
        select_had.clicked.connect(lambda _: self._ety_clicked(EdgeType.HADAMARD))
        yield ToolbarSection(select_simple, select_had, exclusive=True)

        # Toolbar for global import/export/reset
        import_ = QToolButton(self, text="Import")
        export = QToolButton(self, text="Export")
        reset = QToolButton(self, text="Reset")
        import_.clicked.connect(self._import_diagram_clicked)
        export.clicked.connect(self._export_diagram_clicked)
        reset.clicked.connect(self._reset_clicked)
        yield ToolbarSection(import_, export, reset)

    def _vty_clicked(self, vty: VertexType) -> None:
        self._curr_vty = vty
        selected = list(self.graph_scene.selected_vertices)
        if len(selected) > 0:
            cmd = ChangeNodeColor(self.graph_view, selected, vty)
            self.undo_stack.push(cmd)

    def _ety_clicked(self, ety: EdgeType) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety

    def _add_vert(self, x: float, y: float) -> None:
        cmd = AddNode(self.graph_view, x, y, self._curr_vty)
        self.undo_stack.push(cmd)

    def _add_edge(self, u: VT, v: VT) -> None:
        cmd = AddEdge(self.graph_view, u, v, self._curr_ety)
        self.undo_stack.push(cmd)

    def _vert_moved(self, v: VT, x: float, y: float) -> None:
        cmd = MoveNode(self.graph_view, v, x, y)
        self.undo_stack.push(cmd)

    def _vert_double_clicked(self, v: VT) -> None:
        if self.graph.type(v) == VertexType.BOUNDARY:
            return

        input_, ok = QInputDialog.getText(
            self, "Input Dialog", "Enter Desired Phase Value:"
        )
        if not ok:
            return
        try:
            new_phase = Fraction(input_)
        except ValueError:
            show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1/2, 2)")
            return
        cmd = ChangePhase(self.graph_view, v, new_phase)
        self.undo_stack.push(cmd)

    def _reset_clicked(self) -> None:
        while self.undo_stack.canUndo():
            self.undo_stack.undo()

    def _import_diagram_clicked(self) -> None:
        g = import_diagram_dialog(self)
        if g is not None:
            cmd = SetGraph(self.graph_view, g)
            self.undo_stack.push(cmd)

    def _export_diagram_clicked(self) -> None:
        export_diagram_dialog(self.graph, self)

