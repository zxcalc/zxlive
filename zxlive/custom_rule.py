
import json
from typing import TYPE_CHECKING, Callable, List

import networkx as nx
import numpy as np
import pyzx
from networkx.algorithms.isomorphism import (GraphMatcher,
                                             categorical_node_match)
from networkx.classes.reportviews import NodeView
from pyzx.utils import EdgeType, VertexType
from shapely import Polygon

from .common import ET, VT, GraphT

if TYPE_CHECKING:
    from .proof_actions import ProofAction

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

    def __call__(self, graph: GraphT, vertices: List[VT]) -> pyzx.rules.RewriteOutputType[ET,VT]:
        subgraph_nx, boundary_mapping = create_subgraph(graph, vertices)
        graph_matcher = GraphMatcher(self.lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match(['type', 'phase'], default=[1, 0]))
        matching = list(graph_matcher.match())[0]

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
                vertex_map[v] = graph.add_vertex(ty = self.rhs_graph_nx.nodes()[v]['type'],
                                                 row = vertex_positions[v][0],
                                                 qubit = vertex_positions[v][1],
                                                 phase = self.rhs_graph_nx.nodes()[v]['phase'],)

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

    def matcher(self, graph: GraphT, in_selection: Callable[[VT], bool]) -> List[VT]:
        vertices = [v for v in graph.vertices() if in_selection(v)]
        subgraph_nx, _ = create_subgraph(graph, vertices)
        graph_matcher = GraphMatcher(self.lhs_graph_nx, subgraph_nx,
            node_match=categorical_node_match(['type', 'phase'], default=[1, 0]))
        if graph_matcher.is_isomorphic():
            return vertices
        return []

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
        assert (isinstance(lhs_graph, GraphT) and
                isinstance(rhs_graph, GraphT))
        return cls(lhs_graph, rhs_graph, d['name'], d['description'])

    def to_proof_action(self) -> "ProofAction":
        from .proof_actions import MATCHES_VERTICES, ProofAction
        return ProofAction(self.name, self.matcher, self, MATCHES_VERTICES, self.description)


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

def create_subgraph(graph: GraphT, verts: List[VT]) -> tuple[nx.Graph, dict[str, int]]:
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
    left_matrix, right_matrix = rule.lhs_graph.to_matrix(), rule.rhs_graph.to_matrix()
    if not np.allclose(left_matrix, right_matrix):
        if show_error:
            from .dialogs import show_error_msg
            if np.allclose(left_matrix / np.linalg.norm(left_matrix), right_matrix / np.linalg.norm(right_matrix)):
                show_error_msg("Warning!", "The left-hand side and right-hand side of the rule differ by a scalar.")
            else:
                show_error_msg("Warning!", "The left-hand side and right-hand side of the rule have different semantics.")
        return False
    return True
