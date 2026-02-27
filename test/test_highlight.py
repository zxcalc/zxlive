from __future__ import annotations

import copy
import sys
import types

import pytest
from PySide6 import QtCore
from pytestqt.qtbot import QtBot
from pyzx.utils import EdgeType, VertexType


# Ensure compatibility with pyzx versions used by ZXLive. We only patch things
# that are missing, and leave real implementations untouched when they exist.
import pyzx

try:  # pragma: no cover - defensive shims for newer pyzx
    import pyzx.tikz as _pyzx_tikz  # type: ignore[import]
    if not hasattr(_pyzx_tikz, "synonyms_dummy"):
        _pyzx_tikz.synonyms_dummy = ()  # type: ignore[attr-defined]

    import pyzx.settings as _pyzx_settings  # type: ignore[import]
    tc = getattr(_pyzx_settings, "tikz_classes", None)
    if not isinstance(tc, dict) or "dummy" not in tc:
        tc = dict(tc or {})
        tc.setdefault("dummy", "")
        _pyzx_settings.tikz_classes = tc  # type: ignore[attr-defined]
except Exception:
    pass


# Newer versions of pyzx no longer expose the historical `pyzx.rewrite` module,
# but ZXLive still imports `RewriteSimpGraph` from there. Try to import the real
# module first; if that fails, provide a minimal compatibility shim.
try:  # pragma: no cover - prefer real module if available
    import pyzx.rewrite as _pyzx_rewrite  # type: ignore[import]
except Exception:  # pragma: no cover - fallback shim
    if "pyzx.rewrite" not in sys.modules:
        rewrite_module = types.ModuleType("pyzx.rewrite")

        class RewriteSimpGraph:  # type: ignore[override]
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def __class_getitem__(cls, item: object) -> type:  # type: ignore[override]
                return cls

        rewrite_module.RewriteSimpGraph = RewriteSimpGraph  # type: ignore[attr-defined]
        rewrite_module.Rewrite = object  # type: ignore[attr-defined]
        sys.modules["pyzx.rewrite"] = rewrite_module


from zxlive.commands import AddRewriteStep
from zxlive.common import GraphT, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel


def make_two_spider_graph() -> tuple[GraphT, GraphT]:
    """Create initial graph (2 Z spiders, phase 0 and 0.5, connected) and fused graph."""
    g = new_graph()

    v0 = g.add_vertex(VertexType.Z, 0, 0.0)
    v1 = g.add_vertex(VertexType.Z, 0, 1.0)

    # We rely on these being 0 and 1 for clarity in assertions below.
    assert v0 == 0
    assert v1 == 1

    g.set_phase(v1, 0.5)
    g.add_edge((v0, v1), EdgeType.SIMPLE)

    g_fused = copy.deepcopy(g)
    pyzx.rewrite_rules.fuse(g_fused, v0, v1)

    return g, g_fused


@pytest.fixture
def app(qtbot: QtBot) -> MainWindow:
    mw = MainWindow()
    qtbot.addWidget(mw)
    return mw


def test_rewrite_highlight_set_and_cleared_on_step_change(app: MainWindow, qtbot: QtBot) -> None:
    initial_graph, fused_graph = make_two_spider_graph()

    # Open a new tab with our simple two-spider graph.
    app.new_graph(initial_graph, name="Highlight Test")
    assert app.active_panel is not None
    assert isinstance(app.active_panel, GraphEditPanel)
    edit_panel: GraphEditPanel = app.active_panel

    # Start a derivation from this graph to enter proof mode.
    qtbot.mouseClick(edit_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert app.active_panel is not None
    assert isinstance(app.active_panel, ProofPanel)
    proof_panel: ProofPanel = app.active_panel

    # Add a Fuse spiders rewrite as a new proof step using the same mechanism as the UI.
    cmd = AddRewriteStep(proof_panel.graph_view, fused_graph, proof_panel.step_view, "Fuse spiders")
    proof_panel.undo_stack.push(cmd)

    scene = proof_panel.graph_scene

    # "Next change" semantics: on START (index 0) we show the graph at step 0
    # and highlight what will change in the transition 0 -> 1 (the fuse).
    proof_panel.step_view.move_to_step(0)
    # Both spiders that will be fused, and the edge between them, should be highlighted.
    assert scene.is_vertex_highlighted(0)
    assert scene.is_vertex_highlighted(1)
    edges_01 = list(scene.g.edges(0, 1))
    assert len(edges_01) >= 1
    e = edges_01[0]
    s, t = scene.g.edge_st(e)
    edge_01 = (s, t, scene.g.edge_type(e))
    assert scene.is_edge_highlighted(edge_01)

    # On the last step (index 1) there is no "next" transition, so no highlight.
    proof_panel.step_view.move_to_step(1)
    assert not any(scene.is_vertex_highlighted(v) for v in scene.g.vertices())

    # Back to START: again highlight the next change (0 -> 1).
    proof_panel.step_view.move_to_step(0)
    assert scene.is_vertex_highlighted(0)
    assert scene.is_vertex_highlighted(1)

    # Now simulate the user using Undo to remove the rewrite step entirely.
    # When the proof returns to the START state via the undo stack, there
    # should again be no rewrite highlighting at all.
    proof_panel.undo_stack.undo()
    assert proof_panel.step_view.currentIndex().row() == 0
    assert not any(scene.is_vertex_highlighted(v) for v in scene.g.vertices())

