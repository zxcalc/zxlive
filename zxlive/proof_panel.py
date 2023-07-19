import copy
from typing import Iterator

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget, QToolButton, QHBoxLayout
from pyzx import VertexType, basicrules

from .common import VT, GraphT
from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph
from .graphscene import GraphScene
from .graphview import GraphTool
from .vitem import VItem
from . import proof_actions
from . import animations as anims


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: GraphT) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        self.graph_scene.vertex_double_clicked.connect(self._vert_double_clicked)

        super().__init__(graph, self.graph_scene)

        self.init_action_groups()

        self.graph_view.wand_trace_finished.connect(self._magic_slice)



    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        self.selection = QToolButton(self, text="Selection", checkable=True, checked=True)
        self.magic_wand = QToolButton(self, text="Magic Wand", checkable=True)

        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        self.selection.clicked.connect(self._selection_clicked)

        yield ToolbarSection(self.selection, self.magic_wand, exclusive=True)

    def init_action_groups(self):
        self.action_groups = [proof_actions.actions_basic.copy()]
        for group in reversed(self.action_groups):
            hlayout = QHBoxLayout()
            group.init_buttons(self)
            for action in group.actions:
                hlayout.addWidget(action.button)
            hlayout.addStretch()

            widget = QWidget()
            widget.setLayout(hlayout)
            self.layout().insertWidget(1,widget)

    def parse_selection(self):
        selection = list(self.graph_scene.selected_vertices)
        g = self.graph_scene.g
        edges = []
        for e in g.edges():
            s,t = g.edge_st(e)
            if s in selection and t in selection:
                edges.append(e)

        return selection, edges

    def update_on_selection(self):
        selection, edges = self.parse_selection()
        g = self.graph_scene.g

        for group in self.action_groups:
            group.update_active(g,selection,edges)

    def _selection_clicked(self):
        self.graph_view.tool = GraphTool.Selection

    def _magic_wand_clicked(self):
        self.graph_view.tool = GraphTool.MagicWand

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
        self.undo_stack.push(cmd)

    def _magic_slice(self, trace):
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return
        item = filtered[0]
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return
        
        if basicrules.check_remove_id(self.graph, vertex):
            self._remove_id(vertex)
            return

        if trace.end.y() > trace.start.y():
            dir = trace.end - trace.start
        else:
            dir = trace.start - trace.end
        normal = QPointF(-dir.y(), dir.x())
        pos = QPointF(self.graph.row(vertex), self.graph.qubit(vertex))
        left, right = [], []
        for neighbor in self.graph.neighbors(vertex):
            npos = QPointF(self.graph.row(neighbor), self.graph.qubit(neighbor))
            dot = QPointF.dotProduct(pos - npos, normal)
            if dot <= 0:
                left.append(neighbor)
            else:
                right.append(neighbor)
        self._unfuse(vertex, left)

    def _remove_id(self, v: VT) -> None:
        new_g = copy.deepcopy(self.graph)
        basicrules.remove_id(new_g, v)
        anim = anims.remove_id(self.graph_scene.vertex_map[v])
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd, anim_before=anim)

    def _unfuse(self, v: VT, left_neighbours: list[VT]) -> None:
        new_g = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(v), qubit=self.graph.qubit(v),
                                     row=self.graph.row(v) - 0.25)
        new_g.set_row(v, self.graph.row(v) + 0.25)
        for neighbor in left_neighbours:
            new_g.add_edge((neighbor, left_vert),
                           self.graph.edge_type((v, neighbor)))
            new_g.remove_edge((v, neighbor))
        new_g.add_edge((v, left_vert))
        anim = anims.unfuse(self.graph, new_g, v, self.graph_scene)
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd, anim_after=anim)
        
    def _vert_double_clicked(self, v: VT) -> None:
        if self.graph.type(v) == VertexType.BOUNDARY:
            return

        new_g = copy.deepcopy(self.graph)
        basicrules.color_change(new_g, v)
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd)
