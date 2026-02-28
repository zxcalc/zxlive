"""Tests for visual graph items (VItem), such as dummy nodes and their labels.

These tests ensure that rendering artifacts—especially the visual positioning of
dummy node labels—are robust. For instance, tall LaTeX expressions (like integrals 
or fractions) shouldn't overlap with the node body.
"""

import pytest
from pyzx.graph.graph_s import GraphS
from pyzx.utils import VertexType
from pytestqt.qtbot import QtBot

from zxlive.graphscene import GraphScene
from zxlive.common import SCALE

def test_dummy_label_position(qtbot: QtBot) -> None:
    """Test that dummy labels sit cleanly above the node without overlapping.
    
    This verifies the regression fix where tall LaTeX formulas (e.g. `$\\int$`) 
    with a simple fixed upward offset would visually bleed into and overlap the 
    dummy circle below it. The label's `y` position should be dynamically 
    anchored based on its calculated bounding height.
    """
    g = GraphS()
    
    # 1. Plain text label
    v_text = g.add_vertex(VertexType.DUMMY, qubit=0, row=0)
    g.set_vdata(v_text, 'text', 'hello')
    
    # 2. LaTeX label
    v_latex = g.add_vertex(VertexType.DUMMY, qubit=1, row=0)
    g.set_vdata(v_latex, 'text', r'$\int$')
    
    scene = GraphScene()
    scene.set_graph(g)
    
    vitem_text = scene.vertex_map[v_text]
    vitem_latex = scene.vertex_map[v_latex]
    
    # Refresh to ensure dummy labels are created and positioned
    vitem_text.refresh()
    vitem_latex.refresh()
    
    gap = 2.0
    node_top = -0.06 * SCALE
    
    # Check text item position
    assert vitem_text.dummy_text_item is not None
    text_rect = vitem_text.dummy_text_item.boundingRect()
    expected_text_y = node_top - gap - text_rect.height()
    assert vitem_text.dummy_text_item.pos().y() == pytest.approx(expected_text_y)
    
    # Check svg item position
    assert vitem_latex.dummy_svg_item is not None
    assert vitem_latex._dummy_svg_renderer is not None
    svg_rect = vitem_latex._dummy_svg_renderer.viewBoxF()
    expected_svg_y = node_top - gap - svg_rect.height()
    assert vitem_latex.dummy_svg_item.pos().y() == pytest.approx(expected_svg_y)
