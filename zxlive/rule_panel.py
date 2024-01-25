from __future__ import annotations

from typing import Iterator

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLineEdit
from pyzx import EdgeType, VertexType
from pyzx.symbolic import Poly


from .base_panel import ToolbarSection
from .common import GraphT, ToolType
from .custom_rule import CustomRule
from .editor_base_panel import EditorBasePanel
from .graphscene import EditGraphScene
from .graphview import RuleEditGraphView


class RulePanel(EditorBasePanel):
    """Panel for the Rule editor of ZXLive."""

    graph_scene_left: EditGraphScene
    graph_scene_right: EditGraphScene
    start_derivation_signal = Signal(object)

    _curr_ety: EdgeType.Type
    _curr_vty: VertexType.Type


    def __init__(self, graph1: GraphT, graph2: GraphT, name: str, description: str, *actions: QAction) -> None:
        self.name = name
        self.description = description
        super().__init__(*actions)
        self.graph_scene_left = EditGraphScene()
        self.graph_scene_right = EditGraphScene()

        self.graph_view_left = RuleEditGraphView(self, self.graph_scene_left)
        self.graph_view_left.set_graph(graph1)
        self.splitter.addWidget(self.graph_view_left)
        self.graph_view = self.graph_view_left
        self.graph_scene = self.graph_scene_left

        self.graph_view_right = RuleEditGraphView(self, self.graph_scene_right)
        self.graph_view_right.set_graph(graph2)
        self.splitter.addWidget(self.graph_view_right)

        self.graph_scene_left.vertices_moved.connect(self.vert_moved)
        self.graph_scene_left.vertex_double_clicked.connect(self.vert_double_clicked)
        self.graph_scene_left.vertex_added.connect(self.add_vert)
        self.graph_scene_left.edge_added.connect(self.add_edge)

        self.graph_scene_right.vertices_moved.connect(self.vert_moved)
        self.graph_scene_right.vertex_double_clicked.connect(self.vert_double_clicked)
        self.graph_scene_right.vertex_added.connect(self.add_vert)
        self.graph_scene_right.edge_added.connect(self.add_edge)

        self.create_side_bar()
        self.splitter.addWidget(self.sidebar)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield from super()._toolbar_sections()

        self.name_field = QLineEdit(self)
        self.name_field.setPlaceholderText("Rule name")
        self.name_field.setText(self.name)
        self.name_field.setMaximumWidth(150)
        self.description_field = QLineEdit(self)
        self.description_field.setPlaceholderText("Description")
        self.description_field.setText(self.description)
        self.description_field.setMaximumWidth(400)
        yield ToolbarSection(self.name_field, self.description_field)

    def _tool_clicked(self, tool: ToolType) -> None:
        self.graph_scene_left.curr_tool = tool
        self.graph_scene_right.curr_tool = tool

    def get_rule(self) -> CustomRule:
        return CustomRule(self.graph_scene_left.g,
                          self.graph_scene_right.g,
                          self.name_field.text(),
                          self.description_field.text())
    
    def shutdown(self):
        if hasattr(self, 'graph_scene'):
            self.graph_scene.shutdown() 