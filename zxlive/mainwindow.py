# zxlive - An interactive tool for the ZX-calculus
# Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import copy
import json
import logging
import os
import random
from typing import TYPE_CHECKING, Callable, Optional, cast

import networkx as nx
import pyperclip
from PySide6.QtCore import (QByteArray, QEvent, QFile, QFileInfo, QIODevice,
                            QMimeData, QSettings, QTextStream, QTimer, QUrl,
                            Qt)
from PySide6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                           QKeySequence, QMouseEvent, QShortcut)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QMessageBox, QTabBar, QTabWidget,
                               QVBoxLayout, QWidget)
from pyzx.drawing import graphs_to_gif
from pyzx.graph.base import BaseGraph
from pyzx.utils import VertexType

from .base_panel import BasePanel
from .common import (VT, GraphT, from_tikz, get_custom_rules_path, get_data,
                     get_settings_value, new_graph, set_settings_value, to_tikz)
# Use construct_three_cnots as the startup demo — it is the most pedagogically
# relevant built-in example (3 CNOTs = SWAP) and ties into the tutorial.
from .construct import construct_three_cnots
from .commands import MoveNode, ProofModeCommand
from .custom_rule import CustomRule, check_rule, to_networkx
from .dialogs import (FileFormat, ImportGraphOutput, ImportProofOutput,
                      ImportRuleOutput, create_new_rewrite, export_gif_dialog,
                      export_proof_dialog, get_lemma_name_and_description,
                      import_diagram_dialog, import_diagram_from_file,
                      save_diagram_dialog, save_proof_dialog, save_rule_dialog,
                      show_error_msg, write_to_file)
from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .pauliwebs_panel import PauliWebsPanel
from .rule_panel import RulePanel
from .settings import display_setting
from .settings_dialog import open_settings_dialog
from .sfx import SFXEnum, load_sfx
from .tikz import proof_to_tikz, proof_steps_to_tikz

if TYPE_CHECKING:
    from .tutorial import Tutorial


class MainWindow(QMainWindow):
    """The main window of the ZXLive application."""

    CLIPBOARD_MIME = "application/vnd.zxlive-graph+json"

    # The currently running onboarding tutorial, if any (see zxlive.tutorial).
    _active_tutorial: Optional["Tutorial"] = None

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("zxlive", "zxlive")
        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        wlayout = w.layout()
        assert wlayout is not None
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(0)
        self.resize(1200, 800)

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
        tab_position = self.settings.value(
            "tab-bar-location", QTabWidget.TabPosition.North)
        assert isinstance(tab_position, QTabWidget.TabPosition)
        tab_widget.setTabPosition(tab_position)
        self.tab_widget = tab_widget
        self.update_colors()

        self.copied_graph: Optional[GraphT] = None

        menu = self.menuBar()

        # ── File menu ──────────────────────────────────────────────────────
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
        self.save_file = self._new_action(
            "&Save", self.handle_save_file_action,
            QKeySequence.StandardKey.Save,
            "Save the diagram by overwriting the previously loaded file.")
        self.save_as = self._new_action(
            "Save &as...", self.handle_save_as_action,
            QKeySequence.StandardKey.SaveAs,
            "Opens a file-picker dialog to save the diagram in a chosen format")
        self.export_tikz_proof = self._new_action(
            "Export proof to tikz", self.handle_export_tikz_proof_action,
            None, "Exports the proof to tikz")
        self.export_gif_proof = self._new_action(
            "Export proof to gif", self.handle_export_gif_proof_action,
            None, "Exports the proof to gif")
        self.export_tikz_series = self._new_action(
            "Export proof steps to tikz files",
            self.handle_export_tikz_series_action,
            None, "Exports each proof step to a separate tikz file")
        self.auto_save_action = self._new_action(
            "Auto Save", self.toggle_auto_save, None,
            "Automatically save the file after every edit")
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
        file_menu.addAction(self.export_tikz_series)
        file_menu.addAction(self.export_gif_proof)
        file_menu.addSeparator()
        file_menu.addAction(self.auto_save_action)

        # ── Edit menu ──────────────────────────────────────────────────────
        def native_shortcut(key: QKeySequence.StandardKey) -> str:
            return QKeySequence(key).toString(
                QKeySequence.SequenceFormat.NativeText)

        self.undo_action = self._new_action(
            "Undo", self.undo, QKeySequence.StandardKey.Undo,
            f"Undo ({native_shortcut(QKeySequence.StandardKey.Undo)})",
            "undo.svg")
        self.redo_action = self._new_action(
            "Redo", self.redo, QKeySequence.StandardKey.Redo,
            f"Redo ({native_shortcut(QKeySequence.StandardKey.Redo)})",
            "redo.svg")
        self.cut_action = self._new_action(
            "Cut", self.cut_graph, QKeySequence.StandardKey.Cut,
            f"Cut ({native_shortcut(QKeySequence.StandardKey.Cut)})")
        self.copy_action = self._new_action(
            "&Copy", self.copy_graph, QKeySequence.StandardKey.Copy,
            f"Copy ({native_shortcut(QKeySequence.StandardKey.Copy)})")
        self.copy_clipboard_action = self._new_action(
            "Copy tikz to clipboard", self.copy_graph_to_clipboard,
            QKeySequence("Ctrl+Shift+C"),
            "Copy the selected part of the diagram to the clipboard as tikz")
        self.paste_action = self._new_action(
            "Paste", self.paste_graph, QKeySequence.StandardKey.Paste,
            f"Paste ({native_shortcut(QKeySequence.StandardKey.Paste)})")
        self.paste_clipboard_action = self._new_action(
            "Paste tikz from clipboard", self.paste_graph_from_clipboard,
            QKeySequence("Ctrl+Shift+V"),
            "Paste a tikz diagram from the clipboard to ZXLive")
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

        # ── View menu ──────────────────────────────────────────────────────
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
        self.auto_arrange_action = self._new_action(
            "Auto arrange", self.auto_arrange, QKeySequence("Ctrl+L"),
            "Automatically arrange vertices using spring layout")

        view_menu = menu.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_view_action)
        view_menu.addAction(self.auto_arrange_action)

        # ── Rewrites menu ──────────────────────────────────────────────────
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

        # ── Help menu (tutorial entry points) ─────────────────────────────
        user_guide = self._new_action(
            "&User Guide",
            lambda: QDesktopServices.openUrl(
                QUrl("https://zxlive.readthedocs.io/")),
            None, "Open ZXLive user guide")
        check_for_updates = self._new_action(
            "Check for &Updates...", self.check_for_updates, None,
            "Check for new versions of ZXLive")

        # ── Tutorial sub-menu — all entry points ───────────────────────
        # Orientation tours
        quick_tour_action  = self._new_action(
            "&Quick Tour",
            lambda: self.start_tutorial(quick=True), None,
            "Short functional orientation (no ZX theory) — ideal for returning users")
        editor_tour_action = self._new_action(
            "&Full Editor Tour",
            lambda: self.start_tutorial(), None,
            "Guided tour of the editor including ZX-calculus explanations")
        self.proof_tour_action = self._new_action(
            "&Proof Mode Tour",
            lambda: self.start_proof_tutorial(), None,
            "Guided tour of proof mode (only available when a proof tab is active)")

        # Interactive lessons
        learn_basics_action   = self._new_action(
            "&Learn the Basics — 3 CNOTs = SWAP",
            lambda: self.start_learn_basics_tutorial(), None,
            "Hands-on lesson: rewrite 3 CNOTs to a SWAP using spider fusion, "
            "bialgebra and identity removal")
        zz_gadget_action      = self._new_action(
            "&ZZ Phase Gadget",
            lambda: self.start_zz_gadget_tutorial(), None,
            "Explore the ZZ(α) phase gadget: colour-change rule and "
            "applications to QAOA / VQE circuits")
        graph_state_action    = self._new_action(
            "&Graph States and MBQC",
            lambda: self.start_graph_state_tutorial(), None,
            "Three-qubit cluster state: MBQC measurement patterns via "
            "spider fusion and colour change")
        teleportation_action  = self._new_action(
            "&Quantum Teleportation",
            lambda: self.start_teleportation_tutorial(), None,
            "Prove quantum state teleportation using the ZX yanking identity")

        help_menu = menu.addMenu("&Help")
        help_menu.addAction(user_guide)

        tutorial_menu = help_menu.addMenu("&Interactive Tutorial")

        # Orientation sub-group
        tour_menu = tutorial_menu.addMenu("&Orientation Tours")
        tour_menu.addAction(quick_tour_action)
        tour_menu.addAction(editor_tour_action)
        tour_menu.addAction(self.proof_tour_action)

        # Interactive lessons sub-group
        tutorial_menu.addSeparator()
        lessons_menu = tutorial_menu.addMenu("&Interactive Lessons")
        lessons_menu.addAction(learn_basics_action)
        lessons_menu.addAction(zz_gadget_action)
        lessons_menu.addAction(graph_state_action)
        lessons_menu.addAction(teleportation_action)

        help_menu.addAction(check_for_updates)

        menu.setStyleSheet("QMenu::item:disabled { color: gray }")
        self._reset_menus(False)

        self.effects = {e: load_sfx(e) for e in SFXEnum}

        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            self._toggle_sfx)
        QApplication.clipboard().dataChanged.connect(
            self._on_clipboard_changed)

        # Periodic session-state saving for crash protection.
        self.session_save_timer = QTimer(self)
        self.session_save_timer.timeout.connect(self._save_session_state)
        self.session_save_timer.start(60_000)   # every 60 seconds

    # ── Demo graph ────────────────────────────────────────────────────────

    def open_demo_graph(self) -> None:
        """Open the startup demo graph.

        We use the 3-CNOT circuit because it is a meaningful, well-known
        ZX-calculus example (it simplifies to a SWAP) and it ties directly
        into the "Learn the Basics" interactive tutorial.
        """
        self.new_graph(construct_three_cnots(), "3 CNOTs")

    # ── Menu state ────────────────────────────────────────────────────────

    def _reset_menus(self, has_active_tab: bool) -> None:
        is_saveable = (has_active_tab
                       and not isinstance(self.active_panel, PauliWebsPanel))
        self.save_file.setEnabled(is_saveable)
        self.save_as.setEnabled(is_saveable)
        self.cut_action.setEnabled(has_active_tab)
        self.copy_action.setEnabled(has_active_tab)
        self.delete_action.setEnabled(has_active_tab)
        self.select_all_action.setEnabled(has_active_tab)
        self.deselect_all_action.setEnabled(has_active_tab)
        self.zoom_in_action.setEnabled(has_active_tab)
        self.zoom_out_action.setEnabled(has_active_tab)
        self.fit_view_action.setEnabled(has_active_tab)
        self.auto_arrange_action.setEnabled(has_active_tab)
        self.export_tikz_proof.setEnabled(
            has_active_tab and isinstance(self.active_panel, ProofPanel))
        self.export_tikz_series.setEnabled(
            has_active_tab and isinstance(self.active_panel, ProofPanel))
        self.export_gif_proof.setEnabled(
            has_active_tab and isinstance(self.active_panel, ProofPanel))
        # The proof-mode tour is only meaningful when a proof tab is active.
        self.proof_tour_action.setEnabled(
            has_active_tab and isinstance(self.active_panel, ProofPanel))
        self.paste_action.setEnabled(
            has_active_tab and self._has_pasteable_clipboard_data())
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

    def _new_action(
            self,
            name: str,
            trigger: Callable,
            shortcut: QKeySequence | QKeySequence.StandardKey | None,
            tooltip: str,
            icon_file: Optional[str] = None,
            alt_shortcut: Optional[
                QKeySequence | QKeySequence.StandardKey] = None,
    ) -> QAction:
        action = QAction(name, self)
        if icon_file:
            action.setIcon(QIcon(get_data(f"icons/{icon_file}")))
        action.setToolTip(tooltip)
        action.triggered.connect(trigger)
        if shortcut:
            action.setShortcut(shortcut)
            if alt_shortcut and alt_shortcut not in action.shortcuts():
                action.setShortcuts(
                    [shortcut, alt_shortcut])   # type: ignore[arg-type]
        return action

    def _has_pasteable_clipboard_data(self) -> bool:
        if self.copied_graph is not None:
            return True
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return False
        if mime.hasFormat(self.CLIPBOARD_MIME):
            return True
        return bool(mime.text().strip())

    def _on_clipboard_changed(self) -> None:
        self.paste_action.setEnabled(
            self.active_panel is not None
            and self._has_pasteable_clipboard_data())

    @property
    def active_panel(self) -> Optional[BasePanel]:
        current = self.tab_widget.currentWidget()
        if current is not None:
            assert isinstance(current, BasePanel)
            return current
        return None

    # ── Window lifecycle ──────────────────────────────────────────────────

    def open_new_window(self) -> None:
        new_window = MainWindow()
        new_window.new_graph()
        new_window.show()

    def closeEvent(self, e: QCloseEvent) -> None:
        self._save_session_state()
        startup_behavior = get_settings_value(
            "startup-behavior", str, "restore")
        if startup_behavior != "restore":
            while self.active_panel is not None:
                success = self.handle_close_action()
                if not success:
                    e.ignore()
                    return
        self.settings.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    # ── Session state ─────────────────────────────────────────────────────

    def _save_session_state(self) -> None:
        """Persist all open tabs so they can be restored on the next launch."""
        try:
            if self.tab_widget.count() == 0:
                self.settings.remove("session_state")
                return

            tabs_state = []
            for i in range(self.tab_widget.count()):
                panel = self.tab_widget.widget(i)
                assert isinstance(panel, BasePanel)
                tab_data: dict = {
                    "name":      self.tab_widget.tabText(i),
                    "file_path": panel.file_path,
                    "file_type": (panel.file_type.value
                                  if panel.file_type else None),
                }
                if isinstance(panel, GraphEditPanel):
                    tab_data.update(
                        {"type": "graph", "data": panel.graph.to_json()})
                elif isinstance(panel, ProofPanel):
                    tab_data.update(
                        {"type": "proof",
                         "data": panel.proof_model.to_json()})
                elif isinstance(panel, RulePanel):
                    tab_data.update(
                        {"type": "rule",
                         "data": panel.get_rule().to_json()})
                elif isinstance(panel, PauliWebsPanel):
                    tab_data.update(
                        {"type": "pauliwebs",
                         "data": panel.graph.to_json()})
                else:
                    continue
                tabs_state.append(tab_data)

            session_data = {
                "tabs":       tabs_state,
                "active_tab": self.tab_widget.currentIndex(),
            }
            self.settings.setValue(
                "session_state", json.dumps(session_data))
        except Exception as exc:
            logging.warning("Failed to save session state: %s", exc)

    def _restore_session_state(self) -> bool:   # noqa: PLR0912
        """Restore previously saved tabs.  Returns True if any were restored."""
        if get_settings_value(
                "startup-behavior", str, "restore") != "restore":
            return False
        session_json = self.settings.value("session_state")
        if not session_json:
            return False
        try:
            session_data = json.loads(str(session_json))
            tabs_state   = session_data.get("tabs", [])
            active_tab   = session_data.get("active_tab", 0)
            if not tabs_state:
                return False

            for tab_data in tabs_state:
                tab_type      = tab_data.get("type")
                tab_name      = tab_data.get("name", "Untitled")
                file_path     = tab_data.get("file_path")
                file_type_val = tab_data.get("file_type")
                try:
                    if tab_type == "graph":
                        graph: GraphT = BaseGraph.from_json(
                            tab_data["data"])   # type: ignore
                        self.new_graph(graph, tab_name)
                    elif tab_type == "proof":
                        from .proof import ProofModel
                        proof_model   = ProofModel.from_json(tab_data["data"])
                        graphs_list   = proof_model.graphs()
                        initial_graph: GraphT = (graphs_list[0]
                                                 if graphs_list
                                                 else new_graph())
                        panel = ProofPanel(
                            initial_graph,
                            self.undo_action, self.redo_action)
                        panel.step_view.set_model(proof_model)
                        panel.step_view.move_to_step(
                            len(proof_model.steps))
                        panel.start_pauliwebs_signal.connect(
                            self.new_pauli_webs)
                        self._new_panel(panel, tab_name)
                    elif tab_type == "rule":
                        from .custom_rule import CustomRule
                        rule = CustomRule.from_json(tab_data["data"])
                        self.new_rule_editor(rule, tab_name)
                    elif tab_type == "pauliwebs":
                        graph = BaseGraph.from_json(
                            tab_data["data"])   # type: ignore
                        self.new_pauli_webs(
                            graph, tab_name)   # type: ignore
                    else:
                        continue

                    panel_ref = self.active_panel
                    if panel_ref is not None and file_path:
                        panel_ref.file_path = file_path
                        if file_type_val is not None:
                            try:
                                panel_ref.file_type = FileFormat(file_type_val)
                            except ValueError:
                                pass
                except Exception as exc:
                    logging.warning(
                        "Failed to restore tab %r: %s", tab_name, exc)

            if 0 <= active_tab < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(active_tab)
            return self.tab_widget.count() > 0

        except Exception as exc:
            logging.warning("Failed to restore session state: %s", exc)
            return False

    # ── Tab management ────────────────────────────────────────────────────

    def update_tab_name(self, clean: bool) -> None:
        if isinstance(self.active_panel, PauliWebsPanel):
            return
        i    = self.tab_widget.currentIndex()
        name = self.tab_widget.tabText(i).lstrip("*")
        if not clean:
            name = "*" + name
        self.tab_widget.setTabText(i, name)
        self.tab_widget.setTabToolTip(i, name)

    def tab_changed(self, i: int) -> None:
        self.proof_as_rewrite_action.setEnabled(
            isinstance(self.active_panel, ProofPanel))
        self._undo_changed()
        self._redo_changed()
        if self.active_panel:
            self.active_panel.update_colors()
            self._reset_menus(True)
            self.active_panel.set_splitter_size()

    def _undo_changed(self) -> None:
        if self.active_panel:
            self.undo_action.setEnabled(
                self.active_panel.undo_stack.canUndo())

    def _redo_changed(self) -> None:
        if self.active_panel:
            self.redo_action.setEnabled(
                self.active_panel.undo_stack.canRedo())

    # ── File operations ───────────────────────────────────────────────────

    def open_file(self) -> None:
        out = import_diagram_dialog(self)
        if out is not None:
            self._open_file_from_output(out)

    def open_file_from_path(self, file_path: str) -> None:
        out = import_diagram_from_file(file_path, parent=self)
        if out is not None:
            self._open_file_from_output(out)

    def _open_file_from_output(
            self,
            out: ImportGraphOutput | ImportProofOutput | ImportRuleOutput,
    ) -> None:
        name = QFileInfo(out.file_path).baseName()
        if isinstance(out, ImportGraphOutput):
            self.new_graph(out.g, name)
        elif isinstance(out, ImportProofOutput):
            graph = out.p.graphs()[-1]
            self.new_deriv(graph, name)
            assert isinstance(self.active_panel, ProofPanel)
            self.active_panel.step_view.set_model(out.p)
        elif isinstance(out, ImportRuleOutput):
            self.new_rule_editor(out.r, name)
        else:
            raise TypeError("Unknown import type", out)
        assert self.active_panel is not None
        self.active_panel.file_path = out.file_path
        self.active_panel.file_type = out.file_type

    def handle_close_action(self) -> bool:
        i = self.tab_widget.currentIndex()
        if i == -1:
            self.close()
        return self.close_tab(i)

    def close_tab(self, i: int) -> bool:
        if i == -1:
            return False
        widget = self.tab_widget.widget(i)
        assert isinstance(widget, BasePanel)
        if not isinstance(widget, PauliWebsPanel) and (
                not widget.undo_stack.isClean()
                or widget.file_path is None):
            name   = self.tab_widget.tabText(i).replace("*", "")
            button = QMessageBox.StandardButton
            answer = QMessageBox.question(
                self, "Save Changes",
                f"Do you wish to save your changes to {name} before closing?",
                button.Yes | button.No | button.Cancel)  # type: ignore[operator]
            if answer == button.Cancel:
                return False
            if answer == button.Yes:
                self.tab_widget.setCurrentIndex(i)
                if not self.handle_save_file_action():
                    return False
        widget.graph_scene.clearSelection()
        self.tab_widget.removeTab(i)
        self._reset_menus(self.tab_widget.count() > 0)
        return True

    def handle_save_file_action(self) -> bool:
        assert self.active_panel is not None
        if isinstance(self.active_panel, PauliWebsPanel):
            return False
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
            except Exception as exc:
                show_error_msg("Warning!", str(exc), parent=self)
            data = self.active_panel.get_rule().to_json()
        elif self.active_panel.file_type in (
                FileFormat.QGraph, FileFormat.Json):
            data = self.active_panel.graph.to_json()
        elif self.active_panel.file_type == FileFormat.TikZ:
            data = self.active_panel.graph.to_tikz()
        else:
            raise TypeError("Unknown file format", self.active_panel.file_type)

        file = QFile(self.active_panel.file_path)
        if not file.open(
                QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
            show_error_msg("Could not write to file", parent=self)
            return False
        QTextStream(file) << data
        file.close()
        self.active_panel.undo_stack.setClean()
        if random.random() < 0.1:
            self.play_sound(SFXEnum.IRANIAN_BUS)
        return True

    def handle_save_as_action(self) -> bool:
        assert self.active_panel is not None
        if isinstance(self.active_panel, PauliWebsPanel):
            return False
        if isinstance(self.active_panel, ProofPanel):
            out = save_proof_dialog(self.active_panel.proof_model, self)
        elif isinstance(self.active_panel, RulePanel):
            try:
                check_rule(self.active_panel.get_rule())
            except Exception as exc:
                show_error_msg("Warning!", str(exc), parent=self)
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
        self.tab_widget.setTabToolTip(i, name)
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
        graphs: list[BaseGraph] = list(
            self.active_panel.proof_model.graphs())
        graphs_to_gif(graphs, path, 1000)
        return True

    def handle_export_tikz_series_action(self) -> bool:
        """Export each proof step to a separate TikZ file in a chosen directory."""
        assert isinstance(self.active_panel, ProofPanel)
        directory = QFileDialog.getExistingDirectory(
            self, "Select folder for TikZ files",
            options=QFileDialog.Option.ShowDirsOnly)
        if not directory:
            return False

        steps     = proof_steps_to_tikz(self.active_panel.proof_model)
        pad_width = max(3, len(str(max(len(steps) - 1, 0))))
        for i, (name, tikz) in enumerate(steps):
            safe_name = "".join(
                c if c.isalnum() or c in "._-" else "_" for c in name)
            file_path = os.path.join(
                directory, f"{i:0{pad_width}d}_{safe_name}.tikz")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(tikz)
            except OSError as exc:
                show_error_msg(
                    "Export failed",
                    f"Could not write to {file_path}: {exc}",
                    parent=self)
                return False
        return True

    # ── Clipboard ─────────────────────────────────────────────────────────

    def cut_graph(self) -> None:
        assert self.active_panel is not None
        self.copied_graph = self.active_panel.copy_selection()
        self._copy_graph_to_system_clipboard(self.copied_graph)
        self.paste_action.setEnabled(True)
        self.active_panel.delete_selection()

    def copy_graph(self) -> None:
        assert self.active_panel is not None
        self.copied_graph = self.active_panel.copy_selection()
        self._copy_graph_to_system_clipboard(self.copied_graph)
        self.paste_action.setEnabled(True)

    def copy_graph_to_clipboard(self) -> None:
        assert self.active_panel is not None
        self._copy_graph_to_system_clipboard(
            self.active_panel.copy_selection(), include_internal=False)

    def paste_graph(self) -> None:
        assert self.active_panel is not None
        copied = self._read_graph_from_system_clipboard()
        if copied is None:
            copied = self.copied_graph
        if copied is not None:
            self.active_panel.paste_graph(copied)

    def paste_graph_from_clipboard(self) -> None:
        assert self.active_panel is not None
        copied = self._read_graph_from_system_clipboard(
            include_internal=False)
        if copied is not None:
            self.active_panel.paste_graph(copied)

    def _copy_graph_to_system_clipboard(
            self, graph: GraphT, include_internal: bool = True) -> None:
        mime = QMimeData()
        mime.setText(to_tikz(graph))
        if include_internal:
            payload = json.dumps(
                {"graph_json": graph.to_json()}).encode("utf-8")
            mime.setData(self.CLIPBOARD_MIME, QByteArray(payload))
        QApplication.clipboard().setMimeData(mime)

    def _read_graph_from_system_clipboard(
            self, include_internal: bool = True) -> Optional[GraphT]:
        mime = QApplication.clipboard().mimeData()
        if (include_internal
                and mime is not None
                and mime.hasFormat(self.CLIPBOARD_MIME)):
            try:
                raw     = bytes(mime.data(self.CLIPBOARD_MIME).data())
                payload = json.loads(raw.decode("utf-8"))
                graph_json = payload.get("graph_json")
                if isinstance(graph_json, str):
                    g: GraphT = GraphT.from_json(
                        graph_json)     # type: ignore[misc]
                    g.rebind_variables_to_registry()
                    g.set_auto_simplify(False)
                    return g
            except Exception:
                pass

        tikz = QApplication.clipboard().text() or pyperclip.paste()
        if not tikz:
            return None
        try:
            return from_tikz(tikz)
        except Exception as exc:
            from .common import find_unknown_tikz_styles
            unknown = find_unknown_tikz_styles(tikz)
            detail  = str(exc)
            if unknown:
                detail += "\n\nUnknown styles: " + ", ".join(unknown)
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("TikZ import error")
            msg.setInformativeText(detail)
            retry_btn = msg.addButton("Retry ignoring errors",
                                      QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()
            if msg.clickedButton() != retry_btn:
                return None
        try:
            return from_tikz(tikz, ignore_errors=True)
        except Exception as exc:
            show_error_msg("TikZ import error",
                           f"Error while importing TikZ: {exc}", parent=self)
            return None

    def delete_graph(self) -> None:
        assert self.active_panel is not None
        self.active_panel.delete_selection()

    # ── Panel factory helpers ─────────────────────────────────────────────

    def _new_panel(self, panel: BasePanel, name: str) -> None:
        idx = self.tab_widget.addTab(panel, name)
        self.tab_widget.setTabToolTip(idx, name)
        self.tab_widget.setCurrentWidget(panel)
        self._reset_menus(True)
        panel.undo_stack.cleanChanged.connect(self.update_tab_name)
        panel.undo_stack.canUndoChanged.connect(self._undo_changed)
        panel.undo_stack.canRedoChanged.connect(self._redo_changed)
        panel.play_sound_signal.connect(self.play_sound)
        panel.undo_stack.indexChanged.connect(self._auto_save_if_needed)

    def _auto_save_if_needed(self) -> None:
        panel = self.active_panel
        if (panel
                and not isinstance(panel, PauliWebsPanel)
                and getattr(panel, "file_path", None)
                and get_settings_value("auto-save", bool, False)):
            self.handle_save_file_action()

    def new_graph(self, graph: Optional[GraphT] = None,
                  name: Optional[str] = None) -> None:
        _graph = graph or new_graph()
        panel  = GraphEditPanel(_graph, self.undo_action, self.redo_action)
        panel.start_derivation_signal.connect(self.new_deriv)
        panel.start_pauliwebs_signal.connect(self.new_pauli_webs)
        self._new_panel(panel, name or "New Graph")

    def open_graph_for_editing(self, graph: GraphT, name: str) -> None:
        """Open a graph for interactive editing, reusing an existing tab by name."""
        if not isinstance(graph, GraphT):   # type: ignore[misc]
            graph = graph.copy(backend="multigraph")
            graph.set_auto_simplify(False)
        for i in range(self.tab_widget.count()):
            tab_text = self.tab_widget.tabText(i)
            if tab_text in (name, "*" + name):
                self.tab_widget.setCurrentIndex(i)
                assert self.active_panel is not None
                self.active_panel.replace_graph(graph)
                return
        self.new_graph(copy.deepcopy(graph), name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        for i in range(self.tab_widget.count()):
            tab_text = self.tab_widget.tabText(i)
            if tab_text in (name, "*" + name):
                panel = cast(BasePanel, self.tab_widget.widget(i))
                return cast(GraphT, copy.deepcopy(panel.graph_scene.g))
        return None

    def new_rule_editor(self, rule: Optional[CustomRule] = None,
                        name: Optional[str] = None) -> None:
        if rule is None:
            graph1    = new_graph();  graph2 = new_graph()
            rule_name = "";           rule_desc = ""
        else:
            graph1    = rule.lhs_graph;  graph2 = rule.rhs_graph
            rule_name = rule.name;       rule_desc = rule.description
        panel = RulePanel(graph1, graph2, rule_name, rule_desc,
                          self.undo_action, self.redo_action)
        self._new_panel(panel, name or "New Rule")

    def new_deriv(self, graph: GraphT, name: Optional[str] = None) -> None:
        panel = ProofPanel(graph, self.undo_action, self.redo_action)
        panel.start_pauliwebs_signal.connect(self.new_pauli_webs)
        self._new_panel(panel, name or "New Proof")
        # Auto-start the proof-mode tour the first time the user enters
        # proof mode.
        from .tutorial import maybe_start_proof_tutorial
        maybe_start_proof_tutorial(self)

    def new_pauli_webs(self, graph: GraphT,
                       name: Optional[str] = None) -> None:
        panel = PauliWebsPanel(graph, self.undo_action, self.redo_action)
        self._new_panel(panel, name or "New Pauli Webs")

    # ── Tutorial entry points  (Help menu) ────────────────────────────────

    def start_tutorial(self, quick: bool = False) -> None:
        """Replay the editor tutorial; ``quick=True`` for the short version."""
        from .tutorial import start_editor_tutorial
        start_editor_tutorial(self, quick=quick)

    def start_proof_tutorial(self) -> None:
        """Replay the proof-mode tutorial."""
        from .tutorial import start_proof_tutorial
        start_proof_tutorial(self)

    def start_learn_basics_tutorial(self) -> None:
        """Replay the interactive 3 CNOTs → SWAP lesson."""
        from .tutorial import start_learn_basics_tutorial
        start_learn_basics_tutorial(self)

    def start_zz_gadget_tutorial(self) -> None:
        """Replay the ZZ(α) phase-gadget lesson."""
        from .tutorial import start_zz_gadget_tutorial
        start_zz_gadget_tutorial(self)

    def start_graph_state_tutorial(self) -> None:
        """Replay the three-qubit cluster-state / MBQC lesson."""
        from .tutorial import start_graph_state_tutorial
        start_graph_state_tutorial(self)

    def start_teleportation_tutorial(self) -> None:
        """Replay the quantum-state teleportation lesson."""
        from .tutorial import start_teleportation_tutorial
        start_teleportation_tutorial(self)

    # ── Other panel operations ────────────────────────────────────────────

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

    def undo(self) -> None:
        if self.active_panel:
            self.active_panel.undo_stack.undo()

    def redo(self) -> None:
        if self.active_panel:
            self.active_panel.undo_stack.redo()

    def auto_arrange(self) -> None:
        """Automatically arrange vertices using networkx spring layout.

        When vertices are selected only those are repositioned.  Otherwise
        all non-boundary vertices are repositioned with boundary vertices as
        anchors.  W-input vertices stay at their original offset relative to
        their W-output partner.
        """
        assert self.active_panel is not None
        g = self.active_panel.graph_view.graph_scene.g
        if g.num_vertices() == 0:
            return
        movable, fixed = _auto_arrange_partition(
            g,
            set(self.active_panel.graph_view.graph_scene.selected_vertices))
        w_offsets = _auto_arrange_extract_w_inputs(g, movable, fixed)
        if not movable:
            return
        pos   = _auto_arrange_layout(g, movable, fixed)
        moves = _auto_arrange_build_moves(g, movable, w_offsets, pos)
        if moves:
            self._auto_arrange_push(moves)

    def _auto_arrange_push(
            self, moves: list[tuple[VT, float, float]]) -> None:
        assert self.active_panel is not None
        move_cmd = MoveNode(self.active_panel.graph_view, moves)
        if isinstance(self.active_panel, ProofPanel):
            self.active_panel.undo_stack.push(
                ProofModeCommand(move_cmd, self.active_panel))
        else:
            self.active_panel.undo_stack.push(move_cmd)

    # ── Sound effects ─────────────────────────────────────────────────────

    def play_sound(self, sfx: SFXEnum) -> None:
        if get_settings_value("sound-effects", bool, False):
            effect = self.effects.get(sfx)
            if effect is not None:
                effect.play()

    def toggle_auto_save(self) -> None:
        enabled = self.auto_save_action.isChecked()
        set_settings_value("auto-save", enabled, bool)

    def _toggle_sfx(self) -> None:
        current = get_settings_value("sound-effects", bool, False)
        set_settings_value("sound-effects", not current, bool)

    # ── Updates ───────────────────────────────────────────────────────────

    def check_for_updates(self) -> None:
        from .update_checker import UpdateChecker
        from .dialogs import show_update_available_dialog
        checker = UpdateChecker(
            self.settings.value("version", ""), self.settings)
        checker.update_available.connect(
            lambda version, url: show_update_available_dialog(
                self.settings.value("version", ""), version, url, self))
        checker.check_for_updates_async()

    # ── Colour theming ────────────────────────────────────────────────────

    def update_colors(self) -> None:
        dark = display_setting.dark_mode
        bg   = "#2b2b2b" if dark else "#f0f0f0"
        fg   = "#cccccc" if dark else "#333333"
        sel  = "#4a90d9" if dark else "#0078d4"
        self.tab_widget.setStyleSheet(
            f"""
            QTabBar::tab {{
                background: {bg};
                color: {fg};
                padding: 6px 14px;
                border: 1px solid {'#444' if dark else '#ccc'};
                border-bottom: none;
                border-radius: 4px 4px 0 0;
            }}
            QTabBar::tab:selected {{
                background: {'#3c3f41' if dark else '#ffffff'};
                color: {sel};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {'#3a3a3a' if dark else '#e0e0e0'};
            }}
            """
        )

    # ── Proof-as-lemma ────────────────────────────────────────────────────

    def proof_as_lemma(self) -> None:
        assert isinstance(self.active_panel, ProofPanel)
        name, description = get_lemma_name_and_description(self)
        if name is None:
            return
        rule = self.active_panel.proof_model.to_rule(name, description)
        self.new_rule_editor(rule, name)


# ─────────────────────────────────────────────────────────────────────────────
# Custom tab bar (double-click to rename)
# ─────────────────────────────────────────────────────────────────────────────

class CustomTabBar(QTabBar):
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        index = self.tabAt(event.pos())
        if index >= 0:
            self.setTabText(index, self.tabText(index))
        super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-arrange helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auto_arrange_partition(
        g: GraphT,
        selected: set[VT],
) -> tuple[set[VT], set[VT]]:
    """Split vertices into (movable, fixed-anchor) sets for spring layout."""
    from pyzx.utils import VertexType as VT_
    boundary = {v for v in g.vertices() if g.type(v) == VT_.BOUNDARY}
    w_inputs = {v for v in g.vertices() if g.type(v) == VT_.W_INPUT}

    if selected:
        movable = selected - boundary - w_inputs
        fixed   = {
            n for v in movable
            for n in g.neighbors(v)
            if n not in movable
        } | boundary
    else:
        movable = set(g.vertices()) - boundary - w_inputs
        fixed   = boundary
    return movable, fixed


def _auto_arrange_extract_w_inputs(
        g: GraphT,
        movable: set[VT],
        fixed: set[VT],
) -> dict[VT, tuple[VT, float, float]]:
    """Record W-input offsets relative to their W-output partners."""
    from pyzx.utils import VertexType as VT_
    offsets: dict[VT, tuple[VT, float, float]] = {}
    for v in list(movable):
        if g.type(v) == VT_.W_INPUT:
            movable.discard(v)
            fixed.discard(v)
            for partner in g.neighbors(v):
                if g.type(partner) == VT_.W_OUTPUT:
                    offsets[v] = (
                        partner,
                        g.row(v)   - g.row(partner),
                        g.qubit(v) - g.qubit(partner),
                    )
                    break
    return offsets


def _auto_arrange_layout(
        g: GraphT,
        movable: set[VT],
        fixed: set[VT],
) -> dict[VT, tuple[float, float]]:
    """Run networkx spring layout; return {vertex: (row, qubit)} positions."""
    subgraph_nodes = movable | fixed
    G_sub          = to_networkx(g).subgraph(subgraph_nodes)
    initial_pos    = {v: (g.row(v), g.qubit(v)) for v in subgraph_nodes}

    anchor_pos = [initial_pos[v] for v in (fixed or movable)]
    rows   = [r for r, _ in anchor_pos]
    qubits = [q for _, q in anchor_pos]
    width  = max(max(rows)   - min(rows),   1)
    height = max(max(qubits) - min(qubits), 1)
    k      = (width * height / max(len(G_sub), 1)) ** 0.5

    if fixed:
        return dict(nx.spring_layout(
            G_sub, k=k, pos=initial_pos, fixed=fixed,
            iterations=50, seed=0))
    scale  = max(width, height) / 2
    center = (
        (max(rows) + min(rows)) / 2,
        (max(qubits) + min(qubits)) / 2,
    )
    return dict(nx.spring_layout(
        G_sub, k=k, pos=initial_pos, iterations=50,
        scale=scale, center=center, seed=0))


def _auto_arrange_build_moves(
        g: GraphT,
        movable: set[VT],
        w_input_offsets: dict[VT, tuple[VT, float, float]],
        pos: dict[VT, tuple[float, float]],
) -> list[tuple[VT, float, float]]:
    """Translate layout positions into (vertex, row, qubit) move commands."""
    moves: list[tuple[VT, float, float]] = []
    for v in movable:
        if v in pos:
            _append_move_if_changed(g, moves, v, pos[v])
    for v, (partner, row_off, qubit_off) in w_input_offsets.items():
        partner_row, partner_qubit = pos.get(
            partner, (g.row(partner), g.qubit(partner)))
        _append_move_if_changed(
            g, moves, v,
            (partner_row + row_off, partner_qubit + qubit_off))
    return moves


def _append_move_if_changed(
        g: GraphT,
        moves: list[tuple[VT, float, float]],
        v: VT,
        new_pos: tuple[float, float],
) -> None:
    new_row, new_qubit = new_pos
    if (abs(new_row   - g.row(v))   > 0.001
            or abs(new_qubit - g.qubit(v)) > 0.001):
        moves.append((v, new_row, new_qubit))
