#     zxlive - An interactive tool for the ZX calculus
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

from __future__ import annotations
from typing import Callable

from enum import IntEnum

from PySide6.QtGui import QAction, QShortcut

from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .construct import *
from .commands import SetGraph
from .dialogs import import_diagram_dialog, export_diagram_dialog, show_error_msg


class Tab(IntEnum):
    EditTab = 0
    ProofTab = 1


class MainWindow(QMainWindow):
    """A simple window containing a single `GraphView`
    This is just an example, and should be replaced with
    something more sophisticated.
    """

    edit_panel: GraphEditPanel
    proof_panel: ProofPanel

    current_tab: Tab = Tab.EditTab

    def __init__(self) -> None:
        super().__init__()
        conf = QSettings("zxlive", "zxlive")

        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        w.layout().setContentsMargins(0, 0, 0, 0)
        w.layout().setSpacing(0)
        self.resize(1200, 800)

        # restore the window from the last time it was opened
        geom = conf.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        tab_widget = QTabWidget()
        w.layout().addWidget(tab_widget)
        tab_widget.currentChanged.connect(self._tab_changed)

        graph = construct_circuit()

        self.edit_panel = GraphEditPanel(graph)
        tab_widget.addTab(self.edit_panel, "Edit")

        self.proof_panel = ProofPanel(graph)
        tab_widget.addTab(self.proof_panel, "Rewrite")

        menu = self.menuBar()

        new_graph = self._new_action("&New...",self.new_graph,QKeySequence.StandardKey.New,
            "Reinitialize with an empty graph")
        open_file = self._new_action("&Open...", self.open_file,QKeySequence.StandardKey.Open,
            "Open a file-picker dialog to choose a new diagram")
        close_action = self._new_action("Close...", self.close_action,QKeySequence.StandardKey.Close,
            "Closes the window")
        close_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.Close), QKeySequence("Ctrl+W")])
        # TODO: We should remember if we have saved the diagram before, 
        # and give an open to overwrite this file with a Save action
        save_as = self._new_action("&Save as...", self.save_as,QKeySequence.StandardKey.SaveAs,
            "Opens a file-picker dialog to save the diagram in a chosen file format")
        
        file_menu = menu.addMenu("&File")
        file_menu.addAction(new_graph)
        file_menu.addAction(open_file)
        file_menu.addSeparator()
        file_menu.addAction(close_action)
        file_menu.addAction(save_as)

        undo = self._new_action("Undo", self.undo, QKeySequence.StandardKey.Undo,
            "Undoes the last action")
        redo = self._new_action("Redo", self.redo, QKeySequence.StandardKey.Redo,
            "Redoes the last action")
        cut_action = self._new_action("Cut", self.cut_graph,QKeySequence.StandardKey.Cut,
            "Cut the selected part of the diagram")
        copy_action = self._new_action("&Copy", self.copy_graph,QKeySequence.StandardKey.Copy,
            "Copy the selected part of the diagram")
        paste_action = self._new_action("Paste", self.paste_graph,QKeySequence.StandardKey.Paste,
            "Paste the copied part of the diagram")
        delete_action = self._new_action("Delete", self.delete_graph,QKeySequence.StandardKey.Delete,
            "Delete the selected part of the diagram")
        delete_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.Delete),QKeySequence("Backspace")])
        

        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(undo)
        edit_menu.addAction(redo)
        edit_menu.addSeparator()
        edit_menu.addAction(cut_action)
        edit_menu.addAction(copy_action)
        edit_menu.addAction(paste_action)
        edit_menu.addAction(delete_action)


    def _new_action(self,name:str,trigger:Callable,shortcut:QKeySequence | QKeySequence.StandardKey,tooltip:str):
        action = QAction(name, self)
        action.setStatusTip(tooltip)
        action.triggered.connect(trigger)
        action.setShortcut(shortcut)
        return action

    def _tab_changed(self, new_tab: Tab):
        old_panel = self.edit_panel if self.current_tab == Tab.EditTab else self.proof_panel
        new_panel = self.edit_panel if new_tab == Tab.EditTab else self.proof_panel
        # This method is also invoked on application launch, so check
        # if the tab has actually changed
        if self.current_tab != new_tab:
            new_panel.graph_view.set_graph(old_panel.graph)
            new_panel.graph_scene.select_vertices(list(old_panel.graph_scene.selected_vertices))
            # TODO: For now we always invalidate the undo stack when switching
            #  between tabs. In the future this should only happen if we've
            #  actually made changes to the graph before switching.
            new_panel.undo_stack.clear()
            self.current_tab = new_tab
            self.active_panel = new_panel
        else:
            self.active_panel = old_panel

    def closeEvent(self, e: QCloseEvent) -> None:
        # save the shape/size of this window on close
        conf = QSettings("zxlive", "zxlive")
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def new_graph(self,e):
        self.active_panel.clear_graph()

    def undo(self,e):
        self.active_panel.undo_stack.undo()

    def redo(self,e):
        self.active_panel.undo_stack.redo()

    def open_file(self):
        # Currently this does not check which mode we are in. Opening a file should invalidate a proof in Proof mode.
        g = import_diagram_dialog(self)
        if g is not None:
            cmd = SetGraph(self.active_panel.graph_view, g)
            self.active_panel.undo_stack.push(cmd)

    def close_action(self):
        self.close()

    def save_as(self):
        export_diagram_dialog(self.active_panel.graph_scene.g, self)

    def cut_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.save_graph_copy()
            self.active_panel.delete_selection()

    def copy_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.save_graph_copy()

    def paste_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.paste_graph()

    def delete_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.delete_selection()
