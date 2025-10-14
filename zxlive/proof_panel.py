from __future__ import annotations

import copy
import random
from typing import Iterator, Optional, Union, cast

from PySide6.QtCore import QPointF, QSize
from PySide6.QtGui import QAction, QIcon, QVector2D
from PySide6.QtWidgets import QInputDialog, QToolButton

import pyzx
from pyzx import basicrules
from pyzx.graph.jsonparser import string_to_phase
from pyzx.utils import (EdgeType, VertexType, FractionLike, get_w_partner, get_z_box_label,
                        set_z_box_label, vertex_is_z_like)

from . import animations as anims
from .base_panel import BasePanel, ToolbarSection
from .commands import AddEdge, AddNode, AddRewriteStep, ChangeEdgeCurve, MoveNode, SetGraph, UpdateGraph, ProofModeCommand
from .common import ET, VT, GraphT, ToolType, get_data, pos_from_view, pos_to_view
from .dialogs import show_error_msg, update_dummy_vertex_text
from .editor_base_panel import string_to_complex
from .eitem import EItem
from .graphscene import EditGraphScene
from .graphview import GraphTool, ProofGraphView, WandTrace
from .proof import ProofModel, ProofStepView
from .rewrite_action import RewriteActionTreeView
from .settings import display_setting
from .sfx import SFXEnum
from .vitem import SCALE, W_INPUT_OFFSET, DragState, VItem


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZXLive."""

    graph_scene: EditGraphScene

    def __init__(self, graph: GraphT, *actions: QAction) -> None:
        super().__init__(*actions)
        self.graph_scene = EditGraphScene()
        self.graph_view = ProofGraphView(self.graph_scene)
        self.splitter.addWidget(self.graph_view)
        self.graph_view.set_graph(graph)

        self.rewrites_panel = RewriteActionTreeView(self)
        self.splitter.insertWidget(0, self.rewrites_panel)

        self.graph_view.wand_trace_finished.connect(self._wand_trace_finished)
        self.graph_scene.vertex_dragged.connect(self._vertex_dragged)
        self.graph_scene.vertex_dropped_onto.connect(self._vertex_dropped_onto)
        self.graph_scene.edge_dragged.connect(self.change_edge_curves)
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        self.graph_scene.vertex_double_clicked.connect(self._vert_double_clicked)
        self.graph_scene.edge_double_clicked.connect(self._edge_double_clicked)

        self.graph_scene.vertex_added.connect(self._add_dummy_node)
        self.graph_scene.edge_added.connect(self._add_dummy_edge)

        self.step_view = ProofStepView(self)

        self.splitter.addWidget(self.step_view)

    @property
    def proof_model(self) -> ProofModel:
        return self.step_view.model()

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        icon_size = QSize(32, 32)
        self.selection = QToolButton(self)
        self.selection.setCheckable(True)
        self.selection.setChecked(True)
        self.magic_wand = QToolButton(self)
        self.magic_wand.setCheckable(True)
        self.selection.setIcon(QIcon(get_data("icons/tikzit-tool-select.svg")))
        self.magic_wand.setIcon(QIcon(get_data("icons/magic-wand.svg")))
        self.selection.setIconSize(icon_size)
        self.magic_wand.setIconSize(icon_size)
        self.selection.setToolTip("Select (s)")
        self.magic_wand.setToolTip("Magic Wand (w)")
        self.selection.setShortcut("s")
        self.magic_wand.setShortcut("w")
        self.selection.clicked.connect(self._selection_clicked)
        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        # --- Dummy node/edge addition ---
        self._dummy_icon = QToolButton(self)
        self._dummy_icon.setCheckable(True)
        self._dummy_icon.setIcon(QIcon(get_data("icons/tikzit-tool-node.svg")))
        self._dummy_icon.setIconSize(QSize(32, 32))
        self._dummy_icon.setToolTip("Add Dummy Vertex (v)")
        self._dummy_icon.setShortcut("v")
        self._dummy_icon.clicked.connect(self._dummy_node_mode_clicked)

        self._dummy_edge_icon = QToolButton(self)
        self._dummy_edge_icon.setCheckable(True)
        self._dummy_edge_icon.setIcon(QIcon(get_data("icons/tikzit-tool-edge.svg")))
        self._dummy_edge_icon.setIconSize(QSize(32, 32))
        self._dummy_edge_icon.setToolTip("Add Dummy Edge (e)")
        self._dummy_edge_icon.setShortcut("e")
        self._dummy_edge_icon.clicked.connect(self._dummy_edge_mode_clicked)
        yield ToolbarSection(self.selection, self._dummy_icon, self._dummy_edge_icon, self.magic_wand, exclusive=True)

        self.identity_choice = (
            QToolButton(self),
            QToolButton(self)
        )
        self.identity_choice[0].setText("Z")
        self.identity_choice[0].setCheckable(True)
        self.identity_choice[0].setChecked(True)
        self.identity_choice[1].setText("X")
        self.identity_choice[1].setCheckable(True)

        yield ToolbarSection(*self.identity_choice, exclusive=True)
        yield ToolbarSection(*self.actions())

    def update_font(self) -> None:
        self.rewrites_panel.setFont(display_setting.font)
        self.rewrites_panel.reset_rewrite_panel_style()
        super().update_font()

    def parse_selection(self) -> tuple[list[VT], list[ET]]:
        selection = list(self.graph_scene.selected_vertices)
        edges = set(self.graph_scene.selected_edges)
        g = self.graph_scene.g
        for e in g.edges():
            s,t = g.edge_st(e)
            if s in selection and t in selection:
                edges.add(e)

        return selection, list(edges)

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = ProofModeCommand(MoveNode(self.graph_view, vs), self.step_view)
        self.undo_stack.push(cmd)

    def change_edge_curves(self, eitem: EItem, new_distance: float, old_distance: float) -> None:
        cmd = ProofModeCommand(ChangeEdgeCurve(self.graph_view, eitem, new_distance, old_distance), self.step_view)
        self.undo_stack.push(cmd)

    def _selection_clicked(self) -> None:
        self.graph_scene.curr_tool = ToolType.SELECT
        self.graph_view.tool = GraphTool.Selection

    def _magic_wand_clicked(self) -> None:
        self.graph_scene.curr_tool = ToolType.SELECT
        self.graph_view.tool = GraphTool.MagicWand

    def _vertex_dragged(self, state: DragState, v: VT, w: VT) -> None:
        if state == DragState.Onto:
            if pyzx.basicrules.check_fuse(self.graph, v, w):
                anims.anticipate_fuse(self.graph_scene.vertex_map[w])
            elif pyzx.basicrules.check_strong_comp(self.graph, v, w):
                anims.anticipate_strong_comp(self.graph_scene.vertex_map[w])
            elif pyzx.hrules.match_copy(self.graph, lambda x: x in (v, w)): # This function takes a vertex matching function, which we restrict to just match to v and w
                anims.anticipate_strong_comp(self.graph_scene.vertex_map[w])
            elif self._check_h_bialgebra(v, w):
                anims.anticipate_strong_comp(self.graph_scene.vertex_map[w])
        else:
            anims.back_to_default(self.graph_scene.vertex_map[w])

    def _vertex_dropped_onto(self, v: VT, w: VT) -> None:
        g = copy.deepcopy(self.graph)
        if len(list(self.graph.edges(v, w))) == 1 and self.graph.edge_type(self.graph.edge(v, w)) == EdgeType.HADAMARD:
            basicrules.color_change(g, w)
        if pyzx.basicrules.check_fuse(g, v, w):
            pyzx.basicrules.fuse(g, w, v)
            anim = anims.fuse(self.graph_scene.vertex_map[v], self.graph_scene.vertex_map[w])
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "fuse spiders")
            self.play_sound_signal.emit(SFXEnum.THATS_SPIDER_FUSION)
            self.undo_stack.push(cmd, anim_before=anim)
        elif pyzx.hrules.match_copy(g, lambda x: x in (v, w)):
            match = pyzx.hrules.match_copy(g, lambda x: x in (v, w))
            etab, rem_verts, rem_edges, check_isolated_vertices = pyzx.hrules.apply_copy(g, match)
            g.add_edge_table(etab)
            g.remove_edges(rem_edges)
            g.remove_vertices(rem_verts)
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "copy")
            self.undo_stack.push(cmd, anim_after=anim)
        elif pyzx.basicrules.check_strong_comp(g, v, w):
            pyzx.basicrules.strong_comp(g, w, v)
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "bialgebra")
            self.play_sound_signal.emit(SFXEnum.BOOM_BOOM_BOOM)
            self.undo_stack.push(cmd, anim_after=anim)
        elif self._apply_h_color_change(g, v, w):
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "H-box color change")
            self.undo_stack.push(cmd, anim_after=anim)
        elif self._apply_h_bialgebra(g, v, w):
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "H-bialgebra")
            self.play_sound_signal.emit(SFXEnum.BOOM_BOOM_BOOM)
            self.undo_stack.push(cmd, anim_after=anim)
        else:
            view_pos = self.graph_scene.vertex_map[v].pos()
            pos = pos_from_view(view_pos.x(), view_pos.y())
            move_cmd = ProofModeCommand(MoveNode(self.graph_view, [(v, pos[0], pos[1])]), self.step_view)
            self.undo_stack.push(move_cmd)

    def _check_h_bialgebra(self, v: VT, w: VT) -> bool:
        """Check if we can apply H-bialgebra or H-box color change."""
        v_type = self.graph.type(v)
        w_type = self.graph.type(w)
        
        # Check if one is an H-box and the other is a Z or X spider
        if v_type == VertexType.H_BOX and w_type in (VertexType.Z, VertexType.X):
            return True
        if w_type == VertexType.H_BOX and v_type in (VertexType.Z, VertexType.X):
            return True
        return False

    def _apply_h_color_change(self, g: GraphT, v: VT, w: VT) -> bool:
        """Apply color change when a 2-ary H-box is dropped on a Z/X spider.
        
        This implements the ZH rewrite where dropping a Hadamard (2-ary H-box) on a spider
        causes a color change and connects the H-box neighbors to the spider with appropriate edges.
        """
        v_type = g.type(v)
        w_type = g.type(w)
        
        # Determine which is the H-box and which is the spider
        if v_type == VertexType.H_BOX and w_type in (VertexType.Z, VertexType.X):
            h_box, spider = v, w
        elif w_type == VertexType.H_BOX and v_type in (VertexType.Z, VertexType.X):
            h_box, spider = w, v
        else:
            return False
        
        # Check if H-box is a Hadamard (arity 2)
        if not pyzx.hrules.is_hadamard(g, h_box):
            return False
        
        # Get the neighbors of the H-box
        h_neighbors = list(g.neighbors(h_box))
        if len(h_neighbors) != 2:
            return False
        
        # Apply the transformation:
        # The H-box acts as a Hadamard gate between its two neighbors
        # When dropped on a spider, we:
        # 1. Connect both H-box neighbors to the spider
        # 2. Color change the spider (which flips the spider type and toggles all edge types)
        # 3. Remove the H-box
        n1, n2 = h_neighbors
        
        # Connect both neighbors to the spider with simple edges (if not already connected)
        if not g.connected(n1, spider):
            g.add_edge((n1, spider), EdgeType.SIMPLE)
        if not g.connected(n2, spider):
            g.add_edge((n2, spider), EdgeType.SIMPLE)
        
        # Color change the spider (this flips spider type and all adjacent edge types)
        basicrules.color_change(g, spider)
        
        # Remove the H-box
        g.remove_vertex(h_box)
        
        return True

    def _apply_h_bialgebra(self, g: GraphT, v: VT, w: VT) -> bool:
        """Apply H-bialgebra when an H-box is dropped on a Z/X spider.
        
        This implements the ZH bialgebra rewrite where dropping an H-box on a spider
        connects all H-box neighbors to all spider neighbors, similar to regular bialgebra
        but with colors flipped.
        """
        v_type = g.type(v)
        w_type = g.type(w)
        
        # Determine which is the H-box and which is the spider
        if v_type == VertexType.H_BOX and w_type in (VertexType.Z, VertexType.X):
            h_box, spider = v, w
        elif w_type == VertexType.H_BOX and v_type in (VertexType.Z, VertexType.X):
            h_box, spider = w, v
        else:
            return False
        
        # Skip if this is a 2-ary H-box (handled by color change)
        if pyzx.hrules.is_hadamard(g, h_box):
            return False
        
        # Get neighbors
        h_neighbors = list(g.neighbors(h_box))
        spider_neighbors = list(g.neighbors(spider))
        
        # Check arity conditions (similar to strong_comp)
        if len(h_neighbors) <= 1 or len(spider_neighbors) <= 1:
            return False
        
        # Apply the H-bialgebra transformation:
        # 1. Connect all H-box neighbors to all spider neighbors
        # 2. Color change the spider
        # 3. Remove the H-box and spider
        
        for hn in h_neighbors:
            for sn in spider_neighbors:
                if hn != sn and not g.connected(hn, sn):  # Avoid self-loops and duplicate edges
                    g.add_edge((hn, sn), EdgeType.SIMPLE)
        
        # Color change the spider before removing
        basicrules.color_change(g, spider)
        
        # Remove the H-box and spider
        g.remove_vertex(h_box)
        g.remove_vertex(spider)
        
        return True

    def _wand_trace_finished(self, trace: WandTrace) -> None:
        if self._magic_slice(trace):
            return
        elif self._magic_identity(trace):
            return
        elif self._magic_hopf(trace):
            self.play_sound_signal.emit(SFXEnum.THEY_FALL_OFF)
            return

    def _magic_hopf(self, trace: WandTrace) -> bool:
        if not all(isinstance(item, EItem) for item in trace.hit):
            return False
        edges: list[ET] = [item.e for item in trace.hit]  # type: ignore  # We know that the type of `item` is `EItem` because of the check above
        if len(edges) == 0:
            return False
        if not all(edge == edges[0] for edge in edges):
            return False
        source, target = self.graph.edge_st(edges[0])
        source_type, target_type = self.graph.type(source), self.graph.type(target)
        edge_type = self.graph.edge_type(edges[0])
        if (edge_type == EdgeType.HADAMARD and vertex_is_z_like(source_type) and vertex_is_z_like(target_type)) or \
           (edge_type == EdgeType.SIMPLE and vertex_is_z_like(source_type) and target_type == VertexType.X) or \
           (edge_type == EdgeType.SIMPLE and source_type == VertexType.X and vertex_is_z_like(target_type)):
            new_g = copy.deepcopy(self.graph)
            num_edges = len(edges)
            # Remove even number of edges
            if num_edges % 2 != 0:
                num_edges -= 1
            for _ in range(num_edges): # TODO: This doesn't take into account the global scalar factor.
                new_g.remove_edge(edges[0])
            # TODO: Add animation for Hopf
            # anim = anims.hopf(edges, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "Hopf")
            self.undo_stack.push(cmd)
            return True
        return False

    def _magic_identity(self, trace: WandTrace) -> bool:
        if len(trace.hit) != 1 or not all(isinstance(item, EItem) for item in trace.hit):
            return False
        # We know that the type of `item` is `EItem` because of the check above
        item = cast(EItem, next(iter(trace.hit)))
        pos = trace.hit[item][-1]
        pos = QPointF(*pos_from_view(pos.x(), pos.y())) * SCALE
        s = self.graph.edge_s(item.e)
        t = self.graph.edge_t(item.e)
        if self.graph.type(s) == VertexType.DUMMY or self.graph.type(t) == VertexType.DUMMY:
            return False

        if self.identity_choice[0].isChecked():
            vty: VertexType = VertexType.Z
        elif self.identity_choice[1].isChecked():
            vty = VertexType.X
        else:
            raise ValueError("Neither of the spider types are checked.")

        new_g = copy.deepcopy(self.graph)
        v = new_g.add_vertex(vty, row=pos.x()/SCALE, qubit=pos.y()/SCALE)
        new_g.add_edge((s, v), self.graph.edge_type(item.e))
        new_g.add_edge((v, t))
        new_g.remove_edge(item.e)

        anim = anims.add_id(v, self.graph_scene)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "add identity")
        self.undo_stack.push(cmd, anim_after=anim)
        return True

    def _magic_slice(self, trace: WandTrace) -> bool:
        def cross(a: QPointF, b: QPointF) -> float:
            return float(a.y() * b.x() - a.x() * b.y())
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return False
        item = filtered[0]
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X, VertexType.Z_BOX, VertexType.W_OUTPUT):
            return False

        if not trace.shift and basicrules.check_remove_id(self.graph, vertex):
            self._remove_id(vertex)
            return True

        if trace.shift and self.graph.type(vertex) != VertexType.W_OUTPUT:
            phase_is_complex = (self.graph.type(vertex) == VertexType.Z_BOX)
            if phase_is_complex:
                prompt = "Enter desired phase value (complex value):"
                error_msg = "Please enter a valid input (e.g., -1+2j)."
            else:
                prompt = "Enter desired phase value (in units of pi):"
                error_msg = "Please enter a valid input (e.g., 1/2, 2, 0.25, 2a+b)."
            text, ok = QInputDialog().getText(self, "Choose Phase of one Spider", prompt)
            if not ok:
                return False
            try:
                phase = string_to_complex(text) if phase_is_complex else string_to_phase(text, self.graph)
            except ValueError:
                show_error_msg("Invalid Input", error_msg, parent=self)
                return False
        elif self.graph.type(vertex) != VertexType.W_OUTPUT:
            if self.graph.type(vertex) == VertexType.Z_BOX:
                phase = get_z_box_label(self.graph, vertex)
            else:
                phase = self.graph.phase(vertex)

        start = trace.hit[item][0]
        end = trace.hit[item][-1]
        if start.y() > end.y():
            start, end = end, start
        pos = QPointF(*pos_to_view(self.graph.row(vertex), self.graph.qubit(vertex)))
        left, right = [], []
        for edge in set(self.graph.incident_edges(vertex)):
            eitems = self.graph_scene.edge_map[edge]
            for eitem in eitems.values():
                # we use the selection node to determine the center of the edge
                epos = eitem.selection_node.pos()
                # Compute whether each edge is inside the entry and exit points
                i1 = cross(start - pos, epos - pos) * cross(start - pos, end - pos) >= 0
                i2 = cross(end - pos, epos - pos) * cross(end - pos, start - pos) >= 0
                inside = i1 and i2
                if inside:
                    left.append(eitem)
                else:
                    right.append(eitem)
        mouse_dir = ((start + end) * (1/2)) - pos

        if self.graph.type(vertex) == VertexType.W_OUTPUT:
            self._unfuse_w(vertex, left, mouse_dir)
        else:
            self._unfuse(vertex, left, right, mouse_dir, phase)
        return True

    def _remove_id(self, v: VT) -> None:
        new_g = copy.deepcopy(self.graph)
        basicrules.remove_id(new_g, v)
        anim = anims.remove_id(self.graph_scene.vertex_map[v])
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "remove identity")
        self.undo_stack.push(cmd, anim_before=anim)

        s = random.choice([
            SFXEnum.THATS_JUST_WIRE_1,
            SFXEnum.THATS_JUST_WIRE_2
        ])
        self.play_sound_signal.emit(s)

    def _reassign_edges_to_left_vertex(self, v: VT, new_g: GraphT, left_vert: VT,
                                       left_edge_items: list[EItem], skip_edge_type: Optional[EdgeType] = None) -> None:
        """Helper method to reassign edges from the original vertex to the new left vertex.

        Args:
            v: Original vertex
            new_g: New graph to modify
            left_vert: New left vertex to reassign edges to
            left_edge_items: Edge items that should be reassigned
            skip_edge_type: Optional edge type to skip during reassignment
        """
        for edge in set(self.graph.incident_edges(v)):
            if skip_edge_type is not None and self.graph.edge_type(edge) == skip_edge_type:
                continue
            edge_st = self.graph.edge_st(edge)
            neighbor = edge_st[0] if edge_st[1] == v else edge_st[1]
            eitems = self.graph_scene.edge_map[edge]
            for eitem in eitems.values():
                if eitem not in left_edge_items:
                    continue
                new_g.add_edge((neighbor, left_vert), self.graph.edge_type(edge))
                new_g.remove_edge(edge)

    def _finalize_unfuse(self, v: VT, new_g: GraphT) -> None:
        """Helper method to apply animation and push the unfuse command to the undo stack.
        """
        anim = anims.unfuse(self.graph, new_g, v, self.graph_scene)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "unfuse")
        self.undo_stack.push(cmd, anim_after=anim)

    def _unfuse_w(self, v: VT, left_edge_items: list[EItem], mouse_dir: QPointF) -> None:
        new_g = copy.deepcopy(self.graph)

        vi = get_w_partner(self.graph, v)
        par_dir = QVector2D(
            self.graph.row(v) - self.graph.row(vi),
            self.graph.qubit(v) - self.graph.qubit(vi)
        ).normalized()

        perp_dir = QVector2D(mouse_dir - QPointF(self.graph.row(v)/SCALE, self.graph.qubit(v)/SCALE)).normalized()
        perp_dir -= par_dir * QVector2D.dotProduct(perp_dir, par_dir)
        perp_dir.normalize()

        out_offset_x = par_dir.x() * 0.5 + perp_dir.x() * 0.5
        out_offset_y = par_dir.y() * 0.5 + perp_dir.y() * 0.5

        in_offset_x = out_offset_x - par_dir.x()*W_INPUT_OFFSET
        in_offset_y = out_offset_y - par_dir.y()*W_INPUT_OFFSET

        left_vert = new_g.add_vertex(VertexType.W_OUTPUT,
                                     qubit=self.graph.qubit(v) + out_offset_y,
                                     row=self.graph.row(v) + out_offset_x)
        left_vert_i = new_g.add_vertex(VertexType.W_INPUT,
                                     qubit=self.graph.qubit(v) + in_offset_y,
                                     row=self.graph.row(v) + in_offset_x)
        new_g.add_edge((left_vert_i, left_vert), EdgeType.W_IO)
        new_g.add_edge((v, left_vert_i))
        new_g.set_row(v, self.graph.row(v))
        new_g.set_qubit(v, self.graph.qubit(v))

        # TODO: preserve the edge curve here once it is supported (see https://github.com/zxcalc/zxlive/issues/270)
        self._reassign_edges_to_left_vertex(v, new_g, left_vert, left_edge_items, skip_edge_type=EdgeType.W_IO)
        self._finalize_unfuse(v, new_g)

    def _unfuse(self, v: VT, left_edge_items: list[EItem], right_edge_items: list[EItem], mouse_dir: QPointF, phase: Union[FractionLike, complex]) -> None:
        def snap_vector(v: QVector2D) -> None:
            if abs(v.x()) > abs(v.y()):
                v.setY(0.0)
            else:
                v.setX(0.0)
            if not v.isNull():
                v.normalize()

        def compute_avg_vector(pos: QPointF, neighbors: list[EItem]) -> QVector2D:
            avg_vector = QVector2D()
            for eitem in neighbors:
                eitem_pos = pos_from_view(eitem.selection_node.pos().x(), eitem.selection_node.pos().y())
                npos = QPointF(eitem_pos[0], eitem_pos[1])
                dir = QVector2D(npos - pos).normalized()
                avg_vector += dir
            avg_vector.normalize()
            return avg_vector

        pos = QPointF(self.graph.row(v), self.graph.qubit(v))
        avg_left = compute_avg_vector(pos, left_edge_items)
        snap_vector(avg_left)
        avg_right = compute_avg_vector(pos, right_edge_items)
        snap_vector(avg_right)

        if avg_right.isNull():
            avg_right = -avg_left
        elif avg_left.isNull():
            avg_left = -avg_right

        dist = 0.25 if QVector2D.dotProduct(avg_left, avg_right) != 0 else 0.35
        # Put the phase on the left hand side if the mouse direction is closer
        # to the average direction of the left neighbours than the right, i.e.,
        # associate the phase to the larger sliced area.
        phase_left = QVector2D.dotProduct(QVector2D(mouse_dir), avg_left) \
            >= QVector2D.dotProduct(QVector2D(mouse_dir), avg_right)

        new_g: GraphT = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(v),
                                     qubit=self.graph.qubit(v) + dist*avg_left.y(),
                                     row=self.graph.row(v) + dist*avg_left.x())
        new_g.set_row(v, self.graph.row(v) + dist*avg_right.x())
        new_g.set_qubit(v, self.graph.qubit(v) + dist*avg_right.y())
        new_g.add_edge((v, left_vert))

        # TODO: preserve the edge curve here once it is supported (see https://github.com/zxcalc/zxlive/issues/270)
        self._reassign_edges_to_left_vertex(v, new_g, left_vert, left_edge_items)

        first, second = (left_vert, v) if phase_left else (v, left_vert)
        if self.graph.type(v) == VertexType.Z_BOX:
            old_label = get_z_box_label(new_g, v)
            set_z_box_label(new_g, first, old_label / phase)
            set_z_box_label(new_g, second, phase)
        else:
            old_phase = new_g.phase(v)
            new_g.set_phase(first, old_phase - phase)
            new_g.set_phase(second, phase)

        self._finalize_unfuse(v, new_g)

    def _vert_double_clicked(self, v: VT) -> None:
        ty = self.graph.type(v)
        if ty == VertexType.BOUNDARY:
            return
        if ty in (VertexType.Z, VertexType.X):
            new_g = copy.deepcopy(self.graph)
            basicrules.color_change(new_g, v)
            cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "color change")
            self.undo_stack.push(cmd)
            return
        if ty == VertexType.H_BOX:
            new_g = copy.deepcopy(self.graph)
            if not pyzx.hrules.is_hadamard(new_g, v):
                return
            pyzx.hrules.replace_hadamard(new_g, v)
            cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "Turn Hadamard into edge")
            self.undo_stack.push(cmd)
            return
        if ty == VertexType.DUMMY:
            new_graph = update_dummy_vertex_text(self, self.graph, v)
            if new_graph is not None:
                cmd_dummy = ProofModeCommand(SetGraph(self.graph_view, new_graph), self.step_view)
                self.undo_stack.push(cmd_dummy)
            return

    def _edge_double_clicked(self, e: ET) -> None:
        """When an edge is double clicked, we change it to an H-box if it is a Hadamard edge."""
        new_g = copy.deepcopy(self.graph)
        if new_g.edge_type(e) == EdgeType.HADAMARD:
            pyzx.hrules.had_edge_to_hbox(new_g, e)
            cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "Turn edge into Hadamard")
            self.undo_stack.push(cmd)

    def _dummy_node_mode_clicked(self) -> None:
        self.graph_scene.curr_tool = ToolType.VERTEX
        self.graph_view.tool = GraphTool.Selection

    def _dummy_edge_mode_clicked(self) -> None:
        self.graph_scene.curr_tool = ToolType.EDGE
        self.graph_view.tool = GraphTool.Selection

    def _add_dummy_node(self, x: float, y: float, edges: list[EItem]) -> None:
        if self.graph_scene.curr_tool != ToolType.VERTEX:
            return
        cmd = ProofModeCommand(AddNode(self.graph_view, x, y, VertexType.DUMMY), self.step_view)
        self.undo_stack.push(cmd)

    def _add_dummy_edge(self, u: VT, v: VT, verts: list[VItem]) -> None:
        if self.graph_scene.curr_tool != ToolType.EDGE:
            return
        g = self.graph_scene.g
        if g.type(u) != VertexType.DUMMY or g.type(v) != VertexType.DUMMY:
            return
        cmd = ProofModeCommand(AddEdge(self.graph_view, u, v, EdgeType.SIMPLE), self.step_view)
        self.undo_stack.push(cmd)

    def delete_selection(self) -> None:
        g = self.graph_scene.g
        rem_vertices = [v for v in self.graph_scene.selected_vertices if g.type(v) == VertexType.DUMMY]
        rem_edges = []
        for e in self.graph_scene.selected_edges:
            if g.type(g.edge_s(e)) == VertexType.DUMMY and g.type(g.edge_t(e)) == VertexType.DUMMY:
                rem_edges.append(e)
        if not rem_vertices and not rem_edges: return
        new_g = copy.deepcopy(self.graph_scene.g)
        new_g.remove_edges(rem_edges)
        new_g.remove_vertices(list(set(rem_vertices)))
        if len(set(rem_vertices)) > 128:
            cmd = ProofModeCommand(SetGraph(self.graph_view, new_g), self.step_view)
        else:
            cmd = ProofModeCommand(UpdateGraph(self.graph_view, new_g), self.step_view)
        self.undo_stack.push(cmd)

    def paste_graph(self, graph: GraphT) -> None:
        dummy_vertices = [v for v in graph.vertices() if graph.type(v) == VertexType.DUMMY]
        if not dummy_vertices:
            return
        dummy_graph = graph.subgraph_from_vertices(dummy_vertices)
        new_g = copy.deepcopy(self.graph_scene.g)
        new_verts, new_edges = new_g.merge(dummy_graph.translate(0.5, 0.5))
        cmd = ProofModeCommand(UpdateGraph(self.graph_view, new_g), self.step_view)
        self.undo_stack.push(cmd)
        self.graph_scene.select_vertices(new_verts)
