import copy
from dataclasses import dataclass, field, replace
from typing import Callable, Literal, Optional, TYPE_CHECKING

import pyzx

from PySide6.QtWidgets import QPushButton, QButtonGroup
from PySide6.QtCore import QParallelAnimationGroup, QEasingCurve

from . import animations as anims
from .commands import AddRewriteStep
from .common import ANIMATION_DURATION, ET, GraphT, VT
from .custom_rule import CustomRule

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

operations = copy.deepcopy(pyzx.editor.operations)

MatchType = Literal[1, 2]

# Copied from pyzx.editor_actions
MATCHES_VERTICES: MatchType = 1
MATCHES_EDGES: MatchType = 2


@dataclass
class ProofAction(object):
    name: str
    matcher: Callable[[GraphT, Callable], list]
    rule: Callable[[GraphT, list], pyzx.rules.RewriteOutputType[ET,VT]]
    match_type: MatchType
    tooltip: str
    copy_first: bool = field(default=False)  # Whether the graph should be copied before trying to test whether it matches. Needed if the matcher changes the graph.
    button: Optional[QPushButton] = field(default=None, init=False)

    @classmethod
    def from_dict(cls, d: dict) -> "ProofAction":
        if 'copy_first' not in d:
            d['copy_first'] = False
        return cls(d['text'], d['matcher'], d['rule'], d['type'], d['tooltip'], d['copy_first'])

    def do_rewrite(self, panel: "ProofPanel") -> None:
        verts, edges = panel.parse_selection()
        g = copy.deepcopy(panel.graph_scene.g)

        if self.match_type == MATCHES_VERTICES:
            matches = self.matcher(g, lambda v: v in verts)
        else:
            matches = self.matcher(g, lambda e: e in edges)

        etab, rem_verts, rem_edges, check_isolated_vertices = self.rule(g, matches)
        g.remove_edges(rem_edges)
        g.remove_vertices(rem_verts)
        g.add_edge_table(etab)

        cmd = AddRewriteStep(panel.graph_view, g, panel.step_view, self.name)
        anim_before = None
        anim_after = None
        if self.name == operations['spider']['text'] or self.name == operations['fuse_w']['text']:
            anim_before = QParallelAnimationGroup()
            for v1, v2 in matches:
                if v1 in rem_verts:
                    v1, v2 = v2, v1
                anim_before.addAnimation(anims.fuse(panel.graph_scene.vertex_map[v2], panel.graph_scene.vertex_map[v1]))
        elif self.name == operations['to_z']['text']:
            print('To do: animate ' + self.name)
        elif self.name == operations['to_x']['text']:
            print('To do: animate ' + self.name)
        elif self.name == operations['rem_id']['text']:
            anim_before = QParallelAnimationGroup()
            for m in matches:
                anim_before.addAnimation(anims.remove_id(panel.graph_scene.vertex_map[m[0]]))
        elif self.name == operations['copy']['text']:
            anim_before = QParallelAnimationGroup()
            for m in matches:
                anim_before.addAnimation(anims.fuse(panel.graph_scene.vertex_map[m[0]],
                                                    panel.graph_scene.vertex_map[m[1]]))
            anim_after = QParallelAnimationGroup()
            for m in matches:
                anim_after.addAnimation(anims.strong_comp(panel.graph, g, m[1], panel.graph_scene))
        elif self.name == operations['pauli']['text']:
            print('To do: animate ' + self.name)
        elif self.name == operations['bialgebra']['text']:
            anim_before = QParallelAnimationGroup()
            for v1, v2 in matches:
                anim_before.addAnimation(anims.fuse(panel.graph_scene.vertex_map[v1],
                                                    panel.graph_scene.vertex_map[v2], meet_halfway=True))
            anim_after = QParallelAnimationGroup()
            for v1, v2 in matches:
                v2_row, v2_qubit = panel.graph.row(v2), panel.graph.qubit(v2)
                panel.graph.set_row(v2, (panel.graph.row(v1) + v2_row) / 2)
                panel.graph.set_qubit(v2, (panel.graph.qubit(v1) + v2_qubit) / 2)
                anim_after.addAnimation(anims.strong_comp(panel.graph, g, v2, panel.graph_scene))
                panel.graph.set_row(v2, v2_row)
                panel.graph.set_qubit(v2, v2_qubit)
        elif isinstance(self.rule, CustomRule) and self.rule.last_rewrite_center is not None:
            center = self.rule.last_rewrite_center
            duration = ANIMATION_DURATION / 2
            anim_before = anims.morph_graph_to_center(panel.graph, lambda v: v not in g.graph,
                                                      panel.graph_scene, center, duration,
                                                      QEasingCurve(QEasingCurve.Type.InQuad))
            anim_after = anims.morph_graph_from_center(g, lambda v: v not in panel.graph.graph,
                                                       panel.graph_scene, center, duration,
                                                       QEasingCurve(QEasingCurve.Type.OutQuad))

        panel.undo_stack.push(cmd, anim_before=anim_before, anim_after=anim_after)

    def update_active(self, g: GraphT, verts: list[VT], edges: list[ET]) -> None:
        if self.copy_first:
            g = copy.deepcopy(g)
        if self.match_type == MATCHES_VERTICES:
            matches = self.matcher(g, lambda v: v in verts)
        else:
            matches = self.matcher(g, lambda e: e in edges)

        if self.button is None: return
        if matches:
            self.button.setEnabled(True)
        else:
            self.button.setEnabled(False)


class ProofActionGroup(object):
    def __init__(self, name: str, *actions: ProofAction) -> None:
        self.name = name
        self.actions = actions
        self.btn_group: Optional[QButtonGroup] = None
        self.parent_panel = None

    def copy(self) -> "ProofActionGroup":
        copied_actions = []
        for action in self.actions:
            action_copy = replace(action)
            action_copy.button = None
            copied_actions.append(action_copy)
        return ProofActionGroup(self.name, *copied_actions)

    def init_buttons(self, parent: "ProofPanel") -> None:
        self.btn_group = QButtonGroup(parent)
        self.btn_group.setExclusive(False)
        def create_rewrite(action: ProofAction, parent: "ProofPanel") -> Callable[[], None]: # Needed to prevent weird bug with closures in signals
            def rewriter() -> None:
                action.do_rewrite(parent)
            return rewriter
        for action in self.actions:
            if action.button is not None: continue
            btn = QPushButton(action.name, parent)
            btn.setMaximumWidth(150)
            btn.setStatusTip(action.tooltip)
            btn.setEnabled(False)
            btn.clicked.connect(create_rewrite(action, parent))
            self.btn_group.addButton(btn)
            action.button = btn

    def update_active(self, g: GraphT, verts: list[VT], edges: list[ET]) -> None:
        for action in self.actions:
            action.update_active(g, verts, edges)

# We want additional actions that are not part of the original PyZX editor
# So we add them to operations

operations.update({
    "pivot_boundary": {"text": "boundary pivot", 
               "tooltip": "Performs a pivot between a Pauli spider and a spider on the boundary.",
               "matcher": pyzx.rules.match_pivot_boundary, 
               "rule": pyzx.rules.pivot, 
               "type": MATCHES_EDGES,
               "copy_first": True},
     "pivot_gadget": {"text": "gadget pivot", 
               "tooltip": "Performs a pivot between a Pauli spider and a spider with an arbitrary phase, creating a phase gadget.",
               "matcher": pyzx.rules.match_pivot_gadget, 
               "rule": pyzx.rules.pivot, 
               "type": MATCHES_EDGES,
               "copy_first": True},
     "phase_gadget_fuse": {"text": "Fuse phase gadgets",
               "tooltip": "Fuses two phase gadgets with the same connectivity.",
               "matcher": pyzx.rules.match_phase_gadgets, 
               "rule": pyzx.rules.merge_phase_gadgets, 
               "type": MATCHES_VERTICES,
               "copy_first": True},
     "supplementarity": {"text": "Supplementarity",
               "tooltip": "Looks for a pair of internal spiders with the same connectivity and supplementary angles and removes them.",
               "matcher": pyzx.rules.match_supplementarity, 
               "rule": pyzx.rules.apply_supplementarity, 
               "type": MATCHES_VERTICES,
               "copy_first": False},
    }
)



spider_fuse = ProofAction.from_dict(operations['spider'])
to_z = ProofAction.from_dict(operations['to_z'])
to_x = ProofAction.from_dict(operations['to_x'])
rem_id = ProofAction.from_dict(operations['rem_id'])
copy_action = ProofAction.from_dict(operations['copy'])
pauli = ProofAction.from_dict(operations['pauli'])
bialgebra = ProofAction.from_dict(operations['bialgebra'])
euler_rule = ProofAction.from_dict(operations['euler'])
rules_basic = ProofActionGroup("Basic rules", spider_fuse, to_z, to_x, rem_id, copy_action, pauli, bialgebra, euler_rule).copy()

lcomp = ProofAction.from_dict(operations['lcomp'])
pivot = ProofAction.from_dict(operations['pivot'])
pivot_boundary = ProofAction.from_dict(operations['pivot_boundary'])
pivot_gadget = ProofAction.from_dict(operations['pivot_gadget'])
supplementarity = ProofAction.from_dict(operations['supplementarity'])
rules_graph_theoretic = ProofActionGroup("Graph-like rules", lcomp, pivot, pivot_boundary, pivot_gadget, supplementarity).copy()

w_fuse = ProofAction.from_dict(operations['fuse_w'])
z_to_z_box = ProofAction.from_dict(operations['z_to_z_box'])
rules_zxw = ProofActionGroup("ZXW rules",spider_fuse, w_fuse, z_to_z_box).copy()

hbox_to_edge = ProofAction.from_dict(operations['had2edge'])
fuse_hbox = ProofAction.from_dict(operations['fuse_hbox'])
mult_hbox = ProofAction.from_dict(operations['mult_hbox'])
rules_zh = ProofActionGroup("ZH rules", hbox_to_edge, fuse_hbox, mult_hbox).copy()

action_groups = [rules_basic, rules_graph_theoretic, rules_zxw, rules_zh]
