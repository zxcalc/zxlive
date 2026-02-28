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

"""Tests for persistent session state (save/restore tabs across sessions).

Covers the feature implemented in PR #440 / issue #439:
- _save_session_state() serialization of all panel types
- _restore_session_state() deserialization and tab recreation
- Startup-behavior setting ("restore" vs "blank")
- Auto-save timer initialization
- Graceful handling of corrupted session data
- closeEvent integration with session saving
"""

import json

import pytest
from PySide6 import QtCore
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from zxlive.common import GraphT, new_graph, set_settings_value, get_settings_value
from zxlive.construct import construct_circuit
from zxlive.custom_rule import CustomRule
from zxlive.dialogs import FileFormat
from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel
from zxlive.rule_panel import RulePanel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mw(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    """Create a MainWindow with suppressed save-dialog and cleared session state."""
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window = MainWindow()
    # Ensure a clean slate – no leftover session from a previous test
    window.settings.remove("session_state")
    qtbot.addWidget(window)
    return window


# ---------------------------------------------------------------------------
# Auto-save timer
# ---------------------------------------------------------------------------

def test_session_save_timer_exists(mw: MainWindow) -> None:
    """The periodic auto-save timer should be created and running."""
    assert hasattr(mw, "session_save_timer")
    assert mw.session_save_timer.isActive()
    # Default interval is 60 000 ms (1 minute)
    assert mw.session_save_timer.interval() == 60000


# ---------------------------------------------------------------------------
# _save_session_state – basic scenarios
# ---------------------------------------------------------------------------

def test_save_empty_clears_state(mw: MainWindow) -> None:
    """Saving with zero tabs should clear any previously saved state."""
    # Pre-populate a fake session value
    mw.settings.setValue("session_state", '{"tabs": []}')
    assert mw.tab_widget.count() == 0

    mw._save_session_state()

    assert mw.settings.value("session_state") is None


def test_save_single_graph_tab(mw: MainWindow) -> None:
    """A single GraphEditPanel tab should be serialized correctly."""
    graph = construct_circuit()
    mw.new_graph(graph, "Test Graph")
    assert mw.tab_widget.count() == 1

    mw._save_session_state()

    raw = mw.settings.value("session_state")
    assert raw is not None
    data = json.loads(raw)
    assert len(data["tabs"]) == 1
    tab = data["tabs"][0]
    assert tab["type"] == "graph"
    assert tab["name"] == "Test Graph"
    assert tab["file_path"] is None
    assert tab["file_type"] is None
    # The data field should be valid JSON that can round-trip
    assert json.loads(tab["data"]) is not None


def test_save_preserves_file_path_and_type(mw: MainWindow) -> None:
    """File path and file type on a panel should be persisted."""
    mw.new_graph(construct_circuit(), "Saved Graph")
    assert mw.active_panel is not None
    mw.active_panel.file_path = "/tmp/test.zxg"
    mw.active_panel.file_type = FileFormat.QGraph

    mw._save_session_state()

    data = json.loads(mw.settings.value("session_state"))
    tab = data["tabs"][0]
    assert tab["file_path"] == "/tmp/test.zxg"
    assert tab["file_type"] == FileFormat.QGraph.value


def test_save_multiple_tabs_and_active_index(mw: MainWindow) -> None:
    """Multiple tabs should all be saved, along with the active tab index."""
    mw.new_graph(construct_circuit(), "Graph 1")
    mw.new_graph(new_graph(), "Graph 2")
    mw.new_graph(new_graph(), "Graph 3")
    assert mw.tab_widget.count() == 3
    mw.tab_widget.setCurrentIndex(1)

    mw._save_session_state()

    data = json.loads(mw.settings.value("session_state"))
    assert len(data["tabs"]) == 3
    assert data["active_tab"] == 1
    names = [t["name"] for t in data["tabs"]]
    assert names == ["Graph 1", "Graph 2", "Graph 3"]


def test_save_proof_tab(mw: MainWindow, qtbot: QtBot) -> None:
    """A ProofPanel tab should be saved with type 'proof'."""
    mw.new_graph(construct_circuit(), "Proof Source")
    assert isinstance(mw.active_panel, GraphEditPanel)
    qtbot.mouseClick(mw.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert mw.tab_widget.count() == 2
    assert isinstance(mw.active_panel, ProofPanel)

    mw._save_session_state()

    data = json.loads(mw.settings.value("session_state"))
    proof_tabs = [t for t in data["tabs"] if t["type"] == "proof"]
    assert len(proof_tabs) == 1
    # Proof data should be valid JSON containing initial_graph and proof_steps
    proof_data = json.loads(proof_tabs[0]["data"])
    assert "initial_graph" in proof_data
    assert "proof_steps" in proof_data


def test_save_rule_tab(mw: MainWindow) -> None:
    """A RulePanel tab should be saved with type 'rule'."""
    lhs = new_graph()
    rhs = new_graph()
    rule = CustomRule(lhs, rhs, "test rule", "desc")
    mw.new_rule_editor(rule, "My Rule")
    assert mw.tab_widget.count() == 1
    assert isinstance(mw.active_panel, RulePanel)

    mw._save_session_state()

    data = json.loads(mw.settings.value("session_state"))
    rule_tabs = [t for t in data["tabs"] if t["type"] == "rule"]
    assert len(rule_tabs) == 1
    assert rule_tabs[0]["name"] == "My Rule"
    rule_data = json.loads(rule_tabs[0]["data"])
    assert "lhs_graph" in rule_data
    assert "rhs_graph" in rule_data
    assert rule_data["name"] == "test rule"


# ---------------------------------------------------------------------------
# _restore_session_state – basic scenarios
# ---------------------------------------------------------------------------

def test_restore_returns_false_when_blank_setting(mw: MainWindow) -> None:
    """When startup-behavior is 'blank', restore should return False."""
    set_settings_value("startup-behavior", "blank", str)
    mw.new_graph(construct_circuit(), "G")
    mw._save_session_state()

    # Remove the tabs so we start fresh
    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    result = mw._restore_session_state()
    assert result is False
    assert mw.tab_widget.count() == 0

    # Clean up so other tests are not affected
    set_settings_value("startup-behavior", "restore", str)


def test_restore_returns_false_when_no_saved_state(mw: MainWindow) -> None:
    """Restoring with no saved session data should return False."""
    set_settings_value("startup-behavior", "restore", str)
    mw.settings.remove("session_state")

    result = mw._restore_session_state()
    assert result is False


def test_restore_single_graph_tab(mw: MainWindow) -> None:
    """A saved graph tab should be correctly restored."""
    set_settings_value("startup-behavior", "restore", str)

    graph = construct_circuit()
    mw.new_graph(graph, "Restored Graph")
    mw._save_session_state()

    # Close all tabs
    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)
    assert mw.tab_widget.count() == 0

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == 1
    assert mw.tab_widget.tabText(0) == "Restored Graph"
    assert isinstance(mw.active_panel, GraphEditPanel)


def test_restore_multiple_tabs_preserves_active_index(mw: MainWindow) -> None:
    """Restoring should recreate all tabs and activate the correct one."""
    set_settings_value("startup-behavior", "restore", str)

    mw.new_graph(construct_circuit(), "Tab A")
    mw.new_graph(new_graph(), "Tab B")
    mw.new_graph(new_graph(), "Tab C")
    mw.tab_widget.setCurrentIndex(2)  # Make "Tab C" active
    mw._save_session_state()

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == 3
    assert mw.tab_widget.currentIndex() == 2
    names = [mw.tab_widget.tabText(i) for i in range(mw.tab_widget.count())]
    assert names == ["Tab A", "Tab B", "Tab C"]


def test_restore_preserves_file_path_and_type(mw: MainWindow) -> None:
    """File path and file type should survive a save/restore cycle."""
    set_settings_value("startup-behavior", "restore", str)

    mw.new_graph(construct_circuit(), "FP Graph")
    assert mw.active_panel is not None
    mw.active_panel.file_path = "/tmp/persist.zxg"
    mw.active_panel.file_type = FileFormat.QGraph
    mw._save_session_state()

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    mw._restore_session_state()
    assert mw.active_panel is not None
    assert mw.active_panel.file_path == "/tmp/persist.zxg"
    assert mw.active_panel.file_type == FileFormat.QGraph


def test_restore_proof_tab(mw: MainWindow, qtbot: QtBot) -> None:
    """A proof tab should round-trip through save/restore."""
    set_settings_value("startup-behavior", "restore", str)

    mw.new_graph(construct_circuit(), "Proof Base")
    assert isinstance(mw.active_panel, GraphEditPanel)
    qtbot.mouseClick(mw.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert isinstance(mw.active_panel, ProofPanel)
    mw._save_session_state()

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    result = mw._restore_session_state()
    assert result is True
    # The restoration should have created both the graph and proof tabs
    proof_panels = [
        mw.tab_widget.widget(i) for i in range(mw.tab_widget.count())
        if isinstance(mw.tab_widget.widget(i), ProofPanel)
    ]
    assert len(proof_panels) >= 1


def test_restore_rule_tab(mw: MainWindow) -> None:
    """A rule tab should round-trip through save/restore."""
    set_settings_value("startup-behavior", "restore", str)

    rule = CustomRule(new_graph(), new_graph(), "round-trip rule", "description")
    mw.new_rule_editor(rule, "Rule Tab")
    mw._save_session_state()

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == 1
    assert isinstance(mw.active_panel, RulePanel)
    assert mw.tab_widget.tabText(0) == "Rule Tab"


# ---------------------------------------------------------------------------
# Corrupted / malformed data handling
# ---------------------------------------------------------------------------

def test_restore_invalid_json_returns_false(mw: MainWindow) -> None:
    """Corrupted JSON should not crash; restore returns False."""
    set_settings_value("startup-behavior", "restore", str)
    mw.settings.setValue("session_state", "NOT VALID JSON {{{")

    result = mw._restore_session_state()
    assert result is False
    assert mw.tab_widget.count() == 0


def test_restore_empty_tabs_list_returns_false(mw: MainWindow) -> None:
    """An empty tabs list in the JSON should return False."""
    set_settings_value("startup-behavior", "restore", str)
    mw.settings.setValue("session_state", json.dumps({"tabs": [], "active_tab": 0}))

    result = mw._restore_session_state()
    assert result is False


def test_restore_invalid_tab_type_skipped(mw: MainWindow) -> None:
    """A tab with an unknown type should be skipped without crashing."""
    set_settings_value("startup-behavior", "restore", str)

    # Create a valid graph tab plus one with a bogus type
    graph = construct_circuit()
    graph_json = graph.to_json()
    session = {
        "tabs": [
            {"type": "unknown_panel", "name": "Bad Tab", "data": "{}",
             "file_path": None, "file_type": None},
            {"type": "graph", "name": "Good Tab", "data": graph_json,
             "file_path": None, "file_type": None},
        ],
        "active_tab": 0,
    }
    mw.settings.setValue("session_state", json.dumps(session))

    result = mw._restore_session_state()
    assert result is True
    # Only the valid graph tab should be restored
    assert mw.tab_widget.count() == 1
    assert mw.tab_widget.tabText(0) == "Good Tab"


def test_restore_corrupted_tab_data_skipped(mw: MainWindow) -> None:
    """A tab whose data cannot be deserialized should be skipped gracefully."""
    set_settings_value("startup-behavior", "restore", str)

    graph = construct_circuit()
    graph_json = graph.to_json()
    session = {
        "tabs": [
            {"type": "graph", "name": "Broken", "data": "INVALID",
             "file_path": None, "file_type": None},
            {"type": "graph", "name": "OK", "data": graph_json,
             "file_path": None, "file_type": None},
        ],
        "active_tab": 0,
    }
    mw.settings.setValue("session_state", json.dumps(session))

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == 1
    assert mw.tab_widget.tabText(0) == "OK"


def test_restore_missing_data_key_skipped(mw: MainWindow) -> None:
    """A tab entry missing the 'data' key should be skipped."""
    set_settings_value("startup-behavior", "restore", str)

    graph = construct_circuit()
    graph_json = graph.to_json()
    session = {
        "tabs": [
            {"type": "graph", "name": "No Data",
             "file_path": None, "file_type": None},
            {"type": "graph", "name": "With Data", "data": graph_json,
             "file_path": None, "file_type": None},
        ],
        "active_tab": 0,
    }
    mw.settings.setValue("session_state", json.dumps(session))

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == 1
    assert mw.tab_widget.tabText(0) == "With Data"


# ---------------------------------------------------------------------------
# closeEvent integration
# ---------------------------------------------------------------------------

def test_close_event_saves_session(mw: MainWindow, qtbot: QtBot) -> None:
    """Closing the window should persist the session state."""
    set_settings_value("startup-behavior", "restore", str)
    mw.new_graph(construct_circuit(), "Close Test")

    # Trigger close event
    mw.close()

    raw = mw.settings.value("session_state")
    assert raw is not None
    data = json.loads(raw)
    assert len(data["tabs"]) == 1
    assert data["tabs"][0]["name"] == "Close Test"


def test_close_event_with_blank_setting_prompts_save(
    mw: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With startup-behavior='blank', closeEvent should still save state
    and go through the close-tab flow (save dialog)."""
    set_settings_value("startup-behavior", "blank", str)
    mw.new_graph(construct_circuit(), "Blank Mode")

    # The monkeypatch from the fixture already suppresses save dialogs (answers No)
    mw.close()

    # Session state should still be saved (unconditionally) even in blank mode
    raw = mw.settings.value("session_state")
    assert raw is not None
    data = json.loads(raw)
    assert len(data["tabs"]) == 1

    # Reset
    set_settings_value("startup-behavior", "restore", str)


# ---------------------------------------------------------------------------
# Full round-trip (save → clear → restore)
# ---------------------------------------------------------------------------

def test_full_round_trip_graph(mw: MainWindow) -> None:
    """End-to-end: create graph, save, clear, restore, verify graph data."""
    set_settings_value("startup-behavior", "restore", str)

    graph = construct_circuit()
    original_num_vertices = graph.num_vertices()
    original_num_edges = graph.num_edges()
    mw.new_graph(graph, "Round Trip")
    mw._save_session_state()

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    mw._restore_session_state()
    assert mw.tab_widget.count() == 1
    assert isinstance(mw.active_panel, GraphEditPanel)

    restored_graph = mw.active_panel.graph
    assert restored_graph.num_vertices() == original_num_vertices
    assert restored_graph.num_edges() == original_num_edges


def test_full_round_trip_mixed_panels(mw: MainWindow, qtbot: QtBot) -> None:
    """Round-trip with graph + proof + rule tabs simultaneously."""
    set_settings_value("startup-behavior", "restore", str)

    # Add a graph tab
    mw.new_graph(construct_circuit(), "G1")
    # Add a proof tab by starting derivation
    assert isinstance(mw.active_panel, GraphEditPanel)
    qtbot.mouseClick(mw.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    # Add a rule tab
    rule = CustomRule(new_graph(), new_graph(), "r", "d")
    mw.new_rule_editor(rule, "R1")

    total_tabs = mw.tab_widget.count()
    assert total_tabs == 3  # graph, proof, rule

    mw._save_session_state()

    # Verify saved data has all three
    data = json.loads(mw.settings.value("session_state"))
    types = [t["type"] for t in data["tabs"]]
    assert "graph" in types
    assert "proof" in types
    assert "rule" in types

    while mw.tab_widget.count():
        mw.tab_widget.removeTab(0)

    result = mw._restore_session_state()
    assert result is True
    assert mw.tab_widget.count() == total_tabs


# ---------------------------------------------------------------------------
# Settings value
# ---------------------------------------------------------------------------

def test_startup_behavior_default_is_restore() -> None:
    """The default value for startup-behavior should be 'restore'."""
    from zxlive.settings import general_defaults
    assert general_defaults["startup-behavior"] == "restore"


def test_startup_behavior_setting_options() -> None:
    """The settings dialog should expose both blank and restore options."""
    from zxlive.settings_dialog import startup_behavior_options
    assert "blank" in startup_behavior_options
    assert "restore" in startup_behavior_options
