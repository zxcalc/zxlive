from __future__ import annotations

import copy
from typing import Iterator

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QToolButton)
from pyzx import EdgeType, VertexType
from pyzx.circuit.qasmparser import QASMParser
from pyzx.symbolic import Poly

from .base_panel import ToolbarSection
from .commands import UpdateGraph
from .common import GraphT
from .dialogs import show_error_msg, create_circuit_dialog
from .editor_base_panel import EditorBasePanel
from .graphscene import EditGraphScene
from .graphview import GraphView


class GraphEditPanel(EditorBasePanel):
    """Panel for the edit mode of ZXLive."""

    graph_scene: EditGraphScene
    start_derivation_signal = Signal(object)

    _curr_ety: EdgeType.Type
    _curr_vty: VertexType.Type

    def __init__(self, graph: GraphT, *actions: QAction) -> None:
        super().__init__(*actions)
        self.graph_scene = EditGraphScene()
        self.graph_scene.vertices_moved.connect(self.vert_moved)
        self.graph_scene.vertex_double_clicked.connect(self.vert_double_clicked)
        self.graph_scene.vertex_added.connect(self.add_vert)
        self.graph_scene.edge_added.connect(self.add_edge)

        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE

        self.graph_view = GraphView(self.graph_scene)
        self.splitter.addWidget(self.graph_view)
        self.graph_view.set_graph(graph)

        self.create_side_bar()
        self.splitter.addWidget(self.sidebar)


    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield from super()._toolbar_sections()

        self.input_circuit = QToolButton(self)
        self.input_circuit.setText("Input Circuit")
        self.input_circuit.clicked.connect(self._input_circuit)
        yield ToolbarSection(self.input_circuit)

        self.start_derivation = QToolButton(self)
        self.start_derivation.setText("Start Derivation")
        self.start_derivation.clicked.connect(self._start_derivation)
        yield ToolbarSection(self.start_derivation)


    def _start_derivation(self) -> None:
        if not self.graph_scene.g.is_well_formed():
            show_error_msg("Graph is not well-formed")
            return
        new_g: GraphT = copy.deepcopy(self.graph_scene.g)
        for vert in new_g.vertices():
            phase = new_g.phase(vert)
            if isinstance(phase, Poly):
                phase.freeze()
        self.start_derivation_signal.emit(new_g)

    def _input_circuit(self) -> None:
        qasm = create_circuit_dialog(self)
        if qasm is not None:
            new_g = copy.deepcopy(self.graph_scene.g)
            try:
                circ = QASMParser().parse(qasm, strict=False).to_graph()
            except TypeError as err:
                show_error_msg("Invalid circuit", str(err))
                return
            except Exception:
                show_error_msg("Invalid circuit", "Couldn't parse QASM code")
                return

            new_verts, new_edges = new_g.merge(circ)
            cmd = UpdateGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
            self.graph_scene.select_vertices(new_verts)

