from typing import NamedTuple, Union, Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QFont
from pyzx.graph import GraphDiff

from zxlive.common import GraphT


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    rule: str  # Name of the rule that was applied to get to this step
    diff: GraphDiff  # Diff from the last step to this step


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
                return self.steps[index.row()-1].rule
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
        return self.graphs[index].copy()
