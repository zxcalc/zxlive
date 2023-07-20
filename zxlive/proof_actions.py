import copy
from dataclasses import dataclass, field, replace
from typing import Callable, Literal, List, Optional

from PySide6.QtWidgets import QPushButton, QButtonGroup

import pyzx

from .common import VT,ET, GraphT
from .commands import UpdateGraph
from . import animations as anims

operations = pyzx.editor.operations


# Copied from pyzx.editor_actions
MATCHES_VERTICES = 1
MATCHES_EDGES = 2

@dataclass
class ProofAction(object):
    name: str
    matcher: Callable[[GraphT,Callable],List]
    rule: Callable[[GraphT,List],pyzx.rules.RewriteOutputType[ET,VT]]
    match_type: Literal[MATCHES_VERTICES,MATCHES_EDGES]
    tooltip: str
    button: Optional[QPushButton] = field(default=None, init=False)

    @classmethod
    def from_dict(cls,d):
          return cls(d['text'],d['matcher'],d['rule'],d['type'],d['tooltip'])

    def do_rewrite(self,panel: 'BasePanel'):
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

        cmd = UpdateGraph(panel.graph_view, new_g=g)

        if self.name == operations['spider']['text']:
            anim = anims.fuse(panel.graph_scene.vertex_map[verts[0]], panel.graph_scene.vertex_map[verts[1]])
            panel.undo_stack.push(cmd, anim_before=anim)
        elif self.name == operations['to_z']['text']:
            print('To do: animate ' + self.name)
            panel.undo_stack.push(cmd)
        elif self.name == operations['to_x']['text']:
            print('To do: animate ' + self.name)
            panel.undo_stack.push(cmd)
        elif self.name == operations['rem_id']['text']:
            anim = anims.remove_id(panel.graph_scene.vertex_map[verts[0]])
            panel.undo_stack.push(cmd, anim_before=anim)
        elif self.name == operations['copy']['text']:
            anim = anims.strong_comp(panel.graph, g, verts[0], panel.graph_scene)
            panel.undo_stack.push(cmd, anim_after=anim)
            # print('To do: animate ' + self.name)
            # panel.undo_stack.push(cmd)
        elif self.name == operations['pauli']['text']:
            print('To do: animate ' + self.name)
            panel.undo_stack.push(cmd)
        elif self.name == operations['bialgebra']['text']:
            anim = anims.strong_comp(panel.graph, g, verts[0], panel.graph_scene)
            panel.undo_stack.push(cmd, anim_after=anim)
        else:
            panel.undo_stack.push(cmd)

    def update_active(self, g: GraphT, verts: List[VT], edges: List[ET]):
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
    def __init__(self, *actions):
        self.actions = actions
        self.btn_group: Optional[QButtonGroup] = None
        self.parent_panel = None

    def copy(self):
        copied_actions = []
        for action in self.actions:
            action_copy = replace(action)
            action_copy.button = None
            copied_actions.append(action_copy)
        return ProofActionGroup(*copied_actions)

    def init_buttons(self, parent):
        self.btn_group = QButtonGroup(parent, exclusive=False)
        def create_rewrite(action,parent): # Needed to prevent weird bug with closures in signals
            def rewriter():
                action.do_rewrite(parent)
            return rewriter
        for action in self.actions:
            if action.button is not None: continue
            btn = QPushButton(action.name,parent)
            btn.setMaximumWidth(150)
            btn.setStatusTip(action.tooltip)
            btn.setEnabled(False)
            btn.clicked.connect(create_rewrite(action,parent))
            self.btn_group.addButton(btn)
            action.button = btn

    def update_active(self, g: GraphT, verts: List[VT], edges: List[ET]):
        for action in self.actions:
            action.update_active(g,verts,edges)


spider_fuse = ProofAction.from_dict(operations['spider'])
to_z = ProofAction.from_dict(operations['to_z'])
to_x = ProofAction.from_dict(operations['to_x'])
rem_id = ProofAction.from_dict(operations['rem_id'])
copy_action = ProofAction.from_dict(operations['copy'])
pauli = ProofAction.from_dict(operations['pauli'])
bialgebra = ProofAction.from_dict(operations['bialgebra'])

actions_basic = ProofActionGroup(spider_fuse,to_z,to_x,rem_id,copy_action,pauli,bialgebra)

