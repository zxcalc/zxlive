import copy
from enum import Enum
from fractions import Fraction
from typing import Dict, Iterator, TypedDict, Callable, Union
from PySide6.QtCore import Signal, QSize, Qt, QPoint

from PySide6.QtWidgets import QToolButton, QInputDialog, QSplitter, QListView, QListWidget, QListWidgetItem
from PySide6.QtGui import QShortcut, QIcon, QPen, QPainter, QColor, QPixmap
from pyzx import EdgeType, VertexType
from pyzx.utils import vertex_is_w, get_w_partner
from sympy import sympify

from .vitem import BLACK, ZX_GREEN, ZX_RED, H_YELLOW
from .eitem import HAD_EDGE_BLUE

from .common import VT, GraphT, ToolType, get_data
from .base_panel import BasePanel, ToolbarSection
from .commands import (
    AddEdge, AddNode, AddWNode, MoveNode, SetGraph, UpdateGraph, ChangePhase, ChangeNodeType,
    ChangeEdgeColor)
from .dialogs import show_error_msg
from .graphscene import EditGraphScene


class ShapeType(Enum):
    CIRCLE = 1
    SQUARE = 2
    TRIANGLE = 3
    LINE = 4
    DASHED_LINE = 5

class DrawPanelNodeType(TypedDict):
    text: str
    icon: tuple[ShapeType, str]


VERTICES: dict[VertexType.Type, DrawPanelNodeType] = {
    VertexType.Z: {"text": "Z spider", "icon": (ShapeType.CIRCLE, ZX_GREEN)},
    VertexType.X: {"text": "X spider", "icon": (ShapeType.CIRCLE, ZX_RED)},
    VertexType.H_BOX: {"text": "H box", "icon": (ShapeType.SQUARE, H_YELLOW)},
    VertexType.BOUNDARY: {"text": "boundary", "icon": (ShapeType.CIRCLE, BLACK)},
    VertexType.W_OUTPUT: {"text": "W node", "icon": (ShapeType.TRIANGLE, BLACK)},
}

EDGES: dict[EdgeType.Type, DrawPanelNodeType] = {
    EdgeType.SIMPLE: {"text": "Simple", "icon": (ShapeType.LINE, BLACK)},
    EdgeType.HADAMARD: {"text": "Hadamard", "icon": (ShapeType.DASHED_LINE, HAD_EDGE_BLUE)},
}


class GraphEditPanel(BasePanel):
    """Panel for the edit mode of ZX live."""

    graph_scene: EditGraphScene
    start_derivation_signal = Signal(object)

    _curr_ety: EdgeType.Type
    _curr_vty: VertexType.Type

    def __init__(self, graph: GraphT) -> None:
        self.graph_scene = EditGraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        self.graph_scene.vertex_double_clicked.connect(self._vert_double_clicked)
        self.graph_scene.vertex_added.connect(self._add_vert)
        self.graph_scene.edge_added.connect(self._add_edge)

        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE
        super().__init__(graph, self.graph_scene)

        self.sidebar = QSplitter(self)
        self.sidebar.setOrientation(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.sidebar)
        self.vertex_list = self.create_list_widget(VERTICES, self._vty_clicked)
        self.edge_list = self.create_list_widget(EDGES, self._ety_clicked)
        self.sidebar.addWidget(self.vertex_list)
        self.sidebar.addWidget(self.edge_list)

    def create_list_widget(self,
                           data: Dict[Union[VertexType.Type, EdgeType.Type], DrawPanelNodeType],
                           onclick: Callable[[Union[VertexType.Type, EdgeType.Type]], None]) -> QListWidget:
        list_widget = QListWidget(self)
        list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        list_widget.setViewMode(QListView.ViewMode.IconMode)
        list_widget.setMovement(QListView.Movement.Static)
        list_widget.setUniformItemSizes(True)
        list_widget.setGridSize(QSize(60, 64))
        list_widget.setWordWrap(True)
        list_widget.setIconSize(QSize(24, 24))
        for typ, value in data.items():
            icon = self.create_icon(*value["icon"])
            item = QListWidgetItem(icon, value["text"])
            item.setData(Qt.ItemDataRole.UserRole, typ)
            list_widget.addItem(item)
        list_widget.itemClicked.connect(lambda x: onclick(x.data(Qt.ItemDataRole.UserRole)))
        list_widget.setCurrentItem(list_widget.item(0))
        return list_widget

    def create_icon(self, shape: str, color: str) -> QIcon:
        icon = QIcon()
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BLACK), 6))
        painter.setBrush(QColor(color))
        if shape == ShapeType.CIRCLE:
            painter.drawEllipse(4, 4, 56, 56)
        elif shape == ShapeType.SQUARE:
            painter.drawRect(4, 4, 56, 56)
        elif shape == ShapeType.TRIANGLE:
            painter.drawPolygon([QPoint(32, 10), QPoint(2, 60), QPoint(62, 60)])
        elif shape == ShapeType.LINE:
            painter.drawLine(0, 32, 64, 32)
        elif shape == ShapeType.DASHED_LINE:
            painter.setPen(QPen(QColor(color), 6, Qt.PenStyle.DashLine))
            painter.drawLine(0, 32, 64, 32)
        painter.end()
        icon.addPixmap(pixmap)
        return icon

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        # Toolbar section for select, node, edge
        icon_size = QSize(32, 32)
        self.select = QToolButton(self, checkable=True, checked=True)  # Selected by default
        self.vertex = QToolButton(self, checkable=True)
        self.edge = QToolButton(self, checkable=True)
        self.select.setToolTip("Select (s)")
        self.vertex.setToolTip("Add Vertex (v)")
        self.edge.setToolTip("Add Edge (e)")
        self.select.setIcon(QIcon(get_data("icons/tikzit-tool-select.svg")))
        self.vertex.setIcon(QIcon(get_data("icons/tikzit-tool-node.svg")))
        self.edge.setIcon(QIcon(get_data("icons/tikzit-tool-edge.svg")))
        self.select.setShortcut("s")
        self.vertex.setShortcut("v")
        self.edge.setShortcut("e")
        self.select.setIconSize(icon_size)
        self.vertex.setIconSize(icon_size)
        self.edge.setIconSize(icon_size)
        self.select.clicked.connect(lambda: self._tool_clicked(ToolType.SELECT))
        self.vertex.clicked.connect(lambda: self._tool_clicked(ToolType.VERTEX))
        self.edge.clicked.connect(lambda: self._tool_clicked(ToolType.EDGE))
        yield ToolbarSection(self.select, self.vertex, self.edge, exclusive=True)

        self.start_derivation = QToolButton(self, text="Start Derivation")
        self.start_derivation.clicked.connect(self._start_derivation)
        yield ToolbarSection(self.start_derivation)

    def _tool_clicked(self, tool: ToolType) -> None:
        self.graph_scene.curr_tool = tool

    def _vty_clicked(self, vty: VertexType.Type) -> None:
        self._curr_vty = vty
        selected = list(self.graph_scene.selected_vertices)
        if len(selected) > 0:
            cmd = ChangeNodeType(self.graph_view, selected, vty)
            self.undo_stack.push(cmd)

    def _ety_clicked(self, ety: EdgeType.Type) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety
        selected = list(self.graph_scene.selected_edges)
        if len(selected) > 0:
            cmd = ChangeEdgeColor(self.graph_view, selected, ety)
            self.undo_stack.push(cmd)

    def _add_vert(self, x: float, y: float) -> None:
        if self._curr_vty == VertexType.W_OUTPUT:
            cmd = AddWNode(self.graph_view, x, y)
        else:
            cmd = AddNode(self.graph_view, x, y, self._curr_vty)
        self.undo_stack.push(cmd)

    def _add_edge(self, u: VT, v: VT) -> None:
        g = self.graph_scene.g
        if vertex_is_w(g.type(u)) and get_w_partner(g, u) == v:
            return
        if g.type(u) == VertexType.W_INPUT and len(g.neighbors(u)) >= 2 or \
           g.type(v) == VertexType.W_INPUT and len(g.neighbors(v)) >= 2:
            return
        cmd = AddEdge(self.graph_view, u, v, self._curr_ety)
        self.undo_stack.push(cmd)

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
        self.undo_stack.push(cmd)

    def _vert_double_clicked(self, v: VT) -> None:
        if self.graph.type(v) == VertexType.BOUNDARY:
            input_, ok = QInputDialog.getText(
                self, "Input Dialog", "Enter Qubit Index:"
            )
            try:
                self.graph.set_qubit(v, int(input_.strip()))
            except ValueError:
                show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1, 2)")
            return
        elif vertex_is_w(self.graph.type(v)):
            return

        input_, ok = QInputDialog.getText(
            self, "Input Dialog", "Enter Desired Phase Value:"
        )
        if not ok:
            return
        try:
            new_phase = string_to_phase(input_)
        except ValueError:
            show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1/2, 2)")
            return
        cmd = ChangePhase(self.graph_view, v, new_phase)
        self.undo_stack.push(cmd)

    def paste_graph(self, graph: GraphT) -> None:
        if graph is None: return
        new_g = copy.deepcopy(self.graph_scene.g)
        new_verts, new_edges = new_g.merge(graph.translate(0.5,0.5))
        cmd = UpdateGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)
        self.graph_scene.select_vertices(new_verts)

    def delete_selection(self) -> None:
        selection = list(self.graph_scene.selected_vertices)
        selected_edges = list(self.graph_scene.selected_edges)
        rem_vertices = selection.copy()
        for v in selection:
            if vertex_is_w(self.graph_scene.g.type(v)):
                rem_vertices.append(get_w_partner(self.graph_scene.g, v))
        if not rem_vertices and not selected_edges: return
        new_g = copy.deepcopy(self.graph_scene.g)
        self.graph_scene.clearSelection()
        new_g.remove_edges(selected_edges)
        new_g.remove_vertices(list(set(rem_vertices)))
        cmd = SetGraph(self.graph_view,new_g) if len(set(rem_vertices)) > 128 \
            else UpdateGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)

    def _start_derivation(self) -> None:
        self.start_derivation_signal.emit(copy.deepcopy(self.graph_scene.g))

def string_to_phase(string: str) -> Fraction:
    if not string:
        return Fraction(0)
    try:
        s = string.lower().replace(' ', '')
        s = s.replace('\u03c0', '').replace('pi', '')
        if '.' in s or 'e' in s:
            return Fraction(float(s))
        elif '/' in s:
            a, b = s.split("/", 2)
            if not a:
                return Fraction(1, int(b))
            if a == '-':
                a = '-1'
            return Fraction(int(a), int(b))
        else:
            return Fraction(int(s))
    except ValueError:
        return sympify(string)
