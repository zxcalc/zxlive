from __future__ import annotations

import copy
from typing import Optional, TYPE_CHECKING, Union

from pyzx.utils import VertexType, FractionLike, set_z_box_label
from pyzx.rewrite import RewriteSimpGraph
from pyzx.graph.base import BaseGraph

from .common import VT, ET, GraphT
from .unfusion_dialog import UnfusionDialog, UnfusionModeManager
from .eitem import EItem

if TYPE_CHECKING:
    from .proof_panel import ProofPanel


def compute_avg_neighbor_direction(graph: GraphT, origin: VT, edges: list[ET]) -> tuple[float, float]:
    """Average normalized direction from ``origin`` toward each edge's other endpoint,
    snapped to the dominant axis.

    Returns ``(0, 0)`` if there are no (non-self-loop) edges or all directions cancel
    out exactly.
    """
    origin_row = graph.row(origin)
    origin_qubit = graph.qubit(origin)
    sum_x = sum_y = 0.0
    for edge in edges:
        s, t = graph.edge_st(edge)
        other = s if t == origin else t
        if other == origin:
            continue  # Self-loops have no meaningful direction.
        dx = graph.row(other) - origin_row
        dy = graph.qubit(other) - origin_qubit
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            sum_x += dx / length
            sum_y += dy / length
    if sum_x == 0 and sum_y == 0:
        return (0.0, 0.0)
    if abs(sum_x) > abs(sum_y):
        return (1.0 if sum_x > 0 else -1.0, 0.0)
    return (0.0, 1.0 if sum_y > 0 else -1.0)


def compute_unfusion_positions(
    graph: GraphT,
    original_vertex: VT,
    node1_edges: list[ET],
    node2_edges: list[ET],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Compute default placements for the two new unfusion vertices.

    Each new vertex is offset from the original in the average direction of its
    assigned edges' neighbours (snapped to the dominant axis). If one side has no
    edges, it is placed opposite to the other. If both sides are empty (e.g., an
    isolated vertex), falls back to a symmetric diagonal offset. If both sides
    snap to the same direction, the two vertices are nudged perpendicularly so
    they don't end up on top of each other.
    """
    original_row = graph.row(original_vertex)
    original_qubit = graph.qubit(original_vertex)

    avg1 = compute_avg_neighbor_direction(graph, original_vertex, node1_edges)
    avg2 = compute_avg_neighbor_direction(graph, original_vertex, node2_edges)

    if avg1 == (0.0, 0.0) and avg2 == (0.0, 0.0):
        offset = 0.3
        return ((original_row - offset, original_qubit - offset),
                (original_row + offset, original_qubit + offset))
    if avg2 == (0.0, 0.0):
        avg2 = (-avg1[0], -avg1[1])
    elif avg1 == (0.0, 0.0):
        avg1 = (-avg2[0], -avg2[1])

    orthogonal = (avg1[0] * avg2[0] + avg1[1] * avg2[1]) == 0
    dist = 0.35 if orthogonal else 0.25

    pos1 = (original_row + dist * avg1[0], original_qubit + dist * avg1[1])
    pos2 = (original_row + dist * avg2[0], original_qubit + dist * avg2[1])

    if avg1 == avg2:
        # Both partitions snap to the same direction (e.g., all neighbours on the
        # same side); offset perpendicularly so the two new vertices stay distinct.
        perp_dist = 0.15
        perp = (-avg1[1], avg1[0])
        pos1 = (pos1[0] - perp_dist * perp[0], pos1[1] - perp_dist * perp[1])
        pos2 = (pos2[0] + perp_dist * perp[0], pos2[1] + perp_dist * perp[1])

    return pos1, pos2


def _reassign_edges_from_original(graph: GraphT, original_vertex: VT,
                                  edges: list[ET], new_node: VT) -> None:
    """Move ``edges`` from ``original_vertex`` to ``new_node`` in-place on ``graph``."""
    # TODO: preserve the edge curve here once it is supported (see #270).
    for edge in edges:
        if edge not in graph.edges():
            continue
        s, t = graph.edge_st(edge)
        other_vertex = s if t == original_vertex else t
        if other_vertex == original_vertex:
            other_vertex = new_node  # Self-loop case.
        edge_type = graph.edge_type(edge)
        graph.add_edge((other_vertex, new_node), edge_type)
        graph.remove_edge(edge)


def apply_unfusion(
    graph: GraphT,
    original_vertex: VT,
    node1_edges: list[ET],
    node2_edges: list[ET],
    num_connecting_edges: int,
    phase1: Union[FractionLike, complex],
    phase2: Union[FractionLike, complex],
    node1_pos: Optional[tuple[float, float]] = None,
    node2_pos: Optional[tuple[float, float]] = None,
) -> GraphT:
    """Build a new graph in which ``original_vertex`` is unfused into two new vertices.

    The two new vertices take the same type as the original. Edges incident on the
    original are reassigned to the new vertices according to ``node1_edges`` and
    ``node2_edges``, and ``num_connecting_edges`` regular edges are added between
    the new vertices. The original vertex is then removed.

    If ``node1_pos`` or ``node2_pos`` is omitted, the new vertex is placed via
    :func:`compute_unfusion_positions`, which offsets it from the original in the
    average direction of its assigned edges' neighbours.
    """
    if num_connecting_edges < 1:
        raise ValueError("Number of connecting edges must be at least 1.")

    new_g = copy.deepcopy(graph)
    original_type = graph.type(original_vertex)

    if node1_pos is None or node2_pos is None:
        default_pos1, default_pos2 = compute_unfusion_positions(
            graph, original_vertex, node1_edges, node2_edges)
        node1_pos = node1_pos or default_pos1
        node2_pos = node2_pos or default_pos2

    node1 = new_g.add_vertex(original_type, row=node1_pos[0], qubit=node1_pos[1])
    node2 = new_g.add_vertex(original_type, row=node2_pos[0], qubit=node2_pos[1])

    if original_type in (VertexType.Z, VertexType.X):
        new_g.set_phase(node1, phase1)
        new_g.set_phase(node2, phase2)
    elif original_type == VertexType.Z_BOX:
        set_z_box_label(new_g, node1, phase1)
        set_z_box_label(new_g, node2, phase2)

    _reassign_edges_from_original(new_g, original_vertex, node1_edges, node1)
    _reassign_edges_from_original(new_g, original_vertex, node2_edges, node2)

    for _ in range(num_connecting_edges):
        new_g.add_edge((node1, node2))

    new_g.remove_vertex(original_vertex)
    return new_g


def match_unfuse_single_vertex(graph: GraphT, vertices: list[VT]) -> list[VT]:
    """Matcher for unfusion - matches single selected vertices that can be unfused."""
    if len(vertices) == 1 and (graph.type(vertices[0]) not in (VertexType.BOUNDARY,
                                                               VertexType.DUMMY,
                                                               VertexType.H_BOX,
                                                               VertexType.W_INPUT,
                                                               VertexType.W_OUTPUT)):  # TODO: Support H_BOX and W node unfusions
        return vertices
    return []


class UnfusionRewrite(RewriteSimpGraph[VT, ET]):
    """RewriteSimpGraph subclass with an is_match method for unfusion.

    The actual unfusion logic is handled interactively by UnfusionRewriteAction,
    so apply/simp just raise NotImplementedError.
    """

    def __init__(self) -> None:
        def _no_op_applier(graph: BaseGraph[VT, ET], vertices: list[VT]) -> bool:
            raise NotImplementedError("Interactive unfusion should be handled by UnfusionRewriteAction.")

        def _no_op_simp(graph: BaseGraph[VT, ET]) -> bool:
            raise NotImplementedError("Interactive unfusion should be handled by UnfusionRewriteAction.")

        super().__init__(_no_op_applier, _no_op_simp)

    def is_match(self, graph: GraphT, vertices: list[VT]) -> bool:  # type: ignore[override]
        return bool(match_unfuse_single_vertex(graph, vertices))


unfusion_rewrite: UnfusionRewrite = UnfusionRewrite()


class UnfusionRewriteAction:
    """Special rewrite action that handles the interactive unfusion process."""

    def __init__(self, proof_panel: ProofPanel) -> None:
        self.proof_panel = proof_panel
        self.unfusion_manager: UnfusionModeManager | None = None
        self.dialog: UnfusionDialog | None = None

    def can_unfuse(self, vertex: VT) -> bool:
        """Check if a vertex can be unfused."""
        graph = self.proof_panel.graph_scene.g
        return bool(graph.type(vertex) != VertexType.BOUNDARY)

    def start_unfusion(self, vertex: VT) -> bool:
        """Start the unfusion process for a vertex."""
        if not self.can_unfuse(vertex):
            return False

        self.unfusion_manager = UnfusionModeManager(self.proof_panel.graph_scene, vertex)
        self.unfusion_manager.enter_mode()

        self.proof_panel.graph_scene.selection_changed_custom.connect(self._on_selection_changed)

        # Show the configuration dialog
        graph = self.proof_panel.graph_scene.g
        original_phase = graph.phase(vertex) if graph.type(vertex) in (VertexType.Z, VertexType.X) else 0

        self.dialog = UnfusionDialog(original_phase, self.proof_panel.graph_scene.g, self.proof_panel)
        self.dialog.confirmed.connect(self._on_confirmed)
        self.dialog.cancelled.connect(self._on_cancelled)
        self.dialog.show()

        return True

    def _on_selection_changed(self) -> None:
        """Handle selection changes to catch edge selections."""
        if self.unfusion_manager and self.unfusion_manager.active:
            # Check if any edges are selected and toggle them
            scene = self.proof_panel.graph_scene
            for item in scene.selectedItems():
                if isinstance(item, EItem):
                    # Check if this edge is connected to target vertex
                    graph = scene.g
                    s, t = graph.edge_st(item.e)
                    if s == self.unfusion_manager.target_vertex or t == self.unfusion_manager.target_vertex:
                        self.unfusion_manager.toggle_edge_selection(item)

    def _on_confirmed(self, num_connecting_edges: int, phase1: FractionLike, phase2: FractionLike) -> None:
        """Handle confirmation of the unfusion parameters."""
        if not self.unfusion_manager:
            return
        node1_edges, node2_edges = self.unfusion_manager.get_edge_assignments()
        self._record_unfusion_step(self.unfusion_manager.target_vertex, node1_edges, node2_edges,
                                   num_connecting_edges, phase1, phase2)
        self._cleanup()

    def _on_cancelled(self) -> None:
        """Handle cancellation of the unfusion."""
        self._cleanup()

    def _record_unfusion_step(self, original_vertex: VT, node1_edges: list[ET],
                               node2_edges: list[ET], num_connecting_edges: int,
                               phase1: FractionLike, phase2: FractionLike) -> None:
        """Apply the unfusion to the graph and push it onto the undo stack as a proof step."""
        from .commands import AddRewriteStep
        from . import animations as anims
        from .rewrite_data import rules_basic

        graph = self.proof_panel.graph_scene.g
        new_g = apply_unfusion(graph, original_vertex, node1_edges, node2_edges,
                               num_connecting_edges, phase1, phase2)

        cmd = AddRewriteStep(self.proof_panel.graph_view, new_g,
                             self.proof_panel.step_view, rules_basic['unfuse']['text'])
        anim = anims.unfuse(graph, new_g, original_vertex, self.proof_panel.graph_scene)
        self.proof_panel.undo_stack.push(cmd, anim_after=anim)

    def _cleanup(self) -> None:
        """Clean up the unfusion mode."""
        if self.unfusion_manager:
            self.unfusion_manager.exit_mode()
            self.unfusion_manager = None
        if self.dialog:
            self.dialog.close()
            self.dialog = None
        try:
            self.proof_panel.graph_scene.selection_changed_custom.disconnect(self._on_selection_changed)
        except RuntimeError:
            pass  # Connection might not exist
