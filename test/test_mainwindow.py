#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pytest
import os
from pathlib import Path
from PySide6 import QtCore
from pytestqt.qtbot import QtBot

from pyzx.utils import EdgeType, VertexType

from zxlive.dialogs import import_diagram_from_file
from zxlive.common import GraphT, W_INPUT_OFFSET, new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
from zxlive.pauliwebs_panel import PauliWebsPanel
from zxlive.proof_panel import ProofPanel
from zxlive.settings_dialog import SettingsDialog


@pytest.fixture
def app(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    # Suppress the "save changes?" dialog that would otherwise block tests
    # when closing unsaved tabs (e.g. the demo graph which has no file path).
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    mw = MainWindow()
    mw.open_demo_graph()
    qtbot.addWidget(mw)
    return mw


def test_close_action(app: MainWindow) -> None:
    # The app (currently) starts with one tab. Check that closing it doesn't close the app.
    app.close_action.trigger()
    assert app.tab_widget.count() == 0
    assert not app.isHidden()

    # Check that the close action on the last tab closes the app.
    app.close_action.trigger()
    assert app.isHidden()


def test_undo_redo_actions(app: MainWindow) -> None:
    # Check that undo and redo are initially disabled.
    assert not app.undo_action.isEnabled()
    assert not app.redo_action.isEnabled()

    # Cut and paste, then check that undo is enabled and redo is disabled.
    app.select_all_action.trigger()
    app.cut_action.trigger()
    app.paste_action.trigger()
    assert app.undo_action.isEnabled()
    assert not app.redo_action.isEnabled()

    # Undo once, then check that both undo and redo are enabled.
    app.undo_action.trigger()
    assert app.undo_action.isEnabled()
    assert app.redo_action.isEnabled()

    # Undo once more, then check that undo is disabled and redo is enabled.
    app.undo_action.trigger()
    assert not app.undo_action.isEnabled()
    assert app.redo_action.isEnabled()


def test_start_derivation(app: MainWindow, qtbot: QtBot) -> None:
    # Demo graph is not a proof, so export to tikz should be disabled.
    assert app.active_panel is not None
    assert isinstance(app.active_panel, GraphEditPanel)
    assert not app.export_tikz_proof.isEnabled()
    assert not app.export_tikz_series.isEnabled()

    # Start a derivation. Export to tikz is enabled.
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert app.tab_widget.count() == 2
    assert isinstance(app.active_panel, ProofPanel)
    assert app.export_tikz_proof.isEnabled()
    assert app.export_tikz_series.isEnabled()

    # Switch to the demo graph tab. Export to tikz is disabled.
    app.tab_widget.setCurrentIndex(0)
    assert not app.export_tikz_proof.isEnabled()
    assert not app.export_tikz_series.isEnabled()

    # Switch back to the proof tab. Export to tikz is enabled.
    app.tab_widget.setCurrentIndex(1)
    assert app.export_tikz_proof.isEnabled()
    assert app.export_tikz_series.isEnabled()

    # Close the proof tab. Export to tikz is disabled.
    app.close_action.trigger()
    assert app.tab_widget.count() == 1
    assert not app.export_tikz_proof.isEnabled()
    assert not app.export_tikz_series.isEnabled()


def test_export_tikz_series(app: MainWindow, qtbot: QtBot, tmp_path: Path,
                            monkeypatch: pytest.MonkeyPatch) -> None:
    """Exporting proof steps writes one .tikz file per step into the chosen directory."""
    from PySide6.QtWidgets import QFileDialog

    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert isinstance(app.active_panel, ProofPanel)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(tmp_path))
    assert app.handle_export_tikz_series_action()

    files = sorted(p.name for p in tmp_path.iterdir())
    num_steps = len(list(app.active_panel.proof_model.graphs()))
    assert len(files) == num_steps
    # Filenames have a zero-padded numeric prefix (minimum 3 digits) and a safe step name.
    padding_width = max(3, len(str(max(num_steps - 1, 0))))
    assert files[0] == f"{0:0{padding_width}d}_START.tikz"
    for i, filename in enumerate(files):
        prefix, _, rest = filename.partition("_")
        assert prefix == f"{i:0{padding_width}d}"
        assert rest.endswith(".tikz")
        stem = rest[:-len(".tikz")]
        assert all(c.isalnum() or c in "._-" for c in stem)


def test_settings_dialog(app: MainWindow) -> None:
    # Warning: Do not actually change the settings in this test as this will impact the app's real settings.
    dialog = SettingsDialog(app)
    dialog.show()
    dialog.close()


def test_file_formats_preserved(app: MainWindow) -> None:
    # Disable the pop-up error message dialog for this test.
    import zxlive.dialogs
    zxlive.dialogs.show_error_msg = lambda *args, **kwargs: None

    def check_file_format(filename: str) -> None:
        assert import_diagram_from_file(os.path.join(os.path.dirname(__file__), filename)), \
            (f"File format has changed. If this is intentional, please overwrite {filename} in the commit and note in "
             f"the commit description that this is a breaking change.")

    check_file_format("demo.zxg")
    check_file_format("demo.zxp")
    check_file_format("demo.zxr")


def test_pauli_webs_no_save(app: MainWindow) -> None:
    app.new_pauli_webs(new_graph())
    assert isinstance(app.active_panel, PauliWebsPanel)
    assert not app.save_file.isEnabled()
    assert not app.save_as.isEnabled()

    app.close_action.trigger()
    assert not isinstance(app.active_panel, PauliWebsPanel)


def test_proof_as_lemma(app: MainWindow, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving a proof as a lemma writes a .zxr file to the custom rules folder."""
    import zxlive.mainwindow

    rules_dir = str(tmp_path)
    monkeypatch.setattr(zxlive.mainwindow, "get_custom_rules_path", lambda: rules_dir)
    monkeypatch.setattr(zxlive.mainwindow, "get_lemma_name_and_description",
                        lambda _parent: ("test lemma", "a description"))

    # Start a derivation from the demo graph.
    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert isinstance(app.active_panel, ProofPanel)

    app.proof_as_lemma()
    expected = os.path.join(rules_dir, "test lemma.zxr")
    assert os.path.exists(expected)

    # Saving again with the monkeypatched QMessageBox (answers No) should not overwrite.
    with open(expected, "w") as f:
        f.write("sentinel")
    app.proof_as_lemma()
    with open(expected, encoding="utf-8") as f:
        assert f.read() == "sentinel"


def test_auto_arrange(app: MainWindow) -> None:
    # The auto arrange action should be enabled when there is an active tab.
    assert app.auto_arrange_action.isEnabled()

    # Closing all tabs should disable the action (and triggering it would otherwise crash).
    app.close_action.trigger()
    assert app.tab_widget.count() == 0
    assert not app.auto_arrange_action.isEnabled()

    # Re-open a graph with the internal spider placed far from where spring_layout will put it,
    # so that triggering auto_arrange is guaranteed to push a MoveNode regardless of randomization.
    app.new_graph(new_graph_with_internal_vertex())
    assert app.active_panel is not None
    g_before = app.active_panel.graph_view.graph_scene.g
    boundary_positions = {v: (g_before.row(v), g_before.qubit(v)) for v in g_before.vertices()
                          if g_before.type(v) == VertexType.BOUNDARY}
    spider_v = next(v for v in g_before.vertices() if g_before.type(v) != VertexType.BOUNDARY)
    spider_orig = (g_before.row(spider_v), g_before.qubit(spider_v))
    assert not app.undo_action.isEnabled()

    app.auto_arrange_action.trigger()
    assert app.undo_action.isEnabled()

    # MoveNode applies a graph diff and swaps graph_scene.g to a new instance, so re-fetch.
    g_after = app.active_panel.graph_view.graph_scene.g
    for v, (r, q) in boundary_positions.items():
        assert g_after.row(v) == r
        assert g_after.qubit(v) == q
    assert (g_after.row(spider_v), g_after.qubit(spider_v)) != spider_orig

    # Undo should restore the spider's original position.
    app.undo_action.trigger()
    g_undone = app.active_panel.graph_view.graph_scene.g
    assert (g_undone.row(spider_v), g_undone.qubit(spider_v)) == spider_orig


def new_graph_with_internal_vertex() -> GraphT:
    # Two boundary vertices connected via an internal Z spider, with the spider placed far from
    # where spring_layout will put it so that auto_arrange is guaranteed to produce a move.
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    spider = g.add_vertex(VertexType.Z, qubit=100, row=100)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    g.add_edge((inp, spider))
    g.add_edge((spider, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))
    return g


def test_auto_arrange_disconnected_vertex(app: MainWindow) -> None:
    # An isolated spider (with no edges) shouldn't crash auto_arrange; its position is
    # unconstrained by any edge, so we just check that the action runs successfully.
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    spider = g.add_vertex(VertexType.Z, qubit=1, row=1)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    g.add_edge((inp, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))
    isolated = g.add_vertex(VertexType.Z, qubit=5, row=5)

    app.new_graph(g)
    assert app.active_panel is not None
    app.auto_arrange_action.trigger()
    # Boundaries are still anchored at their original positions.
    g_after = app.active_panel.graph_view.graph_scene.g
    assert (g_after.row(inp), g_after.qubit(inp)) == (0, 0)
    assert (g_after.row(out), g_after.qubit(out)) == (2, 0)
    # The connected spider and isolated spider should both still exist.
    assert spider in list(g_after.vertices())
    assert isolated in list(g_after.vertices())


def test_auto_arrange_overlapping_boundaries(app: MainWindow) -> None:
    # Two boundary vertices placed at exactly the same position. Since they are fixed,
    # spring_layout cannot separate them; we just check that auto_arrange doesn't crash
    # and that the boundaries stay where they were.
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    spider = g.add_vertex(VertexType.Z, qubit=10, row=10)
    g.add_edge((inp, spider))
    g.add_edge((spider, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))

    app.new_graph(g)
    assert app.active_panel is not None
    app.auto_arrange_action.trigger()
    g_after = app.active_panel.graph_view.graph_scene.g
    assert (g_after.row(inp), g_after.qubit(inp)) == (0, 0)
    assert (g_after.row(out), g_after.qubit(out)) == (0, 0)


def test_auto_arrange_w_pair_preserved(app: MainWindow) -> None:
    # A W_INPUT must remain at its original offset relative to its W_OUTPUT partner after
    # auto_arrange (i.e., it follows the partner instead of being laid out independently).
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    w_out = g.add_vertex(VertexType.W_OUTPUT, qubit=100, row=100)
    w_in = g.add_vertex(VertexType.W_INPUT, qubit=100 - W_INPUT_OFFSET, row=100)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    g.add_edge((w_in, w_out), edgetype=EdgeType.W_IO)
    g.add_edge((inp, w_in))
    g.add_edge((w_out, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))
    orig_offset = (g.row(w_in) - g.row(w_out), g.qubit(w_in) - g.qubit(w_out))

    app.new_graph(g)
    assert app.active_panel is not None
    app.auto_arrange_action.trigger()
    g_after = app.active_panel.graph_view.graph_scene.g
    new_offset = (g_after.row(w_in) - g_after.row(w_out),
                  g_after.qubit(w_in) - g_after.qubit(w_out))
    assert abs(new_offset[0] - orig_offset[0]) < 1e-6
    assert abs(new_offset[1] - orig_offset[1]) < 1e-6


def test_auto_arrange_selection_only(app: MainWindow) -> None:
    # When a subset of vertices is selected, auto_arrange should reposition only the selected
    # vertices; non-selected internal vertices should remain at their original positions.
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    s1 = g.add_vertex(VertexType.Z, qubit=0, row=1)
    s2 = g.add_vertex(VertexType.Z, qubit=50, row=50)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=3)
    g.add_edge((inp, s1))
    g.add_edge((s1, s2))
    g.add_edge((s2, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))

    app.new_graph(g)
    assert app.active_panel is not None
    s1_orig = (g.row(s1), g.qubit(s1))
    app.active_panel.graph_scene.select_vertices([s2])
    app.auto_arrange_action.trigger()

    g_after = app.active_panel.graph_view.graph_scene.g
    # The unselected internal spider should not have moved.
    assert (g_after.row(s1), g_after.qubit(s1)) == s1_orig
    # The selected spider should have moved (it was placed far from any sensible spring position).
    assert (g_after.row(s2), g_after.qubit(s2)) != (50, 50)


def _new_w_pair_graph() -> tuple[GraphT, int, int, int, int]:
    # Builds: boundary_in -> W_INPUT -- W_OUTPUT -> boundary_out, with the W pair placed far
    # from where spring_layout will put it (so auto_arrange is guaranteed to move them).
    g = new_graph()
    inp = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    w_out = g.add_vertex(VertexType.W_OUTPUT, qubit=100, row=100)
    w_in = g.add_vertex(VertexType.W_INPUT, qubit=100 - W_INPUT_OFFSET, row=100)
    out = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    g.add_edge((w_in, w_out), edgetype=EdgeType.W_IO)
    g.add_edge((inp, w_in))
    g.add_edge((w_out, out))
    g.set_inputs((inp,))
    g.set_outputs((out,))
    return g, inp, out, w_out, w_in


def test_auto_arrange_select_w_output_only(app: MainWindow) -> None:
    # Selecting only the W_OUTPUT must still drag the W_INPUT along (the partner can't be
    # treated as a fixed anchor just because it's a neighbour of the selection).
    g, _inp, _out, w_out, w_in = _new_w_pair_graph()
    orig_offset = (g.row(w_in) - g.row(w_out), g.qubit(w_in) - g.qubit(w_out))
    w_out_orig = (g.row(w_out), g.qubit(w_out))

    app.new_graph(g)
    assert app.active_panel is not None
    app.active_panel.graph_scene.select_vertices([w_out])
    app.auto_arrange_action.trigger()

    g_after = app.active_panel.graph_view.graph_scene.g
    assert (g_after.row(w_out), g_after.qubit(w_out)) != w_out_orig
    new_offset = (g_after.row(w_in) - g_after.row(w_out),
                  g_after.qubit(w_in) - g_after.qubit(w_out))
    assert abs(new_offset[0] - orig_offset[0]) < 1e-6
    assert abs(new_offset[1] - orig_offset[1]) < 1e-6


def test_auto_arrange_select_w_input_only(app: MainWindow) -> None:
    # Selecting only the W_INPUT must promote the W_OUTPUT to also be laid out, so the pair
    # actually moves rather than being stuck (W_INPUT removed from layout, partner anchored).
    g, _inp, _out, w_out, w_in = _new_w_pair_graph()
    orig_offset = (g.row(w_in) - g.row(w_out), g.qubit(w_in) - g.qubit(w_out))
    w_out_orig = (g.row(w_out), g.qubit(w_out))

    app.new_graph(g)
    assert app.active_panel is not None
    app.active_panel.graph_scene.select_vertices([w_in])
    app.auto_arrange_action.trigger()

    g_after = app.active_panel.graph_view.graph_scene.g
    assert (g_after.row(w_out), g_after.qubit(w_out)) != w_out_orig
    new_offset = (g_after.row(w_in) - g_after.row(w_out),
                  g_after.qubit(w_in) - g_after.qubit(w_out))
    assert abs(new_offset[0] - orig_offset[0]) < 1e-6
    assert abs(new_offset[1] - orig_offset[1]) < 1e-6


def test_auto_arrange_in_proof_mode(app: MainWindow, qtbot: QtBot) -> None:
    # Auto-arrange in a ProofPanel must keep the ProofModel's graph for the current step in
    # sync with the view, and undo/redo must restore positions on both.
    app.close_action.trigger()
    app.new_graph(new_graph_with_internal_vertex())
    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert isinstance(app.active_panel, ProofPanel)

    g_before = app.active_panel.graph_view.graph_scene.g
    spider_v = next(v for v in g_before.vertices() if g_before.type(v) != VertexType.BOUNDARY)
    spider_orig = (g_before.row(spider_v), g_before.qubit(spider_v))
    step_index = app.active_panel.step_view.currentIndex().row()

    app.auto_arrange_action.trigger()
    g_after = app.active_panel.graph_view.graph_scene.g
    spider_after = (g_after.row(spider_v), g_after.qubit(spider_v))
    assert spider_after != spider_orig
    # The proof step's stored graph must match the view's graph.
    proof_graph = app.active_panel.proof_model.get_graph(step_index)
    assert (proof_graph.row(spider_v), proof_graph.qubit(spider_v)) == spider_after

    app.undo_action.trigger()
    g_undone = app.active_panel.graph_view.graph_scene.g
    assert (g_undone.row(spider_v), g_undone.qubit(spider_v)) == spider_orig
    proof_graph = app.active_panel.proof_model.get_graph(step_index)
    assert (proof_graph.row(spider_v), proof_graph.qubit(spider_v)) == spider_orig

    app.redo_action.trigger()
    g_redone = app.active_panel.graph_view.graph_scene.g
    assert (g_redone.row(spider_v), g_redone.qubit(spider_v)) == spider_after
    proof_graph = app.active_panel.proof_model.get_graph(step_index)
    assert (proof_graph.row(spider_v), proof_graph.qubit(spider_v)) == spider_after


def test_proof_cleanup_before_close(app: MainWindow, qtbot: QtBot) -> None:
    # Regression test to check that the app doesn't crash when closing a proof tab with a derivation in progress,
    # due to accessing the graph after it has been deallocated.
    # See https://github.com/zxcalc/zxlive/issues/218 for context.
    assert app.active_panel is not None
    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    app.select_all_action.trigger()
    app.close_action.trigger()
