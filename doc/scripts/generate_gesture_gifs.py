"""Generate the animated GIFs used by ``doc/proof-mode-gestures.md``.

Each proof-mode gesture is illustrated by a small "before -> after" GIF. The
*before* diagram is built by hand and the *after* diagram is produced by calling
the very same ``pyzx.rewrite_rules`` functions that ``zxlive/proof_panel.py``
invokes when the gesture is performed in the app, so the pictures cannot drift
out of sync with what ZXLive actually does. Both states are rendered through the
real :class:`~zxlive.graphscene.GraphScene`, so the spiders, wires and phase
labels look exactly as they do in the editor.

Rendering is fully headless and depends only on PySide6, pyzx and Pillow --- no
ffmpeg or other external tool is required. Run it from the repository root::

    QT_QPA_PLATFORM=offscreen python doc/scripts/generate_gesture_gifs.py

The GIFs are written into ``doc/_static/``. Re-run this whenever a rewrite or
the rendering changes, and commit the regenerated assets.
"""

from __future__ import annotations

import copy
import io
import os
from fractions import Fraction
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import pyzx
from pyzx.utils import EdgeType, VertexType

STATIC_DIR = Path(__file__).resolve().parents[1] / "_static"

# Rendering parameters.
IMG_WIDTH = 460
PADDING = 36                  # scene units of whitespace around the diagram
CROP_MARGIN = 16              # px of white border kept after autocrop
BEFORE_MS = 1100
AFTER_MS = 1500

Z = VertexType.Z
X = VertexType.X
B = VertexType.BOUNDARY
SIMPLE = EdgeType.SIMPLE
HADAMARD = EdgeType.HADAMARD


def g_new():
    # Imported lazily so a QApplication exists before zxlive is imported.
    from zxlive.common import new_graph
    return new_graph()


def render_pair(before, after):
    """Render ``before`` and ``after`` graphs into two aligned PIL images."""
    from zxlive.graphscene import GraphScene

    scenes = []
    union = QRectF()
    for g in (before, after):
        scene = GraphScene()
        scene.set_graph(g)
        rect = scene.itemsBoundingRect()
        union = rect if union.isNull() else union.united(rect)
        scenes.append(scene)
    union = union.adjusted(-PADDING, -PADDING, PADDING, PADDING)

    height = max(1, round(IMG_WIDTH * union.height() / union.width()))
    frames = []
    for scene in scenes:
        image = QImage(IMG_WIDTH, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, IMG_WIDTH, height), union)
        painter.end()

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        image.save(buffer, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB"))

    return _joint_autocrop(frames)


def _joint_autocrop(frames):
    """Crop all frames to the shared bounding box of their non-white content."""
    bbox = None
    for frame in frames:
        inverted = Image.eval(frame, lambda px: 255 - px)
        fb = inverted.getbbox()
        if fb is None:
            continue
        if bbox is None:
            bbox = fb
        else:
            bbox = (min(bbox[0], fb[0]), min(bbox[1], fb[1]),
                    max(bbox[2], fb[2]), max(bbox[3], fb[3]))
    if bbox is None:
        return frames
    w, h = frames[0].size
    box = (max(0, bbox[0] - CROP_MARGIN), max(0, bbox[1] - CROP_MARGIN),
           min(w, bbox[2] + CROP_MARGIN), min(h, bbox[3] + CROP_MARGIN))
    return [frame.crop(box) for frame in frames]


def save_gif(name, before, after):
    before_img, after_img = render_pair(before, after)
    out = STATIC_DIR / name
    before_img.save(
        out, save_all=True, append_images=[after_img],
        duration=[BEFORE_MS, AFTER_MS], loop=0, optimize=True,
    )
    rel = out.relative_to(STATIC_DIR.parents[1])
    print(f"wrote {rel}  ({before_img.size[0]}x{before_img.size[1]})")


# --- Gesture definitions: each returns (before_graph, after_graph) ----------
# "before" is built by hand; "after" applies the same rewrite as proof_panel.py.

def drag_fuse():
    g = g_new()
    bi = g.add_vertex(B, qubit=0, row=0)
    a = g.add_vertex(Z, qubit=0, row=1, phase=Fraction(1, 4))
    b = g.add_vertex(Z, qubit=0, row=2, phase=Fraction(1, 4))
    bo = g.add_vertex(B, qubit=0, row=3)
    g.add_edge((bi, a), SIMPLE)
    g.add_edge((a, b), SIMPLE)
    g.add_edge((b, bo), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.fuse(after, a, b)
    return g, after


def drag_copy_pi():
    g = g_new()
    z = g.add_vertex(Z, qubit=1, row=1)
    x = g.add_vertex(X, qubit=1, row=0, phase=1)   # Pauli (pi) spider, single neighbour
    b1 = g.add_vertex(B, qubit=0, row=2)
    b2 = g.add_vertex(B, qubit=2, row=2)
    g.add_edge((x, z), SIMPLE)
    g.add_edge((z, b1), SIMPLE)
    g.add_edge((z, b2), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.copy(after, x)
    return g, after


def drag_push_pauli():
    g = g_new()
    bi = g.add_vertex(B, qubit=1, row=0)
    x = g.add_vertex(X, qubit=1, row=1, phase=1)    # Pauli being pushed
    z = g.add_vertex(Z, qubit=1, row=2, phase=Fraction(1, 4))
    o1 = g.add_vertex(B, qubit=0, row=3)
    o2 = g.add_vertex(B, qubit=2, row=3)
    g.add_edge((bi, x), SIMPLE)
    g.add_edge((x, z), SIMPLE)
    g.add_edge((z, o1), SIMPLE)
    g.add_edge((z, o2), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.pauli_push(after, z, x)      # (target, pauli) as in proof_panel
    return g, after


def wand_add_identity():
    g = g_new()
    bi = g.add_vertex(B, qubit=0, row=0)
    bo = g.add_vertex(B, qubit=0, row=2)
    g.add_edge((bi, bo), SIMPLE)
    after = copy.deepcopy(g)
    e = after.edge(bi, bo)
    v = after.add_vertex(Z, qubit=0, row=1)
    after.add_edge((bi, v), SIMPLE)
    after.add_edge((v, bo), SIMPLE)
    after.remove_edge(e)
    return g, after


def wand_remove_identity():
    g = g_new()
    bi = g.add_vertex(B, qubit=0, row=0)
    v = g.add_vertex(Z, qubit=0, row=1)
    bo = g.add_vertex(B, qubit=0, row=2)
    g.add_edge((bi, v), SIMPLE)
    g.add_edge((v, bo), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.remove_id(after, v)
    return g, after


def wand_unfuse():
    # Drawing the wand through a spider splits its legs into two new spiders.
    g = g_new()
    v = g.add_vertex(Z, qubit=1, row=1, phase=Fraction(1, 2))
    for q, r in [(0, 0), (2, 0), (0, 2), (2, 2)]:
        g.add_edge((g.add_vertex(B, qubit=q, row=r), v), SIMPLE)
    # after: split into left spider (carrying the phase) and right spider.
    after = g_new()
    left = after.add_vertex(Z, qubit=1, row=0.7, phase=Fraction(1, 2))
    right = after.add_vertex(Z, qubit=1, row=1.3)
    after.add_edge((left, right), SIMPLE)
    for q, r in [(0, 0), (2, 0)]:
        after.add_edge((after.add_vertex(B, qubit=q, row=r), left), SIMPLE)
    for q, r in [(0, 2), (2, 2)]:
        after.add_edge((after.add_vertex(B, qubit=q, row=r), right), SIMPLE)
    return g, after


def wand_hopf():
    # Two parallel wires between complementary spiders cancel in pairs.
    g = g_new()
    bi = g.add_vertex(B, qubit=1, row=0)
    z = g.add_vertex(Z, qubit=1, row=1)
    x = g.add_vertex(X, qubit=1, row=2)
    bo = g.add_vertex(B, qubit=1, row=3)
    g.add_edge((bi, z), SIMPLE)
    g.add_edge((z, x), SIMPLE)
    g.add_edge((z, x), SIMPLE)   # parallel pair
    g.add_edge((x, bo), SIMPLE)
    after = copy.deepcopy(g)
    after.remove_edges(list(after.edges(z, x)))
    return g, after


def dblclick_color_change():
    g = g_new()
    bi = g.add_vertex(B, qubit=0, row=0)
    v = g.add_vertex(Z, qubit=0, row=1, phase=Fraction(1, 4))
    bo = g.add_vertex(B, qubit=0, row=2)
    g.add_edge((bi, v), SIMPLE)
    g.add_edge((v, bo), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.color_change(after, v)
    return g, after


def dblclick_hadamard():
    g = g_new()
    bi = g.add_vertex(B, qubit=0, row=0)
    a = g.add_vertex(Z, qubit=0, row=1)
    b = g.add_vertex(Z, qubit=0, row=2)
    bo = g.add_vertex(B, qubit=0, row=3)
    g.add_edge((bi, a), SIMPLE)
    g.add_edge((a, b), HADAMARD)
    g.add_edge((b, bo), SIMPLE)
    after = copy.deepcopy(g)
    pyzx.rewrite_rules.had_edge_to_hbox(after, a, b)
    return g, after


GESTURES: dict[str, Callable] = {
    "drag_fuse.gif": drag_fuse,
    "drag_copy_pi.gif": drag_copy_pi,
    "drag_push_pauli.gif": drag_push_pauli,
    "wand_add_identity.gif": wand_add_identity,
    "wand_remove_identity.gif": wand_remove_identity,
    "wand_unfuse.gif": wand_unfuse,
    "wand_hopf.gif": wand_hopf,
    "dblclick_color_change.gif": dblclick_color_change,
    "dblclick_hadamard.gif": dblclick_hadamard,
}


def main():
    # The offscreen platform lets the script render without a display server.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication([])
    for name, build in GESTURES.items():
        before, after = build()
        save_gif(name, before, after)


if __name__ == "__main__":
    main()
