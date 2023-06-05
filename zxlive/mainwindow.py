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

from enum import IntEnum

from PySide6.QtCore import QByteArray, QSettings, QFile, QTextStream, QIODevice
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from pyzx.utils import VertexType
import copy
from fractions import Fraction

from .edit_panel import GraphEditPanel
from .graphview import GraphView
from .proof_panel import ProofPanel
from .rules import *
from .construct import *
from .commands import *

from pyzx import basicrules
from pyzx import to_gh


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

    def _tab_changed(self, new_tab: Tab):
        # This method is also invoked on application launch, so check
        # if the tab has actually changed
        if self.current_tab != new_tab:
            old_panel = self.edit_panel if self.current_tab == Tab.EditTab else self.proof_panel
            new_panel = self.edit_panel if new_tab == Tab.EditTab else self.proof_panel
            # TODO: Do we want to maintain node selections when switching
            new_panel.graph_view.set_graph(old_panel.graph)
            # TODO: For now we always invalidate the undo stack when switching
            #  between tabs. In the future this should only happen if we've
            #  actually made changes to the graph before switching.
            new_panel.undo_stack.clear()
            self.current_tab = new_tab



    def _old(self):

        # add a GraphView as the only widget in the window
        self.graph_view = GraphView(GraphScene())
        w.layout().addWidget(self.graph_view)

        self.graph_view.set_graph(construct_circuit())
        # self.graph_view.set_graph(zx.generate.cliffords(5, 5))

        def fuse_clicked():
            g, vs = self.get_elements()
            if vs == []:
                self.graph_view.set_graph(g)
                return

            new_g = copy.deepcopy(g)

            if len(vs) == 1:
                basicrules.remove_id(new_g, vs[0])
                cmd = SetGraph(self.graph_view, g, new_g)
                self.graph_view.graph_scene.undo_stack.push(cmd)
                return

            x_vertices = [v for v in vs if g.type(v) == VertexType.X]
            z_vertices = [v for v in vs if g.type(v) == VertexType.Z]
            vs = [x_vertices, z_vertices]
            fuse = False
            for lst in vs:
                lst = sorted(lst)
                to_fuse = {}
                visited = set()
                for v in lst:
                    if v in visited:
                        continue
                    to_fuse[v] = []
                    # dfs
                    stack = [v]
                    while stack:
                        u = stack.pop()
                        if u in visited:
                            continue
                        visited.add(u)
                        for w in g.neighbors(u):
                            if w in lst:
                                to_fuse[v].append(w)
                                stack.append(w)

                for v in to_fuse:
                    for w in to_fuse[v]:
                        basicrules.fuse(new_g, v, w)
                        fuse = True

            if not fuse:
                self.graph_view.set_graph(g)
                return

            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def reset_clicked():
            undo_stack = self.graph_view.graph_scene.undo_stack
            while undo_stack.canUndo():
                undo_stack.undo()

        def undo_clicked():
            self.graph_view.graph_scene.undo_stack.undo()

        def redo_clicked():
            self.graph_view.graph_scene.undo_stack.redo()

        def add_wire_clicked():
            g, vs = self.get_elements()
            if len(vs) != 2:
                self.graph_view.set_graph(g)
                return

            new_g = copy.deepcopy(g)
            e = new_g.edge(vs[0], vs[1])
            new_g.add_edge_smart(e, edgetype=ET_SIM)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def add_node_clicked():
            g, vs = self.get_elements()
            if len(vs) != 2:
                self.graph_view.set_graph(g)
                return

            cmd = AddIdentity(self.graph_view, vs[0], vs[1])
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def bialgebra_clicked():
            g, vs = self.get_elements()
            if not vs:
                self.graph_view.set_graph(g)
                return

            new_g = copy.deepcopy(g)
            bialgebra(new_g, vs)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def edit_node_color_clicked():
            _, vs = self.get_elements()
            cmd = ToggleNodeColor(self.graph_view, vs)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def change_color_clicked():
            _, vs = self.get_elements()
            cmd = ChangeColor(self.graph_view, vs)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def gh_state_clicked():
            g = self.graph_view.graph_scene.g
            new_g = copy.deepcopy(g)
            to_gh(new_g)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def change_phase_clicked():
            g, vs = self.get_elements()
            if len(vs) != 1:
                self.graph_view.set_graph(g)
                return

            v = vs[0]
            old_phase = g.phase(v)

            input, ok = QInputDialog.getText(
                self, "Input Dialog", "Enter Desired Phase Value:"
            )
            if not ok:
                return
            try:
                new_phase = Fraction(input)
            except ValueError:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Wrong Input Type")
                info_text = "Please enter a valid input (e.g. 1/2, 2)"
                msg.setInformativeText(info_text)
                msg.exec_()
                self.graph_view.set_graph(g)
                return

            cmd = ChangePhase(self.graph_view, v, old_phase, new_phase)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def import_diagram_clicked():
            supported_formats = [
                ("QGraph (*.zxg)", "zxg"),
                ("QASM (*.qasm)", "qasm"),
                ("TikZ (*.tikz)", "tikz"),
                ("JSON (*.json)", "json"),
            ]
            file_path, selected_format = QFileDialog.getOpenFileName(
                parent=w,
                caption="Open File",
                filter=";;".join([f[0] for f in supported_formats]),
            )

            file = QFile(file_path)
            if not file.open(QIODevice.ReadOnly | QIODevice.Text):
                return
            input = QTextStream(file)

            g = self.graph_view.graph_scene.g
            if selected_format == "QGraph (*.zxg)":
                try:
                    new_g = zx.Graph().from_json(input.readAll())
                except Exception as e:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Failed to import QGraph file")
                    msg.setInformativeText(str(e))
                    msg.exec_()
                    self.graph_view.set_graph(g)
                    return
                cmd = SetGraph(self.graph_view, g, new_g)
                self.graph_view.graph_scene.undo_stack.push(cmd)
            elif selected_format == "QASM (*.qasm)":
                try:
                    new_g = zx.Circuit.from_qasm(input.readAll()).to_graph()
                except Exception as e:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Failed to import QASM file")
                    msg.setInformativeText(str(e))
                    msg.exec_()
                    self.graph_view.set_graph(g)
                    return
                cmd = SetGraph(self.graph_view, g, new_g)
                self.graph_view.graph_scene.undo_stack.push(cmd)
            elif selected_format == "TikZ (*.tikz)":
                try:
                    new_g = zx.Graph().from_tikz(input.readAll())
                except Exception as e:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Failed to import TikZ file")
                    msg.setInformativeText(str(e))
                    msg.exec_()
                    self.graph_view.set_graph(g)
                    return
                cmd = SetGraph(self.graph_view, g, new_g)
                self.graph_view.graph_scene.undo_stack.push(cmd)
            elif selected_format == "JSON (*.json)":
                try:
                    new_g = zx.Graph().from_json(input.readAll())
                except Exception as e:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Failed to import JSON file")
                    msg.setInformativeText(str(e))
                    msg.exec_()
                    self.graph_view.set_graph(g)
                    return
                cmd = SetGraph(self.graph_view, g, new_g)
                self.graph_view.graph_scene.undo_stack.push(cmd)

            file.close()

        def export_diagram_clicked():
            supported_formats = [
                ("QGraph (*.zxg)", "zxg"),
                ("QASM (*.qasm)", "qasm"),
                ("TikZ (*.tikz)", "tikz"),
                ("JSON (*.json)", "json"),
            ]
            file_path, selected_format = QFileDialog.getSaveFileName(
                parent=w,
                caption="Save File",
                filter=";;".join([f[0] for f in supported_formats]),
            )

            # add file extension if not already there
            file_extension = supported_formats[
                [format_name for format_name, _ in supported_formats].index(
                    selected_format
                )
            ][1]
            if file_extension == file_path.split(".")[-1]:
                file = QFile(file_path)
            else:
                file = QFile(file_path + "." + file_extension)

            if not file.open(QIODevice.WriteOnly | QIODevice.Text):
                return
            out = QTextStream(file)

            g = self.graph_view.graph_scene.g
            if selected_format == "QGraph (*.zxg)":
                out << g.to_json()
            elif selected_format == "QASM (*.qasm)":
                try:
                    circuit = zx.extract_circuit(g)
                except Exception as e:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Failed to convert the ZX-diagram to quantum circuit")
                    msg.setInformativeText(str(e))
                    msg.exec_()
                    return
                out << circuit.to_qasm()
            elif selected_format == "TikZ (*.tikz)":
                out << g.to_tikz()
            elif selected_format == "JSON (*.json)":
                out << g.to_json()

            file.close()

        def make_edit_tool_bar():
            def edit_button_clicked():
                edit_tool_bar = self.findChild(QToolBar, "edit_tool_bar")
                self.removeToolBar(edit_tool_bar)
                self.addToolBar(Qt.LeftToolBarArea, make_rewrite_tool_bar())

            edit_mode_selection = QToolButton()
            edit_mode_selection.setText("Use Rewrite Mode")
            edit_mode_selection.setCheckable(False)
            edit_mode_selection.setAutoExclusive(False)

            edit_undo = QToolButton()
            edit_undo.setText("Undo")
            edit_undo.setCheckable(False)
            edit_undo.setAutoExclusive(False)

            edit_redo = QToolButton()
            edit_redo.setText("Redo (Unundo)")
            edit_redo.setCheckable(False)
            edit_redo.setAutoExclusive(False)

            edit_toggle_wire = QToolButton()
            edit_toggle_wire.setText("Add Wire")
            edit_toggle_wire.setCheckable(False)
            edit_toggle_wire.setAutoExclusive(False)

            edit_add_node = QToolButton()
            edit_add_node.setText("Add Node")
            edit_add_node.setCheckable(False)
            edit_add_node.setAutoExclusive(False)

            edit_edit_node = QToolButton()
            edit_edit_node.setText("Edit Node Color")
            edit_edit_node.setCheckable(False)
            edit_edit_node.setAutoExclusive(False)

            edit_change_phase = QToolButton()
            edit_change_phase.setText("Change Phase")
            edit_change_phase.setCheckable(False)
            edit_change_phase.setAutoExclusive(False)

            edit_import_diagram = QToolButton()
            edit_import_diagram.setText("Import Diagram")
            edit_import_diagram.setCheckable(False)
            edit_import_diagram.setAutoExclusive(False)

            edit_export_diagram = QToolButton()
            edit_export_diagram.setText("Export Diagram")
            edit_export_diagram.setCheckable(False)
            edit_export_diagram.setAutoExclusive(False)

            edit_reset = QToolButton()
            edit_reset.setText("Reset")
            edit_reset.setCheckable(False)
            edit_reset.setAutoExclusive(False)
            edit_reset.setProperty("class", "danger")

            edit_mode_selection.clicked.connect(edit_button_clicked)
            edit_undo.clicked.connect(undo_clicked)
            edit_redo.clicked.connect(redo_clicked)
            edit_toggle_wire.clicked.connect(add_wire_clicked)
            edit_add_node.clicked.connect(add_node_clicked)
            edit_edit_node.clicked.connect(edit_node_color_clicked)
            edit_change_phase.clicked.connect(change_phase_clicked)
            edit_import_diagram.clicked.connect(import_diagram_clicked)
            edit_export_diagram.clicked.connect(export_diagram_clicked)
            edit_reset.clicked.connect(reset_clicked)

            edit_tool_bar = QToolBar("edit_tool_bar", self)
            edit_tool_bar.setObjectName("edit_tool_bar")
            edit_tool_bar.addWidget(edit_mode_selection)
            edit_tool_bar.addWidget(edit_undo)
            edit_tool_bar.addWidget(edit_redo)
            edit_tool_bar.addWidget(edit_toggle_wire)
            edit_tool_bar.addWidget(edit_add_node)
            edit_tool_bar.addWidget(edit_edit_node)
            edit_tool_bar.addWidget(edit_change_phase)
            edit_tool_bar.addWidget(edit_import_diagram)
            edit_tool_bar.addWidget(edit_export_diagram)
            edit_tool_bar.addWidget(edit_reset)

            return edit_tool_bar

        def make_rewrite_tool_bar():
            def rewrite_button_clicked():
                rewrite_tool_bar = self.findChild(QToolBar, "rewrite_tool_bar")
                self.removeToolBar(rewrite_tool_bar)
                self.addToolBar(Qt.LeftToolBarArea, make_edit_tool_bar())

            rewrite_mode_selection = QToolButton()
            rewrite_mode_selection.setText("Use Edit Mode")
            rewrite_mode_selection.setCheckable(False)
            rewrite_mode_selection.setAutoExclusive(False)

            rewrite_fuse = QToolButton()
            rewrite_fuse.setText("Fuse")
            """Button_Fuse.setObjectName("Button")
            Button_Fuse.setStyleSheet(style)"""
            rewrite_fuse.setCheckable(False)
            rewrite_fuse.setAutoExclusive(False)
            rewrite_fuse.setProperty("class", "success")

            rewrite_undo = QToolButton()
            rewrite_undo.setText("Undo")
            rewrite_undo.setCheckable(False)
            rewrite_undo.setAutoExclusive(False)

            rewrite_redo = QToolButton()
            rewrite_redo.setText("Redo (Unundo)")
            rewrite_redo.setCheckable(False)
            rewrite_redo.setAutoExclusive(False)

            rewrite_change_phase = QToolButton()
            rewrite_change_phase.setText("Change Phase")
            rewrite_change_phase.setCheckable(False)
            rewrite_change_phase.setAutoExclusive(False)

            rewrite_change_color = QToolButton()
            rewrite_change_color.setText("Color Change")
            rewrite_change_color.setCheckable(False)
            rewrite_change_color.setAutoExclusive(False)

            rewrite_do_bialgebra = QToolButton()
            rewrite_do_bialgebra.setText("Bialgebra")
            rewrite_do_bialgebra.setCheckable(False)
            rewrite_do_bialgebra.setAutoExclusive(False)

            rewrite_gh_state = QToolButton()
            rewrite_gh_state.setText("GH State")
            rewrite_gh_state.setCheckable(False)
            rewrite_gh_state.setAutoExclusive(False)

            rewrite_import_diagram = QToolButton()
            rewrite_import_diagram.setText("Import Diagram")
            rewrite_import_diagram.setCheckable(False)
            rewrite_import_diagram.setAutoExclusive(False)

            rewrite_export_diagram = QToolButton()
            rewrite_export_diagram.setText("Export Diagram")
            rewrite_export_diagram.setCheckable(False)
            rewrite_export_diagram.setAutoExclusive(False)

            rewrite_reset = QToolButton()
            rewrite_reset.setText("Reset")
            rewrite_reset.setCheckable(False)
            rewrite_reset.setAutoExclusive(False)
            rewrite_reset.setProperty("class", "danger")

            rewrite_mode_selection.clicked.connect(rewrite_button_clicked)
            rewrite_fuse.clicked.connect(fuse_clicked)
            rewrite_undo.clicked.connect(undo_clicked)
            rewrite_redo.clicked.connect(redo_clicked)
            rewrite_change_phase.clicked.connect(change_phase_clicked)
            rewrite_change_color.clicked.connect(change_color_clicked)
            rewrite_do_bialgebra.clicked.connect(bialgebra_clicked)
            rewrite_gh_state.clicked.connect(gh_state_clicked)
            rewrite_import_diagram.clicked.connect(import_diagram_clicked)
            rewrite_export_diagram.clicked.connect(export_diagram_clicked)
            rewrite_reset.clicked.connect(reset_clicked)

            rewrite_tool_bar = QToolBar("rewrite_tool_bar", self)
            rewrite_tool_bar.setObjectName("rewrite_tool_bar")
            rewrite_tool_bar.addWidget(rewrite_mode_selection)
            rewrite_tool_bar.addWidget(rewrite_fuse)
            rewrite_tool_bar.addWidget(rewrite_undo)
            rewrite_tool_bar.addWidget(rewrite_redo)
            rewrite_tool_bar.addWidget(rewrite_change_color)
            rewrite_tool_bar.addWidget(rewrite_do_bialgebra)
            rewrite_tool_bar.addWidget(rewrite_gh_state)
            rewrite_tool_bar.addWidget(rewrite_import_diagram)
            rewrite_tool_bar.addWidget(rewrite_export_diagram)
            rewrite_tool_bar.addWidget(rewrite_reset)
            return rewrite_tool_bar

        edit_tool_bar = make_edit_tool_bar()
        self.addToolBar(Qt.LeftToolBarArea, edit_tool_bar)

    def closeEvent(self, e: QCloseEvent) -> None:
        # save the shape/size of this window on close
        conf = QSettings("zxlive", "zxlive")
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def get_elements(self):
        g = self.graph_view.graph_scene.g
        items = self.graph_view.graph_scene._selected_items
        vs = [item.v for item in items]

        self.graph_view.graph_scene._selected_items = []
        return g, vs
