from PySide6.QtCore import QSettings
from pyzx.tikz import TIKZ_BASE, _to_tikz

from zxlive.proof import ProofModel


def proof_to_tikz(proof: ProofModel) -> str:
    settings = QSettings("zxlive", "zxlive")
    vspace = float(settings.value("tikz/layout/vspace"))
    hspace = float(settings.value("tikz/layout/hspace"))
    max_width = float(settings.value("tikz/layout/max-width"))
    draw_scalar = False

    xoffset = -max_width
    yoffset = -10
    idoffset = 0
    total_verts, total_edges = [], []
    for i, g in enumerate(proof.graphs()):
        # Compute graph dimensions
        width = max(g.row(v) for v in g.vertices()) - min(g.row(v) for v in g.vertices())
        height = max(g.qubit(v) for v in g.vertices()) - min(g.qubit(v) for v in g.vertices())

        # Translate graph so that the first vertex starts at 0
        min_x = min(g.row(v) for v in g.vertices())
        g = g.translate(-min_x, 0)

        if i > 0:
            rewrite = proof.steps[i-1]
            # Try to look up name in settings
            name = settings.value(f"tikz/names/{rewrite.rule}") if settings.contains(f"tikz/names/{rewrite.rule}") else rewrite.rule
            eq = f"\\node [style=none] ({idoffset}) at ({xoffset - hspace/2:.2f}, {-yoffset - height/2:.2f}) {{$\\overset{{\\mathit{{{name}}}}}{{=}}$}};"
            total_verts.append(eq)
            idoffset += 1

        verts, edges = _to_tikz(g, draw_scalar, xoffset, yoffset, idoffset)
        total_verts.extend(verts)
        total_edges.extend(edges)

        if xoffset + hspace > max_width:
            xoffset = -max_width
            yoffset += height + vspace
        else:
            xoffset += width + hspace

        max_index = max(g.vertices()) + 2 * g.num_inputs() + 2
        idoffset += max_index

    return TIKZ_BASE.format(vertices="\n".join(total_verts), edges="\n".join(total_edges))

