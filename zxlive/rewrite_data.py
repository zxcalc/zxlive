from __future__ import annotations

import copy
import os
from typing import Callable, Literal, cast, Optional
from typing_extensions import TypedDict, NotRequired

import pyzx
from pyzx import simplify, extract_circuit
from pyzx.graph import VertexType
from pyzx.rewrite import Rewrite, RewriteSimpGraph

from .common import ET, GraphT, VT, get_custom_rules_path
from .custom_rule import CustomRule
from .unfusion_rewrite import unfusion_rewrite


MatchType = Literal[1, 2, 3]

MATCH_SINGLE: MatchType = 1
MATCH_DOUBLE: MatchType = 2
MATCH_COMPOUND: MatchType = 3


class RewriteData(TypedDict):
    text: str
    rule: Rewrite
    type: MatchType
    tooltip: str
    copy_first: NotRequired[bool]
    returns_new_graph: NotRequired[bool]
    picture: NotRequired[str]
    custom_rule: NotRequired[bool]
    lhs: NotRequired[GraphT]
    rhs: NotRequired[GraphT]
    repeat_rule_application: NotRequired[bool]
    file_path: NotRequired[str]


def is_rewrite_data(d: dict) -> bool:
    proof_action_keys = {"text", "tooltip", "rule", "type"}
    return proof_action_keys.issubset(set(d.keys()))


def read_custom_rules() -> list[RewriteData]:
    custom_rules = []
    for root, dirs, files in os.walk(get_custom_rules_path()):
        for file in files:
            if file.endswith(".zxr"):
                zxr_file = os.path.join(root, file)
                with open(zxr_file, "r") as f:
                    rule = CustomRule.from_json(f.read()).to_rewrite_data()
                    rule['file_path'] = zxr_file
                    custom_rules.append(rule)
    return custom_rules



def selection_or_all_matcher(graph: GraphT, matches: Callable[[VT], bool]) -> list[VT]:
    """Returns a list of vertices in the selection or all vertices if no selection is made."""
    matches_list = [v for v in graph.vertices() if matches(v)]
    if len(matches_list) == 0:
        return list(graph.vertices())
    return matches_list


# def apply_simplification(simplification: Callable[[GraphT], Optional[int]]) -> Callable[[GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]]:
#     def rule(g: GraphT, matches: list) -> pyzx.rules.RewriteOutputType[VT, ET]:
#         if set(g.vertices()) == set(matches):
#             simplification(g)
#             return ({}, [], [], True)
#         subgraph = create_subgraph_with_boundary(g, matches)
#         simplified = cast(GraphT, subgraph.copy())
#         simplification(simplified)
#         return CustomRule(subgraph, simplified, "", "")(g, matches)
#     return rule

def rewrite_strategy_to_rewrite(strategy: Callable[[GraphT], Optional[int]]) -> RewriteSimpGraph:
    def rule(g: GraphT, matches: list) -> bool:
        if set(g.vertices()) == set(matches):
            strategy(g)
            return True
        subgraph = create_subgraph_with_boundary(g, matches)
        simplified = cast(GraphT, subgraph.copy())
        strategy(simplified)
        return CustomRule(subgraph, simplified, "", "").applier(g, matches)
    return RewriteSimpGraph(rule, rule)

def create_subgraph_with_boundary(graph: GraphT, verts: list[VT]) -> GraphT:
    verts = [v for v in verts if graph.type(v) != VertexType.BOUNDARY]
    subgraph = cast(GraphT, graph.subgraph_from_vertices(verts))
    for v in verts:
        for e in graph.incident_edges(v):
            s, t = graph.edge_st(e)
            if s not in verts or t not in verts:
                boundary_node = subgraph.add_vertex(VertexType.BOUNDARY)
                subgraph.add_edge((v, boundary_node), graph.edge_type(e))
    return subgraph


def _extract_circuit(graph: GraphT) -> GraphT:
    graph.auto_detect_io()
    simplify.full_reduce(graph)
    return cast(GraphT, extract_circuit(graph).to_graph())


rewrites_graph_theoretic: dict[str, RewriteData] = {
    "lcomp": {
        "text": "local complementation",
        "tooltip": "Deletes a spider with a pi/2 phase by performing a local complementation on its neighbors",
        "rule": pyzx.simplify.lcomp_simp,
        "type": MATCH_SINGLE,
        "copy_first": True,
        "picture": "lcomp.png"
    },
    "pivot": {
        "text": "pivot",
        "tooltip": "Deletes a pair of spiders with 0/pi phases by performing a pivot",
        "rule": pyzx.simplify.pivot_simp,
        "type": MATCH_DOUBLE,
        "copy_first": True,
        "picture": "pivot_regular.png"
    },
    "pivot_boundary": {
        "text": "boundary pivot",
        "tooltip": "Performs a pivot between a Pauli spider and a spider on the boundary.",
        "rule": pyzx.simplify.pivot_boundary_simp,
        "type": MATCH_DOUBLE,
        "copy_first": True
    },
    "pivot_gadget": {
        "text": "gadget pivot",
        "tooltip": "Performs a pivot between a Pauli spider and a spider with an arbitrary phase, creating a phase gadget.",
        "rule": pyzx.simplify.pivot_gadget_simp,
        "type": MATCH_DOUBLE,
        "copy_first": True,
        "picture": "pivot_gadget.png"
    },
    "phase_gadget_fuse": {
        "text": "Fuse phase gadgets",
        "tooltip": "Fuses two phase gadgets with the same connectivity.",
        "rule": pyzx.simplify.gadget_simp,
        "type": MATCH_COMPOUND,
        "copy_first": True,
        "picture": "gadget_fuse.png"
    },
    "supplementarity": {
        "text": "Supplementarity",
        "tooltip": "Looks for a pair of internal spiders with the same connectivity and supplementary angles and removes them.",
        "rule": pyzx.simplify.supplementarity_simp,
        "type": MATCH_COMPOUND,
        "copy_first": False
    },
}


simplifications: dict[str, RewriteData] = {
    'bialg_simp': {
        "text": "bialgebra simp",
        "tooltip": "bialg_simp",
        "rule": simplify.bialg_simp,
        "type": MATCH_DOUBLE,
        "repeat_rule_application": True
    },
    'phase_free_simp': {
        "text": "phase free",
        "tooltip": "phase_free_simp",
        "rule": rewrite_strategy_to_rewrite(simplify.phase_free_simp),
        "type": MATCH_COMPOUND,
    },
    'pivot_simp': {
        "text": "pivot",
        "tooltip": "pivot_simp",
        "rule": simplify.pivot_simp,
        "type": MATCH_DOUBLE,
        "repeat_rule_application": True
    },
    'pivot_gadget_simp': {
        "text": "pivot gadget",
        "tooltip": "pivot_gadget_simp",
        "rule": simplify.pivot_gadget_simp,
        "type": MATCH_COMPOUND,
        "repeat_rule_application": True
    },
    'pivot_boundary_simp': {
        "text": "pivot boundary",
        "tooltip": "pivot_boundary_simp",
        "rule": simplify.pivot_boundary_simp,
        "type": MATCH_COMPOUND,
        "repeat_rule_application": True
    },
    'gadget_simp': {
        "text": "gadget",
        "tooltip": "gadget_simp",
        "rule": simplify.gadget_simp,
        "type": MATCH_COMPOUND,
        "repeat_rule_application": True
    },
    'lcomp_simp': {
        "text": "local complementation",
        "tooltip": "lcomp_simp",
        "rule": simplify.lcomp_simp,
        "type": MATCH_SINGLE,
        "repeat_rule_application": True
    },
    'clifford_simp': {
        "text": "clifford simplification",
        "tooltip": "clifford_simp",
        "rule": rewrite_strategy_to_rewrite(simplify.clifford_simp),
        "type": MATCH_COMPOUND,
    },
    'to_gh': {
        "text": "to green-hadamard form",
        "tooltip": "to_gh",
        "rule": rewrite_strategy_to_rewrite(simplify.to_gh),
        "type": MATCH_COMPOUND,
    },
    'to_rg': {
        "text": "to red-green form",
        "tooltip": "to_rg",
        "rule": rewrite_strategy_to_rewrite(simplify.to_rg),
        "type": MATCH_COMPOUND,
    },
    'full_reduce': {
        "text": "full reduce",
        "tooltip": "full_reduce",
        "rule": rewrite_strategy_to_rewrite(simplify.full_reduce),
        "type": MATCH_COMPOUND,
    },
    'supplementarity_simp': {
        "text": "supplementarity",
        "tooltip": "supplementarity_simp",
        "rule": simplify.supplementarity_simp,
        "type": MATCH_COMPOUND,
        "repeat_rule_application": True
    },
    'to_clifford_normal_form_graph': {
        "text": "to clifford normal form",
        "tooltip": "to_clifford_normal_form_graph",
        "rule": rewrite_strategy_to_rewrite(simplify.to_clifford_normal_form_graph),
        "type": MATCH_COMPOUND,
    },
    # 'extract_circuit': {
    #     "text": "circuit extraction",
    #     "tooltip": "extract_circuit",
    #     "rule": rewrite_strategy_to_rewrite(_extract_circuit),
    #     "type": MATCH_COMPOUND,
    #     "repeat_rule_application": True,
    #     "returns_new_graph": True,
    # },
}


# The OCM action simply saves the current graph without modifying anything.
# This can be used to make repositioning the vertices an explicit proof step.
def ocm_rule(_graph: GraphT) -> int:
    return 1

rules_basic = {
    'id_simp': {
        "text": "Remove identity",
        "tooltip": "Removes a 2-ary phaseless spider",
        "rule": simplify.id_simp,
        "type": MATCH_SINGLE,
        "repeat_rule_application": True
    },
    'fuse_simp': {
        "text": "Fuse spiders",
        "tooltip": "Fuses connected spiders of the same color, also works for W-spiders",
        "rule": simplify.fuse_simp,
        "type": MATCH_DOUBLE,
        "repeat_rule_application": True
    },
    'remove_self_loops': {
        "text": "Remove self-loops",
        "tooltip": "Removes all self-loops on a spider",
        "rule": simplify.remove_self_loop_simp,
        "type": MATCH_SINGLE,
        "repeat_rule_application": True
    },
    "hopf": {
        "text": "Remove parallel edges",
        "tooltip": "Applies the Hopf rule between pairs of spiders that share parallel edges",
        "rule": simplify.hopf_simp,
        "type": MATCH_DOUBLE,
        "repeat_rule_application": True
    },
    'unfuse': {
        "text": "Unfuse spider",
        "tooltip": "Unfuse a spider",
        "rule": unfusion_rewrite,
        "type": MATCH_COMPOUND,
    },
    'ocm': {
        "text": "Save changed positions",
        "tooltip": "Only Connectivity Matters. Saves the graph with the current vertex positions",
        "rule": rewrite_strategy_to_rewrite(ocm_rule),
        "type": MATCH_COMPOUND,
    },
    'copy': {
        "text": "Copy 0/pi spider through its neighbour", 
        "tooltip": "Copies a single-legged spider with a 0/pi phase through its neighbor",
        "picture": "copy_pi.png",
        "rule": simplify.copy_simp,
        "type": MATCH_SINGLE,
    },
    "pauli": {
        "text": "Push Pauli", 
        "tooltip": "Pushes an arity 2 pi-phase through a selected neighbor",
        "picture": "push_pauli.png",
        "rule": simplify.push_pauli_rewrite,
        "type": MATCH_DOUBLE
    },
     "cc": {
        "text": "Colour change", 
        "tooltip": "Changes the color of a given vertex",
        "rule": simplify.color_change_rewrite,
        "type": MATCH_SINGLE
    },
    'bialgebra': {
        "text": "Strong complementarity",
        "tooltip": "Apply the strong complementarity rule to connected spiders of different colors",
        "picture": "bialgebra.png",
        "rule": simplify.bialg_simp,
        "type": MATCH_DOUBLE,
        "repeat_rule_application": False
    },
    'bialgebra_op': {
        "text": "Strong complementarity in opposite direction",
        "tooltip": "Apply strong complementarity from right to left, matching on complete bipartite graph of Z- and X-spiders",
        "picture": "bialgebra.png",
        "rule": simplify.bialg_op_simp,
        "type": MATCH_COMPOUND,
    },
    "euler": {
        "text": "Decompose Hadamard", 
        "tooltip": "Expands a Hadamard-edge into its component spiders using its Euler decomposition",
        "rule": simplify.euler_expansion_rewrite,
        "type": MATCH_DOUBLE,
    },
}

rewrites_fault_tolerant = {
    "Elim Rewrite": {
        "text": "FE Identity removal",
        "tooltip": "Removes a 2-ary phaseless spider",
        "rule": pyzx.ft_simplify.elim_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": True,
        "picture": "FE_id_removal.png"
    },
    "pauli": {
        "text": "FE Push Pauli", 
        "tooltip": "Pushes an arity 2 pi-phase through a selected neighbor",
        "picture": "push_pauli.png",
        "rule": simplify.push_pauli_rewrite,
        "type": MATCH_DOUBLE
    },
     "cc": {
        "text": "FE Colour change", 
        "tooltip": "Changes the color of a given vertex",
        "rule": simplify.color_change_rewrite,
        "type": MATCH_SINGLE
    },
    "Fuse-1 Rewrite": {
        "text": "FE Fuse-1",
        "tooltip": "Fuses connected spiders of the same color, one of the spiders cannot have any other neighbours",  
        "rule": pyzx.ft_simplify.fuse_1_FE_simp,
        "type": MATCH_SINGLE,
        "repeat_rule_application": False,
        "picture": "FE_(un)fuse_1.png"
    },
    "Unfuse-1 Rewrite": {
        "text": "FE Unfuse-1",
        "tooltip": "Unfuses connected spiders of the same color, guaranteeing one spider has no additional neighbours",
        "rule": pyzx.ft_simplify.unfuse_1_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False,
        "picture": "FE_(un)fuse_1.png"
    },
    "Unfuse-4 Simp": {
        "text": "FE Unfuse-4",
        "tooltip": "Unfuses a degree-4 spider into a square",
        "rule": pyzx.ft_simplify.unfuse_4_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False,
        "picture": "FE_(un)fuse_4.png"
    },
    "fuse-4 simp": {
        "text": "FE Fuse-4",
        "tooltip": "fuses 4 spiders of the same type in a square configuration into a single spider (right to left)",
        "rule": pyzx.ft_simplify.fuse_4_FE_simp,
        "type": MATCH_COMPOUND,
        "picture": "FE_(un)fuse_4.png"
    },
    "Unfuse-5 Simp": {
        "text": "FE Unfuse-5",
        "tooltip": "Unfuses a degree-5 spider into a pentagon",
        "rule": pyzx.ft_simplify.unfuse_5_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False
    },
    "fuse-5 simp": {
        "text": "FE Fuse-5",
        "tooltip": "fuses 5 spiders of the same type in a square configuration into a single spider (right to left)",
        "rule": pyzx.ft_simplify.fuse_5_FE_simp,
        "type": MATCH_COMPOUND,
    },
     "Unfuse-n Simp": {
        "text": "2FE Unfuse-n",
        "tooltip": "Unfuses a degree-n spider into a n-sided polygon",
        "rule": pyzx.ft_simplify.unfuse_n_2FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False
    },
    "fuse-n simp": {
        "text": "2FE Fuse-n",
        "tooltip": "fuses n (at least 6) spiders of the same type in a square configuration into a single spider (right to left)",
        "rule": pyzx.ft_simplify.fuse_n_2FE_simp,
        "type": MATCH_COMPOUND,
    },
    "Unfuse-2n Simp": {
        "text": "FE Unfuse-2n",
        "tooltip": "Unfuses a degree-2n spider into two degree-n spiders",
        "rule": pyzx.ft_simplify.unfuse_2n_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False,
        "picture": "FE_(un)fuse_2n.png"
    },
    "Unfuse-2n Plus Simp": {
        "text": "FE Unfuse-2n Plus",
        "tooltip": "Unfuses a degree-(2n + 1) spider into a degree-n spider and a degree-(n + 1) spider",
        "rule": pyzx.ft_simplify.unfuse_2n_plus_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False,
    },
    "Recursive Unfuse Simp": {
        "text": "FE Recursive Unfuse",
        "tooltip": "Recursively unfuses a spider",
        "rule": pyzx.ft_simplify.recursive_unfuse_FE_simp,
        "type": MATCH_SINGLE,
        "copy_first": False,
        "repeat_rule_application": False
    }
}

# rules_zxw = ["spider", "fuse_w", "z_to_z_box"]

# rules_zh = ["had2edge", "fuse_hbox", "mult_hbox"]


action_groups = {
    "Basic rules": rules_basic, #{'ocm': ocm_action} | {key: operations[key] for key in rules_basic},
    "Custom rules": {},
    #"Graph-like rules": rewrites_graph_theoretic,
    # "ZXW rules": {key: operations[key] for key in rules_zxw},
    # "ZH rules": {key: operations[key] for key in rules_zh},
    "Simplification routines": simplifications, 
    "Fault Equivalent Rewrites": rewrites_fault_tolerant,
}


def refresh_custom_rules() -> None:
    action_groups["Custom rules"] = {rule["text"]: rule for rule in read_custom_rules()}


refresh_custom_rules()
