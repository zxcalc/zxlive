from collections import namedtuple
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, Optional, Iterable, Set, Union, List, Any
import copy

from PySide6.QtCore import QItemSelection, QModelIndex, QItemSelectionModel, \
    QSignalBlocker
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QListView

from pyzx import basicrules
from pyzx.graph import GraphDiff
from pyzx.utils import EdgeType, VertexType, get_w_partner, vertex_is_w

from .common import VT, ET, W_INPUT_OFFSET, GraphT
from .graphview import GraphView
from .proof import ProofModel, Rewrite


@dataclass
class BaseCommand(QUndoCommand):
    """Abstract base class for all commands.

    Each command has a reference to the graph view whose graph it
    modifies. This allows the command to notify the view that the
    graph has changed and requires redrawing."""
    graph_view: GraphView

    def __post_init__(self) -> None:
        # We need to make sure that `__init__` of the super `QUndoCommand`
        # is being called, but a normal dataclass doesn't do that.
        # Overriding `__init__` also doesn't work since the command sub-
        # dataclasses don't call modified super constructors. Thus, we
        # hook it into `__post_init__`.
        super().__init__()
        self.g = copy.deepcopy(self.graph_view.graph_scene.g)

    def update_graph_view(self, select_new: bool = False) -> None:
        """Notifies the graph view that graph needs to be redrawn.

        :param select_new: If True, add all new vertices to the selection set.
        """
        # TODO: For performance reasons, we should track which parts
        #  of the graph have changed and only update those. For example
        #  we could store "dirty flags" for each node/edge.
        self.graph_view.update_graph(self.g, select_new)

@dataclass
class CommandGroup(QUndoCommand):
    """A command that groups together multiple commands.
    Undoing/redoing this command undoes/redoes all commands in the group.
    """
    commands: Iterable[QUndoCommand]

    def __post_init__(self) -> None:
        super().__init__()

    def undo(self) -> None:
        for cmd in reversed(self.commands):
            cmd.undo()

    def redo(self) -> None:
        for cmd in self.commands:
            cmd.redo()

@dataclass
class SetGraph(BaseCommand):
    """Replaces the current graph with an entirely new graph."""
    new_g: GraphT
    old_g: Optional[GraphT] = field(default=None, init=False)

    def undo(self) -> None:
        assert self.old_g is not None
        self.graph_view.set_graph(self.old_g)

    def redo(self) -> None:
        self.old_g = self.graph_view.graph_scene.g
        self.graph_view.set_graph(self.new_g)


@dataclass
class UpdateGraph(BaseCommand):
    """Updates the current graph with a modified one.
    It will try to reuse existing QGraphicsItem's as much as possible."""
    new_g: GraphT
    old_g: Optional[GraphT] = field(default=None, init=False)
    old_selected: Optional[Set[VT]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self.old_g is not None and self.old_selected is not None
        self.g = self.old_g
        self.update_graph_view()
        self.graph_view.graph_scene.select_vertices(self.old_selected)

    def redo(self) -> None:
        self.old_g = self.graph_view.graph_scene.g
        self.old_selected = set(self.graph_view.graph_scene.selected_vertices)
        self.g = self.new_g
        self.update_graph_view(True)


@dataclass
class ChangeNodeType(BaseCommand):
    """Changes the color of a set of spiders."""
    vs: Iterable[VT]
    vty: VertexType.Type

    WInfo = namedtuple('WInfo', ['partner', 'partner_type', 'partner_pos', 'neighbors'])

    _old_vtys: Optional[list[VertexType.Type]] = field(default=None, init=False)
    _old_w_info: Optional[Dict[VT, WInfo]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._old_vtys is not None
        for v, old_vty in zip(self.vs, self._old_vtys):  # TODO: strict=True in Python 3.10
            if vertex_is_w(old_vty):
                assert self._old_w_info is not None
                v2 = self._old_w_info[v].partner
                self.g.add_vertex_indexed(v2)
                self.g.set_type(v2, self._old_w_info[v].partner_type)
                self.g.set_row(v2, self._old_w_info[v].partner_pos[0])
                self.g.set_qubit(v2, self._old_w_info[v].partner_pos[1])
                self.g.add_edge(self.g.edge(v,v2), edgetype=EdgeType.W_IO)
                for v3 in self._old_w_info[v].neighbors:
                    self.g.add_edge(self.g.edge(v2,v3), edgetype=self.g.edge_type(self.g.edge(v,v3)))
                    self.g.remove_edge(self.g.edge(v,v3))
            self.g.set_type(v, old_vty)
        self.update_graph_view()

    def redo(self) -> None:
        if self._old_w_info is None:
            self._old_w_info = {}
        if vertex_is_w(self.vty):
            return
        self._old_vtys = [self.g.type(v) for v in self.vs]
        for v1 in self.vs:
            if vertex_is_w(self.g.type(v1)):
                v2 = get_w_partner(self.g, v1)
                v2_neighbors = [v for v in self.g.neighbors(v2) if v != v1]
                for v3 in v2_neighbors:
                    self.g.add_edge(self.g.edge(v1,v3), edgetype=self.g.edge_type(self.g.edge(v2,v3)))
                self._old_w_info[v1] = self.WInfo(partner=v2,
                                                  partner_type=self.g.type(v2),
                                                  partner_pos=(self.g.row(v2), self.g.qubit(v2)),
                                                  neighbors=v2_neighbors)
                self.g.remove_vertex(v2)
            self.g.set_type(v1, self.vty)
        self.update_graph_view()


@dataclass
class ChangeEdgeColor(BaseCommand):
    """Changes the color of a set of edges"""
    es: Iterable[ET]
    ety: EdgeType.Type

    _old_etys: Optional[list[EdgeType]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._old_etys is not None
        for e, old_ety in zip(self.es, self._old_etys):  # TODO: strict=True in Python 3.10
            self.g.set_edge_type(e, old_ety)
        self.update_graph_view()

    def redo(self) -> None:
        self._old_etys = [self.g.edge_type(e) for e in self.es]
        for e in self.es:
            self.g.set_edge_type(e, self.ety)
        self.update_graph_view()


@dataclass
class AddNode(BaseCommand):
    """Adds a new spider at a given position."""
    x: float
    y: float
    vty: VertexType.Type

    _added_vert: Optional[VT] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._added_vert is not None
        self.g.remove_vertex(self._added_vert)
        self.update_graph_view()

    def redo(self) -> None:
        self._added_vert = self.g.add_vertex(self.vty, self.y, self.x)
        self.update_graph_view()

@dataclass
class AddWNode(BaseCommand):
    """Adds a new W node at a given position."""
    x: float
    y: float

    _added_input_vert: Optional[VT] = field(default=None, init=False)
    _added_output_vert: Optional[VT] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._added_input_vert is not None
        assert self._added_output_vert is not None
        self.g.remove_vertex(self._added_input_vert)
        self.g.remove_vertex(self._added_output_vert)
        self.update_graph_view()

    def redo(self) -> None:
        self._added_input_vert = self.g.add_vertex(VertexType.W_INPUT, self.y - W_INPUT_OFFSET, self.x)
        self._added_output_vert = self.g.add_vertex(VertexType.W_OUTPUT, self.y, self.x)
        self.g.add_edge((self._added_input_vert, self._added_output_vert), EdgeType.W_IO)
        self.update_graph_view()

@dataclass
class AddEdge(BaseCommand):
    """Adds an edge between two spiders."""
    u: VT
    v: VT
    ety: EdgeType.Type

    _old_ety: Optional[EdgeType.Type] = field(default=None, init=False)

    def undo(self) -> None:
        u, v = self.u, self.v
        e = self.g.edge(u, v)
        if self._old_ety:
            self.g.add_edge(e, self._old_ety)
        else:
            self.g.remove_edge(e)
        self.update_graph_view()

    def redo(self) -> None:
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
    """Updates the location of a collection of nodes."""
    vs: list[tuple[VT, float, float]]

    _old_positions: Optional[list[tuple[float, float]]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._old_positions is not None
        for (v, _, _), (x, y) in zip(self.vs, self._old_positions):
            self.g.set_row(v, x)
            self.g.set_qubit(v, y)
        self.update_graph_view()

    def redo(self) -> None:
        self._old_positions = []
        for v, x, y in self.vs:
            self._old_positions.append((self.g.row(v), self.g.qubit(v)))
            self.g.set_row(v, x)
            self.g.set_qubit(v, y)
        self.update_graph_view()


@dataclass
class AddIdentity(BaseCommand):
    """Adds an X or Z identity spider on an edge between two vertices."""
    u: VT
    v: VT
    vty: VertexType.Type

    _new_vert: Optional[VT] = field(default=None, init=False)

    def undo(self) -> None:
        u, v, w = self.u, self.v, self._new_vert
        assert w is not None
        g = self.g
        et = g.edge_type(g.edge(v, w))
        g.remove_edge(g.edge(u, w))
        g.remove_edge(g.edge(v, w))
        g.remove_vertex(w)
        g.add_edge(g.edge(u, v), et)
        self.update_graph_view()

    def redo(self) -> None:
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

    _old_phase: Optional[Union[Fraction, int]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._old_phase is not None
        self.g.set_phase(self.v, self._old_phase)
        self.update_graph_view()

    def redo(self) -> None:
        self._old_phase = self.g.phase(self.v)
        self.g.set_phase(self.v, self.new_phase)
        self.update_graph_view()


@dataclass
class ChangeColor(BaseCommand):
    """Applies the color-change rule on a set of vertices.

    Changes the spider type using Hadamard conjugation."""
    vs: Iterable[VT]

    def toggle(self) -> None:
        for v in self.vs:
            basicrules.color_change(self.g, v)
        self.update_graph_view()

    undo = redo = toggle


@dataclass
class AddRewriteStep(SetGraph):
    """Adds a new rewrite to the proof.

    The rewrite is inserted after the currently selected step. In particular, it
    replaces all rewrites that were previously after the current selection.
    """
    step_view: QListView
    name: str
    diff: Optional[GraphDiff] = None

    _old_selected: Optional[int] = field(default=None, init=False)
    _old_steps: list[tuple[Rewrite, GraphT]] = field(default_factory=list, init=False)

    @property
    def proof_model(self) -> ProofModel:
        model = self.step_view.model()
        assert isinstance(model, ProofModel)
        return model

    def redo(self) -> None:
        # Remove steps from the proof model until we're at the currently selected step
        self._old_selected = self.step_view.currentIndex().row()
        self._old_steps = []
        for _ in range(self.proof_model.rowCount() - self._old_selected - 1):
            self._old_steps.append(self.proof_model.pop_rewrite())

        diff = self.diff or GraphDiff(self.g, self.new_g)
        self.proof_model.add_rewrite(Rewrite(self.name, diff), self.new_g)

        # Select the added step
        idx = self.step_view.model().index(self.proof_model.rowCount() - 1, 0, QModelIndex())
        self.step_view.selectionModel().blockSignals(True)
        self.step_view.setCurrentIndex(idx)
        self.step_view.selectionModel().blockSignals(False)
        super().redo()

    def undo(self) -> None:
        # Undo the rewrite
        self.step_view.selectionModel().blockSignals(True)
        self.proof_model.pop_rewrite()
        self.step_view.selectionModel().blockSignals(False)

        # Add back steps that were previously removed
        for rewrite, graph in reversed(self._old_steps):
            self.proof_model.add_rewrite(rewrite, graph)

        # Select the previously selected step
        assert self._old_selected is not None
        idx = self.step_view.model().index(self._old_selected, 0, QModelIndex())
        self.step_view.selectionModel().blockSignals(True)
        self.step_view.setCurrentIndex(idx)
        self.step_view.selectionModel().blockSignals(False)
        super().undo()


@dataclass
class GoToRewriteStep(SetGraph):
    """Shows the graph at some step in the proof.

    Undoing returns to the previously selected proof step.
    """

    def __init__(self, graph_view: GraphView, step_view: QListView, old_step: int, step: int) -> None:
        proof_model = step_view.model()
        assert isinstance(proof_model, ProofModel)
        SetGraph.__init__(self, graph_view, proof_model.get_graph(step))
        self.step_view = step_view
        self.step = step
        self.old_step = old_step

    def redo(self) -> None:
        idx = self.step_view.model().index(self.step, 0, QModelIndex())
        self.step_view.clearSelection()
        self.step_view.selectionModel().blockSignals(True)
        self.step_view.setCurrentIndex(idx)
        self.step_view.selectionModel().blockSignals(False)
        self.step_view.update(idx)
        super().redo()

    def undo(self) -> None:
        idx = self.step_view.model().index(self.old_step, 0, QModelIndex())
        self.step_view.clearSelection()
        self.step_view.selectionModel().blockSignals(True)
        self.step_view.setCurrentIndex(idx)
        self.step_view.selectionModel().blockSignals(False)
        self.step_view.update(idx)
        super().undo()


@dataclass
class MoveNodeInStep(MoveNode):
    step_view: QListView

    def redo(self) -> None:
        super().redo()
        model = self.step_view.model()
        assert isinstance(model, ProofModel)
        model.graphs[self.step_view.currentIndex().row()] = self.g

    def undo(self) -> None:
        super().undo()
        model = self.step_view.model()
        assert isinstance(model, ProofModel)
        model.graphs[self.step_view.currentIndex().row()] = self.g
