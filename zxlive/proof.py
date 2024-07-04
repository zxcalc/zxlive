import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractListModel, QModelIndex,
                            QPersistentModelIndex, Qt, QPoint)
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QListView, QMenu

from .common import GraphT


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # New graph after applying the rewrite
    grouped_rewrites: Optional[list['Rewrite']] = None # Optional field to store the grouped rewrites

    def to_json(self) -> str:
        """Serializes the rewrite to JSON."""
        return json.dumps({
            "display_name": self.display_name,
            "rule": self.rule,
            "graph": self.graph.to_json()
        })

    @staticmethod
    def from_json(json_str: str) -> "Rewrite":
        """Deserializes the rewrite from JSON."""
        d = json.loads(json_str)

        return Rewrite(
            display_name=d.get("display_name", d["rule"]), # Old proofs may not have display names
            rule=d["rule"],
            graph=GraphT.from_json(d["graph"]),
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
            old_step = self.steps[index-1]
            new_step = Rewrite(old_step.display_name, old_step.rule, graph)
            self.steps[index-1] = new_step

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int=Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if index.row() >= len(self.steps)+1 or index.column() >= 1:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.row() == 0:
                return "START"
            else:
                return self.steps[index.row()-1].display_name
        elif role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.headerData`.

        Indicates that this model doesn't have a header.
        """
        return None

    def columnCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of columns"""
        return 1

    def rowCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on tree models, the
        # user has to specify the index of the parent. In a list, we always expect the
        # parent to be `None` or the empty `QModelIndex()`
        if not index or not index.isValid():
            return len(self.steps)+1
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
            return self.initial_graph.copy()
        else:
            copy = self.steps[index-1].graph.copy()
            # Mypy issue: https://github.com/python/mypy/issues/11673
            assert isinstance(copy, GraphT)  # type: ignore
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
            "Grouped Steps: " + " -> ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
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

    def to_json(self) -> str:
        """Serializes the model to JSON."""
        initial_graph = self.initial_graph.to_json()
        proof_steps = [step.to_json() for step in self.steps]

        return json.dumps({
            "initial_graph": initial_graph,
            "proof_steps": proof_steps
        })

    @staticmethod
    def from_json(json_str: str) -> "ProofModel":
        """Deserializes the model from JSON."""
        d = json.loads(json_str)
        initial_graph = GraphT.from_json(d["initial_graph"])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert isinstance(initial_graph, GraphT)  # type: ignore
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
        self.proof_model = ProofModel(self.graph_view.graph_scene.g)
        self.setModel(self.proof_model)
        self.setCurrentIndex(self.proof_model.index(0, 0))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setPalette(QColor(255, 255, 255))
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setAlternatingRowColors(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    # overriding this method to change the return type and stop mypy from complaining
    def model(self) -> ProofModel:
        return self.proof_model

    def move_to_step(self, index: int) -> None:
        idx = self.model().index(index, 0, QModelIndex())
        self.clearSelection()
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(idx)
        self.selectionModel().blockSignals(False)
        self.update(idx)
        self.graph_view.set_graph(self.proof_model.get_graph(index))

    def show_context_menu(self, position: QPoint) -> None:
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return
        context_menu = QMenu(self)
        action_function_map = {}

        if len(selected_indexes) > 1:
            group_action = context_menu.addAction("Group Steps")
            action_function_map[group_action] = self.group_selected_steps

        if len(selected_indexes) == 1:
            index = selected_indexes[0].row()
            if index != 0 and self.proof_model.steps[index - 1].grouped_rewrites is not None:
                ungroup_action = context_menu.addAction("Ungroup Steps")
                action_function_map[ungroup_action] = self.ungroup_selected_step

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_function_map:
            action_function_map[action]()

    def group_selected_steps(self) -> None:
        from .commands import GroupRewriteSteps
        from .dialogs import show_error_msg
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) < 2:
            raise ValueError("Can only group two or more steps")

        indices = sorted(index.row() for index in selected_indexes)
        if indices[-1] - indices[0] != len(indices) - 1:
            show_error_msg("Can only group contiguous steps")
            return
        if indices[0] == 0:
            show_error_msg("Cannot group the first step")
            return

        self.move_to_step(indices[-1] - 1)
        cmd = GroupRewriteSteps(self.graph_view, self, indices[0] - 1, indices[-1] - 1)
        self.undo_stack.push(cmd)

    def ungroup_selected_step(self) -> None:
        from .commands import UngroupRewriteSteps
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) != 1:
            raise ValueError("Can only ungroup one step")

        index = selected_indexes[0].row()
        if index == 0 or self.proof_model.steps[index - 1].grouped_rewrites is None:
            raise ValueError("Step is not grouped")

        self.move_to_step(index - 1)
        cmd = UngroupRewriteSteps(self.graph_view, self, index - 1)
        self.undo_stack.push(cmd)
