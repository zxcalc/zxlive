import copy
from typing import Iterator

from PySide6.QtWidgets import QToolButton
from pyzx import VertexType, to_gh, basicrules
from pyzx.graph.base import BaseGraph, VT
import pyzx

from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph, AddIdentity, ChangeColor
from .graphscene import GraphScene
from .rules import bialgebra


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        super().__init__(graph, self.graph_scene)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
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
        print("update on selection")
        selection, edges = self.parse_selection()
        g = self.graph_scene.g

        for name,action in self.rewrite_actions.items():
            if action['type'] == pyzx.editor.MATCHES_VERTICES:
                matches = action['matcher'](g, lambda v: v in selection)
            else:
                matches = action['matcher'](g, lambda e: e in edges)
            if matches:
                print(name,matches)
                action['button'].setEnabled(True)
            else:
                action['button'].setEnabled(False)

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
        self.undo_stack.push(cmd)

