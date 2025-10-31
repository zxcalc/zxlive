import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel, QAbstractListModel,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QSize, Qt)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
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
    # Optional field to store the grouped rewrites
    grouped_rewrites: Optional[list['Rewrite']] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the rewrite to Python dictionary."""
        grouped = None
        if self.grouped_rewrites:
            grouped = [r.to_dict() for r in self.grouped_rewrites]
        return {
            "display_name": self.display_name,
            "rule": self.rule,
            "graph": self.graph.to_dict(),
            "grouped_rewrites": grouped
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

        grouped = None
        if grouped_rewrites:
            grouped = [Rewrite.from_json(r) for r in grouped_rewrites]
        # Old proofs may not have display names
        display_name = d.get("display_name", d["rule"])
        return Rewrite(
            display_name=display_name,
            rule=d["rule"],
            graph=graph,
            grouped_rewrites=grouped
        )


class ProofModel(QAbstractListModel):
    """List model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore,
    we store the rewrite that was used to go from one graph to next.
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
            old_step = self.steps[index-1]
            new_step = Rewrite(old_step.display_name, old_step.rule, graph)
            self.steps[index-1] = new_step

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex],
             role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with
        rewrite steps"""

        if index.row() >= len(self.steps)+1 or index.column() >= 1:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.row() == 0:
                return "START"
            else:
                return self.steps[index.row()-1].display_name
        elif role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)

    def flags(self,
              index: Union[QModelIndex, QPersistentModelIndex]
              ) -> Qt.ItemFlag:
        if index.row() == 0:
            return super().flags(index)
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.headerData`.

        Indicates that this model doesn't have a header.
        """
        return None

    def columnCount(self,
                    index: Union[QModelIndex,
                                 QPersistentModelIndex] = QModelIndex()
                    ) -> int:
        """The number of columns"""
        return 1

    def rowCount(self,
                 index: Union[QModelIndex,
                              QPersistentModelIndex] = QModelIndex()
                 ) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on
        # tree models, the user has to specify the index of the parent.
        # In a list, we always expect the parent to be `None` or the
        # empty `QModelIndex()`
        if not index or not index.isValid():
            return len(self.steps)+1
        else:
            return 0

    def add_rewrite(self, rewrite: Rewrite,
                    position: Optional[int] = None) -> None:
        """Adds a rewrite step to the model."""
        if position is None:
            position = len(self.steps)
        self.beginInsertRows(QModelIndex(), position + 1, position + 1)
        self.steps.insert(position, rewrite)
        self.endInsertRows()

    def pop_rewrite(self,
                    position: Optional[int] = None
                    ) -> tuple[Rewrite, GraphT]:
        """Removes the latest rewrite from the model.

        Returns the rewrite and the graph that previously resulted from
        this rewrite.
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

        # Must create a new Rewrite object instead of modifying current
        # object since Rewrite inherits NamedTuple and is hence immutable
        self.steps[index] = Rewrite(name, old_step.rule, old_step.graph,
                                    old_step.grouped_rewrites)

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index`
        with a new grouped step"""
        names = [self.steps[i].display_name
                 for i in range(start_index, end_index + 1)]
        new_rewrite = Rewrite(
            "Grouped Steps: " + " 🡒 ".join(names),
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
                              self.createIndex(
                                  index + len(individual_steps), 0),
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
        print("Initializing ProofStepView")
        super().__init__(parent)
        self.graph_view = parent.graph_view
        self.undo_stack = parent.undo_stack
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
            bg_role = self.viewport().backgroundRole()
            pal.setColor(bg_role, QColor(255, 255, 255))
        self.setPalette(pal)
        self.setSpacing(0)
        mode = QAbstractItemView.SelectionMode.ContiguousSelection
        self.setSelectionMode(mode)
        behavior = QAbstractItemView.SelectionBehavior.SelectRows
        self.setSelectionBehavior(behavior)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setAlternatingRowColors(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        sel_model = self.selectionModel()
        sel_model.selectionChanged.connect(self.proof_step_selected)
        self.setItemDelegate(ProofStepItemDelegate(self))

    # overriding this method to change the return type and stop mypy
    # from complaining
    def model(self) -> ProofModel:
        model = super().model()
        assert isinstance(model, ProofModel)
        return model

    def set_model(self, model: ProofModel) -> None:
        self.setModel(model)
        # it looks like the selectionModel is linked to the model, so after
        # updating the model we need to reconnect the selectionModel signals.
        sel_model = self.selectionModel()
        sel_model.selectionChanged.connect(self.proof_step_selected)
        self.setCurrentIndex(model.index(len(model.steps), 0))

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

            def edit_func() -> None:
                self.edit(selected_indexes[0])
            action_function_map[rename_action] = edit_func
            grouped_rewrites = self.model().steps[index - 1].grouped_rewrites
            if grouped_rewrites is not None:
                ungroup_action = context_menu.addAction("Ungroup Steps")
                ungroup_func = self.ungroup_selected_step
                action_function_map[ungroup_action] = ungroup_func

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_function_map:
            action_function_map[action]()

    def rename_proof_step(self, new_name: str, index: int) -> None:
        from .commands import UndoableChange
        old_name = self.model().steps[index].display_name
        cmd = UndoableChange(
            self.graph_view,
            lambda: self.model().rename_step(index, old_name),
            lambda: self.model().rename_step(index, new_name)
        )
        self.undo_stack.push(cmd)

    def proof_step_selected(self, selected: QItemSelection,
                            deselected: QItemSelection) -> None:
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
        cmd = GroupRewriteSteps(self.graph_view, self, indices[0] - 1,
                                indices[-1] - 1)
        self.undo_stack.push(cmd)

    def ungroup_selected_step(self) -> None:
        from .commands import UngroupRewriteSteps
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) != 1:
            raise ValueError("Can only ungroup one step")

        index = selected_indexes[0].row()
        grouped_rewrites = self.model().steps[index - 1].grouped_rewrites
        if index == 0 or grouped_rewrites is None:
            raise ValueError("Step is not grouped")

        self.move_to_step(index - 1)
        cmd = UngroupRewriteSteps(self.graph_view, self, index - 1)
        self.undo_stack.push(cmd)


class ProofStepItemDelegate(QStyledItemDelegate):
    """This class controls the painting of items in the proof steps list
    view.

    We paint a "git-style" line with circles to denote individual steps
    in a proof.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(
            self, painter: QPainter, option: QStyleOptionViewItem,
            index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()
        # Draw background
        painter.setPen(Qt.GlobalColor.transparent)
        is_selected: bool = bool(
            option.state & QStyle.StateFlag.State_Selected)  # type: ignore
        is_mouse_over: bool = bool(
            option.state & QStyle.StateFlag.State_MouseOver)  # type: ignore
        if display_setting.dark_mode:
            if is_selected:
                painter.setBrush(QColor(60, 80, 120))
            elif is_mouse_over:
                painter.setBrush(QColor(50, 60, 80))
            else:
                painter.setBrush(QColor(35, 39, 46))
        else:
            if is_selected:
                painter.setBrush(QColor(204, 232, 255))
            elif is_mouse_over:
                painter.setBrush(QColor(229, 243, 255))
            else:
                painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(option.rect)  # type: ignore[attr-defined]

        # Draw line
        is_last = index.row() == index.model().rowCount() - 1
        rect_height = option.rect.height()  # type: ignore
        line_height = rect_height if not is_last else rect_height / 2
        line_rect = QRect(
            self.line_padding,
            int(option.rect.y()),  # type: ignore[attr-defined]
            self.line_width,
            int(line_height)
        )
        if display_setting.dark_mode:
            painter.setBrush(QColor(180, 180, 180))
        else:
            painter.setBrush(Qt.GlobalColor.black)
        painter.drawRect(line_rect)

        # Draw circle
        if display_setting.dark_mode:
            gray_color = QColor(180, 180, 180)
            painter.setPen(QPen(gray_color, self.circle_outline_width))
        else:
            black_pen = QPen(Qt.GlobalColor.black, self.circle_outline_width)
            painter.setPen(black_pen)
        painter.setBrush(display_setting.effective_colors["z_spider"])
        if is_selected:
            circle_radius = self.circle_radius_selected
        else:
            circle_radius = self.circle_radius
        circle_x = self.line_padding + self.line_width / 2
        circle_y = option.rect.y() + option.rect.height() / 2  # type: ignore
        painter.drawEllipse(
            QPointF(circle_x, circle_y),
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        font_metrics = QFontMetrics(option.font)  # type: ignore
        text_height = font_metrics.height()
        text_x = (option.rect.x() + self.line_width +  # type: ignore
                  2 * self.line_padding)
        text_y = (option.rect.y() + option.rect.height() / 2 -  # type: ignore
                  text_height / 2)
        text_rect = QRect(
            int(text_x),
            int(text_y),
            option.rect.width(),  # type: ignore[attr-defined]
            text_height
        )
        font = option.font  # type: ignore[attr-defined]
        if is_selected:
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

    def sizeHint(
            self, option: QStyleOptionViewItem,
            index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(
            size.width(),
            size.height() + 2 * self.vert_padding)  # noqa: E501

    def createEditor(
            self, parent: QWidget, option: QStyleOptionViewItem,
            index: Union[QModelIndex, QPersistentModelIndex]) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(
            self, editor: QWidget,
            index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        assert isinstance(editor, QLineEdit)
        text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        editor.setText(text)

    def setModelData(
            self, editor: QWidget, model: QAbstractItemModel,
            index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        step_view.rename_proof_step(editor.text(), index.row() - 1)
