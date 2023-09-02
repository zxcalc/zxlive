from typing import List

from pyzx.utils import EdgeType, VertexType

from .common import GraphT


def construct_circuit() -> GraphT:
    qubits = 4

    vlist = [
        (0, 0, 1), (1, 1, 2), (2, 2, 1), (3, 3, 1), (4, 0, 1), (5, 1, 1),
        (6, 2, 2), (7, 3, 1), (8, 0, 1), (9, 1, 2), (10, 2, 1), (11, 3, 1),
        (12, 0, 2), (13, 1, 2), (14, 2, 1), (15, 3, 2)]
    elist = [
        (0, 4, 0), (0, 1, 0), (1, 5, 0), (1, 6, 0), (2, 6, 0), (3, 7, 0),
        (5, 9, 1), (4, 8, 0), (6, 10, 0), (7, 11, 0), (8, 12, 0), (8, 13, 0),
        (9, 13, 1), (9, 14, 1), (10, 13, 0), (10, 14, 0), (11, 15, 0),
        (11, 14, 0)]

    nvertices = len(vlist) + (2 * qubits)

    ty: List[VertexType.Type] = [VertexType.BOUNDARY] * nvertices

    nvlist: list[tuple[int, int, VertexType.Type]] = []
    # Adding inputs nodes to the nvlist.
    for i in range(qubits):
        nvlist.append((i, i, VertexType.BOUNDARY))
        ty[i] = VertexType.BOUNDARY

    # Adding the actual vertices to the nvlist.
    for vert in vlist:
        # print(vert[2])
        if vert[2] == 1:
            ty[vert[0]+qubits] = VertexType.Z
            # print(ty)
        elif vert[2] == 2:
            ty[vert[0]+qubits] = VertexType.X
        nvlist.append((vert[0]+qubits, vert[1], ty[i+qubits-1]))

    # Adding the output nodes to the nvlist.
    for i in range(qubits):
        nvlist.append((nvertices - qubits + i, i, VertexType.BOUNDARY))
        ty[nvertices - qubits + i] = VertexType.BOUNDARY

    nelist = []

    # Updating the user provided elist to include input indices
    for edge in elist:
        nelist.append((edge[0]+qubits, edge[1]+qubits, edge[2]))

    # Adding the edges between inputs nodes and output nodes to internal nodes
    for i in range(qubits):
        nelist.append((i, i+qubits, 0))
        nelist.append((nvertices - qubits + i, nvertices - (2*qubits) + i, 0))

    cur_row = [1] * qubits

    g = GraphT()

    # Adding vertices to the graph
    for (i, qu, tp) in nvlist:
        rw = cur_row[qu]
        g.add_vertex(ty[i], qu, rw)
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
