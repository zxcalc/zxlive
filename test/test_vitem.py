"""Tests for visual graph items (VItem), such as dummy nodes and their labels.

These tests ensure that rendering artifacts—especially the visual positioning of
dummy node labels—are robust. For instance, tall LaTeX expressions (like integrals
or fractions) shouldn't overlap with the node body.
"""

from fractions import Fraction
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsSceneMouseEvent
from pyzx.utils import VertexType
from pytestqt.qtbot import QtBot

from zxlive.edit_panel import GraphEditPanel
from zxlive.eitem import EItem, EItemAnimation
from zxlive.graphscene import GraphScene
from zxlive.common import SCALE, new_graph
from zxlive.rule_panel import RulePanel
from zxlive.settings import DisplaySettings, display_setting
from zxlive.vitem import VItem, VItemAnimation


def _drag(
    scene: GraphScene,
    start: QPointF,
    end: QPointF,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
) -> None:
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    press.setScenePos(start)
    press.setButton(button)
    press.setButtons(button)
    press.setModifiers(modifiers)
    press.setButtonDownScenePos(button, start)
    scene.mousePressEvent(press)

    move = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
    move.setScenePos(end)
    move.setLastScenePos(start)
    move.setButtons(button)
    move.setModifiers(modifiers)
    move.setButtonDownScenePos(button, start)
    scene.mouseMoveEvent(move)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(end)
    release.setLastScenePos(end)
    release.setButton(button)
    release.setButtons(Qt.MouseButton.NoButton)
    release.setModifiers(modifiers)
    release.setButtonDownScenePos(button, start)
    scene.mouseReleaseEvent(release)


@pytest.mark.parametrize("grabber_selected", [True, False])
def test_selected_vertices_share_snapped_drag_offset(qtbot: QtBot, grabber_selected: bool) -> None:
    g = new_graph()
    # These origins put per-item offsets on opposite sides of the 1.5-grid rounding boundary.
    vertices = [
        g.add_vertex(VertexType.Z, qubit=qubit, row=row)
        for row, qubit in [(35.42516536005408, 0), (28.13661789343115, 1)]
    ]
    panel = GraphEditPanel(g)
    qtbot.addWidget(panel)
    scene = panel.graph_scene

    items = [scene.vertex_map[v] for v in vertices]
    snap = display_setting.SNAP

    positions_before = [QPointF(item.pos()) for item in items]
    spacing_before = positions_before[1] - positions_before[0]

    if grabber_selected:
        scene.select_vertices(vertices)
        dragged_item = items[0]
        modifiers = Qt.KeyboardModifier.NoModifier
    else:
        scene.select_vertices(vertices[:1])
        dragged_item = items[1]
        modifiers = Qt.KeyboardModifier.ControlModifier

    start = dragged_item.pos()
    _drag(scene, start, start + QPointF(3 * snap / 2, 0), modifiers)

    expected_offset = QPointF(2 * snap, 0)
    assert [item.pos() - before for item, before in zip(items, positions_before)] == [expected_offset] * len(items)
    assert items[1].pos() - items[0].pos() == spacing_before

    panel.undo_stack.undo()
    assert [item.pos() for item in items] == positions_before


@pytest.mark.parametrize("button", [Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton])
def test_noop_mouse_gesture_does_not_leave_item_dragging(qtbot: QtBot, button: Qt.MouseButton) -> None:
    g = new_graph()
    vertex = g.add_vertex(VertexType.Z, qubit=0, row=0)
    scene = GraphScene()
    scene.set_graph(g)
    item = scene.vertex_map[vertex]
    position = QPointF(item.pos())
    moved = []
    scene.vertices_moved.connect(moved.append)

    _drag(scene, position, position, Qt.KeyboardModifier.NoModifier, button)

    assert item.pos() == position
    assert not item.is_dragging
    assert moved == []


def test_dummy_label_position(qtbot: QtBot) -> None:
    """Test that dummy labels sit cleanly above the node without overlapping.

    This verifies the regression fix where tall LaTeX formulas (e.g. `$\\int$`)
    with a simple fixed upward offset would visually bleed into and overlap the
    dummy circle below it. The label's `y` position should be dynamically
    anchored based on its calculated bounding height.
    """
    g = new_graph()

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


def test_phase_and_plain_dummy_fonts_update_independently(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase_font = QFont("Phase Font", 17)
    dummy_font = QFont("Dummy Font", 19)
    monkeypatch.setattr(display_setting, "phase_font", phase_font)
    monkeypatch.setattr(display_setting, "dummy_font", dummy_font)

    g = new_graph()
    v_phase = g.add_vertex(VertexType.Z, qubit=0, row=0, phase=Fraction(1, 4))
    v_dummy = g.add_vertex(VertexType.DUMMY, qubit=1, row=0)
    g.set_vdata(v_dummy, 'text', 'hello')

    scene = GraphScene()
    scene.set_graph(g)
    phase_vitem = scene.vertex_map[v_phase]
    dummy_vitem = scene.vertex_map[v_dummy]

    assert phase_vitem.phase_item.font() == phase_font
    assert dummy_vitem.dummy_text_item is not None
    assert dummy_vitem.dummy_text_item.font() == dummy_font

    updated_phase_font = QFont("Updated Phase Font", 23)
    updated_dummy_font = QFont("Updated Dummy Font", 29)
    monkeypatch.setattr(display_setting, "phase_font", updated_phase_font)
    monkeypatch.setattr(display_setting, "dummy_font", updated_dummy_font)

    phase_vitem.update_font()
    dummy_vitem.update_font()

    assert phase_vitem.phase_item.font() == updated_phase_font
    assert dummy_vitem.dummy_text_item.font() == updated_dummy_font


def test_graph_label_fonts_can_inherit_or_override_app_font(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[str, str | int | bool] = {
        "snap-granularity": "4",
        "font/family": "Application Font",
        "font/size": 13,
        "phase-font/family": "Phase Font",
        "phase-font/size": 17,
        "dummy-font/same-as-app": False,
        "dummy-font/family": "Dummy Font",
        "dummy-font/size": 19,
    }
    monkeypatch.setattr(
        "zxlive.settings.get_settings_value",
        lambda name, _type, default=None: values.get(name, default),
    )

    settings = DisplaySettings()

    assert settings.phase_font == settings.font
    assert settings.dummy_font.family() == "Dummy Font"
    assert settings.dummy_font.pointSize() == 19

    values["phase-font/same-as-app"] = False
    values["dummy-font/same-as-app"] = True
    settings.update()

    assert settings.phase_font.family() == "Phase Font"
    assert settings.phase_font.pointSize() == 17
    assert settings.dummy_font == settings.font


def test_rule_panel_updates_fonts_in_both_views() -> None:
    left_view = Mock()
    right_view = Mock()
    panel = Mock(graph_view_left=left_view, graph_view_right=right_view)

    RulePanel.update_font(panel)

    left_view.update_font.assert_called_once_with()
    right_view.update_font.assert_called_once_with()


def test_latex_dummy_size_tracks_dummy_font_on_update(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    rendered_sizes: list[float] = []

    def fake_latex_to_svg(text: str, color: str, size: float) -> bytes:
        rendered_sizes.append(size)
        return b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>'

    monkeypatch.setattr("zxlive.latex_render.latex_to_svg", fake_latex_to_svg)
    monkeypatch.setattr(display_setting, "dummy_font", QFont("Dummy Font", 20))

    g = new_graph()
    v = g.add_vertex(VertexType.DUMMY, qubit=0, row=0)
    g.set_vdata(v, 'text', r'$x$')
    scene = GraphScene()
    scene.set_graph(g)
    vitem = scene.vertex_map[v]

    assert rendered_sizes == [pytest.approx(20 * 1.4)]
    assert vitem.dummy_svg_item is not None

    monkeypatch.setattr(display_setting, "dummy_font", QFont("New Dummy Font", 30))
    vitem.update_font()

    assert rendered_sizes == [pytest.approx(20 * 1.4), pytest.approx(30 * 1.4)]


def test_boundary_phase_cleared_on_refresh(qtbot: QtBot) -> None:
    """Test that boundary vertices never display stale phase labels.

    Regression test for #462.
    """
    g = new_graph()
    v = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)

    scene = GraphScene()
    scene.set_graph(g)
    vitem = scene.vertex_map[v]

    assert vitem.phase_item.toPlainText() == ""

    vitem.phase_item.setPlainText("π/4")
    assert vitem.phase_item.toPlainText() == "π/4"

    vitem.phase_item.refresh()
    assert vitem.phase_item.toPlainText() == ""


def test_boundary_io_labels_preserved_on_refresh(qtbot: QtBot) -> None:
    """Test that I/O labels set via set_boundary_label survive a refresh."""
    g = new_graph()
    v_in = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    v_out = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=2)

    scene = GraphScene()
    scene.set_graph(g)

    # Labels set through the proper API must survive refresh().
    scene.vertex_map[v_in].phase_item.set_boundary_label("in-0")
    scene.vertex_map[v_out].phase_item.set_boundary_label("out-0")

    scene.vertex_map[v_in].phase_item.refresh()
    scene.vertex_map[v_out].phase_item.refresh()

    assert scene.vertex_map[v_in].phase_item.toPlainText() == "in-0"
    assert scene.vertex_map[v_out].phase_item.toPlainText() == "out-0"


def test_boundary_phase_cleared_after_type_change(qtbot: QtBot) -> None:
    """Test that changing a vertex from Z to BOUNDARY clears its phase label.

    Simulates scenario where incremental graph update changes vertex's type
    from Z to BOUNDARY. The PhaseItem text set for the Z spider must be
    cleared.
    """
    g = new_graph()
    v = g.add_vertex(VertexType.Z, qubit=0, row=0, phase=Fraction(1, 4))

    scene = GraphScene()
    scene.set_graph(g)
    vitem = scene.vertex_map[v]
    assert vitem.phase_item.toPlainText() != ""

    new_g = new_graph()
    new_v = new_g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)

    scene.update_graph(new_g)

    new_vitem = scene.vertex_map[new_v]
    assert new_vitem.phase_item.toPlainText() == ""


def test_boundary_label_dropped_on_type_transition(qtbot: QtBot) -> None:
    """Stored I/O labels must not resurrect after a BOUNDARY -> other ->
    BOUNDARY round trip."""
    g = new_graph()
    v = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)

    scene = GraphScene()
    scene.set_graph(g)
    vitem = scene.vertex_map[v]

    vitem.phase_item.set_boundary_label("in-0")
    assert vitem.phase_item.toPlainText() == "in-0"

    # Simulate the vertex type changing away from boundary.
    g.set_type(v, VertexType.Z)
    vitem.phase_item.refresh()

    # Now change back to boundary. The stale I/O label must not return.
    g.set_type(v, VertexType.BOUNDARY)
    vitem.phase_item.refresh()
    assert vitem.phase_item.toPlainText() == ""


def test_update_io_labels_overwrites_stale_labels(qtbot: QtBot) -> None:
    """update_io_labels should reassign correct in-N/out-N indices and clear
    stale labels."""
    g = new_graph()
    v_in0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    v_in1 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=0)
    v_z0 = g.add_vertex(VertexType.Z, qubit=0, row=1)
    v_z1 = g.add_vertex(VertexType.Z, qubit=1, row=1)
    v_out0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    v_out1 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=2)
    g.add_edge((v_in0, v_z0))
    g.add_edge((v_in1, v_z1))
    g.add_edge((v_z0, v_out0))
    g.add_edge((v_z1, v_out1))

    scene = GraphScene()
    scene.set_graph(g)

    # Seed stale labels that should be overwritten on the next call.
    scene.vertex_map[v_in0].phase_item.set_boundary_label("in-99")
    scene.vertex_map[v_out1].phase_item.set_boundary_label("out-99")

    RulePanel.update_io_labels(None, scene)  # type: ignore[arg-type]

    assert scene.vertex_map[v_in0].phase_item.toPlainText() == "in-0"
    assert scene.vertex_map[v_in1].phase_item.toPlainText() == "in-1"
    assert scene.vertex_map[v_out0].phase_item.toPlainText() == "out-0"
    assert scene.vertex_map[v_out1].phase_item.toPlainText() == "out-1"


def test_vitem_animation_handles_missing_vertex(qtbot: QtBot) -> None:
    """A VItemAnimation whose target id is absent from ``vertex_map`` must
    no-op rather than raise. Regression test for #482."""
    g = new_graph()
    v = g.add_vertex(VertexType.Z, qubit=0, row=0)
    scene = GraphScene()
    scene.set_graph(g)

    anim = VItemAnimation(v, VItem.Properties.Position, scene, refresh=True)
    anim.setStartValue(QPointF(0, 0))
    anim.setEndValue(QPointF(SCALE, SCALE))
    anim.setDuration(50)
    del scene.vertex_map[v]

    assert anim.it is None
    anim._on_state_changed(QAbstractAnimation.State.Running)
    anim._on_state_changed(QAbstractAnimation.State.Stopped)
    anim.updateCurrentValue(QPointF(SCALE / 2, SCALE / 2))
    with qtbot.waitSignal(anim.finished, timeout=500):
        anim.start()


def test_eitem_animation_handles_missing_edge(qtbot: QtBot) -> None:
    """An EItemAnimation whose target edge is absent from ``edge_map`` must
    no-op rather than raise. Regression test for #482."""
    g = new_graph()
    a = g.add_vertex(VertexType.Z, qubit=0, row=0)
    b = g.add_vertex(VertexType.Z, qubit=0, row=1)
    g.add_edge((a, b))
    scene = GraphScene()
    scene.set_graph(g)
    e = next(iter(scene.edge_map))

    anim = EItemAnimation(e, EItem.Properties.Opacity, scene)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setDuration(50)
    del scene.edge_map[e]

    assert anim.it is None
    anim._on_state_changed(QAbstractAnimation.State.Running)
    anim._on_state_changed(QAbstractAnimation.State.Stopped)
    anim.updateCurrentValue(0.5)
    with qtbot.waitSignal(anim.finished, timeout=500):
        anim.start()
