import copy
from typing import Iterator, Optional

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QToolButton
from pyzx import VertexType, to_gh, basicrules, EdgeType
from pyzx.graph.base import BaseGraph, VT
import pyzx

from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph, AddIdentity, ChangeColor, BaseCommand
from .graphscene import GraphScene
from .rules import bialgebra
from .graphview import WandTrace, GraphTool
from .graphscene import VItem


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        self.graph_scene.vertex_dragged_onto.connect(self._vertex_dragged_onto)
        self.graph_scene.vertex_dropped_onto.connect(self._vertex_dropped_onto)
        super().__init__(graph, self.graph_scene)

        self.graph_view.wand_trace_finished.connect(self._unfuse_slice)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        self.selection = QToolButton(self, text="Selection", checkable=True, checked=True)
        self.magic_wand = QToolButton(self, text="Magic Wand", checkable=True)

        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        self.selection.clicked.connect(self._selection_clicked)

        yield ToolbarSection(self.selection, self.magic_wand, exclusive=True)
        
        self.rewrite_actions = {}
        buttons = []
        for name,action in pyzx.editor.operations.items():
            btn = QToolButton(self, text=action['text'])
            btn.clicked.connect(self._do_rewrite(name,action['matcher'],action['rule'],action['type']))
            btn.setStatusTip(action['tooltip'])
            btn.setEnabled(False)
            self.rewrite_actions[name] = {'matcher':action['matcher'],
                                          'rule':action['rule'],
                                          'button':btn,
                                          'type':action['type']}
            buttons.append(btn)
        # fuse = QToolButton(self, text="Fuse")
        # identity_z = QToolButton(self, text="Z identity")
        # identity_x = QToolButton(self, text="X identity")
        # color_change = QToolButton(self, text="Color change")
        # bialgebra = QToolButton(self, text="Bialgebra")
        # strong_comp = QToolButton(self, text="Strong comp")
        # gh_state = QToolButton(self, text="To GH form")

        # fuse.clicked.connect(self._fuse_clicked)
        # identity_z.clicked.connect(lambda: self._identity_clicked(VertexType.Z))
        # identity_x.clicked.connect(lambda: self._identity_clicked(VertexType.X))
        # color_change.clicked.connect(self._color_change_clicked)
        # bialgebra.clicked.connect(self._bialgebra_clicked)
        # strong_comp.clicked.connect(self._strong_comp_clicked)
        # gh_state.clicked.connect(self._gh_state_clicked)

        # yield ToolbarSection(fuse, identity_z, identity_x, color_change, bialgebra,
        #                      strong_comp, gh_state, exclusive=True)
        yield ToolbarSection(*buttons)

    def parse_selection(self):
        selection = list(self.graph_scene.selected_vertices)
        g = self.graph_scene.g
        edges = []
        for e in g.edges():
            s,t = g.edge_st(e)
            if s in selection and t in selection:
                edges.append(e)

        return selection, edges

    def _do_rewrite(self,name,matcher,rule,ty):
        def do_rewrite():
            selection, edges = self.parse_selection()
            g = copy.deepcopy(self.graph_scene.g)
            if ty == pyzx.editor.MATCHES_EDGES:
                matches = matcher(g, lambda e: e in edges)
            else: matches = matcher(g, lambda v: v in selection)

            etab, rem_verts, rem_edges, check_isolated_vertices = rule(g, matches)
            g.remove_edges(rem_edges)
            g.remove_vertices(rem_verts)
            g.add_edge_table(etab)
            cmd = SetGraph(self.graph_view,g)
            self.undo_stack.push(cmd)
            new_verts = g.vertex_set()
            self.graph_scene.select_vertices(v for v in selection if v in new_verts)
        return do_rewrite

    def update_on_selection(self):
        selection, edges = self.parse_selection()
        g = self.graph_scene.g

        for name,action in self.rewrite_actions.items():
            if action['type'] == pyzx.editor.MATCHES_VERTICES:
                matches = action['matcher'](g, lambda v: v in selection)
            else:
                matches = action['matcher'](g, lambda e: e in edges)
            if matches:
                action['button'].setEnabled(True)
            else:
                action['button'].setEnabled(False)

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
        vertex = filtered[0].v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return
        
        dir = trace.end - trace.start
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

    def _vertex_dragged_onto(self, v: VT, w: VT) -> None:
        ty1, ty2 = self.graph.type(v), self.graph.type(w)
        if ty1 == ty2 and self.graph.connected(v, w) and self.graph.edge_type(self.graph.edge(v, w)) == EdgeType.SIMPLE:
            self.graph_scene.highlight_vertex(w)
        # TODO: Copying, ...

    def _vertex_dropped_onto(self, v: VT, w: VT) -> None:
        ty1, ty2 = self.graph.type(v), self.graph.type(w)
        if ty1 == ty2 and self.graph.connected(v, w) and self.graph.edge_type(self.graph.edge(v, w)) == EdgeType.SIMPLE:
            g = copy.deepcopy(self.graph_scene.g)
            pyzx.basicrules.fuse(g, w, v)
            cmd = SetGraph(self.graph_view, g)
            self.undo_stack.push(cmd)
        # TODO: Copying, ...


