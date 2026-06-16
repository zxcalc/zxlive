from PySide6.QtCore import QSettings
from pyzx.tikz import TIKZ_BASE, _to_tikz

from .common import GraphT, get_settings_value
from zxlive.proof import ProofModel, Rewrite


def _escape_tex(s: str) -> str:
    """Escape characters that would otherwise break LaTeX parsing."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append(r"\backslash{}")
        elif ch in "{}%#&$_":
            out.append("\\" + ch)
        elif ch == "^":
            out.append(r"\string^")
        elif ch == "~":
            out.append(r"\string~")
        else:
            out.append(ch)
    return "".join(out)


def _normalise_graph(g: GraphT) -> tuple[GraphT, int, float, float]:
    """Translate ``g`` so its vertices start at the origin.

    Returns the translated graph, the maximum vertex ID, width and height.
    Empty graphs are returned untouched with max vertex ID -1 and zero width
    and height.
    """
    vertex_ids = list(g.vertices())
    if not vertex_ids:
        return g, -1, 0.0, 0.0
    rows = [g.row(v) for v in vertex_ids]
    qubits = [g.qubit(v) for v in vertex_ids]
    min_x, max_x = min(rows), max(rows)
    min_y, max_y = min(qubits), max(qubits)
    g_t = g.translate(-min_x, -min_y)
    assert isinstance(g_t, GraphT)
    return g_t, max(vertex_ids), max_x - min_x, max_y - min_y


def _eq_node(settings: QSettings, rewrite: Rewrite, idoffset: int, xoffset: float,
             yoffset: float, hspace: float, eq_height: float) -> str:
    """Format the equal-sign node that sits between two adjacent proof graphs."""
    key = f"tikz/names/{rewrite.rule}"
    name = settings.value(key) if settings.contains(key) else rewrite.rule
    # Escape TeX-special characters since the name is interpolated into LaTeX.
    name = _escape_tex(str(name))
    return (f"\\node [style=none] ({idoffset}) at "
            f"({xoffset - hspace/2:.2f}, {-yoffset - eq_height/2:.2f}) "
            f"{{$\\mathrel{{\\mathop{{=}}\\limits^{{\\mathit{{{name}}}}}}}$}};")


def proof_to_tikz(proof: ProofModel) -> str:
    settings = QSettings("zxlive", "zxlive")
    vspace = get_settings_value("tikz/layout/vspace", float, settings=settings)
    hspace = get_settings_value("tikz/layout/hspace", float, settings=settings)
    max_width = get_settings_value("tikz/layout/max-width", float, settings=settings)

    xoffset = -max_width
    yoffset = -10.0
    idoffset = 0
    total_verts, total_edges = [], []
    prev_height = 0.0
    row_max_height = 0.0
    for i, g_in in enumerate(proof.graphs()):
        g, max_vertex_id, width, height = _normalise_graph(g_in)

        # Wrap before emitting the graph so it is never placed past max_width,
        # and advance yoffset by the tallest graph in the row being closed (not
        # just the last one) so the next row cannot overlap a taller neighbour.
        wrapped = False
        if i > 0 and xoffset + width > max_width:
            xoffset = -max_width
            yoffset += row_max_height + vspace
            row_max_height = 0.0
            wrapped = True

        if i > 0:
            # Use the max of prev_height and current height to centre the equal
            # sign. If wrapped to a new row, ignore prev_height since it is on
            # a different row.
            eq_height = height if wrapped else max(prev_height, height)
            total_verts.append(_eq_node(settings, proof.steps[i - 1], idoffset,
                                        xoffset, yoffset, hspace, eq_height))
            idoffset += 1

        verts, edges = _to_tikz(g, False, xoffset, yoffset, idoffset)
        total_verts.extend(verts)
        total_edges.extend(edges)

        row_max_height = max(row_max_height, height)
        xoffset += width + hspace

        if max_vertex_id >= 0:
            idoffset += max_vertex_id + 2 * g.num_inputs() + 2
        prev_height = height

    return TIKZ_BASE.format(vertices="\n".join(total_verts), edges="\n".join(total_edges))


def graph_to_tikz(graph: GraphT) -> str:
    """Convert a single graph to TikZ format."""
    g_t, _, _, _ = _normalise_graph(graph)
    verts, edges = _to_tikz(g_t, draw_scalar=False, xoffset=0, yoffset=0, idoffset=0)
    return TIKZ_BASE.format(vertices="\n".join(verts), edges="\n".join(edges))


def proof_steps_to_tikz(proof: ProofModel) -> list[tuple[str, str]]:
    """Convert each proof step to a separate TikZ string.

    Returns a list of (step_name, tikz_string) tuples.
    """
    result = []
    graphs = proof.graphs()

    for i, g in enumerate(graphs):
        if i == 0:
            name = "START"
        else:
            name = proof.steps[i - 1].display_name

        tikz = graph_to_tikz(g)
        result.append((name, tikz))

    return result
