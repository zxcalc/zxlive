from typing import Optional

from pyzx import basicrules
from pyzx.utils import toggle_vertex, EdgeType, VertexType

from PySide6.QtGui import QUndoCommand

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
    def __init__(self, graph_scene, x, y):
        super().__init__()
        self.graph_scene = graph_scene
        self.x = x
        self.y = y

    def undo(self):
        g = self.graph_scene.g
        w = self.w
        g.remove_vertex(w)

        self.graph_scene.set_graph(g)

    def redo(self):
        g = self.graph_scene.g
        w = g.add_vertex(VT_Z, self.y, self.x)
        self.w = w

        self.graph_scene.set_graph(g)


class AddEdge(QUndoCommand):
    _old_ety: Optional[EdgeType]

    def __init__(self, graph_scene, u, v):
        super().__init__()
        self.graph_scene = graph_scene
        self.u = u
        self.v = v

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
            g.set_edge_type(e, ET_SIM)
        else:
            self._old_ety = None
            g.add_edge(e, ET_SIM)

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
