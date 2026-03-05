import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel, QEvent,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QSize, Qt)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QMouseEvent, QPainter,
                           QPen, QPolygonF)
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QMenu,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTreeView, QWidget)

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


class ProofModel(QAbstractItemModel):
    """Tree model capturing the individual steps in a proof.

    There is a top-level row for each graph sequence.
    Grouped rewrites have child rows representing their individual sub-steps.
    """

    initial_graph: GraphT
    steps: list[Rewrite]

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.initial_graph = start_graph
        self.steps = []

    def index(self, row: int, column: int,
              parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, child: Union[QModelIndex, QPersistentModelIndex]) -> QModelIndex:
        if not child.isValid() or child.internalId() == 0:
            return QModelIndex()
        return self.createIndex(child.internalId() - 1, 0, 0)

    def rowCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self.steps) + 1
        if parent.internalId() != 0:
            return 0  # No grandchildren
        step_idx = parent.row() - 1
        if step_idx < 0 or step_idx >= len(self.steps):
            return 0
        grouped = self.steps[step_idx].grouped_rewrites
        return len(grouped) if grouped else 0

    def columnCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        return 1

    def hasChildren(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> bool:
        return self.rowCount(parent) > 0

    def _display_name(self, index: Union[QModelIndex, QPersistentModelIndex]) -> Any:
        """Return the display name for a model index."""
        if index.internalId() == 0:
            if index.row() == 0:
                return "START"
            step_idx = index.row() - 1
            return self.steps[step_idx].display_name if step_idx < len(self.steps) else None
        parent_step_idx = index.internalId() - 2  # internalId = parent_row + 1, step_idx = parent_row - 1
        if 0 <= parent_step_idx < len(self.steps):
            grouped = self.steps[parent_step_idx].grouped_rewrites
            if grouped and index.row() < len(grouped):
                return grouped[index.row()].display_name
        return None

    def data(self, index: Union[QModelIndex, QPersistentModelIndex],
             role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_name(index)
        if role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)
        return None

    def flags(self, index: Union[QModelIndex, QPersistentModelIndex]) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags  # type: ignore[return-value]
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.internalId() == 0 and index.row() == 0:
            return base  # type: ignore[return-value]  # START not editable
        return base | Qt.ItemFlag.ItemIsEditable  # type: ignore[return-value]

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        return None

    def set_graph(self, index: int, graph: GraphT) -> None:
        if index == 0:
            self.initial_graph = graph
        else:
            old = self.steps[index - 1]
            self.steps[index - 1] = Rewrite(old.display_name, old.rule, graph, old.grouped_rewrites)
            mi = self.createIndex(index, 0, 0)
            self.dataChanged.emit(mi, mi, [])

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

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
        """Change the display name of a step (and sync sub-step names if applicable)."""
        old = self.steps[index]
        grouped = old.grouped_rewrites
        if grouped and "\u2192" in name:
            body = name.split(": ", 1)[-1] if ": " in name else name
            sub_names = [s.strip() for s in body.split("\u2192")]
            if len(sub_names) == len(grouped):
                grouped = [
                    Rewrite(sub_names[i], rw.rule, rw.graph, rw.grouped_rewrites)
                    if sub_names[i] != rw.display_name else rw
                    for i, rw in enumerate(grouped)
                ]
        self.steps[index] = Rewrite(name, old.rule, old.graph, grouped)
        mi = self.createIndex(index + 1, 0, 0)
        self.dataChanged.emit(mi, mi, [])

    def rename_sub_step(self, step_index: int, sub_index: int, name: str) -> None:
        """Change the display name of a sub-step."""
        old = self.steps[step_index]
        grouped = old.grouped_rewrites
        if grouped is None or sub_index >= len(grouped):
            return
        old_sub = grouped[sub_index]
        new_grouped = list(grouped)
        new_grouped[sub_index] = Rewrite(name, old_sub.rule, old_sub.graph, old_sub.grouped_rewrites)
        self.steps[step_index] = Rewrite(old.display_name, old.rule, old.graph, new_grouped)
        parent_mi = self.index(step_index + 1, 0)
        child_mi = self.index(sub_index, 0, parent_mi)
        self.dataChanged.emit(child_mi, child_mi, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index` with a new grouped step"""
        new_rewrite = Rewrite(
            "Grouped Steps: " + " \u2192 ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
            "Grouped",
            self.get_graph(end_index + 1),
            self.steps[start_index:end_index + 1]
        )
        for _ in range(end_index - start_index + 1):
            self.pop_rewrite(start_index)
        self.add_rewrite(new_rewrite, start_index)

    def ungroup_steps(self, index: int) -> None:
        """Replace the grouped step at `index` with the individual_steps"""
        individual_steps = self.steps[index].grouped_rewrites
        if individual_steps is None:
            raise ValueError("Step is not grouped")
        self.pop_rewrite(index)
        for i, step in enumerate(individual_steps):
            self.add_rewrite(step, index + i)

    def truncate_group(self, step_index: int, keep_count: int) -> 'Rewrite':
        """Truncate a grouped step, keeping only the first `keep_count` sub-steps.

        If keep_count == 1 the group is replaced by the single remaining sub-step
        (i.e. the group is "ungrouped").  Returns the *original* Rewrite so that
        the caller can restore it later via `restore_group`.
        """
        old = self.steps[step_index]
        assert old.grouped_rewrites is not None
        assert 0 < keep_count <= len(old.grouped_rewrites)

        kept = old.grouped_rewrites[:keep_count]

        if keep_count == 1:
            # Ungroup: replace the grouped step with the single sub-step.
            self.pop_rewrite(step_index)
            self.add_rewrite(kept[0], step_index)
        else:
            # Shrink in-place, notifying the tree view about removed children.
            parent_idx = self.index(step_index + 1, 0)
            n_old = len(old.grouped_rewrites)
            if keep_count < n_old:
                self.beginRemoveRows(parent_idx, keep_count, n_old - 1)
            self.steps[step_index] = Rewrite(
                old.display_name, old.rule, kept[-1].graph, kept,
            )
            if keep_count < n_old:
                self.endRemoveRows()
            mi = self.createIndex(step_index + 1, 0, 0)
            self.dataChanged.emit(mi, mi, [])

        return old

    def restore_group(self, step_index: int, original: 'Rewrite') -> None:
        """Restore a previously truncated / ungrouped step to its original group."""
        self.pop_rewrite(step_index)
        self.add_rewrite(original, step_index)
    def to_dict(self) -> Dict[str, Any]:
        """Serializes the model to Python dict."""
        return {
            "initial_graph": self.initial_graph.to_dict(),
            "proof_steps": [step.to_dict() for step in self.steps]
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
            model.add_rewrite(Rewrite.from_json(step))
        return model


class ProofStepView(QTreeView):
    """A view for displaying the steps in a proof."""

    def __init__(self, parent: 'ProofPanel'):
        super().__init__(parent)
        self.graph_view = parent.graph_view
        self.undo_stack = parent.undo_stack
        self.setModel(ProofModel(self.graph_view.graph_scene.g))
        self.setCurrentIndex(self.model().index(0, 0))

        # Tree config: all visual layout handled by our delegate
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)
        self.setHeaderHidden(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        # Styling
        pal = self.palette()
        if display_setting.dark_mode:
            self.setStyleSheet("background-color: #23272e;")
            pal.setColor(self.backgroundRole(), QColor(35, 39, 46))
            pal.setColor(self.viewport().backgroundRole(), QColor(35, 39, 46))
        else:
            self.setStyleSheet("")
            pal.setColor(self.backgroundRole(), QColor(255, 255, 255))
            pal.setColor(self.viewport().backgroundRole(), QColor(255, 255, 255))
        self.setPalette(pal)

        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setUniformRowHeights(True)
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
        # it looks like the selectionModel is linked to the model, so after updating the model we need to reconnect the selectionModel signals.
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setCurrentIndex(model.index(len(model.steps), 0))

    def move_to_step(self, index: int) -> None:
        idx = self.model().index(index, 0, QModelIndex())
        self.setCurrentIndex(idx)

    def proof_step_selected(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        if not selected:
            return
        index = selected.first().topLeft()
        if not index.isValid():
            return
        if index.parent().isValid():
            # Sub-step clicked → show sub-step graph natively
            step_idx = index.parent().row() - 1
            sub_idx = index.row()
            step = self.model().steps[step_idx]
            if step.grouped_rewrites and sub_idx < len(step.grouped_rewrites):
                self.graph_view.set_graph(step.grouped_rewrites[sub_idx].graph.copy())
        else:
            self.graph_view.set_graph(self.model().get_graph(index.row()))

    # Context menu

    def show_context_menu(self, position: QPoint) -> None:
        index = self.indexAt(position)
        if not index.isValid():
            return
        context_menu = QMenu(self)
        action_map: dict[Any, Any] = {}

        if index.parent().isValid():
            # Right-clicked on a sub-step
            rename_action = context_menu.addAction("Rename Sub-step")
            action_map[rename_action] = lambda: self.edit(index)
        else:
            top_level = [i for i in self.selectedIndexes() if not i.parent().isValid()]
            if len(top_level) > 1:
                action_map[context_menu.addAction("Group Steps")] = self.group_selected_steps
            elif index.row() != 0:
                action_map[context_menu.addAction("Rename Step")] = lambda: self.edit(index)
                step_idx = index.row() - 1
                if step_idx < len(self.model().steps) and self.model().steps[step_idx].grouped_rewrites is not None:
                    action_map[context_menu.addAction("Ungroup Steps")] = self.ungroup_selected_step

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_map:
            action_map[action]()

    # Rename

    def rename_proof_sub_step(self, new_name: str, step_index: int, sub_index: int) -> None:
        from .commands import UndoableChange
        step = self.model().steps[step_index]
        if step.grouped_rewrites is None:
            return
        old_name = step.grouped_rewrites[sub_index].display_name
        cmd = UndoableChange(self.graph_view,
                             lambda: self.model().rename_sub_step(step_index, sub_index, old_name),
                             lambda: self.model().rename_sub_step(step_index, sub_index, new_name))
        self.undo_stack.push(cmd)

    def rename_proof_step(self, new_name: str, index: int) -> None:
        from .commands import UndoableChange
        old_name = self.model().steps[index].display_name
        cmd = UndoableChange(self.graph_view,
                             lambda: self.model().rename_step(index, old_name),
                             lambda: self.model().rename_step(index, new_name))
        self.undo_stack.push(cmd)

    # Group / Ungroup

    def group_selected_steps(self) -> None:
        from .commands import GroupRewriteSteps
        from .dialogs import show_error_msg
        selected = sorted(i.row() for i in self.selectedIndexes() if not i.parent().isValid())
        if len(selected) < 2:
            raise ValueError("Can only group two or more steps")
        if selected[-1] - selected[0] != len(selected) - 1:
            show_error_msg("Can only group contiguous steps")
            raise ValueError("Can only group contiguous steps")
        if selected[0] == 0:
            show_error_msg("Cannot group the first step")
            raise ValueError("Cannot group the first step")
        self.move_to_step(selected[-1] - 1)
        self.undo_stack.push(GroupRewriteSteps(self.graph_view, self, selected[0] - 1, selected[-1] - 1))

    def ungroup_selected_step(self) -> None:
        from .commands import UngroupRewriteSteps
        top_level = [i for i in self.selectedIndexes() if not i.parent().isValid()]
        if len(top_level) != 1:
            raise ValueError("Can only ungroup one step")
        row = top_level[0].row()
        if row == 0 or self.model().steps[row - 1].grouped_rewrites is None:
            raise ValueError("Step is not grouped")
        self.move_to_step(row - 1)
        self.undo_stack.push(UngroupRewriteSteps(self.graph_view, self, row - 1))


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

    triangle_size = 5
    sub_indent = 20

    def editorEvent(self, event: QEvent, model: QAbstractItemModel,
                    option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> bool:
        """Handle triangle clicks natively within the delegate's event flow without view coordinate tracking."""
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            step_view = self.parent()
            if isinstance(step_view, QTreeView):
                rect = option.rect  # type: ignore[attr-defined]
                text_h = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
                row_h = text_h + 2 * self.vert_padding
                text_x = rect.x() + self.line_width + 2 * self.line_padding
                cy = rect.y() + row_h / 2
                s = self.triangle_size
                
                pos = event.pos()
                # Check hit test using native option rect properties
                if text_x <= pos.x() <= text_x + s * 2 and cy - s <= pos.y() <= cy + s:
                    if not index.parent().isValid() and model.hasChildren(index):
                        step_view.setCurrentIndex(index)
                        step_view.setExpanded(index, not step_view.isExpanded(index))
                        return True
        return super().editorEvent(event, model, option, index)

    @staticmethod
    def _bg_color(selected: bool, hovered: bool) -> QColor:
        """Return background color for the given state."""
        dark = display_setting.dark_mode
        if selected:
            return QColor(60, 80, 120) if dark else QColor(204, 232, 255)
        if hovered:
            return QColor(50, 60, 80) if dark else QColor(229, 243, 255)
        return QColor(35, 39, 46) if dark else QColor(255, 255, 255)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)  # type: ignore[attr-defined]
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)  # type: ignore[attr-defined]

        # Background
        painter.setPen(Qt.GlobalColor.transparent)
        painter.setBrush(self._bg_color(is_selected, is_hovered))
        painter.drawRect(option.rect)  # type: ignore[attr-defined]

        font = QFont(option.font)  # type: ignore[attr-defined]
        text_h = QFontMetrics(font).height()
        row_h = text_h + 2 * self.vert_padding
        fg = QColor(224, 224, 224) if display_setting.dark_mode else QColor(0, 0, 0)
        line_clr = QColor(180, 180, 180) if display_setting.dark_mode else QColor(0, 0, 0)

        if index.parent().isValid():
            self._paint_child(painter, option, index, font, text_h, row_h, fg, line_clr)
        else:
            self._paint_toplevel(painter, option, index, font, text_h, row_h, fg, line_clr)

        painter.restore()

    def _paint_toplevel(self, painter: QPainter, option: QStyleOptionViewItem,
                        index: Union[QModelIndex, QPersistentModelIndex],
                        font: QFont, text_h: int, row_h: int,
                        fg: QColor, line_clr: QColor) -> None:
        """Paint a top-level step on the main timeline."""
        rect = option.rect  # type: ignore[attr-defined]
        main_cx = self.line_padding + self.line_width / 2
        circle_cy = rect.y() + row_h / 2

        pen = QPen(line_clr, self.line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.GlobalColor.transparent)

        # Line: top → circle
        painter.drawLine(QPointF(main_cx, rect.y()), QPointF(main_cx, circle_cy))

        # Check grouped & expanded
        is_grouped = False
        is_expanded = False
        model = index.model()
        if isinstance(model, ProofModel) and index.row() > 0:
            step_idx = index.row() - 1
            if step_idx < len(model.steps) and model.steps[step_idx].grouped_rewrites:
                is_grouped = True
                view = self.parent()
                is_expanded = isinstance(view, QTreeView) and view.isExpanded(index)

        is_last = index.row() == index.model().rowCount() - 1

        # Line: circle → bottom
        if is_expanded:
            painter.drawLine(QPointF(main_cx, circle_cy),
                             QPointF(main_cx + self.sub_indent, rect.y() + rect.height()))
        elif not is_last:
            painter.drawLine(QPointF(main_cx, circle_cy),
                             QPointF(main_cx, rect.y() + rect.height()))

        # Circle
        painter.setPen(QPen(line_clr, self.circle_outline_width))
        painter.setBrush(display_setting.effective_colors["z_spider"])
        cr = self.circle_radius_selected \
            if option.state & QStyle.StateFlag.State_Selected else self.circle_radius  # type: ignore[attr-defined]
        painter.drawEllipse(QPointF(main_cx, circle_cy), cr, cr)

        # Text (with optional triangle for groups)
        text_x = int(rect.x() + self.line_width + 2 * self.line_padding)
        if is_grouped:
            s = self.triangle_size
            tri_cy = int(rect.y() + row_h / 2)
            painter.setPen(Qt.GlobalColor.transparent)
            painter.setBrush(fg)
            if is_expanded:
                tri = QPolygonF([QPointF(text_x, tri_cy - s * 0.5),
                                 QPointF(text_x + s * 2, tri_cy - s * 0.5),
                                 QPointF(text_x + s, tri_cy + s * 0.5 + 1)])
            else:
                tri = QPolygonF([QPointF(text_x, tri_cy - s),
                                 QPointF(text_x + s, tri_cy),
                                 QPointF(text_x, tri_cy + s)])
            painter.drawPolygon(tri)
            text_x += s * 2 + 4

        draw_font = QFont(font)
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
            draw_font.setWeight(QFont.Weight.Bold)
        painter.setFont(draw_font)
        painter.setPen(fg)
        painter.drawText(
            QRect(text_x, int(rect.y() + row_h / 2 - text_h / 2),
                  int(rect.width() - text_x + rect.x()), text_h),
            Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole))

    def _paint_child(self, painter: QPainter, option: QStyleOptionViewItem,
                     index: Union[QModelIndex, QPersistentModelIndex],
                     font: QFont, text_h: int, row_h: int,
                     fg: QColor, line_clr: QColor) -> None:
        """Paint a sub-step on the branch line."""
        rect = option.rect  # type: ignore[attr-defined]
        main_cx = self.line_padding + self.line_width / 2
        branch_x = main_cx + self.sub_indent
        circle_cy = rect.y() + row_h / 2
        n_siblings = index.model().rowCount(index.parent())
        is_last = index.row() == n_siblings - 1

        pen = QPen(line_clr, self.line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.GlobalColor.transparent)

        # Branch line: top → circle
        painter.drawLine(QPointF(branch_x, rect.y()), QPointF(branch_x, circle_cy))
        # Branch line: circle → bottom (or diagonal back to main axis)
        if is_last:
            painter.drawLine(QPointF(branch_x, circle_cy),
                             QPointF(main_cx, rect.y() + rect.height()))
        else:
            painter.drawLine(QPointF(branch_x, circle_cy),
                             QPointF(branch_x, rect.y() + rect.height()))

        # Circle
        painter.setPen(QPen(line_clr, self.line_width))
        painter.setBrush(display_setting.effective_colors["z_spider"])
        cr = self.circle_radius_selected \
            if option.state & QStyle.StateFlag.State_Selected else self.circle_radius  # type: ignore[attr-defined]
        painter.drawEllipse(QPointF(branch_x, circle_cy), cr, cr)

        # Text
        sub_text_x = int(branch_x + self.circle_radius + 10)
        draw_font = QFont(font)
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
            draw_font.setWeight(QFont.Weight.Bold)
        painter.setFont(draw_font)
        painter.setPen(fg)
        painter.drawText(
            QRect(sub_text_x, int(circle_cy - text_h / 2),
                  int(rect.width() - sub_text_x), text_h),
            Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole))

    def sizeHint(self, option: QStyleOptionViewItem,
                 index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        size = super().sizeHint(option, index)
        text_h = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
        return QSize(size.width(), text_h + 2 * self.vert_padding)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem,
                     index: Union[QModelIndex, QPersistentModelIndex]) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(self, editor: QWidget,
                      index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        assert isinstance(editor, QLineEdit)
        editor.setText(str(index.model().data(index, Qt.ItemDataRole.DisplayRole)))

    def setModelData(self, editor: QWidget, model: QAbstractItemModel,
                     index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        if index.parent().isValid():
            step_view.rename_proof_sub_step(editor.text(), index.parent().row() - 1, index.row())
        else:
            step_view.rename_proof_step(editor.text(), index.row() - 1)
