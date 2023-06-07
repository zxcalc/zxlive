from abc import ABC
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Iterable, Union
from PySide6.QtGui import QUndoCommand

from pyzx import basicrules
from pyzx.graph.base import VT, BaseGraph, ET
from pyzx.utils import EdgeType, VertexType

from .graphview import GraphView


class BaseCommandMeta(type(QUndoCommand), type(ABC)):
    """Dummy metaclass to enable `BaseCommand` to inherit from both
    `QUndoCommand` and `ABC`.

    This avoids Python's infamous metaclass conflict issue.
    See http://www.phyast.pitt.edu/~micheles/python/metatype.html """
    pass


@dataclass
class BaseCommand(QUndoCommand, ABC, metaclass=BaseCommandMeta):
    """Abstract base class for all commands.

    Each command has a reference to the graph view whose graph it
    modifies. This allows the command to notify the view that the
    graph has changed and requires redrawing."""
    graph_view: GraphView

    def __new__(cls, *args, **kwargs):
        # This is a bit hacky: We need to make sure that `__init__`
        # of the super `QUndoCommand` is being called, but a normal
        # dataclass doesn't do that. Overriding `__init__` only in
        # this `BaseCommand` also doesn't work since the command
        # sub-dataclasses don't call modified super constructors.
        # But, we can do a slightly illegal thing and call the
        # constructor in `__new__`:
        self = super().__new__(cls)
        super().__init__(self)
        return self

    @property
    def g(self) -> BaseGraph[VT, ET]:
        """The graph this command modifies."""
        return self.graph_view.graph_scene.g

    def update_graph_view(self) -> None:
        """Notifies the graph view that graph needs to be redrawn.
        
        Also resets the current selection in the graph view."""
        # TODO: For performance reasons, we should track which parts
        #  of the graph have changed and only update those. For example
        #  we could store "dirty flags" for each node/edge.
        self.graph_view.graph_scene.clear_selection()
        self.graph_view.set_graph(self.g)


@dataclass
class SetGraph(BaseCommand):
    """Replaces the current graph with an entirely new graph."""
    new_g: BaseGraph[VT, ET]
    old_g: Optional[BaseGraph[VT, ET]] = None

    def undo(self):
        assert self.old_g is not None
        self.graph_view.set_graph(self.old_g)

    def redo(self):
        self.old_g = self.graph_view.graph_scene.g
        self.graph_view.set_graph(self.new_g)


@dataclass
class ChangeNodeColor(BaseCommand):
    """Changes the color of a set of spiders."""
    vs: Iterable[VT]
    vty: VertexType

    _old_vtys: Optional[list[VertexType]] = None

    def undo(self) -> None:
        assert self._old_vtys is not None
        for v, old_vty in zip(self.vs, self._old_vtys):  # TODO: strict=True in Python 3.10
            self.g.set_type(v, old_vty)
        self.update_graph_view()

    def redo(self) -> None:
        self._old_vtys = [self.g.type(v) for v in self.vs]
        for v in self.vs:
            self.g.set_type(v, self.vty)
        self.update_graph_view()


@dataclass
class AddNode(BaseCommand):
    """Adds a new spider at a given position."""
    x: float
    y: float
    vty: VertexType

    _added_vert: Optional[VT] = None

    def undo(self):
        assert self._added_vert is not None
        self.g.remove_vertex(self._added_vert)
        self.update_graph_view()

    def redo(self):
        self._added_vert = self.g.add_vertex(self.vty, self.y, self.x)
        self.update_graph_view()


@dataclass
class AddEdge(BaseCommand):
    """Adds an edge between two spiders."""
    u: VT
    v: VT
    ety: EdgeType

    _old_ety: Optional[EdgeType] = None

    def undo(self):
        u, v = self.u, self.v
        e = self.g.edge(u, v)
        if self._old_ety:
            self.g.add_edge(e, self._old_ety)
        else:
            self.g.remove_edge(e)
        self.update_graph_view()

    def redo(self):
        u, v = self.u, self.v
        e = self.g.edge(u, v)
        if self.g.connected(u, v):
            self._old_ety = self.g.edge_type(e)
            self.g.set_edge_type(e, self.ety)
        else:
            self._old_ety = None
            self.g.add_edge(e, self.ety)
        self.update_graph_view()


@dataclass
class MoveNode(BaseCommand):
    """Updates the location of a given node."""
    v: VT
    x: float
    y: float

    _old_x: Optional[float] = None
    _old_y: Optional[float] = None

    def undo(self):
        assert self._old_x is not None and self._old_y is not None
        self.g.set_row(self.v, self._old_x)
        self.g.set_qubit(self.v, self._old_y)
        self.update_graph_view()

    def redo(self):
        self._old_x = self.g.row(self.v)
        self._old_y = self.g.qubit(self.v)
        self.g.set_row(self.v, self.x)
        self.g.set_qubit(self.v, self.y)
        self.update_graph_view()


@dataclass
class AddIdentity(BaseCommand):
    """Adds an X or Z identity spider on an edge between two vertices."""
    u: VT
    v: VT
    vty: VertexType

    _new_vert: Optional[VT] = None

    def undo(self):
        u, v, w = self.u, self.v, self._new_vert
        assert w is not None
        g = self.g
        et = g.edge_type(g.edge(v, w))
        g.remove_edge(g.edge(u, w))
        g.remove_edge(g.edge(v, w))
        g.remove_vertex(w)
        g.add_edge(g.edge(u, v), et)
        self.update_graph_view()

    def redo(self):
        u, v = self.u, self.v
        g = self.g
        uv = g.edge(u, v)
        r = 0.5 * (g.row(u) + g.row(v))
        q = 0.5 * (g.qubit(u) + g.qubit(v))
        self._new_vert = g.add_vertex(self.vty, q, r, 0)

        g.add_edge(g.edge(u, self._new_vert))
        g.add_edge(g.edge(v, self._new_vert), g.edge_type(uv))
        g.remove_edge(uv)
        self.update_graph_view()


@dataclass
class ChangePhase(BaseCommand):
    """Updates the phase of a spider."""
    v: VT
    new_phase: Union[Fraction, int]

    _old_phase: Optional[Union[Fraction, int]] = None

    def undo(self):
        assert self._old_phase is not None
        self.g.set_phase(self.v, self._old_phase)
        self.update_graph_view()

    def redo(self):
        self._old_phase = self.g.phase(self.v)
        self.g.set_phase(self.v, self.new_phase)
        self.update_graph_view()


@dataclass
class ChangeColor(BaseCommand):
    """Applies the color-change rule on a set of vertices.

    Changes the spider type using Hadamard conjugation."""
    vs: Iterable[VT]

    def toggle(self):
        for v in self.vs:
            basicrules.color_change(self.g, v)
        self.update_graph_view()

    undo = redo = toggle
