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

from __future__ import annotations

import copy
import random
from typing import Callable, Optional, cast

from PySide6.QtCore import (QByteArray, QDir, QEvent, QFile, QFileInfo,
                            QIODevice, QSettings, QTextStream, Qt, QUrl)
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (QDialog, QMainWindow, QMessageBox,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget, QApplication)

import pyperclip

from .base_panel import BasePanel
from .common import GraphT, get_data, new_graph, to_tikz, from_tikz, get_settings_value, set_settings_value
from .construct import *
from .custom_rule import CustomRule, check_rule
from .dialogs import (FileFormat, ImportGraphOutput, ImportProofOutput,
                      ImportRuleOutput, create_new_rewrite,
                      save_diagram_dialog, save_proof_dialog,
                      save_rule_dialog, get_lemma_name_and_description,
                      import_diagram_dialog, import_diagram_from_file, show_error_msg,
                      export_proof_dialog, export_gif_dialog)
from .settings import display_setting
from .settings_dialog import open_settings_dialog

from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .rule_panel import RulePanel
from .sfx import SFXEnum, load_sfx
from .tikz import proof_to_tikz
from pyzx.graph.base import BaseGraph
from pyzx.drawing import graphs_to_gif


class MainWindow(QMainWindow):
    """The main window of the ZXLive application."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("zxlive", "zxlive")

        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        wlayout = w.layout()
        assert wlayout is not None # for mypy
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(0)
        self.resize(1200, 800)

        # restore the window from the last time it was opened
        geom = self.settings.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        tab_widget = QTabWidget(self)
        wlayout.addWidget(tab_widget)
        tab_widget.setTabsClosable(True)
        tab_widget.currentChanged.connect(self.tab_changed)
        tab_widget.tabCloseRequested.connect(self.close_tab)
        tab_widget.setMovable(True)
        tab_position = self.settings.value("tab-bar-location", QTabWidget.TabPosition.North)
        assert isinstance(tab_position, QTabWidget.TabPosition)
        tab_widget.setTabPosition(tab_position)
        self.tab_widget = tab_widget

        # Currently the copied part is stored internally, and is not made available to the clipboard.
        # We could do this by using pyperclip.
        self.copied_graph: Optional[GraphT] = None

        menu = self.menuBar()

        new_graph = self._new_action("&New", self.new_graph, QKeySequence.StandardKey.New,
            "Create a new tab with an empty graph", alt_shortcut=QKeySequence.StandardKey.AddTab)
        new_window = self._new_action("New &Window", self.open_new_window, QKeySequence("Ctrl+Shift+N"), "Open a new window")
        open_file = self._new_action("&Open...", self.open_file, QKeySequence.StandardKey.Open,
            "Open a file-picker dialog to choose a new diagram")
        self.close_action = self._new_action("Close", self.handle_close_action, QKeySequence.StandardKey.Close,
            "Closes the window", alt_shortcut=QKeySequence("Ctrl+W"))
        # TODO: We should remember if we have saved the diagram before,
        # and give an option to overwrite this file with a Save action.
        self.save_file = self._new_action("&Save", self.handle_save_file_action, QKeySequence.StandardKey.Save,
            "Save the diagram by overwriting the previous loaded file.")
        self.save_as = self._new_action("Save &as...", self.handle_save_as_action, QKeySequence.StandardKey.SaveAs,
            "Opens a file-picker dialog to save the diagram in a chosen file format")
        self.export_tikz_proof = self._new_action("Export proof to tikz", self.handle_export_tikz_proof_action, None,
            "Exports the proof to tikz")
        self.export_gif_proof = self._new_action("Export proof to gif", self.handle_export_gif_proof_action, None,
            "Exports the proof to gif")
        self.auto_save_action = self._new_action(
            "Auto Save", self.toggle_auto_save, None,
            "Automatically save the file after every edit"
        )
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setChecked(get_settings_value("auto-save", bool, False))

        file_menu = menu.addMenu("&File")
        file_menu.addAction(new_graph)
        file_menu.addAction(new_window)
        file_menu.addAction(open_file)
        file_menu.addSeparator()
        file_menu.addAction(self.close_action)
        file_menu.addAction(self.save_file)
        file_menu.addAction(self.save_as)
        file_menu.addAction(self.export_tikz_proof)
        file_menu.addAction(self.export_gif_proof)
        file_menu.addSeparator()
        file_menu.addAction(self.auto_save_action)

        self.undo_action = self._new_action("Undo", self.undo, QKeySequence.StandardKey.Undo,
            "Undoes the last action", "undo.svg")
        self.redo_action = self._new_action("Redo", self.redo, QKeySequence.StandardKey.Redo,
            "Redoes the last action", "redo.svg")
        self.cut_action = self._new_action("Cut", self.cut_graph, QKeySequence.StandardKey.Cut,
            "Cut the selected part of the diagram")
        self.copy_action = self._new_action("&Copy", self.copy_graph, QKeySequence.StandardKey.Copy,
            "Copy the selected part of the diagram")
        self.copy_clipboard_action = self._new_action("Copy tikz to clipboard", self.copy_graph_to_clipboard, 
                                                      QKeySequence("Ctrl+Shift+C"), "Copy the selected part of the diagram to the clipboard as tikz")
        self.paste_action = self._new_action("Paste", self.paste_graph, QKeySequence.StandardKey.Paste,
            "Paste the copied part of the diagram")
        self.paste_clipboard_action = self._new_action("Paste tikz from clipboard", self.paste_graph_from_clipboard,
                                                       QKeySequence("Ctrl+Shift+V"), "Paste a tikz diagram in the clipboard to ZXLive")
        self.delete_action = self._new_action("Delete", self.delete_graph,QKeySequence.StandardKey.Delete,
            "Delete the selected part of the diagram", alt_shortcut = QKeySequence("Backspace"))
        self.select_all_action = self._new_action("Select &All", self.select_all, QKeySequence.StandardKey.SelectAll, "Select all")
        self.deselect_all_action = self._new_action("&Deselect All", self.deselect_all, QKeySequence.StandardKey.Deselect,
            "Deselect all", alt_shortcut = QKeySequence("Ctrl+D"))
        self.preferences_action = self._new_action("&Preferences...", lambda: open_settings_dialog(self), None, "Open the preferences dialog")

        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.copy_clipboard_action)
        edit_menu.addAction(self.paste_clipboard_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.select_all_action)
        edit_menu.addAction(self.deselect_all_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.preferences_action)

        self.zoom_in_action  = self._new_action("Zoom in", self.zoom_in,   QKeySequence.StandardKey.ZoomIn,"Zooms in by a fixed amount",
            alt_shortcut = QKeySequence("Ctrl+="))
        self.zoom_out_action = self._new_action("Zoom out", self.zoom_out, QKeySequence.StandardKey.ZoomOut, "Zooms out by a fixed amount")
        self.fit_view_action = self._new_action("Fit view", self.fit_view, QKeySequence("C"), "Fits the view to the diagram")

        view_menu = menu.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_view_action)

        new_rewrite_from_file = self._new_action("New rewrite from file", lambda: create_new_rewrite(self), None, "New rewrite from file")
        new_rewrite_editor = self._new_action("New rewrite", lambda: self.new_rule_editor(), None, "New rewrite")
        self.proof_as_rewrite_action = self._new_action("Save proof as a rewrite", self.proof_as_lemma, None, "Save proof as a rewrite")
        rewrite_menu = menu.addMenu("&Rewrites")
        rewrite_menu.addAction(new_rewrite_editor)
        rewrite_menu.addAction(new_rewrite_from_file)
        rewrite_menu.addAction(self.proof_as_rewrite_action)

        menu.setStyleSheet("QMenu::item:disabled { color: gray }")
        self._reset_menus(False)

        self.effects = {e: load_sfx(e) for e in SFXEnum}

        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(self._toggle_sfx)

    def open_demo_graph(self) -> None:
        graph = construct_circuit()
        self.new_graph(graph)

    def _reset_menus(self, has_active_tab: bool) -> None:
        self.save_file.setEnabled(has_active_tab)
        self.save_as.setEnabled(has_active_tab)
        self.cut_action.setEnabled(has_active_tab)
        self.copy_action.setEnabled(has_active_tab)
        self.delete_action.setEnabled(has_active_tab)
        self.select_all_action.setEnabled(has_active_tab)
        self.deselect_all_action.setEnabled(has_active_tab)
        self.zoom_in_action.setEnabled(has_active_tab)
        self.zoom_out_action.setEnabled(has_active_tab)
        self.fit_view_action.setEnabled(has_active_tab)

        # Export to tikz and gif are enabled only if there is a proof in the active tab.
        self.export_tikz_proof.setEnabled(has_active_tab and isinstance(self.active_panel, ProofPanel))
        self.export_gif_proof.setEnabled(has_active_tab and isinstance(self.active_panel, ProofPanel))

        # Paste is enabled only if there is something in the clipboard.
        self.paste_action.setEnabled(has_active_tab and self.copied_graph is not None)

        # Undo and redo are always disabled whether on a new tab or closing the last tab.
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

        # TODO: As an enhancement, cut, copy, delete, select all and deselect all should start 
        # disabled even on a new tab, and should only be enabled once anything is selected.

    def _new_action(self, name: str, trigger: Callable, shortcut: QKeySequence | QKeySequence.StandardKey | None,
                    tooltip: str, icon_file: Optional[str] = None,
                    alt_shortcut: Optional[QKeySequence | QKeySequence.StandardKey] = None) -> QAction:
        assert not alt_shortcut or shortcut
        action = QAction(name, self)
        if icon_file:
            action.setIcon(QIcon(get_data(f"icons/{icon_file}")))
        action.setStatusTip(tooltip)
        action.triggered.connect(trigger)
        if shortcut:
            action.setShortcut(shortcut)
            if alt_shortcut:
                if not action.shortcuts():
                    action.setShortcut(alt_shortcut)
                elif alt_shortcut not in action.shortcuts():
                    action.setShortcuts([shortcut, alt_shortcut])  # type: ignore
        return action

    @property
    def active_panel(self) -> Optional[BasePanel]:
        current_widget = self.tab_widget.currentWidget()
        if current_widget is not None:
            assert isinstance(current_widget, BasePanel)
            return current_widget
        return None

    def open_new_window(self) -> None:
        new_window = MainWindow()
        new_window.new_graph()
        new_window.show()

    def closeEvent(self, e: QCloseEvent) -> None:
        while self.active_panel is not None:  # We close all the tabs and ask the user if they want to save progress
            success = self.handle_close_action()
            if not success:
                e.ignore()  # Abort the closing
                return

        # save the shape/size of this window on close
        self.settings.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def undo(self, e: QEvent) -> None:
        if self.active_panel is None:
            e.ignore()
            return
        self.active_panel.undo_stack.undo()

    def redo(self, e: QEvent) -> None:
        if self.active_panel is None:
            e.ignore()
            return
        self.active_panel.undo_stack.redo()

    def update_tab_name(self, clean:bool) -> None:
        i = self.tab_widget.currentIndex()
        name = self.tab_widget.tabText(i)
        if name.endswith("*"): name = name[:-1]
        if not clean: name += "*"
        self.tab_widget.setTabText(i,name)

    def tab_changed(self, i: int) -> None:
        if isinstance(self.active_panel, ProofPanel):
            self.proof_as_rewrite_action.setEnabled(True)
        else:
            self.proof_as_rewrite_action.setEnabled(False)
        self._undo_changed()
        self._redo_changed()
        if self.active_panel:
            self.active_panel.update_colors()
            self._reset_menus(True)
            self.active_panel.set_splitter_size()

    def _undo_changed(self) -> None:
        if self.active_panel:
            self.undo_action.setEnabled(self.active_panel.undo_stack.canUndo())

    def _redo_changed(self) -> None:
        if self.active_panel:
            self.redo_action.setEnabled(self.active_panel.undo_stack.canRedo())

    def open_file(self) -> None:
        out = import_diagram_dialog(self)
        if out is not None:
            self._open_file_from_output(out)

    def open_file_from_path(self, file_path: str) -> None:
        out = import_diagram_from_file(file_path, parent=self)
        if out is not None:
            self._open_file_from_output(out)

    def _open_file_from_output(self, out: ImportGraphOutput | ImportProofOutput | ImportRuleOutput) -> None:
            name = QFileInfo(out.file_path).baseName()
            if isinstance(out, ImportGraphOutput):
                self.new_graph(out.g, name)
            elif isinstance(out, ImportProofOutput):
                graph = out.p.graphs()[-1]
                self.new_deriv(graph, name)
                assert isinstance(self.active_panel, ProofPanel)
                proof_panel: ProofPanel = self.active_panel
                proof_panel.step_view.set_model(out.p)
            elif isinstance(out, ImportRuleOutput):
                self.new_rule_editor(out.r, name)
            else:
                raise TypeError("Unknown import type", out)
            assert self.active_panel is not None
            self.active_panel.file_path = out.file_path
            self.active_panel.file_type = out.file_type

    def handle_close_action(self) -> bool:
        i = self.tab_widget.currentIndex()
        if i == -1: # no tabs open, close the app
            self.close()
        return self.close_tab(i)

    def close_tab(self, i: int) -> bool:
        if i == -1:
            return False
        widget = self.tab_widget.widget(i)
        assert isinstance(widget, BasePanel)
        if not widget.undo_stack.isClean():
            name = self.tab_widget.tabText(i).replace("*","")
            answer = QMessageBox.question(self, "Save Changes",
                            f"Do you wish to save your changes to {name} before closing?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel) # type: ignore
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Yes:
                self.tab_widget.setCurrentIndex(i)
                val = self.handle_save_file_action()
                if not val:
                    return False
        widget.graph_scene.clearSelection()
        self.tab_widget.removeTab(i)
        if self.tab_widget.count() == 0:
            self._reset_menus(False)
        else:
            self._reset_menus(True)
        return True

    def handle_save_file_action(self) -> bool:
        assert self.active_panel is not None
        if self.active_panel.file_path is None:
            return self.handle_save_as_action()
        if self.active_panel.file_type == FileFormat.QASM:
            show_error_msg("Can't save to circuit file",
                           "You imported this file from a circuit description. You can currently only save it in a graph format.",
                           parent=self)
            return self.handle_save_as_action()

        if isinstance(self.active_panel, ProofPanel):
            data = self.active_panel.proof_model.to_json()
        elif isinstance(self.active_panel, RulePanel):
            try:
                check_rule(self.active_panel.get_rule())
            except Exception as e:
                show_error_msg("Warning!", str(e), parent=self)
            data = self.active_panel.get_rule().to_json()
        elif self.active_panel.file_type in (FileFormat.QGraph, FileFormat.Json):
            data = self.active_panel.graph.to_json()
        elif self.active_panel.file_type == FileFormat.TikZ:
            data = self.active_panel.graph.to_tikz()
        else:
            raise TypeError("Unknown file format", self.active_panel.file_type)

        file = QFile(self.active_panel.file_path)
        if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
            show_error_msg("Could not write to file", parent=self)
            return False
        out = QTextStream(file)
        out << data
        file.close()
        self.active_panel.undo_stack.setClean()
        if random.random() < 0.1:
            self.play_sound(SFXEnum.IRANIAN_BUS)
        return True


    def handle_save_as_action(self) -> bool:
        assert self.active_panel is not None
        if isinstance(self.active_panel, ProofPanel):
            out = save_proof_dialog(self.active_panel.proof_model, self)
        elif isinstance(self.active_panel, RulePanel):
            try:
                check_rule(self.active_panel.get_rule())
            except Exception as e:
                show_error_msg("Warning!", str(e), parent=self)
            out = save_rule_dialog(self.active_panel.get_rule(), self)
        else:
            out = save_diagram_dialog(self.active_panel.graph_scene.g, self)
        if out is None: return False
        file_path, file_type = out
        self.active_panel.file_path = file_path
        self.active_panel.file_type = file_type
        self.active_panel.undo_stack.setClean()
        name = QFileInfo(file_path).baseName()
        i = self.tab_widget.currentIndex()
        self.tab_widget.setTabText(i,name)
        return True

    def handle_export_tikz_proof_action(self) -> bool:
        assert isinstance(self.active_panel, ProofPanel)
        path = export_proof_dialog(self)
        if path is None:
            show_error_msg("Export failed", "Invalid path", parent=self)
            return False
        with open(path, "w") as f:
            f.write(proof_to_tikz(self.active_panel.proof_model))
        return True

    def handle_export_gif_proof_action(self) -> bool:
        assert isinstance(self.active_panel, ProofPanel)
        path = export_gif_dialog(self)
        if path is None:
            show_error_msg("Export failed", "Invalid path", parent=self)
            return False
        graphs: list[BaseGraph] = list(self.active_panel.proof_model.graphs())
        graphs_to_gif(graphs, path, 1000) # 1000ms per frame
        return True

    def cut_graph(self) -> None:
        assert self.active_panel is not None
        self.copied_graph = self.active_panel.copy_selection()
        self.paste_action.setEnabled(True)
        self.active_panel.delete_selection()

    def copy_graph(self) -> None:
        assert self.active_panel is not None
        self.copied_graph = self.active_panel.copy_selection()
        self.paste_action.setEnabled(True)

    def copy_graph_to_clipboard(self) -> None:
        """Copies the selected graph to the clipboard as a tikz string that can be understood by Tikzit."""
        assert self.active_panel is not None
        copied_graph = self.active_panel.copy_selection()
        tikz = to_tikz(copied_graph)
        pyperclip.copy(tikz)

    def paste_graph(self) -> None:
        assert self.active_panel is not None
        if self.copied_graph is not None:
            self.active_panel.paste_graph(self.copied_graph)

    def paste_graph_from_clipboard(self) -> None:
        assert self.active_panel is not None
        tikz = pyperclip.paste()
        copied_graph = from_tikz(tikz)
        if copied_graph is not None:
            self.active_panel.paste_graph(copied_graph)

    def delete_graph(self) -> None:
        assert self.active_panel is not None
        self.active_panel.delete_selection()

    def _new_panel(self, panel: BasePanel, name: str) -> None:
        self.tab_widget.addTab(panel, name)
        self.tab_widget.setCurrentWidget(panel)

        self._reset_menus(True)

        panel.undo_stack.cleanChanged.connect(self.update_tab_name)
        panel.undo_stack.canUndoChanged.connect(self._undo_changed)
        panel.undo_stack.canRedoChanged.connect(self._redo_changed)
        panel.play_sound_signal.connect(self.play_sound)
        panel.undo_stack.indexChanged.connect(self._auto_save_if_needed)

    def _auto_save_if_needed(self) -> None:
        panel = self.active_panel
        if panel and getattr(panel, 'file_path', None) and get_settings_value("auto-save", bool, False):
            self.handle_save_file_action()

    def new_graph(self, graph: Optional[GraphT] = None, name: Optional[str] = None) -> None:
        _graph = graph or new_graph()
        panel = GraphEditPanel(_graph, self.undo_action, self.redo_action)
        panel.start_derivation_signal.connect(self.new_deriv)
        if name is None: name = "New Graph"
        self._new_panel(panel, name)

    def open_graph_from_notebook(self, graph: GraphT, name: str) -> None:
        """Opens a ZXLive window from within a Jupyter notebook to edit a graph.

        Replaces the graph in an existing tab if it has the same name."""

        if not isinstance(graph, GraphT): # The graph we are given is not a MultiGraph
            graph = graph.copy(backend='multigraph')
            graph.set_auto_simplify(False)

        # TODO: handle multiple tabs with the same name somehow
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == name or self.tab_widget.tabText(i) == name + "*":
                self.tab_widget.setCurrentIndex(i)
                assert self.active_panel is not None
                self.active_panel.replace_graph(graph)
                return
        self.new_graph(copy.deepcopy(graph), name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        # TODO: handle multiple tabs with the same name somehow
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == name or self.tab_widget.tabText(i) == name + "*":
                panel = cast(BasePanel, self.tab_widget.widget(i))
                return cast(GraphT, copy.deepcopy(panel.graph_scene.g))
        return None

    def new_rule_editor(self, rule: Optional[CustomRule] = None, name: Optional[str] = None) -> None:
        if rule is None:
            graph1 = new_graph()
            graph2 = new_graph()
            rule_name = ""
            rule_description = ""
        else:
            graph1 = rule.lhs_graph
            graph2 = rule.rhs_graph
            rule_name = rule.name
            rule_description = rule.description
        panel = RulePanel(graph1, graph2, rule_name, rule_description, self.undo_action, self.redo_action)
        if name is None: name = "New Rule"
        self._new_panel(panel, name)

    def new_deriv(self, graph:GraphT, name:Optional[str]=None) -> None:
        panel = ProofPanel(graph, self.undo_action, self.redo_action)
        if name is None: name = "New Proof"
        self._new_panel(panel, name)

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

    def proof_as_lemma(self) -> None:
        assert self.active_panel is not None
        assert isinstance(self.active_panel, ProofPanel)
        name, description = get_lemma_name_and_description(self)
        if name is None or description is None:
            return
        lhs_graph = self.active_panel.proof_model.graphs()[0]
        rhs_graph = self.active_panel.proof_model.graphs()[-1]
        rule = CustomRule(lhs_graph, rhs_graph, name, description)
        save_rule_dialog(rule, self, name + ".zxr" if name else "")

    def update_colors(self) -> None:
        # Apply dark or light stylesheet to the app and widgets
        app = QApplication.instance()
        if isinstance(app, QApplication):
            if display_setting.dark_mode:
                dark_stylesheet = """
                    QMainWindow, QWidget, QDialog, QMenuBar, QMenu, QTabWidget, QTableWidget, QSpinBox, QPushButton {
                        background-color: #232323;
                        color: #e0e0e0;
                    }
                    QLineEdit, QTextEdit, QPlainTextEdit {
                        background-color: #2d2d2d;
                        color: #e0e0e0;
                    }
                    QTableWidget QHeaderView::section {
                        background-color: #232323;
                        color: #e0e0e0;
                    }
                    QTabBar::tab:selected {
                        background: #333333;
                    }
                    QTabBar::tab:!selected {
                        background: #232323;
                    }
                    QMenu::item:selected {
                        background: #444444;
                    }
                    QPushButton {
                        background-color: #333333;
                        color: #e0e0e0;
                    }
                    QSpinBox, QComboBox {
                        background-color: #2d2d2d;
                        color: #e0e0e0;
                    }
                """
                app.setStyleSheet(dark_stylesheet)
            else:
                app.setStyleSheet("")
        if self.active_panel is not None:
            self.active_panel.update_colors()

    @property
    def sfx_on(self) -> bool:
        return get_settings_value("sound-effects",bool,False,self.settings)

    @sfx_on.setter
    def sfx_on(self, value: bool) -> None:
        set_settings_value("sound-effects", value,bool,self.settings)

    def play_sound(self, s: SFXEnum) -> None:
        if self.sfx_on:
            self.effects[s].play()

    def _toggle_sfx(self) -> None:
        self.sfx_on = not self.sfx_on
        if self.sfx_on:
            self.play_sound(random.choice([
                SFXEnum.WELCOME_EVERYBODY,
                SFXEnum.OK_IM_GONNA_START,
            ]))

    def update_font(self) -> None:
        self.menuBar().setFont(display_setting.font)
        for i in range(self.tab_widget.count()):
            w = cast(BasePanel, self.tab_widget.widget(i))
            w.update_font()

    def toggle_auto_save(self) -> None:
        """Toggle the auto-save setting from the File menu."""
        from .common import set_settings_value
        checked = self.auto_save_action.isChecked()
        set_settings_value("auto-save", checked, bool)
