from pyzx.utils import EdgeType, VertexType

from .common import GraphT, new_graph


def construct_circuit() -> GraphT:
    qubits = 4

    # Note: The qubit numbers in the graph which is returned from this function
    # will be 4 plus the numbers in vlist and elist, since the input nodes are
    # numbered from 0 to 3.

    # id, qubit number, vertex type (1 = Z, 2 = X).
    z, x = VertexType.Z, VertexType.X
    vlist = [
        (0, 0, z), (1, 1, x), (2, 2, z), (3, 3, z), (4, 0, z), (5, 1, z),
        (6, 2, x), (7, 3, z), (8, 0, z), (9, 1, x), (10, 2, z), (11, 3, z),
        (12, 0, x), (13, 1, x), (14, 2, z), (15, 3, x)]
    # id1, id2, edge type (0 = SIMPLE, 1 = HADAMARD)
    s, h = EdgeType.SIMPLE, EdgeType.HADAMARD
    elist = [
        (0, 1, s), (0, 4, s), (1, 5, s), (1, 6, s), (2, 6, s), (3, 7, s),
        (4, 8, s), (5, 9, h), (6, 10, s), (7, 11, s), (8, 12, s), (8, 13, s),
        (9, 13, h), (9, 14, h), (10, 13, s), (10, 14, s), (11, 14, s),
        (11, 15, s)]

    nvertices = len(vlist) + (2 * qubits)

    nvlist: list[tuple[int, int, VertexType]] = []
    # Adding inputs nodes to the nvlist.
    for i in range(qubits):
        nvlist.append((i, i, VertexType.BOUNDARY))

    # Adding the actual vertices to the nvlist.
    for vert in vlist:
        nvlist.append((vert[0]+qubits, vert[1], vert[2]))

    # Adding the output nodes to the nvlist.
    for i in range(qubits):
        nvlist.append((nvertices - qubits + i, i, VertexType.BOUNDARY))

    nelist:  list[tuple[int, int, EdgeType]] = []

    # Updating the user provided elist to include input indices
    for edge in elist:
        nelist.append((edge[0]+qubits, edge[1]+qubits, edge[2]))

    # Adding the edges between inputs nodes and output nodes to internal nodes
    for i in range(qubits):
        nelist.append((i, i+qubits, EdgeType.SIMPLE))
        nelist.append((nvertices - qubits + i, nvertices - (2*qubits) + i, EdgeType.SIMPLE))

    cur_row = [1] * qubits

    g = new_graph()

    # Adding vertices to the graph
    for (_, qu, tp) in nvlist:
        rw = cur_row[qu]
        g.add_vertex(tp, qu, rw)
        cur_row[qu] += 1

    es1 = [edge[:2] for edge in nelist if not edge[2]]
    es2 = [edge[:2] for edge in nelist if edge[2]]

    # TODO: add the phase part
    # for w, phase in phases.items():
    #     g.set_phase(w,phase)

    g.add_edges(es1, EdgeType.SIMPLE)
    g.add_edges(es2, EdgeType.HADAMARD)

    inputs = []
    outputs = []

    for i in range(qubits):
        inputs.append(i)
        outputs.append(nvertices-qubits+i)

    g.set_inputs(tuple(inputs))
    g.set_outputs(tuple(outputs))

    return g
