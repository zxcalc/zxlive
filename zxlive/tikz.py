from PySide6.QtCore import QSettings
from pyzx.tikz import TIKZ_BASE, _to_tikz

from .common import GraphT, get_settings_value
from zxlive.proof import ProofModel


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


def proof_to_tikz(proof: ProofModel) -> str:
    settings = QSettings("zxlive", "zxlive")
    vspace = get_settings_value("tikz/layout/vspace", float, settings=settings)
    hspace = get_settings_value("tikz/layout/hspace", float, settings=settings)
    max_width = get_settings_value("tikz/layout/max-width", float, settings=settings)
    draw_scalar = False

    xoffset = -max_width
    yoffset = -10
    idoffset = 0
    total_verts, total_edges = [], []
    prev_height = 0.0
    prev_wrapped = False
    for i, g in enumerate(proof.graphs()):
        # Compute graph dimensions and origin offsets in a single pass.
        vertex_ids = list(g.vertices())
        rows = [g.row(v) for v in vertex_ids]
        qubits = [g.qubit(v) for v in vertex_ids]
        min_x, max_x = min(rows), max(rows)
        min_y, max_y = min(qubits), max(qubits)
        width = max_x - min_x
        height = max_y - min_y

        # Translate graph so that vertices start at the origin.
        g_t = g.translate(-min_x, -min_y)
        assert isinstance(g_t, GraphT)
        g = g_t

        if i > 0:
            rewrite = proof.steps[i - 1]
            # Try to look up name in settings
            name = settings.value(f"tikz/names/{rewrite.rule}") if settings.contains(f"tikz/names/{rewrite.rule}") else rewrite.rule
            # Escape TeX-special characters since the name is interpolated into LaTeX.
            name = _escape_tex(str(name))
            # Use the max of prev_height and current height to centre the equal sign.
            # If the previous graph wrapped to a new row, ignore its height since
            # it is on a different row.
            eq_height = height if prev_wrapped else max(prev_height, height)
            eq = f"\\node [style=none] ({idoffset}) at ({xoffset - hspace/2:.2f}, {-yoffset - eq_height/2:.2f}) {{$\\mathrel{{\\mathop{{=}}\\limits^{{\\mathit{{{name}}}}}}}$}};"
            total_verts.append(eq)
            idoffset += 1

        verts, edges = _to_tikz(g, draw_scalar, xoffset, yoffset, idoffset)
        total_verts.extend(verts)
        total_edges.extend(edges)

        next_xoffset = xoffset + width + hspace
        if next_xoffset > max_width:
            xoffset = -max_width
            yoffset += height + vspace
            prev_wrapped = True
        else:
            xoffset = next_xoffset
            prev_wrapped = False

        max_index = max(vertex_ids) + 2 * g.num_inputs() + 2
        idoffset += max_index
        prev_height = height

    return TIKZ_BASE.format(vertices="\n".join(total_verts), edges="\n".join(total_edges))
