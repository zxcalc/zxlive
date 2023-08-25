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
from typing import Callable, Optional, TypedDict

import copy

from PySide6.QtCore import QFile, QFileInfo, QTextStream, QIODevice, QSettings, QByteArray, QEvent
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import QMessageBox, QMainWindow, QWidget, QVBoxLayout, QTabWidget
from pyzx.graph.base import BaseGraph

from .commands import AddRewriteStep
from .base_panel import BasePanel
from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .construct import *
from .dialogs import ImportGraphOutput, create_new_rewrite, export_proof_dialog, import_diagram_dialog, export_diagram_dialog, show_error_msg, FileFormat
from .common import GraphT

from pyzx import Graph, extract_circuit, simplify, Circuit


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
        tab_widget.currentChanged.connect(self.tab_changed)
        tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget = tab_widget

        # Currently the copied part is stored internally, and is not made available to the clipboard.
        # We could do this by using pyperclip.
        self.copied_graph: Optional[GraphT] = None

        menu = self.menuBar()

        new_graph = self._new_action("&New", self.new_graph, QKeySequence.StandardKey.New,
            "Reinitialize with an empty graph")
        open_file = self._new_action("&Open...", self.open_file, QKeySequence.StandardKey.Open,
            "Open a file-picker dialog to choose a new diagram")
        close_action = self._new_action("Close", self.close_action, QKeySequence.StandardKey.Close,
            "Closes the window")
        close_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.Close), QKeySequence("Ctrl+W")])
        # TODO: We should remember if we have saved the diagram before,
        # and give an open to overwrite this file with a Save action
        save_file = self._new_action("&Save", self.save_file, QKeySequence.StandardKey.Save,
            "Save the diagram by overwriting the previous loaded file.")
        save_as = self._new_action("Save &as...", self.save_as, QKeySequence.StandardKey.SaveAs,
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
        new_tab = self._new_action("new_tab", self.new_graph, QKeySequence.StandardKey.AddTab,
            "Create a new tab")
        self.addAction(new_tab)
        select_all = self._new_action("Select &All", self.select_all, QKeySequence.StandardKey.SelectAll, "Select all")
        deselect_all = self._new_action("&Deselect All", self.deselect_all, QKeySequence.StandardKey.Deselect, "Deselect all")
        deselect_all.setShortcuts([QKeySequence(QKeySequence.StandardKey.Deselect), QKeySequence("Ctrl+D")])

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
        edit_menu.addAction(deselect_all)

        zoom_in  = self._new_action("Zoom in", self.zoom_in,   QKeySequence.StandardKey.ZoomIn,"Zooms in by a fixed amount")
        zoom_out = self._new_action("Zoom out", self.zoom_out, QKeySequence.StandardKey.ZoomOut, "Zooms out by a fixed amount")
        zoom_in.setShortcuts([QKeySequence(QKeySequence.StandardKey.ZoomIn), QKeySequence("Ctrl+=")])
        fit_view = self._new_action("Fit view", self.fit_view, QKeySequence("C"), "Fits the view to the diagram")
        self.addAction(zoom_in)
        self.addAction(zoom_out)
        self.addAction(fit_view)

        view_menu = menu.addMenu("&View")
        view_menu.addAction(zoom_in)
        view_menu.addAction(zoom_out)
        view_menu.addAction(fit_view)

        new_rewrite = self._new_action("Create new rewrite", lambda: create_new_rewrite(self), None, "Create a new rewrite")
        rewrite_menu = menu.addMenu("&Rewrite")
        rewrite_menu.addAction(new_rewrite)

        simplify_actions = []
        for simp in simplifications.values():
            simplify_actions.append(self._new_action(simp["text"], self.apply_pyzx_reduction(simp), None, simp["tool_tip"]))
        self.simplify_menu = menu.addMenu("&Simplify")
        for action in simplify_actions:
            self.simplify_menu.addAction(action)
        self.simplify_menu.menuAction().setVisible(False)

        graph = construct_circuit()
        self.new_graph(graph)

    def _new_action(self,name:str,trigger:Callable,shortcut:QKeySequence | QKeySequence.StandardKey | None,tooltip:str) -> QAction:
        action = QAction(name, self)
        action.setStatusTip(tooltip)
        action.triggered.connect(trigger)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    @property
    def active_panel(self) -> Optional[BasePanel]:
        current_widget = self.tab_widget.currentWidget()
        if current_widget is not None:
            assert isinstance(current_widget, BasePanel)
            return current_widget
        return None


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

    def undo(self,e: QEvent) -> None:
        if self.active_panel is None: return
        self.active_panel.undo_stack.undo()

    def redo(self,e: QEvent) -> None:
        if self.active_panel is None: return
        self.active_panel.undo_stack.redo()

    def update_tab_name(self, clean:bool) -> None:
        i = self.tab_widget.currentIndex()
        name = self.tab_widget.tabText(i)
        if name.endswith("*"): name = name[:-1]
        if not clean: name += "*"
        self.tab_widget.setTabText(i,name)

    def tab_changed(self, i: int) -> None:
        if isinstance(self.active_panel, ProofPanel):
            self.simplify_menu.menuAction().setVisible(True)
        else:
            self.simplify_menu.menuAction().setVisible(False)

    def open_file(self) -> None:
        out = import_diagram_dialog(self)
        if out is not None:
            assert self.active_panel is not None
            name = QFileInfo(out.file_path).baseName()
            if isinstance(out, ImportGraphOutput):
                self.new_graph(out.g, name)
            else:
                graph = out.p.graphs[-1]
                self.new_deriv(graph, name)
                proof_panel: BasePanel = self.active_panel
                proof_panel.proof_model = out.p
                proof_panel.step_view.setModel(proof_panel.proof_model)
                proof_panel.step_view.setCurrentIndex(proof_panel.proof_model.index(len(proof_panel.proof_model.steps), 0))
                proof_panel.step_view.selectionModel().selectionChanged.connect(proof_panel._proof_step_selected)
            self.active_panel.file_path = out.file_path
            self.active_panel.file_type = out.file_type

    def close_action(self) -> bool:
        assert self.active_panel is not None
        i = self.tab_widget.currentIndex()
        if i == -1: # no tabs open
            self.close()
        return self.close_tab(i)

    def close_tab(self, i: int) -> bool:
        if i == -1:
            return False
        if not self.tab_widget.widget(i).undo_stack.isClean():
            name = self.tab_widget.tabText(i).replace("*","")
            answer = QMessageBox.question(self, "Save Changes",
                            f"Do you wish to save your changes to {name} before closing?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Yes:
                self.tab_widget.setCurrentIndex(i)
                val = self.save_file()
                if not val:
                    return False
        self.tab_widget.removeTab(i)
        return True

    def save_file(self) -> bool:
        assert self.active_panel is not None
        if self.active_panel.file_path is None:
            return self.save_as()
        if self.active_panel.file_type == FileFormat.QASM:
            show_error_msg("Can't save to circuit file",
                "You imported this file from a circuit description. You can currently only save it in a graph format.")
            return self.save_as()

        if isinstance(self.active_panel, ProofPanel):
            data = self.active_panel.proof_model.to_json()
        elif self.active_panel.file_type in (FileFormat.QGraph, FileFormat.Json):
            data = self.active_panel.graph.to_json()
        elif self.active_panel.file_type == FileFormat.TikZ:
            data = self.active_panel.graph.to_tikz()
        else:
            raise TypeError("Unknown file format", self.active_panel.file_type)

        file = QFile(self.active_panel.file_path)
        if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
            show_error_msg("Could not write to file")
            return False
        out = QTextStream(file)
        out << data
        file.close()
        self.active_panel.undo_stack.setClean()
        return True


    def save_as(self) -> bool:
        assert self.active_panel is not None
        if isinstance(self.active_panel, ProofPanel):
            out = export_proof_dialog(self.active_panel.proof_model, self)
        else:
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


    def cut_graph(self) -> None:
        assert self.active_panel is not None
        if isinstance(self.active_panel, GraphEditPanel):
            self.copied_graph = self.active_panel.copy_selection()
            self.active_panel.delete_selection()

    def copy_graph(self) -> None:
        assert self.active_panel is not None
        self.copied_graph = self.active_panel.copy_selection()

    def paste_graph(self) -> None:
        assert self.active_panel is not None
        if isinstance(self.active_panel, GraphEditPanel) and self.copied_graph is not None:
            self.active_panel.paste_graph(self.copied_graph)

    def delete_graph(self) -> None:
        assert self.active_panel is not None
        if isinstance(self.active_panel, GraphEditPanel):
            self.active_panel.delete_selection()

    def new_graph(self, graph:Optional[GraphT] = None, name:Optional[str]=None) -> None:
        graph = graph or Graph()
        panel = GraphEditPanel(graph)
        panel.start_derivation_signal.connect(self.new_deriv)
        if name is None: name = "New Graph"
        self.tab_widget.addTab(panel, name)
        self.tab_widget.setCurrentWidget(panel)
        panel.undo_stack.cleanChanged.connect(self.update_tab_name)

    def new_deriv(self, graph:GraphT, name:Optional[str]=None) -> None:
        panel = ProofPanel(graph)
        if name is None: name = "New Proof"
        self.tab_widget.addTab(panel, name)
        self.tab_widget.setCurrentWidget(panel)
        panel.undo_stack.cleanChanged.connect(self.update_tab_name)

    def select_all(self) -> None:
        assert self.active_panel is not None
        self.active_panel.select_all()

    def deselect_all(self) -> None:
        assert self.active_panel is not None
        self.active_panel.deselect_all()

    def zoom_in(self) -> None:
        assert self.active_panel is not None
        self.active_panel.graph_view.zoom_in()

    def zoom_out(self) -> None:
        assert self.active_panel is not None
        self.active_panel.graph_view.zoom_out()

    def fit_view(self) -> None:
        assert self.active_panel is not None
        self.active_panel.graph_view.fit_view()

    def apply_pyzx_reduction(self, reduction: SimpEntry) -> Callable[[],None]:
        def reduce() -> None:
            assert self.active_panel is not None
            old_graph = self.active_panel.graph
            new_graph = copy.deepcopy(old_graph)
            try:
                if reduction["in_place"]:
                    reduction["function"](new_graph)
                else:
                    new_graph = reduction["function"](new_graph)
                cmd = AddRewriteStep(self.active_panel.graph_view, new_graph, self.active_panel.step_view, reduction["text"])
                self.active_panel.undo_stack.push(cmd)
            except Exception as e:
                show_error_msg("Error", str(e))
        return reduce


class SimpEntry(TypedDict):
    text: str
    tool_tip: str
    function: Callable[[BaseGraph], int | None | BaseGraph] | Callable[[BaseGraph | Circuit], int]


def _extract_circuit(graph: BaseGraph) -> BaseGraph:
    graph.auto_detect_io()
    simplify.full_reduce(graph)
    return extract_circuit(graph).to_graph()

simplifications: dict[str, SimpEntry] = {
    'bialg_simp': {"text": "bialg_simp", "tool_tip":"bialg_simp", "function": simplify.bialg_simp, "in_place": True},
    'spider_simp': {"text": "spider_simp", "tool_tip":"spider_simp", "function": simplify.spider_simp, "in_place": True},
    'id_simp': {"text": "id_simp", "tool_tip":"id_simp", "function": simplify.id_simp, "in_place": True},
    'phase_free_simp': {"text": "phase_free_simp", "tool_tip":"phase_free_simp", "function": simplify.phase_free_simp, "in_place": True},
    'pivot_simp': {"text": "pivot_simp", "tool_tip":"pivot_simp", "function": simplify.pivot_simp, "in_place": True},
    'pivot_gadget_simp': {"text": "pivot_gadget_simp", "tool_tip":"pivot_gadget_simp", "function": simplify.pivot_gadget_simp, "in_place": True},
    'pivot_boundary_simp': {"text": "pivot_boundary_simp", "tool_tip":"pivot_boundary_simp", "function": simplify.pivot_boundary_simp, "in_place": True},
    'gadget_simp': {"text": "gadget_simp", "tool_tip":"gadget_simp", "function": simplify.gadget_simp, "in_place": True},
    'lcomp_simp': {"text": "lcomp_simp", "tool_tip":"lcomp_simp", "function": simplify.lcomp_simp, "in_place": True},
    'clifford_simp': {"text": "clifford_simp", "tool_tip":"clifford_simp", "function": simplify.clifford_simp, "in_place": True},
    'tcount': {"text": "tcount", "tool_tip":"tcount", "function": simplify.tcount, "in_place": True},
    'to_gh': {"text": "to_gh", "tool_tip":"to_gh", "function": simplify.to_gh, "in_place": True},
    'to_rg': {"text": "to_rg", "tool_tip":"to_rg", "function": simplify.to_rg, "in_place": True},
    'full_reduce': {"text": "full_reduce", "tool_tip":"full_reduce", "function": simplify.full_reduce, "in_place": True},
    'teleport_reduce': {"text": "teleport_reduce", "tool_tip":"teleport_reduce", "function": simplify.teleport_reduce, "in_place": True},
    'reduce_scalar': {"text": "reduce_scalar", "tool_tip":"reduce_scalar", "function": simplify.reduce_scalar, "in_place": True},
    'supplementarity_simp': {"text": "supplementarity_simp", "tool_tip":"supplementarity_simp", "function": simplify.supplementarity_simp, "in_place": True},
    'to_clifford_normal_form_graph': {"text": "to_clifford_normal_form_graph", "tool_tip":"to_clifford_normal_form_graph", "function": simplify.to_clifford_normal_form_graph, "in_place": True},
    'extract_circuit': {"text": "extract_circuit", "tool_tip":"extract_circuit", "function": _extract_circuit, "in_place": False},
}
