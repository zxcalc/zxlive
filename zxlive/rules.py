from pyzx.utils import EdgeType, VertexType

from statistics import fmean

ET_SIM = EdgeType.SIMPLE
ET_HAD = EdgeType.HADAMARD

VT_Z = VertexType.Z
VT_X = VertexType.X

def check_bialgebra(g, v_list):
    v_list = [v.v for v in v_list]

    phases = g.phases()
    x_vertices = []
    z_vertices = []

    for v in v_list:
        if phases[v] != 0:
            return False
        if g.type(v) == VT_X:
            x_vertices.append(v)
        elif g.type(v) == VT_Z:
            z_vertices.append(v)
        else:
            return False

    # all x vertices are connected to all z vertices
    for x in x_vertices:
        for z in z_vertices:
            if x not in g.neighbors(z):
                return False
            if g.edge_type(g.edge(x, z)) != ET_SIM:
                return False

    # not connected among themselves
    for vs in [x_vertices, z_vertices]:
        for v1 in vs:
            for v2 in vs:
                if v1 != v2 and v1 in g.neighbors(v2):
                    return False

    return True

def bialgebra(g, v_list):
    '''
    g: BaseGraph[[VT,ET]]
    v_list: list of vertex where bialgebra needs to be applied
    returns: The graph with bialgebra rule applied if the vertices provided can be simplified by this rule
    '''
    if not check_bialgebra(g, v_list):
        return

    v_list = [v.v for v in v_list]

    x_vertices = list(filter(lambda v: g.type(v) == VT_X, v_list))
    z_vertices = list(filter(lambda v: g.type(v) == VT_Z, v_list))

    nodes = []

    for nt, vs in [(VT_Z, x_vertices), (VT_X, z_vertices)]:
        q = fmean([g.qubit(x) for x in vs])
        r = fmean([g.row(x) for x in vs])
        node = g.add_vertex(nt, q, r)
        nodes.append(node)

        for v in vs:
            for n in g.neighbors(v):
                g.add_edge(g.edge(node, n), ET_SIM)
            g.remove_vertex(v)
    
    g.add_edge(g.edge(nodes[0], nodes[1]), ET_SIM)

def add_node(g, u, v):
    '''
    g: BaseGraph[[VT,ET]]
    u: node 1
    v: node 2
    returns: a graph with between 'u' and 'v', connected via regular edge
    '''
    uv = g.edge(u, v)
    if uv in g.edge_set():
        r = 0.5 * (g.row(u) + g.row(v))
        q = 0.5 * (g.qubit(u) + g.qubit(v))
        w = g.add_vertex(VT_Z, q, r, 0)

        g.add_edge(g.edge(u, w), ET_SIM)
        g.add_edge(g.edge(v, w), g.edge_type(uv))
        g.remove_edge(uv)
