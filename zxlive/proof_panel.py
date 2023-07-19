import copy
from typing import Iterator

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget, QToolButton, QHBoxLayout
from PySide6.QtGui import QVector2D
from pyzx import VertexType, basicrules

from .common import VT, GraphT, SCALE
from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph
from .graphscene import GraphScene
from .graphview import GraphTool
from .vitem import VItem
from .eitem import EItem
from . import proof_actions
from . import animations as anims


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: GraphT) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        super().__init__(graph, self.graph_scene)

        self.init_action_groups()

        self.graph_view.wand_trace_finished.connect(self._wand_trace_finished)



    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        self.selection = QToolButton(self, text="Selection", checkable=True, checked=True)
        self.magic_wand = QToolButton(self, text="Magic Wand", checkable=True)
        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        self.selection.clicked.connect(self._selection_clicked)
        yield ToolbarSection(self.selection, self.magic_wand, exclusive=True)

        self.identity_choice = [
            QToolButton(self, text="Z", checkable=True, checked=True),
            QToolButton(self, text="X", checkable=True)
        ]
        yield ToolbarSection(*self.identity_choice, exclusive=True)

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

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
        self.undo_stack.push(cmd)

    def _selection_clicked(self):
        self.graph_view.tool = GraphTool.Selection

    def _magic_wand_clicked(self):
        self.graph_view.tool = GraphTool.MagicWand

    def _wand_trace_finished(self, trace):
        if self._magic_slice(trace):
            return
        elif self._magic_identity(trace):
            return

    def _magic_identity(self, trace):
        if len(trace.hit) != 1 or not all(isinstance(item, EItem) for item in trace.hit):
            return False

        item = next(iter(trace.hit))
        pos = trace.hit[item][-1]
        s = self.graph.edge_s(item.e)
        t = self.graph.edge_t(item.e)

        if self.identity_choice[0].isChecked():
            vty = VertexType.Z
        elif self.identity_choice[1].isChecked():
            vty = VertexType.X

        new_g = copy.deepcopy(self.graph)
        v = new_g.add_vertex(vty, row=pos.x()/SCALE, qubit=pos.y()/SCALE)
        new_g.add_edge(self.graph.edge(s, v), self.graph.edge_type(item.e))
        new_g.add_edge(self.graph.edge(v, t))
        new_g.remove_edge(item.e)

        anim = anims.add_id(v, self.graph_scene)
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd, anim_after=anim)

    def _magic_slice(self, trace):
        def cross(a, b):
            return a.y() * b.x() - a.x() * b.y()
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return False
        item = filtered[0]
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return False
        
        if basicrules.check_remove_id(self.graph, vertex):
            self._remove_id(vertex)
            return False
        
        start = trace.hit[item][0]
        end = trace.hit[item][-1]
        if start.y() > end.y():
            start, end = end, start
        pos = QPointF(SCALE * self.graph.row(vertex), SCALE * self.graph.qubit(vertex))
        left, right = [], []
        for neighbor in self.graph.neighbors(vertex):
            npos = QPointF(SCALE * self.graph.row(neighbor), SCALE * self.graph.qubit(neighbor))
            # Compute whether each neighbor is inside the entry and exit points
            i1 = cross(start - pos, npos - pos) * cross(start - pos, end - pos) >= 0
            i2 = cross(end - pos, npos - pos) * cross(end - pos, start - pos) >= 0
            inside = i1 and i2
            if inside:
                left.append(neighbor)
            else:
                right.append(neighbor)
        self._unfuse(vertex, left)
        return True

    def _remove_id(self, v: VT) -> None:
        new_g = copy.deepcopy(self.graph)
        basicrules.remove_id(new_g, v)
        anim = anims.remove_id(self.graph_scene.vertex_map[v])
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd, anim_before=anim)

    def _unfuse(self, v: VT, left_neighbours: list[VT]) -> None:
        def snap_vector(v):
            if abs(v.x()) > abs(v.y()):
                v.setY(0.0)
            else:
                v.setX(0.0)
            if not v.isNull():
                v.normalize()

        # Compute the average position of left vectors
        pos = QPointF(self.graph.row(v), self.graph.qubit(v))
        avg_left = QVector2D()
        for n in left_neighbours:
            npos = QPointF(self.graph.row(n), self.graph.qubit(n))
            dir = QVector2D(npos - pos).normalized()
            avg_left += dir
        avg_left.normalize()
        # And snap it to the grid
        snap_vector(avg_left)
        # Same for right vectors
        avg_right = QVector2D()
        for n in self.graph.neighbors(v):
            if n in left_neighbours: continue
            npos = QPointF(self.graph.row(n), self.graph.qubit(n))
            dir = QVector2D(npos - pos).normalized()
            avg_right += dir
        avg_right.normalize()
        snap_vector(avg_right)
        if avg_right.isNull():
            avg_right = -avg_left
        elif avg_left.isNull():
            avg_left = -avg_right
        
        dist = 0.25 if QVector2D.dotProduct(avg_left, avg_right) != 0 else 0.35

        new_g = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(v), 
                                     qubit=self.graph.qubit(v) + dist*avg_left.y(),
                                     row=self.graph.row(v) + dist*avg_left.x())
        new_g.set_row(v, self.graph.row(v) + dist*avg_right.x())
        new_g.set_qubit(v, self.graph.qubit(v) + dist*avg_right.y())
        for neighbor in left_neighbours:
            new_g.add_edge((neighbor, left_vert),
                           self.graph.edge_type((v, neighbor)))
            new_g.remove_edge((v, neighbor))
        new_g.add_edge((v, left_vert))
        anim = anims.unfuse(self.graph, new_g, v, self.graph_scene)
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd, anim_after=anim)
