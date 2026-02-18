from __future__ import annotations

import copy
from typing import TYPE_CHECKING, cast

from pyzx.utils import VertexType, FractionLike
from pyzx.rewrite import RewriteSimpGraph
from pyzx.graph.base import BaseGraph

from .common import VT, ET, GraphT
from .unfusion_dialog import UnfusionDialog, UnfusionModeManager
from .eitem import EItem

if TYPE_CHECKING:
    from .proof_panel import ProofPanel


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
        return (graph.type(vertex) != VertexType.BOUNDARY and
                len(list(graph.incident_edges(vertex))) >= 2)

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
        self._apply_unfusion(self.unfusion_manager.target_vertex, node1_edges, node2_edges,
                             num_connecting_edges, phase1, phase2)
        self._cleanup()

    def _on_cancelled(self) -> None:
        """Handle cancellation of the unfusion."""
        self._cleanup()

    def _apply_unfusion(self, original_vertex: VT, node1_edges: list[ET],
                        node2_edges: list[ET], num_connecting_edges: int,
                        phase1: FractionLike, phase2: FractionLike) -> None:
        """Apply the actual unfusion transformation."""
        from .commands import AddRewriteStep
        from . import animations as anims

        graph = self.proof_panel.graph_scene.g
        new_g = copy.deepcopy(graph)

        original_type = graph.type(original_vertex)
        original_row = graph.row(original_vertex)
        original_qubit = graph.qubit(original_vertex)

        # Create two new vertices
        # Position them slightly apart from the original position
        offset = 0.3
        node1 = new_g.add_vertex(original_type,
                                 qubit=original_qubit - offset,
                                 row=original_row - offset)
        node2 = new_g.add_vertex(original_type,
                                 qubit=original_qubit + offset,
                                 row=original_row + offset)

        # Set phases for the new vertices
        if original_type in (VertexType.Z, VertexType.X):
            new_g.set_phase(node1, phase1)
            new_g.set_phase(node2, phase2)
        elif original_type == VertexType.Z_BOX:
            from pyzx.utils import set_z_box_label
            set_z_box_label(new_g, node1, phase1)
            set_z_box_label(new_g, node2, phase2)

        def reassign_edges(edges: list[ET], node: VT) -> None:
            for edge in edges:
                if edge not in new_g.edges():
                    continue
                s, t = new_g.edge_st(edge)
                other_vertex = s if t == original_vertex else t
                if other_vertex == original_vertex:
                    other_vertex = node  # Self-loop case
                edge_type = new_g.edge_type(edge)
                new_g.add_edge((other_vertex, node), edge_type)
                new_g.remove_edge(edge)

        reassign_edges(node1_edges, node1)
        reassign_edges(node2_edges, node2)

        # Add connecting edges between the two new vertices
        if num_connecting_edges < 1:
            raise ValueError("Number of connecting edges must be at least 1.")
        for _ in range(num_connecting_edges):
            new_g.add_edge((node1, node2))

        # Remove the original vertex
        new_g.remove_vertex(original_vertex)

        from .rewrite_data import rules_basic
        rewrite_name = cast(str, rules_basic['unfuse']['text'])
        cmd = AddRewriteStep(self.proof_panel.graph_view, new_g,
                             self.proof_panel.step_view, rewrite_name)
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
