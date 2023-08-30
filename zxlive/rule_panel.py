from __future__ import annotations

import copy
from enum import Enum
from typing import Iterator

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QInputDialog, QSplitter, QToolButton)
from pyzx import EdgeType, VertexType
from pyzx.utils import get_w_partner, vertex_is_w


from .base_panel import BasePanel, ToolbarSection
from .commands import (AddEdge, AddNode, AddWNode, ChangeEdgeColor,
                       ChangeNodeType, ChangePhase, CommandGroup, MoveNode,
                       SetGraph, UpdateGraph)
from .common import VT, GraphT, ToolType
from .dialogs import show_error_msg
from .edit_panel import (EDGES, VERTICES, create_list_widget, string_to_phase, toolbar_select_node_edge)
from .graphscene import EditGraphScene
from .graphview import GraphView


class Side(Enum):
    LEFT = 1
    RIGHT = 2

class RulePanel(BasePanel):
    """Panel for the Rule editor of ZX live."""

    graph_scene_left: EditGraphScene
    graph_scene_right: EditGraphScene
    start_derivation_signal = Signal(object)

    _curr_ety: EdgeType.Type
    _curr_vty: VertexType.Type


    def __init__(self, graph1: GraphT, graph2: GraphT) -> None:
        self.graph_scene_left = EditGraphScene()
        self.graph_scene_right = EditGraphScene()
        super().__init__(graph1, self.graph_scene_left)
        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE

        self.graph_view2 = GraphView(self.graph_scene_right)
        self.graph_view2.set_graph(graph2)
        self.splitter.addWidget(self.graph_view2)

        self.graph_scene_left.vertices_moved.connect(lambda *x: self._vert_moved(self.graph_view, *x))
        self.graph_scene_left.vertex_double_clicked.connect(lambda *x: self._vert_double_clicked(self.graph_view, *x))
        self.graph_scene_left.vertex_added.connect(lambda *x: self._add_vert(self.graph_view, *x))
        self.graph_scene_left.edge_added.connect(lambda *x: self._add_edge(self.graph_view, *x))

        self.graph_scene_right.vertices_moved.connect(lambda *x: self._vert_moved(self.graph_view2, *x))
        self.graph_scene_right.vertex_double_clicked.connect(lambda *x: self._vert_double_clicked(self.graph_view2, *x))
        self.graph_scene_right.vertex_added.connect(lambda *x: self._add_vert(self.graph_view2, *x))
        self.graph_scene_right.edge_added.connect(lambda *x: self._add_edge(self.graph_view2, *x))


        self.sidebar = QSplitter(self)
        self.sidebar.setOrientation(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.sidebar)
        self.vertex_list = create_list_widget(self, VERTICES, self._vty_clicked)
        self.edge_list = create_list_widget(self, EDGES, self._ety_clicked)
        self.sidebar.addWidget(self.vertex_list)
        self.sidebar.addWidget(self.edge_list)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield toolbar_select_node_edge(self)

        self.save_rule = QToolButton(self, text="Save rule")
        self.save_rule.clicked.connect(self.save_rule)
        yield ToolbarSection(self.save_rule)

    def _tool_clicked(self, tool: ToolType) -> None:
        self.graph_scene_left.curr_tool = tool
        self.graph_scene_right.curr_tool = tool

    def _vty_clicked(self, vty: VertexType.Type) -> None:
        self._curr_vty = vty
        selected1 = list(self.graph_scene_left.selected_vertices)
        selected2 = list(self.graph_scene_right.selected_vertices)
        if len(selected1) > 0 or len(selected2) > 0:
            cmd1 = ChangeNodeType(self.graph_view, selected1, vty)
            cmd2 = ChangeNodeType(self.graph_view2, selected2, vty)
            self.undo_stack.push(CommandGroup([cmd1, cmd2]))

    def _ety_clicked(self, ety: EdgeType.Type) -> None:
        self._curr_ety = ety
        self.graph_scene_left.curr_ety = ety
        self.graph_scene_right.curr_ety = ety
        selected1 = list(self.graph_scene_left.selected_edges)
        selected2 = list(self.graph_scene_right.selected_edges)
        if len(selected1) > 0 or len(selected2) > 0:
            cmd1 = ChangeEdgeColor(self.graph_view, selected1, ety)
            cmd2 = ChangeEdgeColor(self.graph_view2, selected2, ety)
            self.undo_stack.push(CommandGroup([cmd1, cmd2]))

    def _add_vert(self, graph_view: GraphView, x: float, y: float) -> None:
        self.undo_stack.push(
            AddWNode(graph_view, x, y) if self._curr_vty == VertexType.W_OUTPUT
            else AddNode(graph_view, x, y, self._curr_vty)
        )

    def _add_edge(self, graph_view: GraphView, u: VT, v: VT) -> None:
        graph = self.graph_view.graph_scene.g
        if vertex_is_w(graph.type(u)) and get_w_partner(graph, u) == v:
            return
        if graph.type(u) == VertexType.W_INPUT and len(graph.neighbors(u)) >= 2 or \
           graph.type(v) == VertexType.W_INPUT and len(graph.neighbors(v)) >= 2:
            return
        cmd = AddEdge(graph_view, u, v, self._curr_ety)
        self.undo_stack.push(cmd)

    def _vert_moved(self, graph_view: GraphView, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(graph_view, vs)
        self.undo_stack.push(cmd)

    def _vert_double_clicked(self, graph_view: GraphView, v: VT) -> None:
        graph = graph_view.graph_scene.g
        if graph.type(v) == VertexType.BOUNDARY:
            input_, ok = QInputDialog.getText(
                self, "Input Dialog", "Enter Qubit Index:"
            )
            try:
                graph.set_qubit(v, int(input_.strip()))
            except ValueError:
                show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1, 2)")
            return
        elif vertex_is_w(graph.type(v)):
            return

        input_, ok = QInputDialog.getText(
            self, "Input Dialog", "Enter Desired Phase Value:"
        )
        if not ok:
            return
        try:
            new_phase = string_to_phase(input_)
        except ValueError:
            show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1/2, 2)")
            return
        cmd = ChangePhase(graph_view, v, new_phase)
        self.undo_stack.push(cmd)

    def paste_graph(self, graph: GraphT) -> None:
        if graph is None: return
        new_g = copy.deepcopy(self.graph_scene_left.g)
        new_verts, new_edges = new_g.merge(graph.translate(0.5,0.5))
        cmd = UpdateGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd)
        self.graph_scene_left.select_vertices(new_verts)

    def delete_selection(self) -> None:
        selection = list(self.graph_scene_left.selected_vertices)
        selected_edges = list(self.graph_scene_left.selected_edges)
        rem_vertices = selection.copy()
        for v in selection:
            if vertex_is_w(self.graph_scene_left.g.type(v)):
                rem_vertices.append(get_w_partner(self.graph_scene_left.g, v))
        if not rem_vertices and not selected_edges: return
        new_g = copy.deepcopy(self.graph_scene_left.g)
        self.graph_scene_left.clearSelection()
        new_g.remove_edges(selected_edges)
        new_g.remove_vertices(list(set(rem_vertices)))
        cmd = SetGraph(self.graph_view,new_g) if len(set(rem_vertices)) > 128 \
            else UpdateGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)

    def save_rule(self) -> None:
        pass
