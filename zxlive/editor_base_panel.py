from __future__ import annotations

import copy
from enum import Enum
from typing import Callable, Iterator, TypedDict

from PySide6.QtCore import QPoint, QPointF, QSize, Qt, Signal, QEasingCurve, QParallelAnimationGroup
from PySide6.QtGui import (QAction, QColor, QIcon, QPainter, QPalette, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout,
                               QInputDialog, QLabel, QListView, QListWidget,
                               QListWidgetItem, QScrollArea, QSizePolicy,
                               QSpacerItem, QSplitter, QToolButton, QWidget)
from pyzx import EdgeType, VertexType
from pyzx.utils import get_w_partner, vertex_is_w, phase_to_s, get_z_box_label
from pyzx.graph.jsonparser import string_to_phase
from zxlive.sfx import SFXEnum

from .base_panel import BasePanel, ToolbarSection
from .commands import (BaseCommand, AddEdge, AddEdges, AddNode, AddNodeSnapped, AddWNode, ChangeEdgeColor, ChangeEdgeCurve,
                       ChangeNodeType, ChangePhase, MergeNodes, MoveNode, SetGraph,
                       UpdateGraph)
from .common import VT, GraphT, ToolType, get_data, pos_from_view
from .dialogs import show_error_msg, update_dummy_vertex_text
from .eitem import EItem, HAD_EDGE_BLUE, EItemAnimation
from .vitem import VItem, BLACK, VItemAnimation
from .graphscene import EditGraphScene
from .settings import display_setting

from . import animations


class ShapeType(Enum):
    CIRCLE = 1
    SQUARE = 2
    TRIANGLE = 3
    LINE = 4
    DASHED_LINE = 5

class DrawPanelNodeType(TypedDict):
    text: str
    icon: tuple[ShapeType, QColor]


def vertices_data() -> dict[VertexType, DrawPanelNodeType]:
    return {
        VertexType.Z: {"text": "Z spider", "icon": (ShapeType.CIRCLE, display_setting.effective_colors["z_spider"])},
        VertexType.X: {"text": "X spider", "icon": (ShapeType.CIRCLE, display_setting.effective_colors["x_spider"])},
        VertexType.H_BOX: {"text": "H box", "icon": (ShapeType.SQUARE, display_setting.effective_colors["hadamard"])},
        VertexType.Z_BOX: {"text": "Z box", "icon": (ShapeType.SQUARE, display_setting.effective_colors["z_spider"])},
        VertexType.W_OUTPUT: {"text": "W node", "icon": (ShapeType.TRIANGLE, display_setting.effective_colors["w_output"])},
        VertexType.BOUNDARY: {"text": "boundary", "icon": (ShapeType.CIRCLE, display_setting.effective_colors["w_input"])},
        VertexType.DUMMY: {"text": "Dummy", "icon": (ShapeType.CIRCLE, display_setting.effective_colors["dummy"])},
    }

def edges_data() -> dict[EdgeType, DrawPanelNodeType]:
    return {
        EdgeType.SIMPLE: {"text": "Simple", "icon": (ShapeType.LINE, QColor(BLACK))},
        EdgeType.HADAMARD: {"text": "Hadamard", "icon": (ShapeType.DASHED_LINE, QColor(HAD_EDGE_BLUE))},
    }


class EditorBasePanel(BasePanel):
    """Base class implementing the shared functionality of graph edit
    and rule edit panels of ZXLive."""

    graph_scene: EditGraphScene
    start_derivation_signal = Signal(object)
    sidebar: QSplitter

    _curr_ety: EdgeType
    _curr_vty: VertexType
    snap_vertex_edge = True

    def __init__(self, *actions: QAction) -> None:
        super().__init__(*actions)
        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield from toolbar_select_node_edge(self)
        yield ToolbarSection(*self.actions())

    def create_side_bar(self) -> None:
        self.sidebar = QSplitter(self)
        self.sidebar.setOrientation(Qt.Orientation.Vertical)
        self.vertex_list = create_list_widget(self, vertices_data(), self._vty_clicked, self._vty_double_clicked)
        self.edge_list = create_list_widget(self, edges_data(), self._ety_clicked, self._ety_double_clicked)
        self.variable_viewer = VariableViewer(self)
        self.sidebar.addWidget(self.vertex_list)
        self.sidebar.addWidget(self.edge_list)
        self.sidebar.addWidget(self.variable_viewer)

    def update_side_bar(self) -> None:
        populate_list_widget(self.vertex_list, vertices_data(), self._vty_clicked, self._vty_double_clicked)
        populate_list_widget(self.edge_list, edges_data(), self._ety_clicked, self._ety_double_clicked)

    def update_colors(self) -> None:
        super().update_colors()
        self.update_side_bar()

    def _tool_clicked(self, tool: ToolType) -> None:
        self.graph_scene.curr_tool = tool

    def _snap_vertex_edge_clicked(self) -> None:
        self.snap_vertex_edge = not self.snap_vertex_edge

    def _vty_clicked(self, vty: VertexType) -> None:
        self._curr_vty = vty

    def _vty_double_clicked(self, vty: VertexType) -> None:
        self._curr_vty = vty
        selected = list(self.graph_scene.selected_vertices)
        if len(selected) > 0:
            cmd = ChangeNodeType(self.graph_view, selected, vty)
            self.undo_stack.push(cmd)

    def _ety_clicked(self, ety: EdgeType) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety

    def _ety_double_clicked(self, ety: EdgeType) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety
        selected = list(self.graph_scene.selected_edges)
        if len(selected) > 0:
            cmd = ChangeEdgeColor(self.graph_view, selected, ety)
            self.undo_stack.push(cmd)

    def paste_graph(self, graph: GraphT) -> None:
        new_g = copy.deepcopy(self.graph_scene.g)
        new_verts, new_edges = new_g.merge(graph.translate(0.5, 0.5))
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
        new_g.remove_edges(selected_edges)
        new_g.remove_vertices(list(set(rem_vertices)))
        cmd = SetGraph(self.graph_view,new_g) if len(set(rem_vertices)) > 128 \
            else UpdateGraph(self.graph_view,new_g)
        self.undo_stack.push(cmd)

    def merge_vertices(self) -> None:
        """Merge selected vertices"""
        selected = list(self.graph_scene.selected_vertices)
        if len(selected) < 2:
            return
        cmd = MergeNodes(self.graph_view, selected)
        self.undo_stack.push(cmd)

    def add_vert(self, x: float, y: float, edges: list[EItem]) -> None:
        """Add a vertex at point (x,y). `edges` is a list of EItems that are underneath the current position.
        We will try to connect the vertex to an edge.
        """
        cmd: BaseCommand
        if self.snap_vertex_edge and edges and self._curr_vty != VertexType.W_OUTPUT:
            # Trying to snap vertex to an edge
            for it in edges:
                e = it.e
                g = self.graph_scene.g
                if self.graph_scene.g.edge_type(e) not in (EdgeType.SIMPLE, EdgeType.HADAMARD):
                    continue
                cmd = AddNodeSnapped(self.graph_view, x, y, self._curr_vty, e)
                self.play_sound_signal.emit(SFXEnum.THATS_A_SPIDER)
                self.undo_stack.push(cmd)
                g = cmd.g
                group = QParallelAnimationGroup()
                for e in [next(g.edges(cmd.s, cmd.added_vert)), next(g.edges(cmd.t, cmd.added_vert))]:
                    eitem = self.graph_scene.edge_map[e][0]
                    anim = animations.edge_thickness(eitem,3,400,
                                                     QEasingCurve(QEasingCurve.Type.InCubic),start=7)
                    group.addAnimation(anim)
                self.undo_stack.set_anim(group)
                return

        cmd = AddWNode(self.graph_view, x, y) if self._curr_vty == VertexType.W_OUTPUT \
                else AddNode(self.graph_view, x, y, self._curr_vty)
                
        self.play_sound_signal.emit(SFXEnum.THATS_A_SPIDER)
        self.undo_stack.push(cmd)

    def add_edge(self, u: VT, v: VT, verts: list[VItem]) -> None:
        """Add an edge between vertices u and v. `verts` is a list of VItems that collide with the edge.
        If self.snap_vertex_edge is true, then we try to connect `u` through all the `vertices` in `verts`, and then to `v`.
        """
        cmd: BaseCommand
        graph = self.graph_view.graph_scene.g
        if vertex_is_w(graph.type(u)) and get_w_partner(graph, u) == v:
            return None
        if graph.type(u) == VertexType.W_INPUT and len(graph.neighbors(u)) >= 2 or \
            graph.type(v) == VertexType.W_INPUT and len(graph.neighbors(v)) >= 2:
            return None
        if (graph.type(u) == VertexType.DUMMY and graph.type(v) != VertexType.DUMMY) or \
              (graph.type(u) != VertexType.DUMMY and graph.type(v) == VertexType.DUMMY):
            return None

        # We will try to connect all the vertices together in order
        # First we filter out the vertices that are not compatible with the edge.
        verts = [vitem for vitem in verts if not graph.type(vitem.v) == VertexType.W_INPUT] # we will be adding two edges, which is not compatible with W_INPUT
        # but first we check if there any vertices that we do want to additionally connect.
        if not self.snap_vertex_edge or not verts:
            cmd = AddEdge(self.graph_view, u, v, self._curr_ety)
            self.undo_stack.push(cmd)
            return
        
        ux, uy = graph.row(u), graph.qubit(u)
        # Line was drawn from u to v, we want to order vs with the earlier items first.
        def dist(vitem: VItem) -> float:
            return (graph.row(vitem.v) - ux)**2 + (graph.qubit(vitem.v) - uy)**2  # type: ignore
        verts.sort(key=dist)
        vs = [vitem.v for vitem in verts]
        pairs = [(u, vs[0])]
        for i in range(1, len(vs)):
            pairs.append((vs[i-1],vs[i]))
        pairs.append((vs[-1],v))
        cmd = AddEdges(self.graph_view, pairs, self._curr_ety)
        self.undo_stack.push(cmd)
        group = QParallelAnimationGroup()
        for vitem in verts:
            anim = animations.scale(vitem,1.0,400,QEasingCurve(QEasingCurve.Type.InCubic),start=1.3)
            group.addAnimation(anim)
        self.undo_stack.set_anim(group)

    def vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        self.undo_stack.push(MoveNode(self.graph_view, vs))

    def _vertex_dropped_onto(self, v: VT, w: VT) -> None:
        view_pos = self.graph_scene.vertex_map[v].pos()
        pos = pos_from_view(view_pos.x(), view_pos.y())
        self.vert_moved([(v, pos[0], pos[1])])

    def change_edge_curves(self, eitem: EItem, new_distance: float, old_distance: float) -> None:
        self.undo_stack.push(ChangeEdgeCurve(self.graph_view, eitem, new_distance, old_distance))

    def vert_double_clicked(self, v: VT) -> None:
        graph = self.graph
        old_variables = graph.var_registry.vars()
        if graph.type(v) == VertexType.BOUNDARY or vertex_is_w(graph.type(v)):
            return None
        if graph.type(v) == VertexType.DUMMY:
            new_g = update_dummy_vertex_text(self, self.graph_scene.g, v)
            if new_g is not None:
                self.undo_stack.push(SetGraph(self.graph_view, new_g))
            return
        phase_is_complex = (graph.type(v) == VertexType.Z_BOX)
        if phase_is_complex:
            prompt = "Enter desired phase value (complex value):"
            error_msg = "Please enter a valid input (e.g., -1+2j)."
            current_phase = str(get_z_box_label(graph, v))
        else:
            prompt = "Enter desired phase value (non-variables are multiples of pi):"
            error_msg = "Please enter a valid input. (e.g. pi/2, 1/2, 0.25, a+b)."
            current_phase = phase_to_s(graph.phase(v), graph.type(v))

        input_, ok = QInputDialog.getText(
            self, "Change Phase", prompt, text=current_phase
        )
        if not ok:
            return None
        try:
            new_phase = string_to_complex(input_) if phase_is_complex else string_to_phase(input_, graph)
        except ValueError:
            show_error_msg("Invalid Input", error_msg, parent=self)
            return None
        self.undo_stack.push(ChangePhase(self.graph_view, v, new_phase))
        # For some reason it is important we first push to the stack before we do the following.
        if len(graph.var_registry.vars()) != len(old_variables):
            new_vars = graph.var_registry.vars() - old_variables
            for nv in new_vars:
                self.variable_viewer.add_item(nv)


class VariableViewer(QScrollArea):

    def __init__(self, parent: EditorBasePanel) -> None:
        super().__init__()
        self.parent_panel = parent
        self._widget = QWidget()
        lpal = QApplication.palette("QListWidget")  # type: ignore
        palette = QPalette()
        palette.setBrush(QPalette.ColorRole.Window, lpal.base())
        self._widget.setAutoFillBackground(True)
        self._widget.setPalette(palette)
        self._layout = QGridLayout(self._widget)
        self._layout.setColumnStretch(0, 1)
        self._layout.setColumnStretch(1, 0)
        self._layout.setColumnStretch(2, 0)
        cb = QComboBox()
        cb.insertItems(0, ["Parametric", "Boolean"])
        self._layout.setColumnMinimumWidth(2, cb.minimumSizeHint().width())
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._items = 0

        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(3)
        vline.setLineWidth(1)
        vline.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._layout.addWidget(vline, 0, 1, -1, 1)

        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFixedHeight(3)
        hline.setLineWidth(1)
        hline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(hline, 1, 0, 1, -1)

        vlabel = QLabel("Variable")
        vlabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(vlabel, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        tlabel = QLabel("Type")
        tlabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(tlabel, 0, 2, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding), 2, 2)

        for name in self.parent_panel.graph.var_registry.vars():
            self.add_item(name)

        self.setWidget(self._widget)
        self.setWidgetResizable(True)

    def minimumSizeHint(self) -> QSize:
        if self._items == 0:
            return QSize(0, 0)
        else:
            return super().minimumSizeHint()

    def sizeHint(self) -> QSize:
        if self._items == 0:
            return QSize(0, 0)
        else:
            return super().sizeHint()

    def add_item(self, name: str) -> None:
        combobox = QComboBox()
        combobox.insertItems(0, ["Parametric", "Boolean"])
        is_bool = self.parent_panel.graph.var_registry.get_type(name, default=False)
        combobox.setCurrentIndex(1 if is_bool else 0)
        combobox.currentTextChanged.connect(lambda text: self._text_changed(name, text))
        item = self._layout.itemAtPosition(2 + self._items, 2)
        assert item is not None # For mypy
        self._layout.removeItem(item)
        self._layout.addWidget(QLabel(f"<pre>{name}</pre>"), 2 + self._items, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._layout.addWidget(combobox, 2 + self._items, 2, Qt.AlignmentFlag.AlignCenter)
        self._layout.setRowStretch(2 + self._items, 0)
        self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding), 3 + self._items, 2)
        self._layout.setRowStretch(3 + self._items, 1)
        self._layout.update()
        self._items += 1
        self._widget.updateGeometry()

        if self._items == 1:
            self.updateGeometry()

    def _text_changed(self, name: str, text: str) -> None:
        from .rule_panel import RulePanel
        if text == "Parametric":
            new_type = False
        elif text == "Boolean":
            new_type = True
        else:
            raise ValueError("Unknown variable type")
        if isinstance(self.parent_panel, RulePanel):
            self.parent_panel.graph_scene_left.g.var_registry.set_type(name, new_type)
            self.parent_panel.graph_scene_right.g.var_registry.set_type(name, new_type)
        else:
            self.parent_panel.graph_scene.g.var_registry.set_type(name, new_type)


def toolbar_select_node_edge(parent: EditorBasePanel) -> Iterator[ToolbarSection]:
    icon_size = QSize(32, 32)
    select = QToolButton(parent)  # Selected by default
    vertex = QToolButton(parent)
    edge = QToolButton(parent)
    select.setCheckable(True)
    vertex.setCheckable(True)
    edge.setCheckable(True)
    select.setChecked(True)
    select.setToolTip("Select (s)")
    vertex.setToolTip("Add Vertex (v)")
    edge.setToolTip("Add Edge (e)")
    select.setIcon(QIcon(get_data("icons/tikzit-tool-select.svg")))
    vertex.setIcon(QIcon(get_data("icons/tikzit-tool-node.svg")))
    edge.setIcon(QIcon(get_data("icons/tikzit-tool-edge.svg")))
    select.setShortcut("s")
    vertex.setShortcut("v")
    edge.setShortcut("e")
    select.setIconSize(icon_size)
    vertex.setIconSize(icon_size)
    edge.setIconSize(icon_size)
    select.clicked.connect(lambda: parent._tool_clicked(ToolType.SELECT))
    vertex.clicked.connect(lambda: parent._tool_clicked(ToolType.VERTEX))
    edge.clicked.connect(lambda: parent._tool_clicked(ToolType.EDGE))
    yield ToolbarSection(select, vertex, edge, exclusive=True)

    snap = QToolButton(parent)
    snap.setCheckable(True)
    snap.setChecked(True)
    snap.setIcon(QIcon(get_data("icons/vertex-snap-to-edge.svg")))
    snap.setToolTip("Snap vertices to the edge beneath them when adding vertices or edges (f)")
    snap.setShortcut("f")
    snap.clicked.connect(lambda: parent._snap_vertex_edge_clicked())
    yield ToolbarSection(snap)


def create_list_widget(parent: EditorBasePanel,
                       data: dict[VertexType, DrawPanelNodeType] | dict[EdgeType, DrawPanelNodeType],
                       onclick: Callable[[VertexType], None] | Callable[[EdgeType], None],
                       ondoubleclick: Callable[[VertexType], None] | Callable[[EdgeType], None]) \
                          -> QListWidget:
    list_widget = QListWidget(parent)
    list_widget.setResizeMode(QListView.ResizeMode.Adjust)
    list_widget.setViewMode(QListView.ViewMode.IconMode)
    list_widget.setMovement(QListView.Movement.Static)
    list_widget.setUniformItemSizes(True)
    list_widget.setWordWrap(True)
    list_widget.setIconSize(QSize(24, 24))
    populate_list_widget(list_widget, data, onclick, ondoubleclick)
    list_widget.setCurrentItem(list_widget.item(0))
    return list_widget


def populate_list_widget(list_widget: QListWidget,
                         data: dict[VertexType, DrawPanelNodeType] | dict[EdgeType, DrawPanelNodeType],
                         onclick: Callable[[VertexType], None] | Callable[[EdgeType], None],
                         ondoubleclick: Callable[[VertexType], None] | Callable[[EdgeType], None]) \
                            -> None:
    row = list_widget.currentRow()
    list_widget.clear()
    for typ, value in data.items():
        icon = create_icon(*value["icon"])
        item = QListWidgetItem(icon, value["text"])
        item.setData(Qt.ItemDataRole.UserRole, typ)
        list_widget.addItem(item)
    list_widget.itemClicked.connect(lambda x: onclick(x.data(Qt.ItemDataRole.UserRole)))
    list_widget.itemDoubleClicked.connect(lambda x: ondoubleclick(x.data(Qt.ItemDataRole.UserRole)))
    list_widget.setCurrentRow(row)


def create_icon(shape: ShapeType, color: QColor) -> QIcon:
    icon = QIcon()
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(BLACK), 6))
    painter.setBrush(color)
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


def string_to_complex(string: str) -> complex:
    return complex(string) if string else complex(0)
