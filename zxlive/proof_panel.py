import copy
from typing import Iterator

from PySide6.QtWidgets import QToolButton
from pyzx import VertexType, to_gh, basicrules
from pyzx.graph.base import BaseGraph, VT

from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, SetGraph
from .graphscene import GraphScene
from .rules import bialgebra


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: BaseGraph) -> None:
        self.graph_scene = GraphScene(self._vert_moved)
        super().__init__(graph, self.graph_scene)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        fuse = QToolButton(self, text="Fuse")
        bialgebra = QToolButton(self, text="Bialgebra")
        gh_state = QToolButton(self, text="Boundary")

        fuse.clicked.connect(self._fuse_clicked)
        bialgebra.clicked.connect(self._bialgebra_clicked)
        gh_state.clicked.connect(self._gh_state_clicked)

        yield ToolbarSection(buttons=(fuse, bialgebra, gh_state), exclusive=True)

    def _vert_moved(self, v: VT, x: float, y: float):
        cmd = MoveNode(self.graph_view, v, x, y)
        self.undo_stack.push(cmd)

    def _fuse_clicked(self):
        vs = list(self.graph_scene.selected_vertices)
        self.graph_scene.clear_selection()

        if vs == []:
            self.graph_view.set_graph(self.graph)
            return

        new_g = copy.deepcopy(self.graph)

        if len(vs) == 1:
            basicrules.remove_id(new_g, vs[0])
            cmd = SetGraph(self.graph_view, new_g)
            self.undo_stack.push(cmd)
            return

        x_vertices = [v for v in vs if self.graph.type(v) == VertexType.X]
        z_vertices = [v for v in vs if self.graph.type(v) == VertexType.Z]
        vs = [x_vertices, z_vertices]
        fuse = False
        for lst in vs:
            lst = sorted(lst)
            to_fuse = {}
            visited = set()
            for v in lst:
                if v in visited:
                    continue
                to_fuse[v] = []
                # dfs
                stack = [v]
                while stack:
                    u = stack.pop()
                    if u in visited:
                        continue
                    visited.add(u)
                    for w in self.graph.neighbors(u):
                        if w in lst:
                            to_fuse[v].append(w)
                            stack.append(w)

            for v in to_fuse:
                for w in to_fuse[v]:
                    basicrules.fuse(new_g, v, w)
                    fuse = True

        if not fuse:
            self.graph_view.set_graph(self.graph)
            return

        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd)

    def _bialgebra_clicked(self):
        # TODO: Maybe replace copy with more efficient undo?
        new_g = copy.deepcopy(self.graph)
        bialgebra(new_g, list(self.graph_scene.selected_vertices))
        self.graph_scene.clear_selection()
        cmd = SetGraph(self.graph_view, new_g)
        self.undo_stack.push(cmd)

    def _gh_state_clicked(self):
        # TODO: Do we want to respect selection here?
        new_g = copy.deepcopy(self.graph)
        to_gh(new_g)
        cmd = SetGraph(self.graph_view, new_g)
        self.graph_scene.clear_selection()
        self.undo_stack.push(cmd)

