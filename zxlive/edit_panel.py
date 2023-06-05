from typing import Iterator

from PySide6.QtCore import QFile, QIODevice, QTextStream
from PySide6.QtWidgets import QToolButton, QFileDialog, QMessageBox
from pyzx import EdgeType, VertexType
from pyzx.graph.base import BaseGraph, VT

import pyzx as zx

from .base_panel import BasePanel, ToolbarSection
from .commands import AddEdge, AddNode, MoveNode, SetGraph
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
        import_.clicked.connect(self._import_diagram_clicked)
        export.clicked.connect(self._export_diagram_clicked)
        reset.clicked.connect(self._reset_clicked)
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

    def _reset_clicked(self) -> None:
        while self.undo_stack.canUndo():
            self.undo_stack.undo()

    def _import_diagram_clicked(self) -> None:
        supported_formats = [
            ("QGraph (*.zxg)", "zxg"),
            ("QASM (*.qasm)", "qasm"),
            ("TikZ (*.tikz)", "tikz"),
            ("JSON (*.json)", "json"),
        ]
        file_path, selected_format = QFileDialog.getOpenFileName(
            parent=self,
            caption="Open File",
            filter=";;".join([f[0] for f in supported_formats]),
        )

        file = QFile(file_path)
        if not file.open(QIODevice.ReadOnly | QIODevice.Text):
            return
        input = QTextStream(file)

        g = self.graph_view.graph_scene.g
        if selected_format == "QGraph (*.zxg)":
            try:
                new_g = zx.Graph().from_json(input.readAll())
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Failed to import QGraph file")
                msg.setInformativeText(str(e))
                msg.exec_()
                self.graph_view.set_graph(g)
                return
            cmd = SetGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
        elif selected_format == "QASM (*.qasm)":
            try:
                new_g = zx.Circuit.from_qasm(input.readAll()).to_graph()
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Failed to import QASM file")
                msg.setInformativeText(str(e))
                msg.exec_()
                self.graph_view.set_graph(g)
                return
            cmd = SetGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
        elif selected_format == "TikZ (*.tikz)":
            try:
                new_g = zx.Graph().from_tikz(input.readAll())
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Failed to import TikZ file")
                msg.setInformativeText(str(e))
                msg.exec_()
                self.graph_view.set_graph(g)
                return
            cmd = SetGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
        elif selected_format == "JSON (*.json)":
            try:
                new_g = zx.Graph().from_json(input.readAll())
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Failed to import JSON file")
                msg.setInformativeText(str(e))
                msg.exec_()
                self.graph_view.set_graph(g)
                return
            cmd = SetGraph(self.graph_view, g)
            self.undo_stack.push(cmd)

        file.close()

    def _export_diagram_clicked(self) -> None:
        supported_formats = [
            ("QGraph (*.zxg)", "zxg"),
            ("QASM (*.qasm)", "qasm"),
            ("TikZ (*.tikz)", "tikz"),
            ("JSON (*.json)", "json"),
        ]
        file_path, selected_format = QFileDialog.getSaveFileName(
            parent=self,
            caption="Save File",
            filter=";;".join([f[0] for f in supported_formats]),
        )

        # add file extension if not already there
        file_extension = supported_formats[
            [format_name for format_name, _ in supported_formats].index(
                selected_format
            )
        ][1]
        if file_extension == file_path.split(".")[-1]:
            file = QFile(file_path)
        else:
            file = QFile(file_path + "." + file_extension)

        if not file.open(QIODevice.WriteOnly | QIODevice.Text):
            return
        out = QTextStream(file)

        g = self.graph_view.graph_scene.g
        if selected_format == "QGraph (*.zxg)":
            out << g.to_json()
        elif selected_format == "QASM (*.qasm)":
            try:
                circuit = zx.extract_circuit(g)
            except Exception as e:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Failed to convert the ZX-diagram to quantum circuit")
                msg.setInformativeText(str(e))
                msg.exec_()
                return
            out << circuit.to_qasm()
        elif selected_format == "TikZ (*.tikz)":
            out << g.to_tikz()
        elif selected_format == "JSON (*.json)":
            out << g.to_json()

        file.close()

