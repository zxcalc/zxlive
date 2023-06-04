from dataclasses import dataclass
from typing import Optional
from PySide6.QtGui import QUndoCommand


from pyzx import basicrules
from pyzx.graph.base import VT
from pyzx.utils import toggle_vertex, EdgeType, VertexType

from zxlive.graphscene import GraphScene

ET_SIM = EdgeType.SIMPLE
ET_HAD = EdgeType.HADAMARD

VT_Z = VertexType.Z
VT_X = VertexType.X


class SetGraph(QUndoCommand):
    def __init__(self, graph_view, g, new_g):
        super().__init__()
        self.graph_view = graph_view
        self.g = g
        self.new_g = new_g

    def undo(self):
        self.graph_view.set_graph(self.g)

    def redo(self):
        self.graph_view.set_graph(self.new_g)


class EditNodeColor(QUndoCommand):
    def __init__(self, graph_view, vs):
        super().__init__()
        self.graph_view = graph_view
        self.vs = vs

    def toggle(self):
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []
        for v in self.vs:
            g.set_type(v, toggle_vertex(g.type(v)))
        self.graph_view.set_graph(g)

    undo = redo = toggle


class AddNode(QUndoCommand):
    graph_scene: GraphScene
    x: float
    y: float
    vty: VertexType

    _added_vert: Optional[VT] = None

    def __init__(self, graph_scene: GraphScene, x: float, y: float, vty: VertexType):
        super().__init__()
        self.graph_scene = graph_scene
        self.x = x
        self.y = y
        self.vty = vty

    def undo(self):
        assert self._added_vert is not None
        g = self.graph_scene.g
        g.remove_vertex(self._added_vert)
        self.graph_scene.set_graph(g)

    def redo(self):
        g = self.graph_scene.g
        self._added_vert = g.add_vertex(self.vty, self.y, self.x)
        self.graph_scene.set_graph(g)


class AddEdge(QUndoCommand):
    graph_scene: GraphScene
    u: VT
    v: VT
    ety: EdgeType

    _old_ety: Optional[EdgeType] = None

    def __init__(self, graph_scene: GraphScene, u: VT, v: VT, ety: EdgeType):
        super().__init__()
        self.graph_scene = graph_scene
        self.u = u
        self.v = v
        self.ety = ety

    def undo(self):
        u, v = self.u, self.v
        g = self.graph_scene.g
        self.graph_scene.selected_items = []

        e = g.edge(u, v)
        if self._old_ety:
            g.add_edge(e, self._old_ety)
        else:
            g.remove_edge(e)
        self.graph_scene.set_graph(g)

    def redo(self):
        u, v = self.u, self.v
        g = self.graph_scene.g
        self.graph_scene.selected_items = []

        e = g.edge(u, v)
        if g.connected(u, v):
            self._old_ety = g.edge_type(e)
            g.set_edge_type(e, self.ety)
        else:
            self._old_ety = None
            g.add_edge(e, self.ety)

        self.graph_scene.set_graph(g)


class MoveNode(QUndoCommand):
    graph_scene: GraphScene
    v: VT
    x: float
    y: float

    _old_x: Optional[float] = None
    _old_y: Optional[float] = None

    def __init__(self, graph_scene, v: VT, x: float, y: float):
        super().__init__()
        self.graph_scene = graph_scene
        self.v = v
        self.x = x
        self.y = y

    def undo(self):
        assert self._old_x is not None and self._old_y is not None
        g = self.graph_scene.g
        g.set_row(self.v, self._old_x)
        g.set_qubit(self.v, self._old_y)
        self.graph_scene.set_graph(g)

    def redo(self):
        g = self.graph_scene.g
        self._old_x = g.row(self.v)
        self._old_y = g.qubit(self.v)
        g.set_row(self.v, self.x)
        g.set_qubit(self.v, self.y)
        self.graph_scene.set_graph(g)


class AddIdentity(QUndoCommand):
    def __init__(self, graph_view, u, v):
        super().__init__()
        self.graph_view = graph_view
        self.u = u
        self.v = v

    def undo(self):
        u, v, w = self.u, self.v, self.w
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []

        et = g.edge_type(g.edge(v, w))
        g.remove_edge(g.edge(u, w))
        g.remove_edge(g.edge(v, w))
        g.remove_vertex(w)
        g.add_edge(g.edge(u, v), et)
        self.graph_view.set_graph(g)

    def redo(self):
        u, v = self.u, self.v
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []
        uv = g.edge(u, v)
        r = 0.5 * (g.row(u) + g.row(v))
        q = 0.5 * (g.qubit(u) + g.qubit(v))
        w = g.add_vertex(VT_Z, q, r, 0)
        self.w = w

        g.add_edge(g.edge(u, w), ET_SIM)
        g.add_edge(g.edge(v, w), g.edge_type(uv))
        g.remove_edge(uv)
        self.graph_view.set_graph(g)


class ChangePhase(QUndoCommand):
    def __init__(self, graph_view, v, old_phase, new_phase):
        super().__init__()
        self.graph_view = graph_view
        self.v = v
        self.old_phase = old_phase
        self.new_phase = new_phase

    def undo(self):
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []
        g.set_phase(self.v, self.old_phase)
        self.graph_view.set_graph(g)

    def redo(self):
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []
        g.set_phase(self.v, self.new_phase)
        self.graph_view.set_graph(g)


class ChangeColor(QUndoCommand):
    def __init__(self, graph_view, vs):
        super().__init__()
        self.graph_view = graph_view
        self.vs = vs

    def toggle(self):
        g = self.graph_view.graph_scene.g
        self.graph_view.graph_scene.selected_items = []
        for v in self.vs:
            basicrules.color_change(g, v)
        self.graph_view.set_graph(g)

    undo = redo = toggle
