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
from PySide6.QtCore import QByteArray, QSettings
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

    This is just an example, and should be replaced with something more sophisticated.
    """

    def __init__(self) -> None:
        super().__init__()
        conf = QSettings('zxlive', 'zxlive')

        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        w.layout().setContentsMargins(0,0,0,0)
        w.layout().setSpacing(0)
        self.resize(1200, 800)

        # restore the shape/size of this window from the last time it was opened
        geom = conf.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        # add a GraphView as the only widget in the window
        self.graph_view = GraphView()
        w.layout().addWidget(self.graph_view)

        self.graph_view.set_graph(construct_circuit())
        # self.graph_view.set_graph(construct(5, 5))

        def Button_Fuse_Clicked():
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

        def Button_Reset_Clicked():
            undo_stack = self.graph_view.graph_scene.undo_stack
            while undo_stack.canUndo():
                undo_stack.undo()

        def Button_Undo_Clicked():
            self.graph_view.graph_scene.undo_stack.undo()

        def Button_Redo_Clicked():
            self.graph_view.graph_scene.undo_stack.redo()

        def Button_Add_Wire_Clicked():
            g, vs = self.get_elements()
            if len(vs) != 2:
                self.graph_view.set_graph(g)
                return

            new_g = copy.deepcopy(g)
            e = new_g.edge(vs[0], vs[1])
            new_g.add_edge_smart(e, edgetype=ET_SIM)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def Button_Add_Node_Clicked():
            g, vs = self.get_elements()
            if len(vs) != 2:
                self.graph_view.set_graph(g)
                return

            cmd = AddIdentity(self.graph_view, vs[0], vs[1])
            self.graph_view.graph_scene.undo_stack.push(cmd)

        editToolBar = QToolBar("Edit", self)
        self.addToolBar(Qt.LeftToolBarArea, editToolBar)

        def Button_BiAlgebra_Clicked():
            g, vs = self.get_elements()
            if not vs:
                self.graph_view.set_graph(g)
                return

            new_g = copy.deepcopy(g)
            bialgebra(new_g, vs)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def Button_Edit_Node_Color_Clicked():
            _, vs = self.get_elements()
            cmd = EditNodeColor(self.graph_view, vs)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def Button_Change_Color_Clicked():
            _, vs = self.get_elements()
            cmd = ChangeColor(self.graph_view, vs)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def Button_GH_State_Clicked():
            g = self.graph_view.graph_scene.g
            new_g = copy.deepcopy(g)
            to_gh(new_g)
            cmd = SetGraph(self.graph_view, g, new_g)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        def Button_Change_Phase_Clicked():
            g, vs = self.get_elements()
            if len(vs) != 1:
                self.graph_view.set_graph(g)
                return

            v = vs[0]
            old_phase = g.phase(v)

            input, ok = QInputDialog.getText(
                self, "Input Dialog", "Enter Desired Phase Value:")
            if not ok:
                return
            try:
                new_phase = Fraction(input)
            except ValueError:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Wrong Input Type")
                msg.setInformativeText('Please enter a valid input (e.g. 1/2, 2)')
                msg.exec_()
                self.graph_view.set_graph(g)
                return

            cmd = ChangePhase(self.graph_view, v, old_phase, new_phase)
            self.graph_view.graph_scene.undo_stack.push(cmd)

        Button_Fuse = QToolButton()
        Button_Fuse.setText("Fuse")
        """Button_Fuse.setObjectName("Button")
        Button_Fuse.setStyleSheet(style)"""
        Button_Fuse.setCheckable(False)
        Button_Fuse.setAutoExclusive(False)
        Button_Fuse.setProperty('class', 'success')
        Button_Fuse.clicked.connect(Button_Fuse_Clicked)
        editToolBar.addWidget(Button_Fuse)

        Button_Undo = QToolButton()
        Button_Undo.setText("Undo")
        Button_Undo.setCheckable(False)
        Button_Undo.setAutoExclusive(False)
        Button_Undo.clicked.connect(Button_Undo_Clicked)
        editToolBar.addWidget(Button_Undo)

        Button_Redo = QToolButton()
        Button_Redo.setText("Redo (Unundo)")
        Button_Redo.setCheckable(False)
        Button_Redo.setAutoExclusive(False)
        Button_Redo.clicked.connect(Button_Redo_Clicked)
        editToolBar.addWidget(Button_Redo)

        Button_Toggle_Wire = QToolButton()
        Button_Toggle_Wire.setText("Add Wire")
        Button_Toggle_Wire.setCheckable(False)
        Button_Toggle_Wire.setAutoExclusive(False)
        Button_Toggle_Wire.clicked.connect(Button_Add_Wire_Clicked)
        editToolBar.addWidget(Button_Toggle_Wire)

        Button_Add_Node = QToolButton()
        Button_Add_Node.setText("Add Node")
        Button_Add_Node.setCheckable(False)
        Button_Add_Node.setAutoExclusive(False)
        Button_Add_Node.clicked.connect(Button_Add_Node_Clicked)
        editToolBar.addWidget(Button_Add_Node)

        Button_edit_node = QToolButton()
        Button_edit_node.setText("Edit Node Color")
        Button_edit_node.setCheckable(False)
        Button_edit_node.setAutoExclusive(False)
        Button_edit_node.clicked.connect(Button_Edit_Node_Color_Clicked)
        editToolBar.addWidget(Button_edit_node)

        Button_Change_Phase = QToolButton()
        Button_Change_Phase.setText("Change Phase")
        Button_Change_Phase.setCheckable(False)
        Button_Change_Phase.setAutoExclusive(False)
        Button_Change_Phase.clicked.connect(Button_Change_Phase_Clicked)
        editToolBar.addWidget(Button_Change_Phase)

        Button_Change_Color = QToolButton()
        Button_Change_Color.setText("Color Change")
        Button_Change_Color.setCheckable(False)
        Button_Change_Color.setAutoExclusive(False)
        Button_Change_Color.clicked.connect(Button_Change_Color_Clicked)
        editToolBar.addWidget(Button_Change_Color)

        Button_BiAlgebra = QToolButton()
        Button_BiAlgebra.setText("Bialgebra")
        Button_BiAlgebra.setCheckable(False)
        Button_BiAlgebra.setAutoExclusive(False)
        Button_BiAlgebra.clicked.connect(Button_BiAlgebra_Clicked)
        editToolBar.addWidget(Button_BiAlgebra)

        Button_GH_State = QToolButton()
        Button_GH_State.setText("GH State")
        Button_GH_State.setCheckable(False)
        Button_GH_State.setAutoExclusive(False)
        Button_GH_State.clicked.connect(Button_GH_State_Clicked)
        editToolBar.addWidget(Button_GH_State)

        Button_Reset = QToolButton()
        Button_Reset.setText("Reset")
        Button_Reset.setCheckable(False)
        Button_Reset.setAutoExclusive(False)
        Button_Reset.setProperty('class', 'danger')
        Button_Reset.clicked.connect(Button_Reset_Clicked)
        editToolBar.addWidget(Button_Reset)

    def closeEvent(self, e: QCloseEvent) -> None:
        # save the shape/size of this window on close
        conf = QSettings('zxlive', 'zxlive')
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()

    def get_elements(self):
        g = self.graph_view.graph_scene.g
        items = self.graph_view.graph_scene.selected_items
        vs = [item.v for item in items]

        self.graph_view.graph_scene.selected_items = []
        return g, vs
