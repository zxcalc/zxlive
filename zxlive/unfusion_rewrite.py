from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import pyzx
from pyzx.utils import EdgeType, VertexType

from .common import VT, ET, GraphT
from .unfusion_dialog import UnfusionDialog, UnfusionModeManager
from .eitem import EItem

if TYPE_CHECKING:
    from .proof_panel import ProofPanel


def match_unfuse_single_vertex(graph: GraphT, matches) -> list[VT]:
    """Matcher for unfusion - matches single selected vertices that can be unfused."""
    vertices = [v for v in graph.vertices() if matches(v)]
    valid_vertices = []
    
    for v in vertices:
        # Only allow unfusion for vertices that are not boundary vertices
        # and have at least 2 incident edges
        if (graph.type(v) != VertexType.BOUNDARY and 
            len(list(graph.incident_edges(v))) >= 2):
            valid_vertices.append(v)
    
    return valid_vertices


def apply_unfuse_rule(graph: GraphT, vertices: list[VT]) -> pyzx.rules.RewriteOutputType[VT, ET]:
    """Apply the unfusion rule to a single vertex."""
    if len(vertices) != 1:
        return ({}, [], [], True)
    
    # This function should not be called directly for the interactive unfusion
    # It's here for compatibility with the rewrite system structure
    # The actual unfusion logic is handled by the UnfusionRewriteAction
    return ({}, [], [], True)


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
        
        # Enter Direct Edge Selection Mode
        self.unfusion_manager = UnfusionModeManager(self.proof_panel.graph_scene, vertex)
        self.unfusion_manager.enter_mode()
        
        # Connect edge click handler
        self.proof_panel.graph_scene.edge_double_clicked.connect(self._on_edge_clicked)
        
        # Force signal connection activation (required for Qt signal system)
        # This dummy signal ensures the connection is properly established
        self.proof_panel.graph_scene.edge_double_clicked.emit(None)
        
        # Also connect to selection changed to catch edge selection
        self.proof_panel.graph_scene.selection_changed_custom.connect(self._on_selection_changed)
        
        # Show the configuration dialog
        graph = self.proof_panel.graph_scene.g
        original_phase = graph.phase(vertex) if graph.type(vertex) in (VertexType.Z, VertexType.X) else 0
        
        self.dialog = UnfusionDialog(original_phase, self.proof_panel)
        self.dialog.confirmed.connect(self._on_confirmed)
        self.dialog.cancelled.connect(self._on_cancelled)
        self.dialog.show()
        
        return True
    
    def _on_edge_clicked(self, edge: ET) -> None:
        """Handle edge click during selection mode."""
        if edge is None:
            return
            
        if self.unfusion_manager and self.unfusion_manager.active:
            # Check if this edge is connected to the target vertex
            graph = self.proof_panel.graph_scene.g
            try:
                s, t = graph.edge_st(edge)
                if s == self.unfusion_manager.target_vertex or t == self.unfusion_manager.target_vertex:
                    self.unfusion_manager.toggle_edge_selection(edge)
            except Exception as e:
                pass  # Ignore errors for robustness
    
    def _on_selection_changed(self) -> None:
        """Handle selection changes to potentially catch edge selections."""
        if self.unfusion_manager and self.unfusion_manager.active:
            # Check if any edges are selected and toggle them
            scene = self.proof_panel.graph_scene
            for item in scene.selectedItems():
                if isinstance(item, EItem):
                    # Check if this edge is connected to target vertex
                    graph = scene.g
                    s, t = graph.edge_st(item.e)
                    if s == self.unfusion_manager.target_vertex or t == self.unfusion_manager.target_vertex:
                        self.unfusion_manager.toggle_edge_selection(item.e)
    
    def _on_confirmed(self, num_connecting_edges: int, phase1: complex, phase2: complex) -> None:
        """Handle confirmation of the unfusion parameters."""
        if not self.unfusion_manager:
            return
        
        # Get edge assignments
        node1_edges, node2_edges = self.unfusion_manager.get_edge_assignments()
        target_vertex = self.unfusion_manager.target_vertex
        
        # Apply the unfusion
        self._apply_unfusion(target_vertex, node1_edges, node2_edges, 
                           num_connecting_edges, phase1, phase2)
        
        # Clean up
        self._cleanup()
    
    def _on_cancelled(self) -> None:
        """Handle cancellation of the unfusion."""
        self._cleanup()
    
    def _apply_unfusion(self, original_vertex: VT, node1_edges: set[ET], 
                       node2_edges: set[ET], num_connecting_edges: int,
                       phase1: complex, phase2: complex) -> None:
        """Apply the actual unfusion transformation."""
        from .commands import AddRewriteStep
        from . import animations as anims
        
        graph = self.proof_panel.graph_scene.g
        new_g = copy.deepcopy(graph)
        
        # Get original vertex properties
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
        
        # Reassign edges
        for edge in node1_edges:
            if edge in new_g.edges():
                s, t = graph.edge_st(edge)
                other_vertex = s if t == original_vertex else t
                edge_type = graph.edge_type(edge)
                new_g.add_edge((other_vertex, node1), edge_type)
                new_g.remove_edge(edge)
        
        for edge in node2_edges:
            if edge in new_g.edges():
                s, t = graph.edge_st(edge)
                other_vertex = s if t == original_vertex else t
                edge_type = graph.edge_type(edge)
                new_g.add_edge((other_vertex, node2), edge_type)
                new_g.remove_edge(edge)
        
        # Add connecting edges between the two new vertices
        for _ in range(num_connecting_edges):
            new_g.add_edge((node1, node2))
        
        # Remove the original vertex
        new_g.remove_vertex(original_vertex)
        
        # Create the rewrite step
        cmd = AddRewriteStep(self.proof_panel.graph_view, new_g, 
                           self.proof_panel.step_view, "unfuse")
        
        # Create animation
        anim = anims.unfuse(graph, new_g, original_vertex, self.proof_panel.graph_scene)
        
        # Apply the change
        self.proof_panel.undo_stack.push(cmd, anim_after=anim)
    
    def _cleanup(self) -> None:
        """Clean up the unfusion mode."""
        if self.unfusion_manager:
            self.unfusion_manager.exit_mode()
            self.unfusion_manager = None
        
        if self.dialog:
            self.dialog.close()
            self.dialog = None
        
        # Disconnect edge click handlers
        try:
            self.proof_panel.graph_scene.edge_double_clicked.disconnect(self._on_edge_clicked)
        except:
            pass  # Connection might not exist
            
        try:
            self.proof_panel.graph_scene.selection_changed_custom.disconnect(self._on_selection_changed)
        except:
            pass  # Connection might not exist
