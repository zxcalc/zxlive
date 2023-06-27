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

from PySide6.QtCore import QFile, QFileInfo, QTextStream, QIODevice
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtWidgets import QMessageBox

from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .construct import *
from .commands import SetGraph
from .dialogs import import_diagram_dialog, export_diagram_dialog, show_error_msg, FileFormat

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
        save_file = self._new_action("&Save", self.save_file,QKeySequence.StandardKey.Save,
            "Save the diagram by overwriting the previous loaded file.")
        save_as = self._new_action("Save &as...", self.save_as,QKeySequence.StandardKey.SaveAs,
            "Opens a file-picker dialog to save the diagram in a chosen file format")
        
        file_menu = menu.addMenu("&File")
        file_menu.addAction(new_graph)
        file_menu.addAction(open_file)
        file_menu.addSeparator()
        file_menu.addAction(close_action)
        file_menu.addAction(save_file)
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

        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(undo)
        edit_menu.addAction(redo)
        edit_menu.addSeparator()
        edit_menu.addAction(cut_action)
        edit_menu.addAction(copy_action)
        edit_menu.addAction(paste_action)
        edit_menu.addAction(delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(select_all)

    def _new_action(self,name:str,trigger:Callable,shortcut:QKeySequence | QKeySequence.StandardKey,tooltip:str):
        action = QAction(name, self)
        action.setStatusTip(tooltip)
        action.triggered.connect(trigger)
        action.setShortcut(shortcut)
        return action

    @property
    def active_panel(self):
        return self.tab_widget.currentWidget()


    def closeEvent(self, e: QCloseEvent) -> None:
        while self.active_panel is not None:  # We close all the tabs and ask the user if they want to save progress
            success = self.close_action()
            if not success: 
                e.ignore()  # Abort the closing
                return

        # save the shape/size of this window on close
        conf = QSettings("zxlive", "zxlive")
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def undo(self,e):
        if self.active_panel is None: return
        self.active_panel.undo_stack.undo()

    def redo(self,e):
        if self.active_panel is None: return
        self.active_panel.undo_stack.redo()

    def update_tab_name(self, clean:bool):
        i = self.tab_widget.currentIndex()
        name = self.tab_widget.tabText(i)
        if name.endswith("*"): name = name[:-1]
        if not clean: name += "*"
        self.tab_widget.setTabText(i,name)

    def open_file(self):
        # Currently this does not check which mode we are in. Opening a file should invalidate a proof in Proof mode.
        out = import_diagram_dialog(self)
        if out is not None:
            name = QFileInfo(out.file_path).baseName()
            self.new_graph(out.g, name)
            self.active_panel.file_path = out.file_path
            self.active_panel.file_type = out.file_type

    def close_action(self):
        i = self.tab_widget.currentIndex()
        if i == -1: # no tabs open
            self.close()
        if not self.active_panel.undo_stack.isClean():
            name = self.tab_widget.tabText(i).replace("*","")
            answer = QMessageBox.question(self, "Save Changes", 
                            f"Do you wish to save your changes to {name} before closing?",
                            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel: return False
            if answer == QMessageBox.Yes:
                val = self.save_file()
                if not val: return
        self.tab_widget.tabCloseRequested.emit(i)
        return True

    def save_file(self):
        if self.active_panel.file_path is None:
            return self.save_as()
        if self.active_panel.file_type == FileFormat.QASM:
            show_error_msg("Can't save to circuit file",
                "You imported this file from a circuit description. You can currently only save it in a graph format.")
            return self.save_as()

        if self.active_panel.file_type in (FileFormat.QGraph, FileFormat.Json):
            data = self.active_panel.graph.to_json()
        elif self.active_panel.file_type == FileFormat.TikZ:
            data = self.active_panel.graph.to_tikz()
        else:
            raise TypeError("Unknown file format", self.active_panel.file_type)
        
        file = QFile(self.active_panel.file_path)
        if not file.open(QIODevice.WriteOnly | QIODevice.Text):
            show_error_msg("Could not write to file")
            return False
        out = QTextStream(file)
        out << data
        file.close()
        self.active_panel.undo_stack.setClean()
        return True


    def save_as(self):
        out = export_diagram_dialog(self.active_panel.graph_scene.g, self)
        if out is None: return False
        file_path, file_type = out
        self.active_panel.file_path = file_path
        self.active_panel.file_type = file_type
        self.active_panel.undo_stack.setClean()
        name = QFileInfo(file_path).baseName()
        i = self.tab_widget.currentIndex()
        self.tab_widget.setTabText(i,name)
        return True


    def cut_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.copied_graph = self.active_panel.copy_selection()
            self.active_panel.delete_selection()

    def copy_graph(self):
        self.copied_graph = self.active_panel.copy_selection()

    def paste_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.paste_graph(self.copied_graph)

    def delete_graph(self):
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.delete_selection()

    def new_graph(self, graph=None, name:Optional[str]=None):
        graph = graph or Graph()
        panel = GraphEditPanel(graph)
        panel.start_derivation_signal.connect(self.new_deriv)
        if name is None: name = "New Graph"
        self.tab_widget.addTab(panel, name)
        self.tab_widget.setCurrentWidget(panel)
        panel.undo_stack.cleanChanged.connect(self.update_tab_name)

    def new_deriv(self, graph):
        panel = ProofPanel(graph)
        self.tab_widget.addTab(panel, "New Proof")
        self.tab_widget.setCurrentWidget(panel)
        panel.undo_stack.cleanChanged.connect(self.update_tab_name)

    def select_all(self):
        self.active_panel.select_all()