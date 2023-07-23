import copy
from typing import Iterator, Union

import pyzx
from PySide6.QtCore import QPointF, QPersistentModelIndex, Qt, \
    QModelIndex, QItemSelection, QRect, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QFontMetrics
from PySide6.QtWidgets import QWidget, QToolButton, QHBoxLayout, QListView, \
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
from pyzx import VertexType, basicrules

from .common import VT, GraphT
from .base_panel import BasePanel, ToolbarSection
from .commands import MoveNode, AddRewriteStep, GoToRewriteStep
from .graphscene import GraphScene
from .graphview import GraphTool
from .proof import ProofModel
from .vitem import VItem, DragState, ZX_GREEN
from . import proof_actions
from . import animations as anims


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: GraphT) -> None:
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        super().__init__(graph, self.graph_scene)

        self.init_action_groups()

        self.graph_view.wand_trace_finished.connect(self._magic_slice)
        self.graph_scene.vertex_dragged.connect(self._vertex_dragged)
        self.graph_scene.vertex_dropped_onto.connect(self._vertex_dropped_onto)

        self.step_view = QListView(self)
        self.proof_model = ProofModel(self.graph_view.graph_scene.g)
        self.step_view.setModel(self.proof_model)
        self.step_view.setPalette(QColor(255, 255, 255))
        self.step_view.setSpacing(0)
        self.step_view.setItemDelegate(ProofStepItemDelegate())
        self.step_view.setCurrentIndex(self.proof_model.index(0, 0))
        self.step_view.selectionModel().selectionChanged.connect(self._proof_step_selected)

        self.panel_widget.layout().addWidget(self.step_view)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        self.selection = QToolButton(self, text="Selection", checkable=True, checked=True)
        self.magic_wand = QToolButton(self, text="Magic Wand", checkable=True)

        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        self.selection.clicked.connect(self._selection_clicked)

        yield ToolbarSection(self.selection, self.magic_wand, exclusive=True)

    def init_action_groups(self):
        self.action_groups = [proof_actions.actions_basic.copy()]
        for group in reversed(self.action_groups):
            hlayout = QHBoxLayout()
            group.init_buttons(self)
            for action in group.actions:
                hlayout.addWidget(action.button)
            hlayout.addStretch()

            widget = QWidget()
            widget.setLayout(hlayout)
            self.layout().insertWidget(1,widget)

    def parse_selection(self):
        selection = list(self.graph_scene.selected_vertices)
        g = self.graph_scene.g
        edges = []
        for e in g.edges():
            s,t = g.edge_st(e)
            if s in selection and t in selection:
                edges.append(e)

        return selection, edges

    def update_on_selection(self):
        selection, edges = self.parse_selection()
        g = self.graph_scene.g

        for group in self.action_groups:
            group.update_active(g,selection,edges)

    def _selection_clicked(self):
        self.graph_view.tool = GraphTool.Selection

    def _magic_wand_clicked(self):
        self.graph_view.tool = GraphTool.MagicWand

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNode(self.graph_view, vs)
        self.undo_stack.push(cmd)

    def _vertex_dragged(self, state: DragState, v: VT, w: VT) -> None:
        if state == DragState.Onto:
            if pyzx.basicrules.check_fuse(self.graph, v, w):
                anims.anticipate_fuse(self.graph_scene.vertex_map[w])
            elif pyzx.basicrules.check_strong_comp(self.graph, v, w):
                anims.anticipate_strong_comp(self.graph_scene.vertex_map[w])
        else:
            anims.back_to_default(self.graph_scene.vertex_map[w])

    def _vertex_dropped_onto(self, v: VT, w: VT) -> None:
        if pyzx.basicrules.check_fuse(self.graph, v, w):
            g = copy.deepcopy(self.graph)
            pyzx.basicrules.fuse(g, w, v)
            anim = anims.fuse(self.graph_scene.vertex_map[v], self.graph_scene.vertex_map[w])
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "fuse spiders")
            self.undo_stack.push(cmd, anim_before=anim)
        elif pyzx.basicrules.check_strong_comp(self.graph, v, w):
            g = copy.deepcopy(self.graph)
            pyzx.basicrules.strong_comp(g, w, v)
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = AddRewriteStep(self.graph_view, g, self.step_view, "bialgebra")
            self.undo_stack.push(cmd, anim_after=anim)

    def _magic_slice(self, trace):
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return
        item = filtered[0]
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return
        
        if basicrules.check_remove_id(self.graph, vertex):
            self._remove_id(vertex)
            return

        if trace.end.y() > trace.start.y():
            dir = trace.end - trace.start
        else:
            dir = trace.start - trace.end
        normal = QPointF(-dir.y(), dir.x())
        pos = QPointF(self.graph.row(vertex), self.graph.qubit(vertex))
        left, right = [], []
        for neighbor in self.graph.neighbors(vertex):
            npos = QPointF(self.graph.row(neighbor), self.graph.qubit(neighbor))
            dot = QPointF.dotProduct(pos - npos, normal)
            if dot <= 0:
                left.append(neighbor)
            else:
                right.append(neighbor)
        self._unfuse(vertex, left)

    def _remove_id(self, v: VT) -> None:
        new_g = copy.deepcopy(self.graph)
        basicrules.remove_id(new_g, v)
        anim = anims.remove_id(self.graph_scene.vertex_map[v])
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "id")
        self.undo_stack.push(cmd, anim_before=anim)

    def _unfuse(self, v: VT, left_neighbours: list[VT]) -> None:
        new_g = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(v), qubit=self.graph.qubit(v),
                                     row=self.graph.row(v) - 0.25)
        new_g.set_row(v, self.graph.row(v) + 0.25)
        for neighbor in left_neighbours:
            new_g.add_edge((neighbor, left_vert),
                           self.graph.edge_type((v, neighbor)))
            new_g.remove_edge((v, neighbor))
        new_g.add_edge((v, left_vert))
        anim = anims.unfuse(self.graph, new_g, v, self.graph_scene)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "unfuse")
        self.undo_stack.push(cmd, anim_after=anim)

    def _proof_step_selected(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        if not selected or not deselected:
            return
        cmd = GoToRewriteStep(self.graph_view, self.step_view, deselected.first().topLeft().row(), selected.first().topLeft().row())
        self.undo_stack.push(cmd)


class ProofStepItemDelegate(QStyledItemDelegate):
    """This class controls the painting of items in the proof steps list view.

    We paint a "git-style" line with circles to denote individual steps in a proof.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()

        # Draw background
        painter.setPen(Qt.GlobalColor.transparent)
        if option.state & QStyle.State_Selected:
            painter.setBrush(QColor(204, 232, 255))
        # TODO: Why is hover not working?
        elif option.state & QStyle.State_MouseOver:
            painter.setBrush(QColor(229, 243, 255))
        else:
            painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(option.rect)

        # Draw line
        is_last = index.row() == index.model().rowCount() - 1
        line_rect = QRect(
            self.line_padding,
            option.rect.y(),
            self.line_width,
            option.rect.height() if not is_last else option.rect.height() / 2
        )
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawRect(line_rect)

        # Draw circle
        painter.setPen(QPen(Qt.GlobalColor.black, self.circle_outline_width))
        painter.setBrush(QColor(ZX_GREEN))
        circle_radius = self.circle_radius_selected if option.state & QStyle.State_Selected else self.circle_radius
        painter.drawEllipse(
            QPointF(self.line_padding + self.line_width / 2, option.rect.y() + option.rect.height() / 2),
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.DisplayRole)
        text_height = QFontMetrics(option.font).height()
        text_rect = QRect(
            option.rect.x() + self.line_width + 2 * self.line_padding,
            option.rect.y() + option.rect.height() / 2 - text_height / 2,
            option.rect.width(),
            text_height
        )
        if option.state & QStyle.State_Selected:
            option.font.setWeight(QFont.Bold)
        painter.setFont(option.font)
        painter.setPen(Qt.GlobalColor.black)
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawText(text_rect, Qt.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), size.height() + 2 * self.vert_padding)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        return False

