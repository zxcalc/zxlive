import copy
from fractions import Fraction
from typing import Iterator

from PySide6.QtWidgets import QToolButton, QInputDialog
from PySide6.QtGui import QShortcut
from pyzx import EdgeType, VertexType
from pyzx.graph.base import BaseGraph, VT

from .base_panel import BasePanel, ToolbarSection
from .commands import AddEdge, AddNode, MoveNode, SetGraph, ChangePhase, ChangeNodeColor
from .graphscene import EditGraphScene


class GraphEditPanel(BasePanel):
    """Panel for the edit mode of ZX live."""

    graph_scene: EditGraphScene

    _curr_ety: EdgeType
    _curr_vty: VertexType

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = EditGraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        self.graph_scene.vertex_double_clicked.connect(self._vert_double_clicked)
        self.graph_scene.vertex_added.connect(self._add_vert)
        self.graph_scene.edge_added.connect(self._add_edge)

        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE
        # Currently the copied part is stored internally, and is not made available to the clipboard.
        # We could do this by using pyperclip.
        self.copied_graph: Optional[BaseGraph[VT,ET]] = None
        super().__init__(graph, self.graph_scene)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        # Toolbar section for picking a vertex type
        self.select_z = QToolButton(self, text="Z Spider", checkable=True, checked=True)  # Selected by default
        self.select_x = QToolButton(self, text="X Spider", checkable=True)
        self.select_boundary = QToolButton(self, text="Boundary", checkable=True)
        self.select_z.clicked.connect(lambda: self._vty_clicked(VertexType.Z))
        self.select_x.clicked.connect(lambda: self._vty_clicked(VertexType.X))
        self.select_boundary.clicked.connect(lambda: self._vty_clicked(VertexType.BOUNDARY))
        yield ToolbarSection(self.select_z, self.select_x, self.select_boundary, exclusive=True)
        QShortcut("x",self).activated.connect(self.cycle_vertex_type_selection)

        # Toolbar section for picking an edge type
        self.select_simple = QToolButton(self, text="Simple Edge", checkable=True, checked=True)  # Selected by default
        self.select_had = QToolButton(self, text="Had Edge", checkable=True)
        self.select_simple.clicked.connect(lambda _: self._ety_clicked(EdgeType.SIMPLE))
        self.select_had.clicked.connect(lambda _: self._ety_clicked(EdgeType.HADAMARD))
        yield ToolbarSection(self.select_simple, self.select_had, exclusive=True)
        QShortcut("e",self).activated.connect(self.cycle_edge_type_selection)

        reset = QToolButton(self, text="Reset")
        reset.clicked.connect(self._reset_clicked)
        yield ToolbarSection(reset)

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

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
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

    def cycle_vertex_type_selection(self):
        if self.select_z.isChecked():
            self.select_x.setChecked(True)
            self._curr_vty = VertexType.X
        elif self.select_x.isChecked():
            self.select_boundary.setChecked(True)
            self._curr_vty = VertexType.BOUNDARY
        elif self.select_boundary.isChecked():
            self.select_z.setChecked(True)
            self._curr_vty = VertexType.Z
        else:
            raise ValueError("Something is wrong with the state of the vertex type selectors")

    def cycle_edge_type_selection(self):
        if self.select_simple.isChecked():
            self.select_had.setChecked(True)
            self._curr_ety = EdgeType.HADAMARD
        elif self.select_had.isChecked():
            self.select_simple.setChecked(True)
            self._curr_ety = EdgeType.SIMPLE
        else:
            raise ValueError("Something is wrong with the state of the edge type selectors")

    def save_graph_copy(self):
        selection = list(self.graph_scene.selected_vertices)
        self.copied_graph = self.graph_scene.g.subgraph_from_vertices(selection)

    def paste_graph(self):
        if self.copied_graph is None: return
        new_g = copy.deepcopy(self.graph_scene.g)
        new_verts, new_edges = new_g.merge(self.copied_graph.translate(0.5,0.5))
        cmd = SetGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)
        self.graph_scene.select_vertices(new_verts)

    def delete_selection(self):
        selection = list(self.graph_scene.selected_vertices)
        if not selection: return
        new_g = copy.deepcopy(self.graph_scene.g)
        self.graph_scene.clearSelection()
        new_g.remove_vertices(selection)
        cmd = SetGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)