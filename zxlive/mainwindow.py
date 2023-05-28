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
from PySide6.QtCore import QByteArray, QSettings, QFile, QTextStream, QIODevice
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from pyzx.utils import VertexType
import copy
from fractions import Fraction


from .graphview import GraphView
from .rules import *
from .construct import *
from .commands import *

from pyzx import basicrules
from pyzx import to_gh


class MainWindow(QMainWindow):
    """A simple window containing a single `GraphView`
    This is just an example, and should be replaced with
    something more sophisticated.
    """

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

        # add a GraphView as the only widget in the window
        self.graph_view = GraphView()
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

        edit_tool_bar = QToolBar("Edit", self)
        self.addToolBar(Qt.LeftToolBarArea, edit_tool_bar)

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
            cmd = EditNodeColor(self.graph_view, vs)
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

        fuse = QToolButton()
        fuse.setText("Fuse")
        """Button_Fuse.setObjectName("Button")
        Button_Fuse.setStyleSheet(style)"""
        fuse.setCheckable(False)
        fuse.setAutoExclusive(False)
        fuse.setProperty("class", "success")
        fuse.clicked.connect(fuse_clicked)
        edit_tool_bar.addWidget(fuse)

        undo = QToolButton()
        undo.setText("Undo")
        undo.setCheckable(False)
        undo.setAutoExclusive(False)
        undo.clicked.connect(undo_clicked)
        edit_tool_bar.addWidget(undo)

        redo = QToolButton()
        redo.setText("Redo (Unundo)")
        redo.setCheckable(False)
        redo.setAutoExclusive(False)
        redo.clicked.connect(redo_clicked)
        edit_tool_bar.addWidget(redo)

        toggle_wire = QToolButton()
        toggle_wire.setText("Add Wire")
        toggle_wire.setCheckable(False)
        toggle_wire.setAutoExclusive(False)
        toggle_wire.clicked.connect(add_wire_clicked)
        edit_tool_bar.addWidget(toggle_wire)

        add_node = QToolButton()
        add_node.setText("Add Node")
        add_node.setCheckable(False)
        add_node.setAutoExclusive(False)
        add_node.clicked.connect(add_node_clicked)
        edit_tool_bar.addWidget(add_node)

        edit_node = QToolButton()
        edit_node.setText("Edit Node Color")
        edit_node.setCheckable(False)
        edit_node.setAutoExclusive(False)
        edit_node.clicked.connect(edit_node_color_clicked)
        edit_tool_bar.addWidget(edit_node)

        change_phase = QToolButton()
        change_phase.setText("Change Phase")
        change_phase.setCheckable(False)
        change_phase.setAutoExclusive(False)
        change_phase.clicked.connect(change_phase_clicked)
        edit_tool_bar.addWidget(change_phase)

        change_color = QToolButton()
        change_color.setText("Color Change")
        change_color.setCheckable(False)
        change_color.setAutoExclusive(False)
        change_color.clicked.connect(change_color_clicked)
        edit_tool_bar.addWidget(change_color)

        do_bialgebra = QToolButton()
        do_bialgebra.setText("Bialgebra")
        do_bialgebra.setCheckable(False)
        do_bialgebra.setAutoExclusive(False)
        do_bialgebra.clicked.connect(bialgebra_clicked)
        edit_tool_bar.addWidget(do_bialgebra)

        gh_state = QToolButton()
        gh_state.setText("GH State")
        gh_state.setCheckable(False)
        gh_state.setAutoExclusive(False)
        gh_state.clicked.connect(gh_state_clicked)
        edit_tool_bar.addWidget(gh_state)

        import_diagram = QToolButton()
        import_diagram.setText("Import Diagram")
        import_diagram.setCheckable(False)
        import_diagram.setAutoExclusive(False)
        import_diagram.clicked.connect(import_diagram_clicked)
        edit_tool_bar.addWidget(import_diagram)

        export_diagram = QToolButton()
        export_diagram.setText("Export Diagram")
        export_diagram.setCheckable(False)
        export_diagram.setAutoExclusive(False)
        export_diagram.clicked.connect(export_diagram_clicked)
        edit_tool_bar.addWidget(export_diagram)

        reset = QToolButton()
        reset.setText("Reset")
        reset.setCheckable(False)
        reset.setAutoExclusive(False)
        reset.setProperty("class", "danger")
        reset.clicked.connect(reset_clicked)
        edit_tool_bar.addWidget(reset)

    def closeEvent(self, e: QCloseEvent) -> None:
        # save the shape/size of this window on close
        conf = QSettings("zxlive", "zxlive")
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def get_elements(self):
        g = self.graph_view.graph_scene.g
        items = self.graph_view.graph_scene.selected_items
        vs = [item.v for item in items]

        self.graph_view.graph_scene.selected_items = []
        return g, vs
