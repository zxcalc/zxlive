import copy
from typing import Iterator, Optional

from PySide6.QtCore import QPointF, QPoint, QEasingCurve, QVariantAnimation, \
    QPropertyAnimation
from PySide6.QtWidgets import QWidget, QToolButton, QHBoxLayout
from pyzx import VertexType, basicrules
import pyzx

from .common import VT, GraphT
from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph, AddIdentity, ChangeColor, BaseCommand
from .graphscene import GraphScene, VItemAnimation
from .rules import bialgebra
from .graphview import WandTrace, GraphTool
from .graphscene import VItem
from  . import proof_actions

SPIDER_UNFUSE_TIME = 700  # Time in ms for how long the unfuse animation takes when using magic wand.

class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: GraphT) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        super().__init__(graph, self.graph_scene)

        self.init_action_groups()

        self.graph_view.wand_trace_finished.connect(self._unfuse_slice)



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

    def _unfuse_slice(self, trace):
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return
        item = filtered[0]
        old_pos = item.pos()
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return
        
        if basicrules.check_remove_id(self.graph, vertex):
            new_g = copy.deepcopy(self.graph)
            basicrules.remove_id(new_g, vertex)
            cmd = SetGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
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

        new_g = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(vertex), qubit = pos.y(), row = pos.x() - 0.25)
        new_g.set_row(vertex, pos.x() + 0.25)
        for neighbor in left:
            new_g.add_edge((neighbor, left_vert), self.graph.edge_type((vertex, neighbor)))
            new_g.remove_edge((vertex, neighbor))
        new_g.add_edge((vertex, left_vert))

        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd)

        def animate(it: VItem, start_pos: QPointF, end_pos: QPointF) -> None:
            it.setPos(start_pos)
            anim = VItemAnimation(it, VItem.Properties.Position, refresh=True)
            anim.setDuration(SPIDER_UNFUSE_TIME)
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setEasingCurve(QEasingCurve.OutElastic)
            anim.start()

        item1 = self.graph_scene.vertex_map[vertex]
        item2 = self.graph_scene.vertex_map[left_vert]
        animate(item1, old_pos, item1.pos())
        animate(item2, old_pos, item2.pos())
