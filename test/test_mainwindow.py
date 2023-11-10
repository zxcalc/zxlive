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
from PySide6 import QtCore
from pytestqt.qtbot import QtBot

from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel


@pytest.fixture
def app(qtbot: QtBot) -> MainWindow:
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
    assert app.active_panel is not None
    assert isinstance(app.active_panel, GraphEditPanel)
    qtbot.mouseClick(app.active_panel.start_derivation, QtCore.Qt.MouseButton.LeftButton)
    assert app.tab_widget.count() == 2
    assert isinstance(app.active_panel, ProofPanel)
