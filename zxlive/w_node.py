# Utils for W node
from pyzx.utils import EdgeType, VertexType

from .common import VT, ET, GraphT


def is_w_vertex_type(vertex_type) -> bool:
    return vertex_type == VertexType.W_INPUT or vertex_type == VertexType.W_OUTPUT

def is_w_edge_type(edge_type) -> bool:
    return edge_type == EdgeType.W_IO

def get_w_partner(g: GraphT, v: VT) -> VT:
    assert is_w_vertex_type(g.type(v))
    for u in g.neighbors(v):
        if g.edge_type((u, v)) == EdgeType.W_IO:
            return u
