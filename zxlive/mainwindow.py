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
import json
import logging
import random
from typing import Callable, Optional, cast

import pyperclip
from PySide6.QtCore import (QByteArray, QEvent, QFile, QFileInfo, QIODevice,
                            QSettings, QTextStream, QTimer, QUrl)
from PySide6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                           QKeySequence, QMouseEvent, QShortcut)
from PySide6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QTabBar,
                               QTabWidget, QVBoxLayout, QWidget)
from pyzx.drawing import graphs_to_gif
from pyzx.graph.base import BaseGraph

from .base_panel import BasePanel
from .common import (GraphT, from_tikz, get_data, get_settings_value,
                     new_graph, set_settings_value, to_tikz)
from .construct import construct_circuit
from .custom_rule import CustomRule, check_rule
from .dialogs import (FileFormat, ImportGraphOutput, ImportProofOutput,
                      ImportRuleOutput, create_new_rewrite, export_gif_dialog,
                      export_proof_dialog, get_lemma_name_and_description,
                      import_diagram_dialog, import_diagram_from_file,
                      save_diagram_dialog, save_proof_dialog, save_rule_dialog,
                      show_error_msg)
from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .pauliwebs_panel import PauliWebsPanel
from .rule_panel import RulePanel
from .settings import display_setting
from .settings_dialog import open_settings_dialog
from .sfx import SFXEnum, load_sfx
from .tikz import proof_to_tikz


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
        assert wlayout is not None  # for mypy
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(0)
        self.resize(1200, 800)

        # restore the window from the last time it was opened
        geom = self.settings.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        tab_widget = QTabWidget(self)
        tab_widget.setTabBar(CustomTabBar(tab_widget))
        wlayout.addWidget(tab_widget)
        tab_widget.setTabsClosable(True)
        tab_widget.currentChanged.connect(self.tab_changed)
        tab_widget.tabCloseRequested.connect(self.close_tab)
        tab_widget.setMovable(True)
        tab_widget.setUsesScrollButtons(True)
        tab_position = self.settings.value("tab-bar-location", QTabWidget.TabPosition.North)
        assert isinstance(tab_position, QTabWidget.TabPosition)
        tab_widget.setTabPosition(tab_position)
        self.tab_widget = tab_widget

        # Apply custom tab styling
        self.update_colors()

        # Currently the copied part is stored internally, and is not made
        # available to the clipboard. We could do this by using pyperclip.
        self.copied_graph: Optional[GraphT] = None

        menu = self.menuBar()

        new_graph_action = self._new_action(
            "&New", self.new_graph, QKeySequence.StandardKey.New,
            "Create a new tab with an empty graph",
            alt_shortcut=QKeySequence.StandardKey.AddTab)
        new_window = self._new_action(
            "New &Window", self.open_new_window,
            QKeySequence("Ctrl+Shift+N"), "Open a new window")
        open_file = self._new_action(
            "&Open...", self.open_file, QKeySequence.StandardKey.Open,
            "Open a file-picker dialog to choose a new diagram")
        self.close_action = self._new_action(
            "Close", self.handle_close_action,
            QKeySequence.StandardKey.Close,
            "Closes the window", alt_shortcut=QKeySequence("Ctrl+W"))
        # TODO: We should remember if we have saved the diagram before,
        # and give an option to overwrite this file with a Save action.
        self.save_file = self._new_action(
            "&Save", self.handle_save_file_action,
            QKeySequence.StandardKey.Save,
            "Save the diagram by overwriting the previous loaded file.")
        self.save_as = self._new_action(
            "Save &as...", self.handle_save_as_action,
            QKeySequence.StandardKey.SaveAs,
            "Opens a file-picker dialog to save the diagram in a "
            "chosen file format")
        self.export_tikz_proof = self._new_action(
            "Export proof to tikz", self.handle_export_tikz_proof_action,
            None, "Exports the proof to tikz")
        self.export_gif_proof = self._new_action(
            "Export proof to gif", self.handle_export_gif_proof_action,
            None, "Exports the proof to gif")
        self.auto_save_action = self._new_action(
            "Auto Save", self.toggle_auto_save, None,
            "Automatically save the file after every edit"
        )
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setChecked(
            get_settings_value("auto-save", bool, False))

        file_menu = menu.addMenu("&File")
        file_menu.addAction(new_graph_action)
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

        self.undo_action = self._new_action(
            "Undo", self.undo, QKeySequence.StandardKey.Undo,
            "Undoes the last action", "undo.svg")
        self.redo_action = self._new_action(
            "Redo", self.redo, QKeySequence.StandardKey.Redo,
            "Redoes the last action", "redo.svg")
        self.cut_action = self._new_action(
            "Cut", self.cut_graph, QKeySequence.StandardKey.Cut,
            "Cut the selected part of the diagram")
        self.copy_action = self._new_action(
            "&Copy", self.copy_graph, QKeySequence.StandardKey.Copy,
            "Copy the selected part of the diagram")
        self.copy_clipboard_action = self._new_action(
            "Copy tikz to clipboard", self.copy_graph_to_clipboard,
            QKeySequence("Ctrl+Shift+C"),
            "Copy the selected part of the diagram to the clipboard "
            "as tikz")
        self.paste_action = self._new_action(
            "Paste", self.paste_graph, QKeySequence.StandardKey.Paste,
            "Paste the copied part of the diagram")
        self.paste_clipboard_action = self._new_action(
            "Paste tikz from clipboard", self.paste_graph_from_clipboard,
            QKeySequence("Ctrl+Shift+V"),
            "Paste a tikz diagram in the clipboard to ZXLive")
        self.delete_action = self._new_action(
            "Delete", self.delete_graph, QKeySequence.StandardKey.Delete,
            "Delete the selected part of the diagram",
            alt_shortcut=QKeySequence("Backspace"))
        self.select_all_action = self._new_action(
            "Select &All", self.select_all,
            QKeySequence.StandardKey.SelectAll, "Select all")
        self.deselect_all_action = self._new_action(
            "&Deselect All", self.deselect_all,
            QKeySequence.StandardKey.Deselect,
            "Deselect all", alt_shortcut=QKeySequence("Ctrl+D"))
        self.preferences_action = self._new_action(
            "&Preferences...", lambda: open_settings_dialog(self), None,
            "Open the preferences dialog")

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

        self.zoom_in_action = self._new_action(
            "Zoom in", self.zoom_in, QKeySequence.StandardKey.ZoomIn,
            "Zooms in by a fixed amount",
            alt_shortcut=QKeySequence("Ctrl+="))
        self.zoom_out_action = self._new_action(
            "Zoom out", self.zoom_out, QKeySequence.StandardKey.ZoomOut,
            "Zooms out by a fixed amount")
        self.fit_view_action = self._new_action(
            "Fit view", self.fit_view, QKeySequence("C"),
            "Fits the view to the diagram")

        view_menu = menu.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_view_action)

        new_rewrite_from_file = self._new_action(
            "New rewrite from file", lambda: create_new_rewrite(self),
            None, "New rewrite from file")
        new_rewrite_editor = self._new_action(
            "New rewrite", lambda: self.new_rule_editor(), None,
            "New rewrite")
        self.proof_as_rewrite_action = self._new_action(
            "Save proof as a rewrite", self.proof_as_lemma, None,
            "Save proof as a rewrite")
        rewrite_menu = menu.addMenu("&Rewrites")
        rewrite_menu.addAction(new_rewrite_editor)
        rewrite_menu.addAction(new_rewrite_from_file)
        rewrite_menu.addAction(self.proof_as_rewrite_action)

        user_guide = self._new_action(
            "&User Guide",
            lambda: QDesktopServices.openUrl(QUrl("https://zxlive.readthedocs.io/")),
            None, "Open ZXLive user guide")
        check_for_updates = self._new_action(
            "Check for &Updates...", self.check_for_updates, None,
            "Check for new versions of ZXLive")
        help_menu = menu.addMenu("&Help")
        help_menu.addAction(user_guide)
        help_menu.addAction(check_for_updates)

        menu.setStyleSheet("QMenu::item:disabled { color: gray }")
        self._reset_menus(False)

        self.effects = {e: load_sfx(e) for e in SFXEnum}

        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            self._toggle_sfx)

        # Set up periodic session state saving for crash protection
        # Auto-save session state every 3 minutes if there are open tabs
        self.session_save_timer = QTimer(self)
        self.session_save_timer.timeout.connect(self._save_session_state)
        self.session_save_timer.start(180000)  # 3 minutes in milliseconds

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

        # TODO: As an enhancement, cut, copy, delete, select all and
        # deselect all should start disabled even on a new tab, and
        # should only be enabled once anything is selected.

    def _new_action(
            self, name: str, trigger: Callable,
            shortcut: QKeySequence | QKeySequence.StandardKey | None,
            tooltip: str, icon_file: Optional[str] = None,
            alt_shortcut: Optional[QKeySequence | QKeySequence.StandardKey] = None
            ) -> QAction:
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
        # Save session state before closing tabs for potential restoration on next startup
        self._save_session_state()
        startup_behavior = get_settings_value("startup-behavior", str, "blank")
        if startup_behavior != "restore":
            # We close all the tabs and ask the user if they want to save progress
            while self.active_panel is not None:
                success = self.handle_close_action()
                if not success:
                    e.ignore()  # Abort the closing
                    return

        # save the shape/size of this window on close
        self.settings.setValue("main_window_geometry", self.saveGeometry())

        e.accept()

    def _save_session_state(self) -> None:
        """Save the current state of all open tabs for restoration on next startup."""
        # If there are no tabs open, clear any previously saved session state
        if self.tab_widget.count() == 0:
            self.settings.remove("session_state")
            return

        tabs_state = []
        for i in range(self.tab_widget.count()):
            panel = self.tab_widget.widget(i)
            tab_name = self.tab_widget.tabText(i)

            if isinstance(panel, GraphEditPanel):
                tab_data = {
                    'type': 'graph',
                    'name': tab_name,
                    'graph': panel.graph.to_json(),
                    'file_path': panel.file_path,
                    'file_type': panel.file_type.value if panel.file_type else None,
                }
            elif isinstance(panel, ProofPanel):
                tab_data = {
                    'type': 'proof',
                    'name': tab_name,
                    'proof': panel.proof_model.to_json(),
                    'file_path': panel.file_path,
                    'file_type': panel.file_type.value if panel.file_type else None,
                }
            elif isinstance(panel, RulePanel):
                rule = panel.get_rule()
                tab_data = {
                    'type': 'rule',
                    'name': tab_name,
                    'rule': rule.to_json(),
                    'file_path': panel.file_path,
                    'file_type': panel.file_type.value if panel.file_type else None,
                }
            elif isinstance(panel, PauliWebsPanel):
                # For Pauli webs, we just save the initial graph
                tab_data = {
                    'type': 'pauliwebs',
                    'name': tab_name,
                    'graph': panel.graph.to_json(),
                    'file_path': panel.file_path,
                    'file_type': panel.file_type.value if panel.file_type else None,
                }
            else:
                continue  # Unknown panel type, skip

            tabs_state.append(tab_data)

        # Save active tab index
        active_index = self.tab_widget.currentIndex()
        session_data = {
            'tabs': tabs_state,
            'active_tab': active_index
        }

        self.settings.setValue("session_state", json.dumps(session_data))

    def _restore_session_state(self) -> bool:
        """Restore previously saved tabs. Returns True if any tabs were restored."""
        # Check if user wants to restore session
        startup_behavior = get_settings_value("startup-behavior", str, "blank")
        if startup_behavior != "restore":
            return False

        session_json = self.settings.value("session_state")
        if not session_json:
            return False

        try:
            session_data = json.loads(session_json)
            tabs_state = session_data.get('tabs', [])
            active_tab = session_data.get('active_tab', 0)

            if not tabs_state:
                return False

            # Restore each tab
            for tab_data in tabs_state:
                tab_type = tab_data.get('type')
                tab_name = tab_data.get('name', 'Untitled')
                file_path = tab_data.get('file_path')
                file_type_value = tab_data.get('file_type')

                try:
                    if tab_type == 'graph':
                        graph: GraphT = BaseGraph.from_json(tab_data['graph'])  # type: ignore
                        self.new_graph(graph, tab_name)
                    elif tab_type == 'proof':
                        from .proof import ProofModel
                        proof_model = ProofModel.from_json(tab_data['proof'])
                        # Extract the initial graph from the proof
                        graphs_list = proof_model.graphs()
                        initial_graph: GraphT = graphs_list[0] if graphs_list else new_graph()
                        panel = ProofPanel(initial_graph, self.undo_action, self.redo_action)
                        # Replace the proof model with the loaded one
                        panel.step_view.set_model(proof_model)
                        panel.start_pauliwebs_signal.connect(self.new_pauli_webs)
                        self._new_panel(panel, tab_name)
                    elif tab_type == 'rule':
                        rule = CustomRule.from_json(tab_data['rule'])
                        self.new_rule_editor(rule, tab_name)
                    elif tab_type == 'pauliwebs':
                        pauli_graph: GraphT = BaseGraph.from_json(tab_data['graph'])  # type: ignore
                        self.new_pauli_webs(pauli_graph, tab_name)

                    # Restore file path and file type if available
                    if file_path and self.active_panel:
                        self.active_panel.file_path = file_path
                        if file_type_value:
                            # Find the FileFormat enum by its value
                            for fmt in FileFormat:
                                if fmt.value == file_type_value:
                                    self.active_panel.file_type = fmt
                                    break
                except Exception as e:
                    # If a tab fails to restore, log it but continue with others
                    logging.warning(f"Failed to restore tab '{tab_name}': {e}")
                    continue

            # Restore active tab
            if 0 <= active_tab < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(active_tab)

            return True
        except Exception as e:
            logging.error(f"Failed to restore session state: {e}")
            return False

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

    def update_tab_name(self, clean: bool) -> None:
        i = self.tab_widget.currentIndex()
        name = self.tab_widget.tabText(i)
        if name.endswith("*"):
            name = name[:-1]
        if not clean:
            name += "*"
        self.tab_widget.setTabText(i, name)

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

    def _open_file_from_output(
            self, out: ImportGraphOutput | ImportProofOutput | ImportRuleOutput
            ) -> None:
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
        if i == -1:  # no tabs open, close the app
            self.close()
        return self.close_tab(i)

    def close_tab(self, i: int) -> bool:
        if i == -1:
            return False
        widget = self.tab_widget.widget(i)
        assert isinstance(widget, BasePanel)
        if not widget.undo_stack.isClean():
            name = self.tab_widget.tabText(i).replace("*", "")
            button = QMessageBox.StandardButton
            answer = QMessageBox.question(
                self, "Save Changes",
                f"Do you wish to save your changes to {name} before closing?",
                button.Yes | button.No | button.Cancel)  # type: ignore
            if answer == button.Cancel:
                return False
            if answer == button.Yes:
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
            show_error_msg(
                "Can't save to circuit file",
                "You imported this file from a circuit description. "
                "You can currently only save it in a graph format.",
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
        if out is None:
            return False
        file_path, file_type = out
        self.active_panel.file_path = file_path
        self.active_panel.file_type = file_type
        self.active_panel.undo_stack.setClean()
        name = QFileInfo(file_path).baseName()
        i = self.tab_widget.currentIndex()
        self.tab_widget.setTabText(i, name)
        return True

    def handle_export_tikz_proof_action(self) -> bool:
        assert isinstance(self.active_panel, ProofPanel)
        path = export_proof_dialog(self)
        if path is None:
            show_error_msg("Export failed", "Invalid path", parent=self)
            return False
        with open(path, "w", encoding="utf-8") as f:
            f.write(proof_to_tikz(self.active_panel.proof_model))
        return True

    def handle_export_gif_proof_action(self) -> bool:
        assert isinstance(self.active_panel, ProofPanel)
        path = export_gif_dialog(self)
        if path is None:
            show_error_msg("Export failed", "Invalid path", parent=self)
            return False
        graphs: list[BaseGraph] = list(self.active_panel.proof_model.graphs())
        graphs_to_gif(graphs, path, 1000)  # 1000ms per frame
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
        """Copies the selected graph to the clipboard as a tikz string
        that can be understood by Tikzit."""
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
        if (panel and getattr(panel, 'file_path', None) and
                get_settings_value("auto-save", bool, False)):
            self.handle_save_file_action()

    def new_graph(self, graph: Optional[GraphT] = None, name: Optional[str] = None) -> None:
        _graph = graph or new_graph()
        panel = GraphEditPanel(_graph, self.undo_action, self.redo_action)
        panel.start_derivation_signal.connect(self.new_deriv)
        panel.start_pauliwebs_signal.connect(self.new_pauli_webs)
        if name is None:
            name = "New Graph"
        self._new_panel(panel, name)

    def open_graph_from_notebook(self, graph: GraphT, name: str) -> None:
        """Opens a ZXLive window from within a Jupyter notebook to
        edit a graph.

        Replaces the graph in an existing tab if it has the same name."""

        # The graph we are given is not a MultiGraph
        if not isinstance(graph, GraphT):
            graph = graph.copy(backend='multigraph')
            graph.set_auto_simplify(False)

        # TODO: handle multiple tabs with the same name somehow
        for i in range(self.tab_widget.count()):
            tab_text = self.tab_widget.tabText(i)
            if tab_text == name or tab_text == name + "*":
                self.tab_widget.setCurrentIndex(i)
                assert self.active_panel is not None
                self.active_panel.replace_graph(graph)
                return
        self.new_graph(copy.deepcopy(graph), name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        # TODO: handle multiple tabs with the same name somehow
        for i in range(self.tab_widget.count()):
            tab_text = self.tab_widget.tabText(i)
            if tab_text == name or tab_text == name + "*":
                panel = cast(BasePanel, self.tab_widget.widget(i))
                return cast(GraphT, copy.deepcopy(panel.graph_scene.g))
        return None

    def new_rule_editor(self, rule: Optional[CustomRule] = None,
                        name: Optional[str] = None) -> None:
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
        panel = RulePanel(
            graph1, graph2, rule_name, rule_description,
            self.undo_action, self.redo_action)
        if name is None:
            name = "New Rule"
        self._new_panel(panel, name)

    def new_deriv(self, graph: GraphT, name: Optional[str] = None) -> None:
        panel = ProofPanel(graph, self.undo_action, self.redo_action)
        if name is None:
            name = "New Proof"
        panel.start_pauliwebs_signal.connect(self.new_pauli_webs)
        self._new_panel(panel, name)

    def new_pauli_webs(self, graph: GraphT, name: Optional[str] = None) -> None:
        panel = PauliWebsPanel(graph, self.undo_action, self.redo_action)
        if name is None:
            name = "New Pauli Webs"
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
        """Update app theme using reliable Qt native methods
        (no hardcoded colors)."""

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return

        # Get the path to the close icon
        close_icon_path = get_data("icons/tab-close.svg").replace("\\", "/")

        # Use system color keywords instead of hardcoded colors
        # These automatically adapt to light/dark themes
        stylesheet = f"""
            /* Use palette() colors - Qt provides correct ones automatically */
            CustomTabBar::tab {{
                color: palette(text);
                background: palette(button);
                border: 1px solid palette(mid);
                border-bottom: none;
                padding: 10px 24px;
                margin-right: 2px;
                min-width: 100px;
                max-width: 200px;
            }}

            CustomTabBar::tab:selected {{
                color: palette(ButtonText);
                background: palette(light);
                border-color: palette(midlight);
            }}

            CustomTabBar::tab:!selected {{
                background: palette(mid);
                margin-top: 2px;
            }}

            CustomTabBar::tab:hover {{
                background: palette(midlight);
            }}

            CustomTabBar::close-button {{
                subcontrol-position: right;
                image: url({close_icon_path});
                background: palette(mid);
                border-radius: 5px;
                width: 28px;
                height: 28px;
                padding: 2px;
            }}

            CustomTabBar::close-button:hover {{
                background: palette(dark);
            }}

            /* Let Qt handle all other widget colors automatically */
        """

        app.setStyleSheet(stylesheet)
        if self.active_panel is not None:
            self.active_panel.update_colors()

    @property
    def sfx_on(self) -> bool:
        return get_settings_value("sound-effects", bool, False, self.settings)

    @sfx_on.setter
    def sfx_on(self, value: bool) -> None:
        set_settings_value("sound-effects", value, bool, self.settings)

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

    def check_for_updates(self) -> None:
        """Manually check for updates."""
        from .dialogs import show_update_available_dialog
        from .app import ZXLive

        app = QApplication.instance()
        if not app or not hasattr(app, 'update_checker'):
            return
        zx_app = cast(ZXLive, app)

        checking_msg = QMessageBox(self)
        checking_msg.setWindowTitle("Checking for Updates")
        checking_msg.setText("Checking for updates...")
        checking_msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        checking_msg.setModal(False)
        checking_msg.show()
        QApplication.processEvents()

        # Temporarily disconnect app-level handler to prevent double dialogs.
        # We assume it's connected (it should be from app startup)
        zx_app.update_checker.update_available.disconnect(zx_app.on_update_available)
        update_found = False

        def on_update_available(latest_version: str, url: str) -> None:
            nonlocal update_found
            update_found = True
            checking_msg.accept()
            show_update_available_dialog(
                zx_app.applicationVersion(), latest_version, url, self)

        def on_check_complete() -> None:
            checking_msg.accept()
            # Disconnect our temporary connections and reconnect the app-level one
            zx_app.update_checker.update_available.disconnect(on_update_available)
            zx_app.update_checker.check_complete.disconnect(on_check_complete)
            zx_app.update_checker.update_available.connect(zx_app.on_update_available)
            if not update_found:
                QMessageBox.information(self, "No Updates", "You are using the latest version of ZXLive!")

        zx_app.update_checker.update_available.connect(on_update_available)
        zx_app.update_checker.check_complete.connect(on_check_complete)
        zx_app.update_checker.check_for_updates_async()


class CustomTabBar(QTabBar):
    """Custom tab bar that shows close buttons only on hover."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.hovered_tab: int = -1
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Track which tab is being hovered."""
        super().mouseMoveEvent(event)
        # Get the tab index at the mouse position
        pos = event.pos()
        tab_index = self.tabAt(pos)
        if tab_index != self.hovered_tab:
            self.hovered_tab = tab_index
            self._update_close_buttons()

    def leaveEvent(self, event: QEvent) -> None:
        """Clear hover state when mouse leaves."""
        super().leaveEvent(event)
        self.hovered_tab = -1
        self._update_close_buttons()

    def _update_close_buttons(self) -> None:
        """Update visibility of close buttons based on hover state."""
        for i in range(self.count()):
            button = self.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if button:
                # Show button only for hovered tab
                button.setVisible(i == self.hovered_tab)
