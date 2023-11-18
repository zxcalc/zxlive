import copy
import json
from typing import TYPE_CHECKING, Callable

import networkx as nx
import numpy as np
import pyzx
from networkx.algorithms.isomorphism import (GraphMatcher,
                                             categorical_node_match)
from networkx.classes.reportviews import NodeView
from pyzx.utils import EdgeType, VertexType
from shapely import Polygon

from pyzx.symbolic import Poly

from .common import ET, VT, GraphT

if TYPE_CHECKING:
    from .rewrite_data import RewriteData

class CustomRule:
    def __init__(self, lhs_graph: GraphT, rhs_graph: GraphT, name: str, description: str) -> None:
        lhs_graph.auto_detect_io()
        rhs_graph.auto_detect_io()
        self.lhs_graph = lhs_graph
        self.rhs_graph = rhs_graph
        self.lhs_graph_nx = to_networkx(lhs_graph)
        self.rhs_graph_nx = to_networkx(rhs_graph)
        self.name = name
        self.description = description
        self.last_rewrite_center = None
        self.is_rewrite_unfusable = is_rewrite_unfusable(lhs_graph)
        if self.is_rewrite_unfusable:
            self.lhs_graph_without_boundaries_nx = nx.Graph(self.lhs_graph_nx.subgraph(
                [v for v in self.lhs_graph_nx.nodes() if self.lhs_graph_nx.nodes()[v]['type'] != VertexType.BOUNDARY]))

    def __call__(self, graph: GraphT, vertices: list[VT]) -> pyzx.rules.RewriteOutputType[ET,VT]:
        if self.is_rewrite_unfusable:
            self.unfuse_subgraph_for_rewrite(graph, vertices)

        subgraph_nx, boundary_mapping = create_subgraph(graph, vertices)
        graph_matcher = GraphMatcher(self.lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match('type', 1))
        matchings = graph_matcher.match()
        matchings = filter_matchings_if_symbolic_compatible(matchings, self.lhs_graph_nx, subgraph_nx)
        matching = matchings[0]
        symbolic_params_map = match_symbolic_parameters(matching, self.lhs_graph_nx, subgraph_nx)

        vertices_to_remove = []
        for v in matching:
            if subgraph_nx.nodes()[matching[v]]['type'] != VertexType.BOUNDARY:
                vertices_to_remove.append(matching[v])

        boundary_vertex_map: dict[NodeView, int] = {}
        for v in self.rhs_graph_nx.nodes():
            if self.rhs_graph_nx.nodes()[v]['type'] == VertexType.BOUNDARY:
                for x, data in self.lhs_graph_nx.nodes(data=True):
                    if data['type'] == VertexType.BOUNDARY and \
                        data['boundary_index'] == self.rhs_graph_nx.nodes()[v]['boundary_index']:
                        boundary_vertex_map[v] = boundary_mapping[matching[x]]
                        break

        vertex_positions = get_vertex_positions(graph, self.rhs_graph_nx, boundary_vertex_map)
        self.last_rewrite_center = np.mean([(graph.row(m), graph.qubit(m)) for m in boundary_vertex_map.values()], axis=0)
        vertex_map = boundary_vertex_map
        for v in self.rhs_graph_nx.nodes():
            if self.rhs_graph_nx.nodes()[v]['type'] != VertexType.BOUNDARY:
                phase = self.rhs_graph_nx.nodes()[v]['phase']
                if isinstance(phase, Poly):
                    phase = phase.substitute(symbolic_params_map)
                    if phase.free_vars() == set():
                        phase = phase.terms[0][0] if len(phase.terms) > 0 else 0
                vertex_map[v] = graph.add_vertex(ty = self.rhs_graph_nx.nodes()[v]['type'],
                                                 row = vertex_positions[v][0],
                                                 qubit = vertex_positions[v][1],
                                                 phase = phase,)

        # create etab to add edges
        etab = {}
        for v1, v2, data in self.rhs_graph_nx.edges(data=True):
            v1 = vertex_map[v1]
            v2 = vertex_map[v2]
            if data['type'] == EdgeType.W_IO:
                graph.add_edge(graph.edge(v1, v2), EdgeType.W_IO)
                continue
            if (v1, v2) not in etab: etab[(v1, v2)] = [0, 0]
            etab[(v1, v2)][data['type']-1] += 1

        return etab, vertices_to_remove, [], True

    def unfuse_subgraph_for_rewrite(self, graph, vertices):
        graph_nx = to_networkx(graph)
        subgraph_nx_without_boundaries = nx.Graph(graph_nx.subgraph(vertices))
        lhs_vertices = [v for v in self.lhs_graph.vertices() if self.lhs_graph_nx.nodes()[v]['type'] != VertexType.BOUNDARY]
        lhs_graph_nx = nx.Graph(self.lhs_graph_nx.subgraph(lhs_vertices))
        graph_matcher = GraphMatcher(lhs_graph_nx, subgraph_nx_without_boundaries,
            node_match=categorical_node_match('type', 1))
        matching = list(graph_matcher.match())[0]

        subgraph_nx, boundary_mapping = create_subgraph(graph, vertices)
        for v in matching:
            if len([n for n in self.lhs_graph_nx.neighbors(v) if self.lhs_graph_nx.nodes()[n]['type'] == VertexType.BOUNDARY]) == 1:
                if len([b for b in subgraph_nx.neighbors(matching[v]) if subgraph_nx.nodes()[b]['type'] == VertexType.BOUNDARY]) != 1:
                    # now we unfuse
                    vtype = self.lhs_graph_nx.nodes()[v]['type']
                    if vtype == VertexType.Z or vtype == VertexType.X:
                        self.unfuse_zx(graph, subgraph_nx, matching[v], vtype)

    def unfuse_zx(self, graph, subgraph_nx, v, vtype):
        new_v = graph.add_vertex(vtype, qubit=graph.qubit(v), row=graph.row(v))
        neighbors = list(graph.neighbors(v))
        graph.add_edge(graph.edge(new_v, v))
        for b in neighbors:
            if b not in subgraph_nx.nodes:
                graph.remove_edge(graph.edge(v, b))
                graph.add_edge(graph.edge(new_v, b))

    def matcher(self, graph: GraphT, in_selection: Callable[[VT], bool]) -> list[VT]:
        vertices = [v for v in graph.vertices() if in_selection(v)]
        if self.is_rewrite_unfusable:
            subgraph_nx = nx.Graph(to_networkx(graph).subgraph(vertices))
            lhs_graph_nx = self.lhs_graph_without_boundaries_nx
        else:
            subgraph_nx, _ = create_subgraph(graph, vertices)
            lhs_graph_nx = self.lhs_graph_nx
        graph_matcher = GraphMatcher(lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match('type', 1))
        matchings = filter_matchings_if_symbolic_compatible(graph_matcher.match(), lhs_graph_nx, subgraph_nx)
        return vertices if matchings else []

    def to_json(self) -> str:
        return json.dumps({
            'lhs_graph': self.lhs_graph.to_json(),
            'rhs_graph': self.rhs_graph.to_json(),
            'name': self.name,
            'description': self.description,
        })

    @classmethod
    def from_json(cls, json_str: str) -> "CustomRule":
        d = json.loads(json_str)
        lhs_graph = GraphT.from_json(d['lhs_graph'])
        rhs_graph = GraphT.from_json(d['rhs_graph'])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert (isinstance(lhs_graph, GraphT) and isinstance(rhs_graph, GraphT))  # type: ignore
        return cls(lhs_graph, rhs_graph, d['name'], d['description'])

    def to_rewrite_data(self) -> "RewriteData":
        from .rewrite_data import MATCHES_VERTICES
        return {"text": self.name, "matcher": self.matcher, "rule": self, "type": MATCHES_VERTICES,
                "tooltip": self.description, 'copy_first': False, 'returns_new_graph': False}


def is_rewrite_unfusable(lhs_graph: GraphT) -> bool:
    # if any of the output edges of the lhs_graph is a Hadamard edge, then the rewrite is not unfusable
    for v in lhs_graph.outputs():
        for n in lhs_graph.neighbors(v):
            if lhs_graph.edge_type((v, n)) == EdgeType.HADAMARD:
                return False
    # all nodes must be connected to at most one boundary node
    for v in lhs_graph.vertices():
        if lhs_graph.type(v) == VertexType.BOUNDARY:
            continue
        if len([n for n in lhs_graph.neighbors(v) if lhs_graph.type(n) == VertexType.BOUNDARY]) > 1:
            return False
    return True

def get_linear(v):
    if not isinstance(v, Poly):
        raise ValueError("Not a symbolic parameter")
    if len(v.terms) > 2 or len(v.free_vars()) > 1:
        raise ValueError("Only linear symbolic parameters are supported")
    if len(v.terms) == 0:
        return 1, None, 0
    elif len(v.terms) == 1:
        if len(v.terms[0][1].vars) > 0:
            var_term = v.terms[0]
            const = 0
        else:
            const = v.terms[0][0]
            return 1, None, const
    else:
        if len(v.terms[0][1].vars) > 0:
            var_term = v.terms[0]
            const = v.terms[1][0]
        else:
            var_term = v.terms[1]
            const = v.terms[0][0]
    coeff = var_term[0]
    var, power = var_term[1].vars[0]
    if power != 1:
        raise ValueError("Only linear symbolic parameters are supported")
    return coeff, var, const


def match_symbolic_parameters(match, left, right):
    params = {}
    left_phase = left.nodes.data('phase', default=0)
    right_phase = right.nodes.data('phase', default=0)

    def check_phase_equality(v):
        if left_phase[v] != right_phase[match[v]]:
            raise ValueError("Parameters do not match")

    def update_params(v, var, coeff, const):
        var_value = (right_phase[match[v]] - const) / coeff
        if var in params and params[var] != var_value:
            raise ValueError("Symbolic parameters do not match")
        params[var] = var_value

    for v in left.nodes():
        if isinstance(left_phase[v], Poly):
            coeff, var, const = get_linear(left_phase[v])
            if var is None:
                check_phase_equality(v)
                continue
            update_params(v, var, coeff, const)
        else:
            check_phase_equality(v)

    return params


def filter_matchings_if_symbolic_compatible(matchings, left, right):
    new_matchings = []
    for matching in matchings:
        if len(matching) != len(left):
            continue
        try:
            match_symbolic_parameters(matching, left, right)
            new_matchings.append(matching)
        except ValueError:
            pass
    return new_matchings


def to_networkx(graph: GraphT) -> nx.Graph:
    G = nx.Graph()
    v_data = {v: {"type": graph.type(v),
                  "phase": graph.phase(v),}
              for v in graph.vertices()}
    for i, input_vertex in enumerate(graph.inputs()):
        v_data[input_vertex]["boundary_index"] = f'input_{i}'
    for i, output_vertex in enumerate(graph.outputs()):
        v_data[output_vertex]["boundary_index"] = f'output_{i}'
    G.add_nodes_from([(v, v_data[v]) for v in graph.vertices()])
    G.add_edges_from([(*v, {"type": graph.edge_type(v)}) for v in  graph.edges()])
    return G

def create_subgraph(graph: GraphT, verts: list[VT]) -> tuple[nx.Graph, dict[str, int]]:
    verts = [v for v in verts if graph.type(v) != VertexType.BOUNDARY]
    graph_nx = to_networkx(graph)
    subgraph_nx = nx.Graph(graph_nx.subgraph(verts))
    boundary_mapping = {}
    i = 0
    for v in verts:
        for vn in graph.neighbors(v):
            if vn not in verts:
                boundary_node = 'b' + str(i)
                boundary_mapping[boundary_node] = vn
                subgraph_nx.add_node(boundary_node, type=VertexType.BOUNDARY)
                subgraph_nx.add_edge(v, boundary_node, type=EdgeType.SIMPLE)
                i += 1
    return subgraph_nx, boundary_mapping

def get_vertex_positions(graph: GraphT, rhs_graph: nx.Graph, boundary_vertex_map: dict[NodeView, int]) -> dict[NodeView, tuple[float, float]]:
    pos_dict = {v: (graph.row(m), graph.qubit(m)) for v, m in boundary_vertex_map.items()}
    coords = np.array(list(pos_dict.values()))
    center = np.mean(coords, axis=0)
    angles = np.arctan2(coords[:,1]-center[1], coords[:,0]-center[0])
    coords = coords[np.argsort(-angles)]
    try:
        area = float(Polygon(coords).area)
    except:
        area = 1.
    k = (area ** 0.5) / len(rhs_graph)
    ret: dict[NodeView, tuple[float, float]] = nx.spring_layout(rhs_graph, k=k, pos=pos_dict, fixed=boundary_vertex_map.keys())
    return ret

def check_rule(rule: CustomRule, show_error: bool = True) -> bool:
    rule.lhs_graph.auto_detect_io()
    rule.rhs_graph.auto_detect_io()
    if len(rule.lhs_graph.inputs()) != len(rule.rhs_graph.inputs()) or \
        len(rule.lhs_graph.outputs()) != len(rule.rhs_graph.outputs()):
        if show_error:
            from .dialogs import show_error_msg
            show_error_msg("Warning!", "The left-hand side and right-hand side of the rule have different numbers of inputs or outputs.")
        return False
    if not rule.lhs_graph.variable_types and not rule.rhs_graph.variable_types:
        left_matrix, right_matrix = rule.lhs_graph.to_matrix(), rule.rhs_graph.to_matrix()
        if not np.allclose(left_matrix, right_matrix):
            if show_error:
                from .dialogs import show_error_msg
                if np.allclose(left_matrix / np.linalg.norm(left_matrix), right_matrix / np.linalg.norm(right_matrix)):
                    show_error_msg("Warning!", "The left-hand side and right-hand side of the rule differ by a scalar.")
                else:
                    show_error_msg("Warning!", "The left-hand side and right-hand side of the rule have different semantics.")
            return False
    else:
        if not (rule.rhs_graph.variable_types.items() <= rule.lhs_graph.variable_types.items()):
            if show_error:
                from .dialogs import show_error_msg
                show_error_msg("Warning!", "The right-hand side has more free variables than the left-hand side.")
            return False
        for vertex in rule.lhs_graph.vertices():
            if isinstance(rule.lhs_graph.phase(vertex), Poly):
                try:
                    get_linear(rule.lhs_graph.phase(vertex))
                except ValueError as e:
                    if show_error:
                        from .dialogs import show_error_msg
                        show_error_msg("Warning!", str(e))
                    return False
    return True
