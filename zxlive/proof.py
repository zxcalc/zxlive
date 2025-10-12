import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QSize, Qt)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QMenu, QTreeView,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QWidget)

from .common import GraphT
from .settings import display_setting


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # New graph after applying the rewrite
    grouped_rewrites: Optional[list['Rewrite']] = None # Optional field to store the grouped rewrites

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
    def from_json(json_str: Union[str,Dict[str,Any]]) -> "Rewrite":
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
            display_name=d.get("display_name", d["rule"]), # Old proofs may not have display names
            rule=d["rule"],
            graph=graph,
            grouped_rewrites=[Rewrite.from_json(r) for r in grouped_rewrites] if grouped_rewrites else None
        )

class ProofModel(QAbstractItemModel):
    """Tree model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore, we store the
    rewrite that was used to go from one graph to next.
    Grouped steps can be expanded/collapsed in a tree-like fashion.
    """

    initial_graph: GraphT
    steps: list[Rewrite]
    expanded_groups: set[int]  # Track which grouped steps are expanded

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.initial_graph = start_graph
        self.steps = []
        self.expanded_groups = set()

    def set_graph(self, index: int, graph: GraphT) -> None:
        if index == 0:
            self.initial_graph = graph
        else:
            old_step = self.steps[index-1]
            new_step = Rewrite(old_step.display_name, old_step.rule, graph)
            self.steps[index-1] = new_step

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int=Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if not index.isValid():
            return None

        # Get the step, considering parent-child relationships
        if not index.parent().isValid():
            # Top-level item (including START)
            row = index.row()
            if row >= len(self.steps)+1 or index.column() >= 1:
                return None
            
            if role == Qt.ItemDataRole.DisplayRole:
                if row == 0:
                    return "START"
                else:
                    step = self.steps[row-1]
                    # For grouped steps, add expand/collapse indicator
                    if step.grouped_rewrites is not None:
                        indicator = "▼ " if (row - 1) in self.expanded_groups else "▶ "
                        return indicator + step.display_name
                    return step.display_name
            elif role == Qt.ItemDataRole.FontRole:
                return QFont("monospace", 12)
        else:
            # Child item (sub-step of a grouped rewrite)
            parent_row = index.parent().row()
            if parent_row == 0 or parent_row >= len(self.steps) + 1:
                return None
            parent_step = self.steps[parent_row - 1]
            if parent_step.grouped_rewrites is None or index.row() >= len(parent_step.grouped_rewrites):
                return None
            
            if role == Qt.ItemDataRole.DisplayRole:
                return parent_step.grouped_rewrites[index.row()].display_name
            elif role == Qt.ItemDataRole.FontRole:
                return QFont("monospace", 12)
        
        return None

    def flags(self, index: Union[QModelIndex, QPersistentModelIndex]) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        
        # START row is not editable
        if not index.parent().isValid() and index.row() == 0:
            return super().flags(index)
        
        # All other items (including children) are editable
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
        if not parent.isValid():
            # Top-level: START + all steps
            return len(self.steps) + 1
        
        # Check if parent is a grouped step that is expanded
        parent_row = parent.row()
        if parent_row == 0:  # START has no children
            return 0
        
        parent_step_index = parent_row - 1
        if parent_step_index < 0 or parent_step_index >= len(self.steps):
            return 0
        
        parent_step = self.steps[parent_step_index]
        # Only show children if the group is expanded
        if parent_step.grouped_rewrites is not None and parent_step_index in self.expanded_groups:
            return len(parent_step.grouped_rewrites)
        
        return 0

    def index(self, row: int, column: int, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> QModelIndex:
        """Create index for the given row and column"""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        if not parent.isValid():
            # Top-level item
            return self.createIndex(row, column, None)
        else:
            # Child item - store parent row in internal pointer
            parent_row = parent.row()
            if parent_row == 0:
                return QModelIndex()
            # Use parent_row as internal pointer to identify this is a child
            return self.createIndex(row, column, parent_row)

    def parent(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> QModelIndex:
        """Return parent index"""
        if not index.isValid():
            return QModelIndex()
        
        # If internal pointer is None, it's a top-level item (no parent)
        parent_row = index.internalPointer()
        if parent_row is None:
            return QModelIndex()
        
        # Return the parent index
        return self.createIndex(parent_row, 0, None)

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
            copy = self.steps[index-1].graph.copy()
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
        modelIndex = self.createIndex(index + 1, 0, None)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def toggle_expansion(self, index: int) -> None:
        """Toggle the expansion state of a grouped step"""
        if index < 0 or index >= len(self.steps):
            return
        
        step = self.steps[index]
        if step.grouped_rewrites is None:
            return
        
        model_index = self.createIndex(index + 1, 0, None)
        child_count = len(step.grouped_rewrites)
        
        if index in self.expanded_groups:
            # Collapse: remove children
            if child_count > 0:
                self.beginRemoveRows(model_index, 0, child_count - 1)
                self.expanded_groups.remove(index)
                self.endRemoveRows()
        else:
            # Expand: add children
            if child_count > 0:
                self.beginInsertRows(model_index, 0, child_count - 1)
                self.expanded_groups.add(index)
                self.endInsertRows()
        
        # Update the parent row to change the indicator
        self.dataChanged.emit(model_index, model_index, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index` with a new grouped step"""
        new_rewrite = Rewrite(
            "Grouped Steps: " + " 🡒 ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
            "Grouped",
            self.get_graph(end_index + 1),
            self.steps[start_index:end_index + 1]
        )
        for _ in range(end_index - start_index + 1):
            self.pop_rewrite(start_index)[0]
        self.add_rewrite(new_rewrite, start_index)
        
        # Automatically expand the new group
        modelIndex = self.createIndex(start_index + 1, 0, None)
        child_count = len(new_rewrite.grouped_rewrites) if new_rewrite.grouped_rewrites else 0
        if child_count > 0:
            self.beginInsertRows(modelIndex, 0, child_count - 1)
            self.expanded_groups.add(start_index)
            self.endInsertRows()
        
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def ungroup_steps(self, index: int) -> None:
        """Replace the grouped step at `index` with the individual_steps"""
        individual_steps = self.steps[index].grouped_rewrites
        if individual_steps is None:
            raise ValueError("Step is not grouped")
        
        # Remove from expanded groups if present
        self.expanded_groups.discard(index)
        
        self.pop_rewrite(index)
        for i, step in enumerate(individual_steps):
            self.add_rewrite(step, index + i)
        self.dataChanged.emit(self.createIndex(index + 1, 0, None),
                              self.createIndex(index + len(individual_steps), 0, None),
                              [])

    def to_dict(self) -> Dict[str,Any]:
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
    def from_json(json_str: Union[str,Dict[str,Any]]) -> "ProofModel":
        """Deserializes the model from JSON or Python dict."""
        if isinstance(json_str, str):
            d = json.loads(json_str)
        else:
            d = json_str
        initial_graph = GraphT.from_json(d["initial_graph"])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        if TYPE_CHECKING: assert isinstance(initial_graph, GraphT)
        initial_graph.set_auto_simplify(False)
        model = ProofModel(initial_graph)
        for step in d["proof_steps"]:
            rewrite = Rewrite.from_json(step)
            model.add_rewrite(rewrite)
        return model

class ProofStepView(QTreeView):
    """A view for displaying the steps in a proof."""

    def __init__(self, parent: 'ProofPanel'):
        print("Initializing ProofStepView")
        super().__init__(parent)
        self.graph_view = parent.graph_view
        self.undo_stack = parent.undo_stack
        self.setModel(ProofModel(self.graph_view.graph_scene.g))
        self.setCurrentIndex(self.model().index(0, 0))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        
        # Hide the tree view's default expand/collapse controls
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        
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
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setItemDelegate(ProofStepItemDelegate(self))
        self.clicked.connect(self.handle_click)

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

    def handle_click(self, index: QModelIndex) -> None:
        """Handle clicks on proof steps, toggle expansion for grouped steps"""
        if not index.isValid() or index.parent().isValid():
            # Don't toggle for child items
            return
        
        row = index.row()
        if row == 0:  # START row
            return
        
        step_index = row - 1
        if step_index >= 0 and step_index < len(self.model().steps):
            step = self.model().steps[step_index]
            if step.grouped_rewrites is not None:
                self.model().toggle_expansion(step_index)

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
        
        # Filter out child items from selection for grouping purposes
        # Only work with top-level items
        top_level_indexes = [idx for idx in selected_indexes if not idx.parent().isValid()]
        if not top_level_indexes:
            return
        
        context_menu = QMenu(self)
        action_function_map = {}

        index = top_level_indexes[0].row()
        if len(top_level_indexes) > 1:
            group_action = context_menu.addAction("Group Steps")
            action_function_map[group_action] = self.group_selected_steps
        elif index != 0:
            rename_action = context_menu.addAction("Rename Step")
            action_function_map[rename_action] = lambda: self.edit(top_level_indexes[0])
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
            lambda: self.model().rename_step(index, new_name)
        )
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
        
        # Filter to only top-level items
        top_level_indexes = [idx for idx in selected_indexes if not idx.parent().isValid()]
        
        if not top_level_indexes or len(top_level_indexes) < 2:
            raise ValueError("Can only group two or more steps")

        indices = sorted(index.row() for index in top_level_indexes)
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
        
        # Filter to only top-level items
        top_level_indexes = [idx for idx in selected_indexes if not idx.parent().isValid()]
        
        if not top_level_indexes or len(top_level_indexes) != 1:
            raise ValueError("Can only ungroup one step")

        index = top_level_indexes[0].row()
        if index == 0 or self.model().steps[index - 1].grouped_rewrites is None:
            raise ValueError("Step is not grouped")

        self.move_to_step(index - 1)
        cmd = UngroupRewriteSteps(self.graph_view, self, index - 1)
        self.undo_stack.push(cmd)


class ProofStepItemDelegate(QStyledItemDelegate):
    """This class controls the painting of items in the proof steps list view.

    We paint a "git-style" line with circles to denote individual steps in a proof.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10
    child_indent = 30  # Additional indent for child steps

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()
        
        # Check if this is a child item
        is_child = index.parent().isValid()
        indent_offset = self.child_indent if is_child else 0
        
        # Draw background
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

        # Determine if this is the last item at this level
        is_last = False
        if not is_child:
            # Top-level item
            is_last = index.row() == index.model().rowCount() - 1
        else:
            # Child item
            parent_index = index.parent()
            is_last = index.row() == index.model().rowCount(parent_index) - 1

        # Draw line
        line_rect = QRect(
            self.line_padding + indent_offset,
            int(option.rect.y()),  # type: ignore[attr-defined]
            self.line_width,
            int(option.rect.height() if not is_last else option.rect.height() / 2)  # type: ignore[attr-defined]
        )
        if display_setting.dark_mode:
            painter.setBrush(QColor(180, 180, 180))
        else:
            painter.setBrush(Qt.GlobalColor.black)
        painter.drawRect(line_rect)

        # Draw circle
        if display_setting.dark_mode:
            painter.setPen(QPen(QColor(180, 180, 180), self.circle_outline_width))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, self.circle_outline_width))
        painter.setBrush(display_setting.effective_colors["z_spider"])
        circle_radius = self.circle_radius_selected if option.state & QStyle.StateFlag.State_Selected else self.circle_radius  # type: ignore[attr-defined]
        painter.drawEllipse(
            QPointF(self.line_padding + self.line_width / 2 + indent_offset, option.rect.y() + option.rect.height() / 2),  # type: ignore[attr-defined]
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_height = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
        text_rect = QRect(
            int(option.rect.x() + self.line_width + 2 * self.line_padding + indent_offset),  # type: ignore[attr-defined]
            int(option.rect.y() + option.rect.height() / 2 - text_height / 2),  # type: ignore[attr-defined]
            option.rect.width(),  # type: ignore[attr-defined]
            text_height
        )
        font = option.font  # type: ignore[attr-defined]
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
            font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        if display_setting.dark_mode:
            painter.setPen(QColor(224, 224, 224))
            painter.setBrush(QColor(224, 224, 224))
        else:
            painter.setPen(Qt.GlobalColor.black)
            painter.setBrush(Qt.GlobalColor.black)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), size.height() + 2 * self.vert_padding)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(self, editor: QWidget, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        assert isinstance(editor, QLineEdit)
        value = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        text = str(value)
        
        # Strip the expand/collapse indicator if present
        if text.startswith("▶ ") or text.startswith("▼ "):
            text = text[2:]
        
        editor.setText(text)

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        
        # Only allow renaming top-level items (not child items)
        if not index.parent().isValid():
            step_view.rename_proof_step(editor.text(), index.row() - 1)
