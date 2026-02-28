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
from PySide6 import QtCore
from pytestqt.qtbot import QtBot

from zxlive.dialogs import import_diagram_from_file
from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
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

    # Start a derivation. Export to tikz is enabled.
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert app.tab_widget.count() == 2
    assert isinstance(app.active_panel, ProofPanel)
    assert app.export_tikz_proof.isEnabled()

    # Switch to the demo graph tab. Export to tikz is disabled.
    app.tab_widget.setCurrentIndex(0)
    assert not app.export_tikz_proof.isEnabled()

    # Switch back to the proof tab. Export to tikz is enabled.
    app.tab_widget.setCurrentIndex(1)
    assert app.export_tikz_proof.isEnabled()

    # Close the proof tab. Export to tikz is disabled.
    app.close_action.trigger()
    assert app.tab_widget.count() == 1
    assert not app.export_tikz_proof.isEnabled()


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


def test_proof_cleanup_before_close(app: MainWindow, qtbot: QtBot) -> None:
    # Regression test to check that the app doesn't crash when closing a proof tab with a derivation in progress,
    # due to accessing the graph after it has been deallocated.
    # See https://github.com/zxcalc/zxlive/issues/218 for context.
    assert app.active_panel is not None
    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    app.select_all_action.trigger()
    app.close_action.trigger()
