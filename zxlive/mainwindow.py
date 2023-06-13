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

from pyzx import Graph


class MainWindow(QMainWindow):
    """A simple window containing a single `GraphView`
    This is just an example, and should be replaced with
    something more sophisticated.
    """

    edit_panel: GraphEditPanel
    proof_panel: ProofPanel

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

        file_tab_widget = QTabWidget()
        file_tab_widget.setTabsClosable(True)
        w.layout().addWidget(file_tab_widget)
        file_tab_widget.tabCloseRequested.connect(lambda i: file_tab_widget.removeTab(i))

        tab_widget = QTabWidget()
        w.layout().addWidget(tab_widget)
        tab_widget.setTabsClosable(True)
        tab_widget.tabCloseRequested.connect(lambda i: tab_widget.removeTab(i))
        self.tab_widget = tab_widget

        graph = construct_circuit()
        self.new_graph(graph)
        self.copied_graph = None

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
        new_tab = self._new_action("new_tab", self.new_graph, QKeySequence.AddTab,
            "Create a new tab")
        self.addAction(new_tab)
        select_all = self._new_action("Select All", self.select_all, QKeySequence.StandardKey.SelectAll, "Select all")
        self.addAction(select_all)

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
        active_panel = self.tab_widget.currentWidget()
        export_diagram_dialog(active_panel.graph_scene.g, self)

    def cut_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.copied_graph = self.active_panel.copy_selection()
            self.active_panel.delete_selection()

    def copy_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.copied_graph = self.active_panel.copy_selection()

    def paste_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.paste_graph(self.copied_graph)

    def delete_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.delete_selection()

    def new_graph(self, graph=None):
        graph = graph or Graph()
        panel = GraphEditPanel(graph)
        panel.start_derivation_signal.connect(self.new_deriv)
        self.tab_widget.addTab(panel, "New Graph")
        self.tab_widget.setCurrentWidget(panel)

    def new_deriv(self, graph):
        panel = ProofPanel(graph)
        self.tab_widget.addTab(panel, "New Proof")
        self.tab_widget.setCurrentWidget(panel)

    @property
    def active_panel(self):
        return self.tab_widget.currentWidget()

    def select_all(self):
        self.active_panel.select_all()