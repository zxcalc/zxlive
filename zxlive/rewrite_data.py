from __future__ import annotations

import copy
import os
from typing import Callable, Literal, cast, Optional
from typing_extensions import TypedDict, NotRequired

import pyzx
from pyzx import simplify, extract_circuit

from .common import ET, GraphT, VT, get_custom_rules_path
from .custom_rule import CustomRule

operations = copy.deepcopy(pyzx.editor.operations)

MatchType = Literal[1, 2]

# Copied from pyzx.editor_actions
MATCHES_VERTICES: MatchType = 1
MATCHES_EDGES: MatchType = 2


class RewriteData(TypedDict):
    text: str
    matcher: Callable[[GraphT, Callable], list]
    rule: Callable[[GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]]
    type: MatchType
    tooltip: str
    copy_first: NotRequired[bool]
    returns_new_graph: NotRequired[bool]
    picture: NotRequired[str]
    custom_rule: NotRequired[bool]
    lhs: NotRequired[GraphT]
    rhs: NotRequired[GraphT]


def is_rewrite_data(d: dict) -> bool:
    proof_action_keys = {"text", "tooltip", "matcher", "rule", "type"}
    return proof_action_keys.issubset(set(d.keys()))


def read_custom_rules() -> list[RewriteData]:
    custom_rules = []
    for root, dirs, files in os.walk(get_custom_rules_path()):
        for file in files:
            if file.endswith(".zxr"):
                zxr_file = os.path.join(root, file)
                with open(zxr_file, "r") as f:
                    rule = CustomRule.from_json(f.read()).to_rewrite_data()
                    custom_rules.append(rule)
    return custom_rules

# We want additional actions that are not part of the original PyZX editor
# So we add them to operations

rewrites_graph_theoretic: dict[str, RewriteData] = {
    "lcomp": {
        "text": "local complementation",
        "tooltip": "Deletes a spider with a pi/2 phase by performing a local complementation on its neighbors",
        "matcher": pyzx.rules.match_lcomp_parallel,
        "rule": pyzx.rules.lcomp,
        "type": MATCHES_VERTICES,
        "copy_first": True,
        "picture": "lcomp.png"
    },
    "pivot": {
        "text": "pivot",
        "tooltip": "Deletes a pair of spiders with 0/pi phases by performing a pivot",
        "matcher": lambda g, matchf: pyzx.rules.match_pivot_parallel(g, matchf, check_edge_types=True),
        "rule": pyzx.rules.pivot,
        "type": MATCHES_EDGES,
        "copy_first": True,
        "picture": "pivot_regular.png"
    },
    "pivot_boundary": {
        "text": "boundary pivot",
        "tooltip": "Performs a pivot between a Pauli spider and a spider on the boundary.",
        "matcher": pyzx.rules.match_pivot_boundary,
        "rule": pyzx.rules.pivot,
        "type": MATCHES_EDGES,
        "copy_first": True
    },
    "pivot_gadget": {
        "text": "gadget pivot",
        "tooltip": "Performs a pivot between a Pauli spider and a spider with an arbitrary phase, creating a phase gadget.",
        "matcher": pyzx.rules.match_pivot_gadget,
        "rule": pyzx.rules.pivot,
        "type": MATCHES_EDGES,
        "copy_first": True,
        "picture": "pivot_gadget.png"
    },
    "phase_gadget_fuse": {
        "text": "Fuse phase gadgets",
        "tooltip": "Fuses two phase gadgets with the same connectivity.",
        "matcher": pyzx.rules.match_phase_gadgets,
        "rule": pyzx.rules.merge_phase_gadgets,
        "type": MATCHES_VERTICES,
        "copy_first": True,
        "picture": "gadget_fuse.png"
    },
    "supplementarity": {
        "text": "Supplementarity",
        "tooltip": "Looks for a pair of internal spiders with the same connectivity and supplementary angles and removes them.",
        "matcher": pyzx.rules.match_supplementarity,
        "rule": pyzx.rules.apply_supplementarity,
        "type": MATCHES_VERTICES,
        "copy_first": False
    },
}

const_true = lambda graph, matches: matches


def apply_simplification(simplification: Callable[[GraphT], Optional[int]]) -> Callable[
    [GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]]:
    def rule(g: GraphT, matches: list) -> pyzx.rules.RewriteOutputType[VT, ET]:
        simplification(g)
        return ({}, [], [], True)

    return rule


def _extract_circuit(graph: GraphT, matches: list) -> GraphT:
    graph.auto_detect_io()
    simplify.full_reduce(graph)
    return cast(GraphT, extract_circuit(graph).to_graph())


# The OCM action simply saves the current graph without modifying anything.
# This can be used to make repositioning the vertices an explicit proof step.
def ocm_rule(_graph: GraphT, _matches: list) -> pyzx.rules.RewriteOutputType[VT, ET]:
    return ({}, [], [], True)


ocm_action: RewriteData = {
    "text": "OCM",
    "tooltip": "Only Connectivity Matters. Saves the graph with the current vertex positions",
    "matcher": const_true,
    "rule": ocm_rule,
    "type": MATCHES_VERTICES,
}

simplifications: dict[str, RewriteData] = {
    'bialg_simp': {
        "text": "bialgebra simp",
        "tooltip": "bialg_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.bialg_simp),
        "type": MATCHES_VERTICES,
    },
    'spider_simp': {
        "text": "spider fusion",
        "tooltip": "spider_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.spider_simp),
        "type": MATCHES_VERTICES,
    },
    'id_simp': {
        "text": "id",
        "tooltip": "id_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.id_simp),
        "type": MATCHES_VERTICES,
    },
    'phase_free_simp': {
        "text": "phase free",
        "tooltip": "phase_free_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.phase_free_simp),
        "type": MATCHES_VERTICES,
    },
    'pivot_simp': {
        "text": "pivot",
        "tooltip": "pivot_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.pivot_simp),
        "type": MATCHES_VERTICES,
    },
    'pivot_gadget_simp': {
        "text": "pivot gadget",
        "tooltip": "pivot_gadget_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.pivot_gadget_simp),
        "type": MATCHES_VERTICES,
    },
    'pivot_boundary_simp': {
        "text": "pivot boundary",
        "tooltip": "pivot_boundary_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.pivot_boundary_simp),
        "type": MATCHES_VERTICES,
    },
    'gadget_simp': {
        "text": "gadget",
        "tooltip": "gadget_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.gadget_simp),
        "type": MATCHES_VERTICES,
    },
    'lcomp_simp': {
        "text": "local complementation",
        "tooltip": "lcomp_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.lcomp_simp),
        "type": MATCHES_VERTICES,
    },
    'clifford_simp': {
        "text": "clifford simplification",
        "tooltip": "clifford_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.clifford_simp),
        "type": MATCHES_VERTICES,
    },
    'tcount': {
        "text": "tcount",
        "tooltip": "tcount",
        "matcher": const_true,
        "rule": apply_simplification(simplify.tcount),
        "type": MATCHES_VERTICES,
    },
    'to_gh': {
        "text": "to green-hadamard form",
        "tooltip": "to_gh",
        "matcher": const_true,
        "rule": apply_simplification(simplify.to_gh),
        "type": MATCHES_VERTICES,
    },
    'to_rg': {
        "text": "to red-green form",
        "tooltip": "to_rg",
        "matcher": const_true,
        "rule": apply_simplification(simplify.to_rg),
        "type": MATCHES_VERTICES,
    },
    'full_reduce': {
        "text": "full reduce",
        "tooltip": "full_reduce",
        "matcher": const_true,
        "rule": apply_simplification(simplify.full_reduce),
        "type": MATCHES_VERTICES,
    },
    'teleport_reduce': {
        "text": "teleport reduce",
        "tooltip": "teleport_reduce",
        "matcher": const_true,
        "rule": apply_simplification(simplify.teleport_reduce),
        "type": MATCHES_VERTICES,
    },
    'reduce_scalar': {
        "text": "reduce scalar",
        "tooltip": "reduce_scalar",
        "matcher": const_true,
        "rule": apply_simplification(simplify.reduce_scalar),
        "type": MATCHES_VERTICES,
    },
    'supplementarity_simp': {
        "text": "supplementarity",
        "tooltip": "supplementarity_simp",
        "matcher": const_true,
        "rule": apply_simplification(simplify.supplementarity_simp),
        "type": MATCHES_VERTICES,
    },
    'to_clifford_normal_form_graph': {
        "text": "to clifford normal form",
        "tooltip": "to_clifford_normal_form_graph",
        "matcher": const_true,
        "rule": apply_simplification(simplify.to_clifford_normal_form_graph),
        "type": MATCHES_VERTICES,
    },
    'extract_circuit': {
        "text": "circuit extraction",
        "tooltip": "extract_circuit",
        "matcher": const_true,
        "rule": _extract_circuit,
        "type": MATCHES_VERTICES,
        "returns_new_graph": True,
    },
}

rules_basic = {"spider", "to_z", "to_x", "rem_id", "copy", "pauli", "bialgebra", "euler"}
operations["pauli"]["picture"] = "push_pauli.png"
operations["copy"]["picture"] = "copy_pi.png"
operations["bialgebra"]["picture"] = "bialgebra.png"

rules_zxw = {"spider", "fuse_w", "z_to_z_box"}

rules_zh = {"had2edge", "fuse_hbox", "mult_hbox"}

action_groups = {
    "Basic rules": {'ocm': ocm_action} | {key: operations[key] for key in rules_basic},
    "Custom rules": {},
    "Graph-like rules": rewrites_graph_theoretic,
    "ZXW rules": {key: operations[key] for key in rules_zxw},
    "ZH rules": {key: operations[key] for key in rules_zh},
    "Simplification routines": simplifications,
}


def refresh_custom_rules() -> None:
    action_groups["Custom rules"] = {rule["text"]: rule for rule in read_custom_rules()}


refresh_custom_rules()
