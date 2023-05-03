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
import pyzx as zx
from . import graphscene
from pyzx.utils import EdgeType, VertexType, toggle_edge, toggle_vertex
import copy


from .graphview import GraphView
from .rules import *
from .construct import *

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
        self.u_stack = []
        self.d_stack = []

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
            list_vertices = self.graph_view.graph_scene.selected_items
            if list_vertices == []:
                return 
            g = list_vertices[0].g
            self.u_stack.append(copy.deepcopy(g))
            if len(list_vertices)==1:
                g = identity(list_vertices[0])
                self.graph_view.graph_scene.selected_items = []
                return self.graph_view.set_graph(g)
            else:
                x_vertices = []
                z_vertices = []
                for ver in list_vertices:
                    if g.type(ver.v)==VertexType.X:
                        x_vertices.append(ver)
                    else:
                        z_vertices.append(ver)
            list_vertices = [x_vertices,z_vertices]
            for lst in list_vertices:
                ##print("list:", [it.v for it in lst])
                lst = sorted(lst, key=lambda itm: itm.v)
                ##print("list:", [it.v for it in lst])
                if len(lst)<2:
                    continue
                else:
                    copy_lst = lst.copy()
                    for elem in copy_lst:
                        #print("outer : ", elem.v)
                        i=0
                        if elem in lst:
                            while(len(lst)>1):
                                #print("inner : ", lst[i].v)
                                #print("nighs : ", g.neighbors(elem.v))
                                if lst[i].v in g.neighbors(elem.v):
                                    g = fusion(elem, lst[i])
                                    del lst[i]
                                else:
                                    i+=1
                                if i ==len(lst):
                                    break
                            if len(lst)==1:
                                break
            self.graph_view.graph_scene.selected_items = []
            return self.graph_view.set_graph(g)


        def Button_Reset_Clicked():
            if len(self.u_stack) !=0 :
                self.graph_view.set_graph(self.u_stack.pop(0))
                self.u_stack = []
                self.d_stack = []

        def Button_Undo_Clicked():
            if len(self.u_stack) !=0 :
                self.d_stack.append(self.graph_view.graph_scene.g)
                self.d_stack.append(copy.deepcopy(self.u_stack[-1]))
                self.graph_view.set_graph(self.u_stack.pop())
                print("Undo-D: ",self.d_stack)
                print("Undo-U: ",self.u_stack)

        def Button_Redo_Clicked():
            if len(self.d_stack) != 0 :
                self.u_stack.append(copy.deepcopy(self.d_stack[-1]))
                self.d_stack.pop()
                self.graph_view.set_graph(self.d_stack.pop())
                print("Redo-D:",self.d_stack)
                print("Redo-U:",self.u_stack)

        def Button_Add_Wire_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                if len(list_vertices_Wire) != 0:
                    for i in range (len(list_vertices_Wire)-1):
                        for l in range (i+1,len(list_vertices_Wire)):
                            g = add_wire(list_vertices_Wire[i], list_vertices_Wire[l])
                    self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []

        def Button_Add_Node_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                if len(list_vertices_Wire) != 0:
                    for i in range (len(list_vertices_Wire)-1):
                        for l in range (i+1,len(list_vertices_Wire)):
                            g = add_node(list_vertices_Wire[i], list_vertices_Wire[l])
                    self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []

        editToolBar = QToolBar("Edit", self)
        self.addToolBar(Qt.LeftToolBarArea, editToolBar)

        def Button_BiAlgebra_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                g = bialgebra(list_vertices_Wire)
                self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []

        def Button_Hadamard_Slide_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                for l in list_vertices_Wire:
                    g = Hadamard_slide(l)
                self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []


        def Button_Edit_Node_Color_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                for l in list_vertices_Wire:
                    g = edit_node_color(l)
                self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []

        def Button_Change_Color_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                self.u_stack.append(copy.deepcopy(g))
                for l in list_vertices_Wire:
                    g = color_change(l)
                self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []


        def Button_GH_State_Clicked():
            g = self.graph_view.graph_scene.g
            self.u_stack.append(copy.deepcopy(g))
            g = GH_graph(g)
            self.graph_view.set_graph(g)
            self.graph_view.graph_scene.selected_items = []

        def Button_Change_Phase_Clicked():
            if self.graph_view.graph_scene.selected_items:
                list_vertices_Wire = self.graph_view.graph_scene.selected_items
                g = list_vertices_Wire[0].g
                slash_counter = 0
                includes_slash = False
                includes_else = False
                input_list_int = []
                if len(list_vertices_Wire) != 0:
                    input, ok = QInputDialog.getText(self, "Input Dialog", "Enter Desired Phase Value:")
                    if ok:
                        for l in input:
                            if l == "/":
                                slash_counter += 1
                            if not (l=="0" or l=="1" or l=="2" or l=="3" or l=="4" or l=="5" or l=="6" or l=="7" or l=="8" or l=="9" or l=="/"):
                                includes_else = True
                        if slash_counter == 1: includes_slash = True
                        print(includes_slash, includes_else)
                        if includes_slash == True and includes_else == False:
                            input_list = input.split("/")
                            for l in input_list:
                                input_list_int.append(int(l))
                            for l in input_list_int:
                                self.u_stack.append(copy.deepcopy(g))
                                for i in list_vertices_Wire:
                                    g = phase_change(i, input)
                        elif includes_slash == False and includes_else == False:
                            for l in input:
                                input_list_int.append(int(l))
                            for l in input_list_int:
                                self.u_stack.append(copy.deepcopy(g))
                                for i in list_vertices_Wire:
                                    g = phase_change(i, input)
                        else:
                            msg = QMessageBox()
                            msg.setIcon(QMessageBox.Critical)
                            msg.setText("Wrong Input Type")
                            msg.setInformativeText('Please enter a valid input (e.g. 1/2, 2)')
                            msg.exec_()
                                    
                input_list_int = []
                self.graph_view.set_graph(g)
                self.graph_view.graph_scene.selected_items = []

        #style = "QToolButton#Button{border-radius: 8px}"

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

        Button_H_slide = QToolButton()
        Button_H_slide.setText("Hadamard Rule")
        Button_H_slide.setCheckable(False)
        Button_H_slide.setAutoExclusive(False)
        Button_H_slide.clicked.connect(Button_Hadamard_Slide_Clicked)
        editToolBar.addWidget(Button_H_slide)

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
