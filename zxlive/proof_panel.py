from __future__ import annotations

import copy
import os
from typing import Iterator, Union, cast

import pyzx
from PySide6.QtCore import (QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPointF, QRect, QSize, Qt)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon,
                           QPainter, QPen, QVector2D)
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QListView,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QToolButton, QWidget,
                               QVBoxLayout)
from pyzx import VertexType, basicrules

from . import animations as anims
from . import proof_actions
from .base_panel import BasePanel, ToolbarSection
from .commands import AddRewriteStep, GoToRewriteStep, MoveNodeInStep
from .common import (CUSTOM_RULES_PATH, ET, SCALE, VT, GraphT, get_data,
                     pos_from_view, pos_to_view)
from .custom_rule import CustomRule
from .eitem import EItem
from .graphscene import GraphScene
from .graphview import GraphTool, GraphView, WandTrace
from .proof import ProofModel
from .vitem import ZX_GREEN, DragState, VItem


class ProofPanel(BasePanel):
    """Panel for the proof mode of ZX live."""

    def __init__(self, graph: GraphT, *actions: QAction) -> None:
        super().__init__(*actions)
        self.graph_scene = GraphScene()
        self.graph_scene.vertices_moved.connect(self._vert_moved)
        # TODO: Right now this calls for every single vertex selected, even if we select many at the same time
        self.graph_scene.selectionChanged.connect(self.update_on_selection)
        self.graph_scene.vertex_double_clicked.connect(self._vert_double_clicked)


        self.graph_view = GraphView(self.graph_scene)
        self.splitter.addWidget(self.graph_view)
        self.graph_view.set_graph(graph)

        self.init_action_groups()

        self.graph_view.wand_trace_finished.connect(self._wand_trace_finished)
        self.graph_scene.vertex_dragged.connect(self._vertex_dragged)
        self.graph_scene.vertex_dropped_onto.connect(self._vertex_dropped_onto)

        self.step_view = QListView(self)
        self.proof_model = ProofModel(self.graph_view.graph_scene.g)
        self.step_view.setModel(self.proof_model)
        self.step_view.setPalette(QColor(255, 255, 255))
        self.step_view.setSpacing(0)
        self.step_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.step_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_view.setItemDelegate(ProofStepItemDelegate())
        self.step_view.setCurrentIndex(self.proof_model.index(0, 0))
        self.step_view.selectionModel().selectionChanged.connect(self._proof_step_selected)
        self.step_view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)

        self.splitter.addWidget(self.step_view)

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        icon_size = QSize(32, 32)
        self.selection = QToolButton(self)
        self.selection.setCheckable(True)
        self.selection.setChecked(True)
        self.magic_wand = QToolButton(self)
        self.magic_wand.setCheckable(True)
        self.selection.setIcon(QIcon(get_data("icons/tikzit-tool-select.svg")))
        self.magic_wand.setIcon(QIcon(get_data("icons/magic-wand.svg")))
        self.selection.setIconSize(icon_size)
        self.magic_wand.setIconSize(icon_size)
        self.selection.setToolTip("Select (s)")
        self.magic_wand.setToolTip("Magic Wand (w)")
        self.selection.setShortcut("s")
        self.magic_wand.setShortcut("w")
        self.selection.clicked.connect(self._selection_clicked)
        self.magic_wand.clicked.connect(self._magic_wand_clicked)
        yield ToolbarSection(self.selection, self.magic_wand, exclusive=True)

        self.identity_choice = (
            QToolButton(self),
            QToolButton(self)
        )
        self.identity_choice[0].setText("Z")
        self.identity_choice[0].setCheckable(True)
        self.identity_choice[0].setChecked(True)
        self.identity_choice[1].setText("Z")
        self.identity_choice[1].setCheckable(True)

        yield ToolbarSection(*self.identity_choice, exclusive=True)
        yield ToolbarSection(*self.actions())

    def init_action_groups(self) -> None:
        basic_rules = proof_actions.ProofActionGroup(*proof_actions.rewrites).copy()
        self.action_groups = [basic_rules]
        custom_rules = []
        for root, dirs, files in os.walk(CUSTOM_RULES_PATH):
            for file in files:
                if file.endswith(".zxr"):
                    zxr_file = os.path.join(root, file)
                    with open(zxr_file, "r") as f:
                        rule = CustomRule.from_json(f.read()).to_proof_action()
                        custom_rules.append(rule)
        self.action_groups.append(proof_actions.ProofActionGroup(*custom_rules).copy())
        for group in reversed(self.action_groups):
            hlayout = QHBoxLayout()
            group.init_buttons(self)
            for action in group.actions:
                assert action.button is not None
                hlayout.addWidget(action.button)
            hlayout.addStretch()

            widget = QWidget()
            widget.setLayout(hlayout)
            assert isinstance(layout := self.layout(), QVBoxLayout)
            layout.insertWidget(1, widget)

    def parse_selection(self) -> tuple[list[VT], list[ET]]:
        selection = list(self.graph_scene.selected_vertices)
        g = self.graph_scene.g
        edges = []
        for e in g.edges():
            s,t = g.edge_st(e)
            if s in selection and t in selection:
                edges.append(e)

        return selection, edges

    def update_on_selection(self) -> None:
        selection, edges = self.parse_selection()
        g = self.graph_scene.g

        for group in self.action_groups:
            group.update_active(g,selection,edges)

    def _vert_moved(self, vs: list[tuple[VT, float, float]]) -> None:
        cmd = MoveNodeInStep(self.graph_view, vs, self.step_view)
        self.undo_stack.push(cmd)

    def _selection_clicked(self) -> None:
        self.graph_view.tool = GraphTool.Selection

    def _magic_wand_clicked(self) -> None:
        self.graph_view.tool = GraphTool.MagicWand

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

    def _wand_trace_finished(self, trace: WandTrace) -> None:
        if self._magic_slice(trace):
            return
        elif self._magic_identity(trace):
            return

    def _magic_identity(self, trace: WandTrace) -> bool:
        if len(trace.hit) != 1 or not all(isinstance(item, EItem) for item in trace.hit):
            return False
        # We know that the type of `item` is `EItem` because of the check above
        item = cast(EItem, next(iter(trace.hit)))
        pos = trace.hit[item][-1]
        pos = QPointF(*pos_from_view(pos.x(), pos.y())) * SCALE
        s = self.graph.edge_s(item.e)
        t = self.graph.edge_t(item.e)

        if self.identity_choice[0].isChecked():
            vty: VertexType.Type = VertexType.Z
        elif self.identity_choice[1].isChecked():
            vty = VertexType.X
        else:
            raise ValueError("Neither of the spider types are checked.")

        new_g = copy.deepcopy(self.graph)
        v = new_g.add_vertex(vty, row=pos.x()/SCALE, qubit=pos.y()/SCALE)
        new_g.add_edge(self.graph.edge(s, v), self.graph.edge_type(item.e))
        new_g.add_edge(self.graph.edge(v, t))
        new_g.remove_edge(item.e)

        anim = anims.add_id(v, self.graph_scene)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "remove identity")
        self.undo_stack.push(cmd, anim_after=anim)
        return True

    def _magic_slice(self, trace: WandTrace) -> bool:
        def cross(a: QPointF, b: QPointF) -> float:
            return a.y() * b.x() - a.x() * b.y()
        filtered = [item for item in trace.hit if isinstance(item, VItem)]
        if len(filtered) != 1:
            return False
        item = filtered[0]
        vertex = item.v
        if self.graph.type(vertex) not in (VertexType.Z, VertexType.X):
            return False

        if basicrules.check_remove_id(self.graph, vertex):
            self._remove_id(vertex)
            return True

        start = trace.hit[item][0]
        end = trace.hit[item][-1]
        if start.y() > end.y():
            start, end = end, start
        pos = QPointF(*pos_to_view(self.graph.row(vertex), self.graph.qubit(vertex)))
        left, right = [], []
        for neighbor in self.graph.neighbors(vertex):
            npos = QPointF(*pos_to_view(self.graph.row(neighbor), self.graph.qubit(neighbor)))
            # Compute whether each neighbor is inside the entry and exit points
            i1 = cross(start - pos, npos - pos) * cross(start - pos, end - pos) >= 0
            i2 = cross(end - pos, npos - pos) * cross(end - pos, start - pos) >= 0
            inside = i1 and i2
            if inside:
                left.append(neighbor)
            else:
                right.append(neighbor)
        mouse_dir = ((start + end) * (1/2)) - pos
        self._unfuse(vertex, left, mouse_dir)
        return True

    def _remove_id(self, v: VT) -> None:
        new_g = copy.deepcopy(self.graph)
        basicrules.remove_id(new_g, v)
        anim = anims.remove_id(self.graph_scene.vertex_map[v])
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "id")
        self.undo_stack.push(cmd, anim_before=anim)

    def _unfuse(self, v: VT, left_neighbours: list[VT], mouse_dir: QPointF) -> None:
        def snap_vector(v: QVector2D) -> None:
            if abs(v.x()) > abs(v.y()):
                v.setY(0.0)
            else:
                v.setX(0.0)
            if not v.isNull():
                v.normalize()

        # Compute the average position of left vectors
        pos = QPointF(self.graph.row(v), self.graph.qubit(v))
        avg_left = QVector2D()
        for n in left_neighbours:
            npos = QPointF(self.graph.row(n), self.graph.qubit(n))
            dir = QVector2D(npos - pos).normalized()
            avg_left += dir
        avg_left.normalize()
        # And snap it to the grid
        snap_vector(avg_left)
        # Same for right vectors
        avg_right = QVector2D()
        for n in self.graph.neighbors(v):
            if n in left_neighbours: continue
            npos = QPointF(self.graph.row(n), self.graph.qubit(n))
            dir = QVector2D(npos - pos).normalized()
            avg_right += dir
        avg_right.normalize()
        snap_vector(avg_right)
        if avg_right.isNull():
            avg_right = -avg_left
        elif avg_left.isNull():
            avg_left = -avg_right

        dist = 0.25 if QVector2D.dotProduct(avg_left, avg_right) != 0 else 0.35
        # Put the phase on the left hand side if the mouse direction is further
        # away from the average direction of the left neighbours than the right.
        phase_left = QVector2D.dotProduct(QVector2D(mouse_dir), avg_left) \
            <= QVector2D.dotProduct(QVector2D(mouse_dir), avg_right)

        new_g = copy.deepcopy(self.graph)
        left_vert = new_g.add_vertex(self.graph.type(v),
                                     qubit=self.graph.qubit(v) + dist*avg_left.y(),
                                     row=self.graph.row(v) + dist*avg_left.x())
        new_g.set_row(v, self.graph.row(v) + dist*avg_right.x())
        new_g.set_qubit(v, self.graph.qubit(v) + dist*avg_right.y())
        for neighbor in left_neighbours:
            new_g.add_edge((neighbor, left_vert),
                           self.graph.edge_type((v, neighbor)))
            new_g.remove_edge((v, neighbor))
        new_g.add_edge((v, left_vert))
        if phase_left:
            new_g.set_phase(left_vert, new_g.phase(v))
            new_g.set_phase(v, 0)

        anim = anims.unfuse(self.graph, new_g, v, self.graph_scene)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "unfuse")
        self.undo_stack.push(cmd, anim_after=anim)

    def _vert_double_clicked(self, v: VT) -> None:
        if self.graph.type(v) == VertexType.BOUNDARY:
            return

        new_g = copy.deepcopy(self.graph)
        basicrules.color_change(new_g, v)
        cmd = AddRewriteStep(self.graph_view, new_g, self.step_view, "color change")
        self.undo_stack.push(cmd)

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
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(204, 232, 255))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QColor(229, 243, 255))
        else:
            painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(option.rect)

        # Draw line
        is_last = index.row() == index.model().rowCount() - 1
        line_rect = QRect(
            self.line_padding,
            int(option.rect.y()),
            self.line_width,
            int(option.rect.height() if not is_last else option.rect.height() / 2)
        )
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawRect(line_rect)

        # Draw circle
        painter.setPen(QPen(Qt.GlobalColor.black, self.circle_outline_width))
        painter.setBrush(QColor(ZX_GREEN))
        circle_radius = self.circle_radius_selected if option.state & QStyle.StateFlag.State_Selected else self.circle_radius
        painter.drawEllipse(
            QPointF(self.line_padding + self.line_width / 2, option.rect.y() + option.rect.height() / 2),
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_height = QFontMetrics(option.font).height()
        text_rect = QRect(
            int(option.rect.x() + self.line_width + 2 * self.line_padding),
            int(option.rect.y() + option.rect.height() / 2 - text_height / 2),
            option.rect.width(),
            text_height
        )
        if option.state & QStyle.StateFlag.State_Selected:
            option.font.setWeight(QFont.Weight.Bold)
        painter.setFont(option.font)
        painter.setPen(Qt.GlobalColor.black)
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), size.height() + 2 * self.vert_padding)

