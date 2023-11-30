import json
from typing import NamedTuple, Union, Any

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPersistentModelIndex,
                            Qt, QAbstractItemModel)
from PySide6.QtGui import QFont
from pyzx.graph import GraphDiff

from .common import GraphT


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    diff: GraphDiff  # Diff from the last step to this step

    def to_json(self) -> str:
        """Serializes the rewrite to JSON."""
        return json.dumps({
            "display_name": self.display_name,
            "rule": self.rule,
            "diff": self.diff.to_json()
        })

    @staticmethod
    def from_json(json_str: str) -> "Rewrite":
        """Deserializes the rewrite from JSON."""
        d = json.loads(json_str)

        return Rewrite(
            display_name=d.get("display_name", d["rule"]), # Old proofs may not have display names
            rule=d["rule"],
            diff=GraphDiff.from_json(d["diff"])
        )

class ProofModel(QAbstractListModel):
    """List model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore, we store the
    rewrite that was used to go from one graph to next.
    """

    graphs: list[GraphT]  # n graphs
    steps: list[Rewrite]  # n-1 rewrite steps

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.graphs = [start_graph]
        self.steps = []

    def set_data(self, graphs: list[GraphT], steps: list[Rewrite]) -> None:
        """Sets the model data.

        Can be used to load the model from a saved state.
        """
        assert len(steps) == len(graphs) - 1
        self.beginResetModel()
        self.graphs = graphs
        self.steps = steps
        self.endResetModel()

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int=Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if index.row() >= len(self.graphs) or index.column() >= 1:
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
            return len(self.graphs)
        else:
            return 0

    def add_rewrite(self, rewrite: Rewrite, new_graph: GraphT) -> None:
        """Adds a rewrite step to the model."""
        self.beginInsertRows(QModelIndex(), len(self.graphs), len(self.graphs))
        self.graphs.append(new_graph)
        self.steps.append(rewrite)
        self.endInsertRows()

    def pop_rewrite(self) -> tuple[Rewrite, GraphT]:
        """Removes the latest rewrite from the model.

        Returns the rewrite and the graph that previously resulted from this rewrite.
        """
        self.beginRemoveRows(QModelIndex(), len(self.graphs) - 1, len(self.graphs) - 1)
        rewrite = self.steps.pop()
        graph = self.graphs.pop()
        self.endRemoveRows()
        return rewrite, graph

    def get_graph(self, index: int) -> GraphT:
        """Returns the grap at a given position in the proof."""
        copy = self.graphs[index].copy()
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert isinstance(copy, GraphT)  # type: ignore
        return copy

    def rename_step(self, index: int, name: str):
        """Change the display name"""
        old_step = self.steps[index]

        # Must create a new Rewrite object instead of modifying current object
        # since Rewrite inherits NamedTuple and is hence immutable
        self.steps[index] = Rewrite(name, old_step.rule, old_step.diff)

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def to_json(self) -> str:
        """Serializes the model to JSON."""
        initial_graph_tikz = self.graphs[0].to_json()
        proof_steps = []
        for step in self.steps:
            proof_steps.append(step.to_json())
        return json.dumps({
            "initial_graph": initial_graph_tikz,
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
            rewritten_graph = rewrite.diff.apply_diff(model.graphs[-1])
            # Mypy issue: https://github.com/python/mypy/issues/11673
            assert isinstance(rewritten_graph, GraphT)  # type: ignore
            model.add_rewrite(rewrite, rewritten_graph)
        return model
