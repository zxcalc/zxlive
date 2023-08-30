from __future__ import annotations

import copy
from typing import Iterator

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QSplitter, QToolButton)
from pyzx import EdgeType, VertexType
from pyzx.utils import get_w_partner, vertex_is_w


from .base_panel import BasePanel, ToolbarSection
from .commands import (ChangeEdgeColor, ChangeNodeType, SetGraph, UpdateGraph)
from .common import GraphT, ToolType
from .edit_panel import (EDGES, VERTICES, add_edge, add_vert, create_list_widget, toolbar_select_node_edge, vert_double_clicked, vert_moved)
from .graphscene import EditGraphScene
from .graphview import RuleEditGraphView


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
        super().__init__()

        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE

        self.graph_view_left = RuleEditGraphView(self, self.graph_scene_left)
        self.graph_view_left.set_graph(graph1)
        self.splitter.addWidget(self.graph_view_left)
        self.graph_view = self.graph_view_left
        self.graph_scene = self.graph_scene_left

        self.graph_view_right = RuleEditGraphView(self, self.graph_scene_right)
        self.graph_view_right.set_graph(graph2)
        self.splitter.addWidget(self.graph_view_right)

        self.graph_scene_left.vertices_moved.connect(lambda *x: self.push_cmd_to_undo_stack(vert_moved, *x))
        self.graph_scene_left.vertex_double_clicked.connect(lambda *x: self.push_cmd_to_undo_stack(vert_double_clicked, *x))
        self.graph_scene_left.vertex_added.connect(lambda *x: self.push_cmd_to_undo_stack(add_vert, *x))
        self.graph_scene_left.edge_added.connect(lambda *x: self.push_cmd_to_undo_stack(add_edge, *x))

        self.graph_scene_right.vertices_moved.connect(lambda *x: self.push_cmd_to_undo_stack(vert_moved, *x))
        self.graph_scene_right.vertex_double_clicked.connect(lambda *x: self.push_cmd_to_undo_stack(vert_double_clicked, *x))
        self.graph_scene_right.vertex_added.connect(lambda *x: self.push_cmd_to_undo_stack(add_vert, *x))
        self.graph_scene_right.edge_added.connect(lambda *x: self.push_cmd_to_undo_stack(add_edge, *x))

        self.sidebar = QSplitter(self)
        self.sidebar.setOrientation(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.sidebar)
        self.vertex_list = create_list_widget(self, VERTICES, self._vty_clicked)
        self.edge_list = create_list_widget(self, EDGES, self._ety_clicked)
        self.sidebar.addWidget(self.vertex_list)
        self.sidebar.addWidget(self.edge_list)

    def push_cmd_to_undo_stack(self, command_function, *args) -> None:
        cmd = command_function(self, self.graph_view, *args)
        if cmd is not None:
            self.undo_stack.push(cmd)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield toolbar_select_node_edge(self)

        self.save_rule_button = QToolButton(self, text="Save rule")
        self.save_rule_button.clicked.connect(self.save_rule)
        yield ToolbarSection(self.save_rule_button)

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
