
import json
from fractions import Fraction
from typing import TYPE_CHECKING, Callable, Optional, Sequence, Dict, Union

import networkx as nx
import numpy as np
import pyzx
from networkx.algorithms.isomorphism import (GraphMatcher,
                                             categorical_node_match, categorical_edge_match)
from networkx.classes.reportviews import NodeView
from pyzx.utils import EdgeType, VertexType, get_w_io
from shapely import Polygon

from pyzx.symbolic import Poly, Var

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

    def __call__(self, graph: GraphT, vertices: list[VT]) -> pyzx.rules.RewriteOutputType[VT, ET]:
        if self.is_rewrite_unfusable:
            self.unfuse_subgraph_for_rewrite(graph, vertices)

        subgraph_nx, boundary_mapping = create_subgraph(graph, vertices)
        graph_matcher = GraphMatcher(self.lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match('type', 1),
            edge_match=categorical_edge_match('type', 1))
        matchings = graph_matcher.match()
        matchings = filter_matchings_if_symbolic_compatible(matchings, self.lhs_graph_nx, subgraph_nx)
        if len(matchings) == 0:
            raise ValueError("No matchings found")
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

    def unfuse_subgraph_for_rewrite(self, graph: GraphT, vertices: list[VT]) -> None:
        def get_adjacent_boundary_vertices(g: nx.Graph, v: VT) -> Sequence[VT]:
            return [n for n in g.neighbors(v) if g.nodes()[n]['type'] == VertexType.BOUNDARY]

        subgraph_nx_without_boundaries = nx.Graph(to_networkx(graph).subgraph(vertices))
        lhs_vertices = [v for v in self.lhs_graph.vertices() if self.lhs_graph_nx.nodes()[v]['type'] != VertexType.BOUNDARY]
        lhs_graph_nx = nx.Graph(self.lhs_graph_nx.subgraph(lhs_vertices))
        graph_matcher = GraphMatcher(lhs_graph_nx, subgraph_nx_without_boundaries,
                                     node_match=categorical_node_match('type', 1))
        matching = list(graph_matcher.match())[0]

        subgraph_nx, _ = create_subgraph(graph, vertices)
        for v in matching:
            if len(get_adjacent_boundary_vertices(self.lhs_graph_nx, v)) != 1:
                continue
            vtype = self.lhs_graph_nx.nodes()[v]['type']
            outside_verts = get_adjacent_boundary_vertices(subgraph_nx, matching[v])
            if len(outside_verts) == 1 and \
                subgraph_nx.edges()[(matching[v], outside_verts[0])]['type'] == EdgeType.SIMPLE and \
                vtype != VertexType.W_INPUT:
                continue
            if vtype == VertexType.Z or vtype == VertexType.X or vtype == VertexType.Z_BOX:
                self.unfuse_zx_vertex(graph, subgraph_nx, matching[v], vtype)
            elif vtype == VertexType.H_BOX:
                self.unfuse_h_box_vertex(graph, subgraph_nx, matching[v])
            elif vtype == VertexType.W_OUTPUT or vtype == VertexType.W_INPUT:
                self.unfuse_w_vertex(graph, subgraph_nx, matching[v], vtype)

    def unfuse_update_edges(self, graph: GraphT, subgraph_nx: nx.Graph, old_v: VT, new_v: VT) -> None:
        neighbors = list(graph.neighbors(old_v))
        for b in neighbors:
            if b not in subgraph_nx.nodes:
                graph.add_edge((new_v, b), graph.edge_type((old_v, b)))
                graph.remove_edge(graph.edge(old_v, b))

    def unfuse_zx_vertex(self, graph: GraphT, subgraph_nx: nx.Graph, v: VT, vtype: VertexType) -> None:
        new_v = graph.add_vertex(vtype, qubit=graph.qubit(v), row=graph.row(v))
        self.unfuse_update_edges(graph, subgraph_nx, v, new_v)
        graph.add_edge(graph.edge(new_v, v))

    def unfuse_h_box_vertex(self, graph: GraphT, subgraph_nx: nx.Graph, v: VT) -> None:
        new_h = graph.add_vertex(VertexType.H_BOX, qubit=graph.qubit(v)+0.3, row=graph.row(v)+0.3)
        new_mid_h = graph.add_vertex(VertexType.H_BOX, qubit=graph.qubit(v), row=graph.row(v))
        self.unfuse_update_edges(graph, subgraph_nx, v, new_h)
        graph.add_edge((new_mid_h, v))
        graph.add_edge((new_h, new_mid_h))

    def unfuse_w_vertex(self, graph: GraphT, subgraph_nx: nx.Graph, v: VT, vtype: VertexType) -> None:
        w_in, w_out = get_w_io(graph, v)
        new_w_in = graph.add_vertex(VertexType.W_INPUT, qubit=graph.qubit(w_in), row=graph.row(w_in))
        new_w_out = graph.add_vertex(VertexType.W_OUTPUT, qubit=graph.qubit(w_out), row=graph.row(w_out))
        self.unfuse_update_edges(graph, subgraph_nx, w_in, new_w_in)
        self.unfuse_update_edges(graph, subgraph_nx, w_out, new_w_out)
        if vtype == VertexType.W_OUTPUT:
            graph.add_edge((new_w_in, w_out))
        else:
            graph.add_edge((w_in, new_w_out))
        graph.add_edge((new_w_in, new_w_out), EdgeType.W_IO)

    def matcher(self, graph: GraphT, in_selection: Callable[[VT], bool]) -> list[VT]:
        vertices = [v for v in graph.vertices() if in_selection(v)]
        if self.is_rewrite_unfusable:
            subgraph_nx = nx.Graph(to_networkx(graph).subgraph(vertices))
            lhs_graph_nx = self.lhs_graph_without_boundaries_nx
        else:
            subgraph_nx, _ = create_subgraph(graph, vertices)
            lhs_graph_nx = self.lhs_graph_nx
        graph_matcher = GraphMatcher(lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match('type', 1),
            edge_match=categorical_edge_match('type', 1))
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
                "tooltip": self.description, 'copy_first': False, 'returns_new_graph': False,
                "custom_rule": True, "lhs": self.lhs_graph, "rhs": self.rhs_graph}



def is_rewrite_unfusable(lhs_graph: GraphT) -> bool:
    # if any of the output edges of the lhs_graph is a Hadamard edge, then the rewrite is not unfusable
    for v in lhs_graph.outputs():
        for n in lhs_graph.neighbors(v):
            if lhs_graph.graph[v][n].h != 0:
                return False
    # all nodes must be connected to at most one boundary node
    for v in lhs_graph.vertices():
        if lhs_graph.type(v) == VertexType.BOUNDARY:
            continue
        if len([n for n in lhs_graph.neighbors(v) if lhs_graph.type(n) == VertexType.BOUNDARY]) > 1:
            return False
    return True

def get_linear(v: Poly) -> tuple[Union[int, float, complex, Fraction], Optional[Var], Union[int, float, complex, Fraction]]:
    if not isinstance(v, Poly):
        raise ValueError("Not a symbolic parameter")
    if len(v.terms) > 2 or len(v.free_vars()) > 1:
        raise ValueError("Only linear symbolic parameters are supported")
    if len(v.terms) == 0:
        return 1, None, 0
    elif len(v.terms) == 1:
        if len(v.terms[0][1].vars) > 0:
            var_term = v.terms[0]
            const: Union[int, float, complex, Fraction] = 0
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


def match_symbolic_parameters(match: Dict[VT, VT], left: nx.Graph, right: nx.Graph) -> Dict[Var, Union[int, float, complex, Fraction]]:
    params: Dict[Var, Union[int, float, complex, Fraction]] = {}
    left_phase = left.nodes.data('phase', default=0) # type: ignore
    right_phase = right.nodes.data('phase', default=0) # type: ignore

    def check_phase_equality(v: VT) -> None:
        if left_phase[v] != right_phase[match[v]]:
            raise ValueError("Parameters do not match")

    def update_params(v: VT, var: Var, coeff: Union[int, float, complex, Fraction], const: Union[int, float, complex, Fraction]) -> None:
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


def filter_matchings_if_symbolic_compatible(matchings: list[Dict[VT, VT]], left: nx.Graph, right: nx.Graph) -> list[Dict[VT, VT]]:
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
    G.add_edges_from([(source, target, {"type": typ}) for source, target, typ in  graph.edges()])
    return G

def create_subgraph(graph: GraphT, verts: list[VT]) -> tuple[nx.Graph, dict[str, int]]:
    verts = [v for v in verts if graph.type(v) != VertexType.BOUNDARY]
    graph_nx = to_networkx(graph)
    subgraph_nx = nx.Graph(graph_nx.subgraph(verts))
    boundary_mapping = {}
    i = 0
    for v in verts:
        for e in graph.incident_edges(v):
            s, t = graph.edge_st(e)
            if s not in verts or t not in verts:
                boundary_node = 'b' + str(i)
                boundary_mapping[boundary_node] = s if s not in verts else t
                subgraph_nx.add_node(boundary_node, type=VertexType.BOUNDARY)
                subgraph_nx.add_edge(v, boundary_node, type=graph.edge_type(e))
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
    # if the node type in ret is W_INPUT, move it next to the W_OUTPUT node
    for v in ret:
        if rhs_graph.nodes()[v]['type'] == VertexType.W_INPUT:
            w_out = next((n for n in rhs_graph.neighbors(v) if rhs_graph.edges()[(v, n)]['type'] == EdgeType.W_IO), None)
            if w_out and rhs_graph.nodes()[w_out]['type'] == VertexType.W_OUTPUT:
                ret[v] = (ret[w_out][0] - 0.3, ret[w_out][1])
    return ret


def check_rule(rule: CustomRule) -> None:
    rule.lhs_graph.auto_detect_io()
    rule.rhs_graph.auto_detect_io()
    if len(rule.lhs_graph.inputs()) != len(rule.rhs_graph.inputs()) or \
        len(rule.lhs_graph.outputs()) != len(rule.rhs_graph.outputs()):
        raise ValueError("The left-hand side and right-hand side of the rule have different numbers of inputs or outputs.")
    if not rule.lhs_graph.variable_types and not rule.rhs_graph.variable_types:
        left_matrix, right_matrix = rule.lhs_graph.to_matrix(), rule.rhs_graph.to_matrix()
        if not np.allclose(left_matrix, right_matrix):
            if np.allclose(left_matrix / np.linalg.norm(left_matrix), right_matrix / np.linalg.norm(right_matrix)):
                raise ValueError("The left-hand side and right-hand side of the rule differ by a scalar.")
            else:
                raise ValueError("The left-hand side and right-hand side of the rule have different semantics.")
    else:
        if not (rule.rhs_graph.variable_types.items() <= rule.lhs_graph.variable_types.items()):
            raise ValueError("The right-hand side has more free variables than the left-hand side.")
        for vertex in rule.lhs_graph.vertices():
            if isinstance(rule.lhs_graph.phase(vertex), Poly):
                try:
                    get_linear(rule.lhs_graph.phase(vertex))
                except ValueError as e:
                    raise ValueError(f"Error in left-hand side phase: {str(e)}")
