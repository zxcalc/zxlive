"""Demo of embedded ZXLive running as a standalone script.

Creates a small PyZX graph, opens it in ZXLive for interactive editing,
and retrieves the modified graph after the window is closed.

Usage:
    python embedded_zxlive_demo.py
"""

import pyzx as zx

from zxlive.app import get_embedded_app

# Build a small PyZX circuit (two CNOTs, same style topologiq uses for input).
circuit = zx.Circuit(2)
circuit.add_gate("CNOT", 0, 1)
circuit.add_gate("CNOT", 1, 0)
graph = circuit.to_graph()

print(f"Original graph: {graph.num_vertices()} vertices, {graph.num_edges()} edges")

# Launch ZXLive as an embedded editor.
zxl = get_embedded_app()
zxl.edit_graph(graph, "demo")

# Block until the user closes the ZXLive window.
zxl.exec_()

# Retrieve the (possibly edited) graph.
edited = zxl.get_copy_of_graph("demo")
if edited is not None:
    print(f"Edited graph:   {edited.num_vertices()} vertices, {edited.num_edges()} edges")
else:
    print("No graph returned (tab may have been closed).")
