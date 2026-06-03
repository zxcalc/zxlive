#!/usr/bin/env python3
"""Generate before/after GIFs for proof-mode interaction docs.

Run with:
    QT_QPA_PLATFORM=offscreen python3 doc/scripts/generate_proof_mode_assets.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import pyzx
from fractions import Fraction

from pyzx.utils import VertexType

from zxlive.commands import AddRewriteStep
from zxlive.common import GraphT, new_graph
from zxlive.proof_panel import ProofPanel

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "doc" / "_static"


def process() -> None:
    QApplication.processEvents()
    QApplication.processEvents()
    QApplication.processEvents()


def grab_canvas(panel: ProofPanel, path: Path) -> None:
    """Grab only the graph canvas (not sidebars)."""
    process()
    pix = panel.graph_view.grab()
    pix.save(str(path))


def pngs_to_gif(
    before: Path,
    after: Path,
    out: Path,
    before_hold_s: float = 2.0,
    after_hold_s: float = 2.0,
) -> None:
    """Build a looping before→after GIF with configurable hold times."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        f_before = tmpdir / "frame_before.png"
        f_after = tmpdir / "frame_after.png"
        shutil.copy(before, f_before)
        shutil.copy(after, f_after)

        concat_txt = tmpdir / "concat.txt"
        with open(concat_txt, "w") as f:
            f.write(f"file '{f_before}'\n")
            f.write(f"duration {before_hold_s:.2f}\n")
            f.write(f"file '{f_after}'\n")
            f.write(f"duration {after_hold_s:.2f}\n")
            # repeat last frame so ffmpeg respects the final duration
            f.write(f"file '{f_after}'\n")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                "-loop", "0",
                str(out),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def make_panel(g: GraphT) -> ProofPanel:
    panel = ProofPanel(g)
    panel.resize(800, 550)
    panel.show()
    process()
    br = panel.graph_scene.itemsBoundingRect()
    panel.graph_view.fitInView(br.adjusted(-50, -50, 50, 50),
                               Qt.AspectRatioMode.KeepAspectRatio)
    process()
    return panel


def apply_rewrite(panel: ProofPanel, g: GraphT, name: str) -> None:
    cmd = AddRewriteStep(panel.graph_view, g, panel.step_view, name)
    panel.undo_stack.push(cmd)
    process()
    br = panel.graph_scene.itemsBoundingRect()
    panel.graph_view.fitInView(br.adjusted(-50, -50, 50, 50),
                               Qt.AspectRatioMode.KeepAspectRatio)
    process()


def wire_graph() -> GraphT:
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    g.add_edge((b0, b1))
    return g


def identity_spider_graph() -> GraphT:
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    z  = g.add_vertex(VertexType.Z,        qubit=0, row=1)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    g.add_edge((b0, z))
    g.add_edge((z, b1))
    return g


def hopf_graph() -> GraphT:
    """Three parallel edges between Z and X — wand removes one pair, one remains."""
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    z  = g.add_vertex(VertexType.Z,        qubit=0, row=1)
    x  = g.add_vertex(VertexType.X,        qubit=0, row=2)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    g.add_edge((b0, z))
    g.add_edge((z, x))
    g.add_edge((z, x))
    g.add_edge((z, x))   # three parallel edges; wand removes 2 (one pair), leaving 1
    g.add_edge((x, b1))
    return g


def fuse_graph() -> GraphT:
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    z1 = g.add_vertex(VertexType.Z,        qubit=0, row=1)
    z2 = g.add_vertex(VertexType.Z,        qubit=0, row=2)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    g.add_edge((b0, z1))
    g.add_edge((z1, z2))
    g.add_edge((z2, b1))
    return g


def bialgebra_graph() -> GraphT:
    """Two-qubit circuit fragment where bialgebra applies."""
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=0)
    z  = g.add_vertex(VertexType.Z,        qubit=0, row=1)
    x  = g.add_vertex(VertexType.X,        qubit=1, row=1)
    b2 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    b3 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=2)
    g.add_edge((b0, z))
    g.add_edge((b1, x))
    g.add_edge((z, x))
    g.add_edge((z, b2))
    g.add_edge((x, b3))
    return g


def copy_pi_graph() -> GraphT:
    """Z(π) spider with one non-boundary neighbour (X spider with two outputs).

    "Single-legged" in ZX calculus = one connection to another spider, not counting
    the boundary wire on the left which is just the circuit input port.
    """
    g = new_graph()
    b_in  = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=0)
    z_pi  = g.add_vertex(VertexType.Z,        qubit=1, row=1, phase=Fraction(1, 1))
    x     = g.add_vertex(VertexType.X,        qubit=1, row=2)
    b_out0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    b_out1 = g.add_vertex(VertexType.BOUNDARY, qubit=2, row=3)
    g.add_edge((b_in, z_pi))
    g.add_edge((z_pi, x))
    g.add_edge((x, b_out0))
    g.add_edge((x, b_out1))
    return g


def pauli_graph() -> GraphT:
    """Z(π/2) spider adjacent to an X(π) arity-2 spider (Pauli).

    pauli_push(g, z, x): z = target, x = Pauli (second arg must be Pauli spider).
    After push: X(π) consumed, Z phase remains, X becomes phaseless.
    Phases must be Fraction for pyzx's phase_is_pauli check.
    """
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    z  = g.add_vertex(VertexType.Z,        qubit=0, row=1, phase=Fraction(1, 2))
    x  = g.add_vertex(VertexType.X,        qubit=0, row=2, phase=Fraction(1, 1))
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    g.add_edge((b0, z))
    g.add_edge((z, x))
    g.add_edge((x, b1))
    return g


def unfuse_graph() -> GraphT:
    """Z(π/2) spider with 3 legs — good for demonstrating slice."""
    g = new_graph()
    b0 = g.add_vertex(VertexType.BOUNDARY, qubit=-1, row=0)
    b1 = g.add_vertex(VertexType.BOUNDARY, qubit=1,  row=0)
    z  = g.add_vertex(VertexType.Z,        qubit=0,  row=1, phase=Fraction(1, 2))
    b2 = g.add_vertex(VertexType.BOUNDARY, qubit=0,  row=2)
    g.add_edge((b0, z))
    g.add_edge((b1, z))
    g.add_edge((z, b2))
    return g


def generate() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    tmp = STATIC / "_gen_tmp"
    tmp.mkdir(exist_ok=True)

    # magic wand: add identity
    p = make_panel(wire_graph())
    f_before = tmp / "add_id_before.png"
    grab_canvas(p, f_before)
    g = wire_graph()
    verts = sorted(g.vertices())
    b0, b1 = verts[0], verts[1]
    z = g.add_vertex(VertexType.Z, qubit=0, row=1)
    edge = next(iter(g.edges()))
    g.remove_edge(edge)
    g.add_edge((b0, z))
    g.add_edge((z, b1))
    apply_rewrite(p, g, "Add identity")
    f_after = tmp / "add_id_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "magic_wand_add_identity.gif")

    # magic wand: remove identity
    p = make_panel(identity_spider_graph())
    f_before = tmp / "rem_id_before.png"
    grab_canvas(p, f_before)
    g = identity_spider_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    pyzx.rewrite_rules.remove_id(g, z)
    apply_rewrite(p, g, "Remove identity")
    f_after = tmp / "rem_id_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "magic_wand_remove_identity.gif")

    # magic wand: hopf
    p = make_panel(hopf_graph())
    f_before = tmp / "hopf_before.png"
    grab_canvas(p, f_before)
    g = hopf_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    x = next(v for v in g.vertices() if g.type(v) == VertexType.X)
    # remove one pair from 3 parallel edges, leaving 1
    edges_zx = list(g.edges(z, x))
    for e in edges_zx[:2]:
        g.remove_edge(e)
    apply_rewrite(p, g, "Remove parallel edges")
    f_after = tmp / "hopf_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "magic_wand_hopf.gif")

    # magic wand: unfuse
    p = make_panel(unfuse_graph())
    f_before = tmp / "unfuse_before.png"
    grab_canvas(p, f_before)
    g = unfuse_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    # default (non-Shift) wand: new spider gets phase 0, original keeps its phase
    left = g.add_vertex(VertexType.Z, qubit=-0.5, row=0.5)
    neighbors = list(g.neighbors(z))
    moved = 0
    for nb in neighbors:
        if moved >= 2:
            break
        if g.type(nb) == VertexType.BOUNDARY:
            etype = g.edge_type(g.edge(z, nb))
            g.remove_edge(g.edge(z, nb))
            g.add_edge((left, nb), etype)
            moved += 1
    g.add_edge((z, left))
    apply_rewrite(p, g, "unfuse")
    f_after = tmp / "unfuse_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "magic_wand_unfuse.gif")

    # drag: fuse
    p = make_panel(fuse_graph())
    f_before = tmp / "fuse_before.png"
    grab_canvas(p, f_before)
    g = fuse_graph()
    zs = [v for v in g.vertices() if g.type(v) == VertexType.Z]
    pyzx.rewrite_rules.fuse(g, zs[1], zs[0])
    apply_rewrite(p, g, "Fuse spiders")
    f_after = tmp / "fuse_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "drag_fuse.gif")

    # drag: bialgebra
    p = make_panel(bialgebra_graph())
    f_before = tmp / "bialg_before.png"
    grab_canvas(p, f_before)
    g = bialgebra_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    x = next(v for v in g.vertices() if g.type(v) == VertexType.X)
    pyzx.rewrite_rules.bialgebra(g, x, z)
    apply_rewrite(p, g, "Strong complementarity")
    f_after = tmp / "bialg_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "drag_bialgebra.gif")

    # drag: copy pi
    p = make_panel(copy_pi_graph())
    f_before = tmp / "copy_before.png"
    grab_canvas(p, f_before)
    g = copy_pi_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    pyzx.rewrite_rules.copy(g, z)
    apply_rewrite(p, g, "Copy spider through other spider")
    f_after = tmp / "copy_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "drag_copy_pi.gif")

    # drag: push pauli
    p = make_panel(pauli_graph())
    f_before = tmp / "pauli_before.png"
    grab_canvas(p, f_before)
    g = pauli_graph()
    z = next(v for v in g.vertices() if g.type(v) == VertexType.Z)
    x = next(v for v in g.vertices() if g.type(v) == VertexType.X)
    # second arg to pauli_push is the Pauli spider, not the target
    pyzx.rewrite_rules.pauli_push(g, z, x)
    apply_rewrite(p, g, "Push Pauli")
    f_after = tmp / "pauli_after.png"
    grab_canvas(p, f_after)
    pngs_to_gif(f_before, f_after, STATIC / "drag_push_pauli.gif")

    shutil.rmtree(tmp)


def main() -> None:
    app = QApplication(sys.argv)
    generate()
    app.quit()


if __name__ == "__main__":
    main()
