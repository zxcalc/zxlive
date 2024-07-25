from __future__ import annotations

import copy
from collections import namedtuple
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable, Optional, Set, Union, Callable

from PySide6.QtCore import QModelIndex
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QListView
from pyzx import basicrules
from pyzx.graph import GraphDiff
from pyzx.symbolic import Poly
from pyzx.utils import EdgeType, VertexType, get_w_partner, vertex_is_w, get_w_io, get_z_box_label, set_z_box_label

from .common import ET, VT, W_INPUT_OFFSET, GraphT
from .settings import display_setting
from .eitem import EItem
from .graphview import GraphView
from .proof import ProofModel, ProofStepView, Rewrite


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
class UndoableChange(BaseCommand):
    """ Generic undoable change in the graph that can be appended to the
    undo stack

    Can be initialised as: UndoableChange(<parent>, <undo_cmd>, <redo_cmd>)

    Where <parent> must contain the graph_view attribute as it is used in
    BaseCommand.
    """
    undo: Callable[[], None]
    redo: Callable[[], None]

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
        if not self.old_selected:
            self.old_selected = set(self.graph_view.graph_scene.selected_vertices)
        self.g = self.new_g
        self.update_graph_view(True)


@dataclass
class ChangeNodeType(BaseCommand):
    """Changes the color of a set of spiders."""
    vs: list[VT] | set[VT]
    vty: VertexType

    WInfo = namedtuple('WInfo', ['partner', 'partner_type', 'partner_pos', 'neighbors'])

    _old_vtys: Optional[list[VertexType]] = field(default=None, init=False)
    _old_w_info: Optional[dict[VT, WInfo]] = field(default=None, init=False)
    _new_w_inputs: Optional[list[VT]] = field(default=None, init=False)

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
        if self._new_w_inputs is not None:
            for w_in in self._new_w_inputs.copy():
                self._new_w_inputs.remove(w_in)
                self.g.remove_vertex(w_in)
        self.update_graph_view()

    def redo(self) -> None:
        self._old_w_info = self._old_w_info or {}
        self._new_w_inputs = self._new_w_inputs or []
        self.vs = set(self.vs)
        for v in self.vs.copy():
            is_w_node = vertex_is_w(self.g.type(v))
            if is_w_node and self.vty == VertexType.W_OUTPUT:
                self.vs.discard(v)
            elif is_w_node:
                w_in, w_out = get_w_io(self.g, v)
                self.vs.discard(w_in)
                self.vs.add(w_out)
        self.vs = list(self.vs)
        self._old_vtys = [self.g.type(v) for v in self.vs]
        if self.vty == VertexType.W_OUTPUT:
            for v in self.vs:
                w_input = self.g.add_vertex(VertexType.W_INPUT,
                                            self.g.qubit(v) - W_INPUT_OFFSET,
                                            self.g.row(v))
                self.g.add_edge(self.g.edge(w_input, v), edgetype=EdgeType.W_IO)
                self._new_w_inputs.append(w_input)
        for v in self.vs:
            if vertex_is_w(self.g.type(v)):
                v2 = get_w_partner(self.g, v)
                v2_neighbors = [vn for vn in self.g.neighbors(v2) if vn != v]
                for v3 in v2_neighbors:
                    self.g.add_edge(self.g.edge(v,v3), edgetype=self.g.edge_type(self.g.edge(v2,v3)))
                self._old_w_info[v] = self.WInfo(partner=v2,
                                                 partner_type=self.g.type(v2),
                                                 partner_pos=(self.g.row(v2), self.g.qubit(v2)),
                                                 neighbors=v2_neighbors)
                self.g.remove_vertex(v2)
            self.g.set_type(v, self.vty)
        self.update_graph_view()


@dataclass
class ChangeEdgeColor(BaseCommand):
    """Changes the color of a set of edges"""
    es: Iterable[ET]
    ety: EdgeType

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
    vty: VertexType

    _added_vert: Optional[VT] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._added_vert is not None
        self.g.remove_vertex(self._added_vert)
        self.update_graph_view()

    def redo(self) -> None:
        y = round(self.y * display_setting.SNAP_DIVISION) / display_setting.SNAP_DIVISION
        x = round(self.x * display_setting.SNAP_DIVISION) / display_setting.SNAP_DIVISION
        self._added_vert = self.g.add_vertex(self.vty, y,x)
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
        y = round(self.y * display_setting.SNAP_DIVISION) / display_setting.SNAP_DIVISION
        x = round(self.x * display_setting.SNAP_DIVISION) / display_setting.SNAP_DIVISION
        self._added_input_vert = self.g.add_vertex(VertexType.W_INPUT, y - W_INPUT_OFFSET, self.x)
        self._added_output_vert = self.g.add_vertex(VertexType.W_OUTPUT, y, x)
        self.g.add_edge((self._added_input_vert, self._added_output_vert), EdgeType.W_IO)
        self.update_graph_view()

@dataclass
class AddEdge(BaseCommand):
    """Adds an edge between two spiders."""
    u: VT
    v: VT
    ety: EdgeType

    def undo(self) -> None:
        self.g.remove_edge((self.u, self.v, self.ety))
        self.update_graph_view()

    def redo(self) -> None:
        self.g.add_edge(((self.u, self.v)), self.ety)
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
class MoveNodeProofMode(MoveNode):
    step_view: ProofStepView

    def __init__(self, graph_view: GraphView, vs: list[tuple[VT, float, float]], step_view: ProofStepView) -> None:
        super().__init__(graph_view, vs)
        self.step_view = step_view
        self.proof_step_index = int(step_view.currentIndex().row())

    def undo(self) -> None:
        self.step_view.move_to_step(self.proof_step_index)
        super().undo()
        self.step_view.model().set_graph(self.proof_step_index, self.graph_view.graph_scene.g)

    def redo(self) -> None:
        self.step_view.move_to_step(self.proof_step_index)
        super().redo()
        self.step_view.model().set_graph(self.proof_step_index, self.graph_view.graph_scene.g)


@dataclass
class ChangeEdgeCurve(BaseCommand):
    """Changes the curve of an edge."""
    eitem: EItem
    new_distance: float
    old_distance: float

    def undo(self) -> None:
        self.eitem.curve_distance = self.old_distance
        self.eitem.refresh()

    def redo(self) -> None:
        self.eitem.curve_distance = self.new_distance
        self.eitem.refresh()


@dataclass
class AddIdentity(BaseCommand):
    """Adds an X or Z identity spider on an edge between two vertices."""
    u: VT
    v: VT
    vty: VertexType

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
    new_phase: Union[Fraction, Poly, complex]

    _old_phase: Optional[Union[Fraction, Poly, complex]] = field(default=None, init=False)

    def undo(self) -> None:
        assert self._old_phase is not None
        if self.g.type(self.v) == VertexType.Z_BOX:
            set_z_box_label(self.g, self.v, self._old_phase)
        else:
            self.g.set_phase(self.v, self._old_phase)
        self.update_graph_view()

    def redo(self) -> None:
        if self.g.type(self.v) == VertexType.Z_BOX:
            self._old_phase = get_z_box_label(self.g, self.v)
            set_z_box_label(self.g, self.v, self.new_phase)
        else:
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
class AddRewriteStep(UpdateGraph):
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
        self._old_selected = int(self.step_view.currentIndex().row())
        self._old_steps = []
        for _ in range(self.proof_model.rowCount() - self._old_selected - 1):
            self._old_steps.append(self.proof_model.pop_rewrite())

        self.proof_model.add_rewrite(Rewrite(self.name, self.name, self.new_g))

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
            self.proof_model.add_rewrite(rewrite)

        # Select the previously selected step
        assert self._old_selected is not None
        idx = self.step_view.model().index(self._old_selected, 0, QModelIndex())
        self.step_view.selectionModel().blockSignals(True)
        self.step_view.setCurrentIndex(idx)
        self.step_view.selectionModel().blockSignals(False)
        super().undo()


@dataclass
class GroupRewriteSteps(BaseCommand):
    step_view: ProofStepView
    start_index: int
    end_index: int

    def redo(self) -> None:
        self.step_view.model().group_steps(self.start_index, self.end_index)
        self.step_view.move_to_step(self.start_index + 1)

    def undo(self) -> None:
        self.step_view.model().ungroup_steps(self.start_index)
        self.step_view.move_to_step(self.end_index + 1)

@dataclass
class UngroupRewriteSteps(BaseCommand):
    step_view: ProofStepView
    group_index: int

    def redo(self) -> None:
        self.step_view.model().ungroup_steps(self.group_index)
        self.step_view.move_to_step(self.group_index + 1)

    def undo(self) -> None:
        self.step_view.model().group_steps(self.group_index, self.group_index + 1)
        self.step_view.move_to_step(self.group_index + 1)
