import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel, QAbstractListModel,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QSize, Qt)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QListView, QMenu,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QWidget)

from .common import GraphT
from .settings import display_setting


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str  # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # New graph after applying the rewrite
    grouped_rewrites: Optional[list['Rewrite']] = None  # Optional field to store the grouped rewrites

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the rewrite to Python dictionary."""
        return {
            "display_name": self.display_name,
            "rule": self.rule,
            "graph": self.graph.to_dict(),
            "grouped_rewrites": [r.to_dict() for r in self.grouped_rewrites] if self.grouped_rewrites else None
        }

    def to_json(self) -> str:
        """Serializes the rewrite to JSON."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(json_str: Union[str, Dict[str, Any]]) -> "Rewrite":
        """Deserializes the rewrite from JSON or Python dict."""
        if isinstance(json_str, str):
            d = json.loads(json_str)
        else:
            d = json_str
        grouped_rewrites = d.get("grouped_rewrites")
        graph = GraphT.from_json(d["graph"])
        assert isinstance(graph, GraphT)
        graph.set_auto_simplify(False)

        return Rewrite(
            display_name=d.get("display_name", d["rule"]),  # Old proofs may not have display names
            rule=d["rule"],
            graph=graph,
            grouped_rewrites=[Rewrite.from_json(r) for r in grouped_rewrites] if grouped_rewrites else None
        )


class ProofModel(QAbstractListModel):
    """List model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore, we store the
    rewrite that was used to go from one graph to next.
    """

    initial_graph: GraphT
    steps: list[Rewrite]

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.initial_graph = start_graph
        self.steps = []

    def set_graph(self, index: int, graph: GraphT) -> None:
        if index == 0:
            self.initial_graph = graph
        else:
            old_step = self.steps[index - 1]
            new_step = Rewrite(old_step.display_name, old_step.rule, graph)
            self.steps[index - 1] = new_step

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if index.row() >= len(self.steps) + 1 or index.column() >= 1:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.row() == 0:
                return "START"
            else:
                return self.steps[index.row() - 1].display_name
        elif role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)

    def flags(self, index: Union[QModelIndex, QPersistentModelIndex]) -> Qt.ItemFlag:
        if index.row() == 0:
            return super().flags(index)
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.headerData`.

        Indicates that this model doesn't have a header.
        """
        return None

    def columnCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of columns"""
        return 1

    def rowCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on tree models, the
        # user has to specify the index of the parent. In a list, we always expect the
        # parent to be `None` or the empty `QModelIndex()`
        if not parent or not parent.isValid():
            return len(self.steps) + 1
        else:
            return 0

    def add_rewrite(self, rewrite: Rewrite, position: Optional[int] = None) -> None:
        """Adds a rewrite step to the model."""
        if position is None:
            position = len(self.steps)
        self.beginInsertRows(QModelIndex(), position + 1, position + 1)
        self.steps.insert(position, rewrite)
        self.endInsertRows()

    def pop_rewrite(self, position: Optional[int] = None) -> tuple[Rewrite, GraphT]:
        """Removes the latest rewrite from the model.

        Returns the rewrite and the graph that previously resulted from this rewrite.
        """
        if position is None:
            position = len(self.steps) - 1
        self.beginRemoveRows(QModelIndex(), position + 1, position + 1)
        rewrite = self.steps.pop(position)
        self.endRemoveRows()
        return rewrite, rewrite.graph

    def get_graph(self, index: int) -> GraphT:
        """Returns the graph at a given position in the proof."""
        if index == 0:
            copy = self.initial_graph.copy()
        else:
            copy = self.steps[index - 1].graph.copy()
        assert isinstance(copy, GraphT)
        return copy

    def rename_step(self, index: int, name: str) -> None:
        """Change the display name"""
        old_step = self.steps[index]

        # Must create a new Rewrite object instead of modifying current object
        # since Rewrite inherits NamedTuple and is hence immutable
        self.steps[index] = Rewrite(name, old_step.rule, old_step.graph, old_step.grouped_rewrites)

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index` with a new grouped step"""
        new_rewrite = Rewrite(
            "Grouped Steps: " + " \u2192 ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
            "Grouped",
            self.get_graph(end_index + 1),
            self.steps[start_index:end_index + 1]
        )
        for _ in range(end_index - start_index + 1):
            self.pop_rewrite(start_index)[0]
        self.add_rewrite(new_rewrite, start_index)
        modelIndex = self.createIndex(start_index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def ungroup_steps(self, index: int) -> None:
        """Replace the grouped step at `index` with the individual_steps"""
        individual_steps = self.steps[index].grouped_rewrites
        if individual_steps is None:
            raise ValueError("Step is not grouped")
        self.pop_rewrite(index)
        for i, step in enumerate(individual_steps):
            self.add_rewrite(step, index + i)
        self.dataChanged.emit(self.createIndex(index, 0),
                              self.createIndex(index + len(individual_steps), 0),
                              [])

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the model to Python dict."""
        initial_graph = self.initial_graph.to_dict()
        proof_steps = [step.to_dict() for step in self.steps]

        return {
            "initial_graph": initial_graph,
            "proof_steps": proof_steps
        }

    def to_json(self) -> str:
        """Serializes the model to JSON."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(json_str: Union[str, Dict[str, Any]]) -> "ProofModel":
        """Deserializes the model from JSON or Python dict."""
        if isinstance(json_str, str):
            d = json.loads(json_str)
        else:
            d = json_str
        initial_graph = GraphT.from_json(d["initial_graph"])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        if TYPE_CHECKING:
            assert isinstance(initial_graph, GraphT)
        initial_graph.set_auto_simplify(False)
        model = ProofModel(initial_graph)
        for step in d["proof_steps"]:
            rewrite = Rewrite.from_json(step)
            model.add_rewrite(rewrite)
        return model


class ProofStepView(QListView):
    """A view for displaying the steps in a proof."""

    def __init__(self, parent: 'ProofPanel'):
        super().__init__(parent)
        self.graph_view = parent.graph_view
        self.undo_stack = parent.undo_stack
        self.expanded_groups: set[int] = set()
        self.setModel(ProofModel(self.graph_view.graph_scene.g))
        self.setCurrentIndex(self.model().index(0, 0))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        # Set background color for dark mode (panel background)
        if display_setting.dark_mode:
            self.setStyleSheet("background-color: #23272e;")
        else:
            self.setStyleSheet("")
        # Set background color for dark mode
        pal = self.palette()
        if display_setting.dark_mode:
            pal.setColor(self.backgroundRole(), QColor(35, 39, 46))
            pal.setColor(self.viewport().backgroundRole(), QColor(35, 39, 46))
        else:
            pal.setColor(self.backgroundRole(), QColor(255, 255, 255))
            pal.setColor(self.viewport().backgroundRole(), QColor(255, 255, 255))
        self.setPalette(pal)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(False)
        self.setAlternatingRowColors(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setItemDelegate(ProofStepItemDelegate(self))

    # overriding this method to change the return type and stop mypy from complaining
    def model(self) -> ProofModel:
        model = super().model()
        assert isinstance(model, ProofModel)
        return model

    def set_model(self, model: ProofModel) -> None:
        self.setModel(model)
        self.expanded_groups.clear()
        # it looks like the selectionModel is linked to the model, so after updating the model we need to reconnect the selectionModel signals.
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setCurrentIndex(model.index(len(model.steps), 0))

    def toggle_group_expansion(self, step_index: int) -> None:
        """Toggle the expanded/collapsed state of a grouped step."""
        if step_index in self.expanded_groups:
            self.expanded_groups.discard(step_index)
        else:
            self.expanded_groups.add(step_index)
        model_index = self.model().index(step_index + 1, 0)
        self.model().dataChanged.emit(model_index, model_index, [])
        self.doItemsLayout()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Handle mouse clicks on grouped steps to toggle expansion.

        Collapsed group: clicking anywhere on the row toggles expansion.
        Expanded group: clicking in the header area (top row) collapses it;
        clicking in the sub-step area only selects the step.
        """
        index = self.indexAt(event.pos())
        toggle_idx = -1

        if index.isValid() and index.row() > 0:
            step_idx = index.row() - 1
            if step_idx < len(self.model().steps):
                step = self.model().steps[step_idx]
                if step.grouped_rewrites is not None:
                    delegate = self.itemDelegate()
                    if isinstance(delegate, ProofStepItemDelegate):
                        if step_idx in self.expanded_groups:
                            # Expanded: only collapse when clicking the header row
                            rect = self.visualRect(index)
                            text_h = QFontMetrics(self.font()).height()
                            header_h = text_h + 2 * delegate.vert_padding
                            if event.pos().y() - rect.y() <= header_h:
                                toggle_idx = step_idx
                        else:
                            # Collapsed: any click on the row toggles
                            toggle_idx = step_idx

        super().mousePressEvent(event)

        if toggle_idx >= 0:
            self.toggle_group_expansion(toggle_idx)

    def move_to_step(self, index: int) -> None:
        idx = self.model().index(index, 0, QModelIndex())
        self.clearSelection()
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(idx)
        self.selectionModel().blockSignals(False)
        self.update(idx)
        g = self.model().get_graph(index)
        self.graph_view.set_graph(g)

    def show_context_menu(self, position: QPoint) -> None:
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return
        context_menu = QMenu(self)
        action_function_map = {}

        index = selected_indexes[0].row()
        if len(selected_indexes) > 1:
            group_action = context_menu.addAction("Group Steps")
            action_function_map[group_action] = self.group_selected_steps
        elif index != 0:
            rename_action = context_menu.addAction("Rename Step")
            action_function_map[rename_action] = lambda: self.edit(selected_indexes[0])
            if self.model().steps[index - 1].grouped_rewrites is not None:
                ungroup_action = context_menu.addAction("Ungroup Steps")
                action_function_map[ungroup_action] = self.ungroup_selected_step

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_function_map:
            action_function_map[action]()

    def rename_proof_step(self, new_name: str, index: int) -> None:
        from .commands import UndoableChange
        old_name = self.model().steps[index].display_name
        cmd = UndoableChange(self.graph_view,
                             lambda: self.model().rename_step(index, old_name),
                             lambda: self.model().rename_step(index, new_name))
        self.undo_stack.push(cmd)

    def proof_step_selected(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        if not selected or not deselected:
            return
        step_index = selected.first().topLeft().row()
        self.move_to_step(step_index)

    def group_selected_steps(self) -> None:
        from .commands import GroupRewriteSteps
        from .dialogs import show_error_msg
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) < 2:
            raise ValueError("Can only group two or more steps")

        indices = sorted(index.row() for index in selected_indexes)
        if indices[-1] - indices[0] != len(indices) - 1:
            show_error_msg("Can only group contiguous steps")
            raise ValueError("Can only group contiguous steps")
        if indices[0] == 0:
            show_error_msg("Cannot group the first step")
            raise ValueError("Cannot group the first step")

        self.move_to_step(indices[-1] - 1)
        cmd = GroupRewriteSteps(self.graph_view, self, indices[0] - 1, indices[-1] - 1)
        self.undo_stack.push(cmd)

    def ungroup_selected_step(self) -> None:
        from .commands import UngroupRewriteSteps
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) != 1:
            raise ValueError("Can only ungroup one step")

        index = selected_indexes[0].row()
        if index == 0 or self.model().steps[index - 1].grouped_rewrites is None:
            raise ValueError("Step is not grouped")

        self.move_to_step(index - 1)
        cmd = UngroupRewriteSteps(self.graph_view, self, index - 1)
        self.undo_stack.push(cmd)


class ProofStepItemDelegate(QStyledItemDelegate):
    """This class controls the painting of items in the proof steps list view.

    We paint a "git-style" line with circles to denote individual steps in a proof.
    Grouped steps render as expandable tree nodes with sub-step branches.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    # Sub-tree layout for expanded groups
    triangle_size = 5
    sub_indent = 20
    sub_branch_len = 15
    sub_circle_radius = 3

    def _step_info(self, index: Union[QModelIndex, QPersistentModelIndex]) -> tuple[bool, bool, Optional[list['Rewrite']]]:
        """Return (is_grouped, is_expanded, grouped_rewrites) for a given row."""
        if index.row() == 0:
            return False, False, None
        model = index.model()
        if not isinstance(model, ProofModel):
            return False, False, None
        step_idx = index.row() - 1
        if step_idx >= len(model.steps):
            return False, False, None
        step = model.steps[step_idx]
        if step.grouped_rewrites is None:
            return False, False, None
        view = self.parent()
        is_expanded = isinstance(view, ProofStepView) and step_idx in view.expanded_groups
        return True, is_expanded, step.grouped_rewrites

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()

        is_grouped, is_expanded, grouped_rewrites = self._step_info(index)

        font = QFont(option.font)  # type: ignore[attr-defined]
        text_height = QFontMetrics(font).height()
        row_height = text_height + 2 * self.vert_padding
        fg = QColor(224, 224, 224) if display_setting.dark_mode else QColor(0, 0, 0)
        line_clr = QColor(180, 180, 180) if display_setting.dark_mode else QColor(0, 0, 0)

        # ── Background ──────────────────────────────────────────────────
        painter.setPen(Qt.GlobalColor.transparent)
        if display_setting.dark_mode:
            if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
                painter.setBrush(QColor(60, 80, 120))
            elif option.state & QStyle.StateFlag.State_MouseOver:  # type: ignore[attr-defined]
                painter.setBrush(QColor(50, 60, 80))
            else:
                painter.setBrush(QColor(35, 39, 46))
        else:
            if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
                painter.setBrush(QColor(204, 232, 255))
            elif option.state & QStyle.StateFlag.State_MouseOver:  # type: ignore[attr-defined]
                painter.setBrush(QColor(229, 243, 255))
            else:
                painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(option.rect)  # type: ignore[attr-defined]

        # ── Main timeline line ──────────────────────────────────────────
        is_last = index.row() == index.model().rowCount() - 1
        if is_last:
            line_h = int(row_height / 2)
        else:
            line_h = int(option.rect.height())  # type: ignore[attr-defined]
        line_rect = QRect(
            self.line_padding,
            int(option.rect.y()),  # type: ignore[attr-defined]
            self.line_width,
            line_h
        )
        painter.setPen(Qt.GlobalColor.transparent)
        painter.setBrush(line_clr)
        painter.drawRect(line_rect)

        # ── Main circle ─────────────────────────────────────────────────
        circle_cy = option.rect.y() + row_height / 2  # type: ignore[attr-defined]
        painter.setPen(QPen(line_clr, self.circle_outline_width))
        painter.setBrush(display_setting.effective_colors["z_spider"])
        cr = self.circle_radius_selected \
            if option.state & QStyle.StateFlag.State_Selected else self.circle_radius  # type: ignore[attr-defined]
        main_cx = self.line_padding + self.line_width / 2
        painter.drawEllipse(QPointF(main_cx, circle_cy), cr, cr)

        # ── Text / group indicator ──────────────────────────────────────
        text_x_base = int(option.rect.x() + self.line_width + 2 * self.line_padding)  # type: ignore[attr-defined]

        if is_grouped:
            s = self.triangle_size
            tri_cy = int(option.rect.y() + row_height / 2)  # type: ignore[attr-defined]
            painter.setPen(Qt.GlobalColor.transparent)
            painter.setBrush(fg)

            if is_expanded:
                # Down-pointing triangle  ▼
                triangle = QPolygonF([
                    QPointF(text_x_base, tri_cy - s * 0.5),
                    QPointF(text_x_base + s * 2, tri_cy - s * 0.5),
                    QPointF(text_x_base + s, tri_cy + s * 0.5 + 1),
                ])
            else:
                # Right-pointing triangle  ▶
                triangle = QPolygonF([
                    QPointF(text_x_base, tri_cy - s),
                    QPointF(text_x_base + s, tri_cy),
                    QPointF(text_x_base, tri_cy + s),
                ])
            painter.drawPolygon(triangle)

            tri_offset = s * 2 + 4
            header_text = "Grouped Steps" if is_expanded else index.data(Qt.ItemDataRole.DisplayRole)
            text_rect = QRect(
                text_x_base + tri_offset,
                int(option.rect.y() + row_height / 2 - text_height / 2),  # type: ignore[attr-defined]
                int(option.rect.width() - self.line_width - 2 * self.line_padding - tri_offset),  # type: ignore[attr-defined]
                text_height
            )
            bold_font = QFont(font)
            bold_font.setWeight(QFont.Weight.Bold)
            painter.setFont(bold_font)
            painter.setPen(fg)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, header_text)

            # Draw expanded sub-tree
            if is_expanded and grouped_rewrites:
                self._paint_sub_tree(painter, option, grouped_rewrites,
                                     row_height, text_height, font, fg, line_clr)
        else:
            # Regular (non-grouped) step text
            text = index.data(Qt.ItemDataRole.DisplayRole)
            text_rect = QRect(
                text_x_base,
                int(option.rect.y() + row_height / 2 - text_height / 2),  # type: ignore[attr-defined]
                int(option.rect.width() - self.line_width - 2 * self.line_padding),  # type: ignore[attr-defined]
                text_height
            )
            draw_font = QFont(font)
            if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
                draw_font.setWeight(QFont.Weight.Bold)
            painter.setFont(draw_font)
            painter.setPen(fg)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    # ── Expanded sub-tree painting ──────────────────────────────────────
    def _paint_sub_tree(self, painter: QPainter, option: QStyleOptionViewItem,
                        grouped_rewrites: list['Rewrite'], row_height: int,
                        text_height: int, font: QFont,
                        fg: QColor, line_clr: QColor) -> None:
        main_cx = self.line_padding + self.line_width / 2
        sub_tree_x = main_cx + self.sub_indent
        n = len(grouped_rewrites)

        first_sub_top = option.rect.y() + row_height  # type: ignore[attr-defined]
        last_sub_cy = first_sub_top + (n - 1) * row_height + row_height / 2

        pen = QPen(line_clr, 2)
        painter.setPen(pen)

        # Diagonal connector from main circle down to start of sub-tree
        header_cy = option.rect.y() + row_height / 2  # type: ignore[attr-defined]
        painter.drawLine(
            QPointF(main_cx, header_cy + self.circle_radius_selected),
            QPointF(sub_tree_x, first_sub_top)
        )

        # Sub-tree vertical line
        painter.drawLine(
            QPointF(sub_tree_x, first_sub_top),
            QPointF(sub_tree_x, last_sub_cy)
        )

        sub_circle_cx = sub_tree_x + self.sub_branch_len
        for i, sub_step in enumerate(grouped_rewrites):
            sub_cy = first_sub_top + i * row_height + row_height / 2

            # Horizontal branch
            painter.setPen(pen)
            painter.drawLine(
                QPointF(sub_tree_x, sub_cy),
                QPointF(sub_circle_cx - self.sub_circle_radius, sub_cy)
            )

            # Sub-step circle (steel-blue fill)
            painter.setPen(QPen(line_clr, 2))
            painter.setBrush(QColor(70, 130, 180))
            painter.drawEllipse(
                QPointF(sub_circle_cx, sub_cy),
                self.sub_circle_radius, self.sub_circle_radius
            )

            # Sub-step text
            sub_text_x = int(sub_circle_cx + self.sub_circle_radius + 8)
            sub_text_rect = QRect(
                sub_text_x,
                int(sub_cy - text_height / 2),
                int(option.rect.width() - sub_text_x),  # type: ignore[attr-defined]
                text_height
            )
            painter.setFont(font)
            painter.setPen(fg)
            painter.drawText(sub_text_rect, Qt.AlignmentFlag.AlignLeft, sub_step.display_name)

    def sizeHint(self, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        size = super().sizeHint(option, index)
        text_height = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
        single_row = text_height + 2 * self.vert_padding
        total = single_row

        is_grouped, is_expanded, grouped_rewrites = self._step_info(index)
        if is_grouped and is_expanded and grouped_rewrites:
            total += len(grouped_rewrites) * single_row

        return QSize(size.width(), total)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(self, editor: QWidget, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        assert isinstance(editor, QLineEdit)
        value = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        editor.setText(str(value))

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        step_view.rename_proof_step(editor.text(), index.row() - 1)
