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

from .common import GraphT, ET
from .settings import display_setting


def _apply_rewrite_highlight(  # pylint: disable=too-many-locals,too-many-branches
    scene: "GraphScene",
    rewrite_meta: "Rewrite",
    g_current: GraphT,
) -> None:
    """Apply forward-looking rewrite highlight based on rewrite metadata."""
    current_verts = set(g_current.vertices())

    # 1) Edge-only highlighting (e.g. Add identity - the edge the magic wand acts on).
    highlight_edge_pairs = getattr(rewrite_meta, "highlight_edge_pairs", None)
    if highlight_edge_pairs:
        edges_only_set: set[ET] = set()
        for pair in highlight_edge_pairs:
            if isinstance(pair, tuple) and len(pair) == 2:
                v1, v2 = int(pair[0]), int(pair[1])
                if v1 in current_verts and v2 in current_verts:
                    edges_only_set |= set(g_current.edges(v1, v2))
        if edges_only_set:
            scene.set_rewrite_highlight(set(), edges_only_set)
            return

    # 2) Match-based forward highlighting (MATCH_DOUBLE, e.g. Spider Fusion).
    highlight_match_pairs = getattr(rewrite_meta, "highlight_match_pairs", None)
    if highlight_match_pairs:
        verts_set: set[int] = set()
        edges_set: set[ET] = set()
        for match in highlight_match_pairs:
            if isinstance(match, tuple) and len(match) == 2:
                v1, v2 = int(match[0]), int(match[1])
                if v1 not in current_verts or v2 not in current_verts:
                    continue
                verts_set.add(v1)
                verts_set.add(v2)
                edges_set |= set(g_current.edges(v1, v2))
        scene.set_rewrite_highlight(verts_set, edges_set)
        return

    # 3) Vertex-based highlighting (unfuse, color change, strong comp, remove identity, etc.).
    highlight_verts_list = getattr(rewrite_meta, "highlight_verts", None)
    if highlight_verts_list:
        verts_set = {int(v) for v in highlight_verts_list if int(v) in current_verts}
        if len(verts_set) == 2:
            s = sorted(verts_set)
            edges_highlight = set(g_current.edges(s[0], s[1]))
        else:
            edges_highlight = set()
            for v in verts_set:
                for e in g_current.incident_edges(v):
                    s, t = g_current.edge_st(e)
                    if s in verts_set and t in verts_set:
                        edges_highlight.add(e)
        scene.set_rewrite_highlight(verts_set, edges_highlight)
        return

    scene.clear_rewrite_highlight()


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str  # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # New graph after applying the rewrite
    grouped_rewrites: Optional[list['Rewrite']] = None  # Optional field to store the grouped rewrites
    # Optional semantic highlight for forward highlighting:
    # - highlight_match_pairs: For MATCH_DOUBLE (e.g. Spider Fusion) [(v1, v2), ...].
    # - highlight_verts: Vertex IDs to highlight (unfuse, color change, strong comp, remove id, etc.).
    # - highlight_edge_pairs: Edge-only (e.g. Add identity) [(v1, v2), ...] - highlight edges between pairs only.
    highlight_match_pairs: Optional[list[tuple[int, int]]] = None
    highlight_verts: Optional[list[int]] = None
    highlight_edge_pairs: Optional[list[tuple[int, int]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the rewrite to Python dictionary."""
        return {
            "display_name": self.display_name,
            "rule": self.rule,
            "graph": self.graph.to_dict(),
            "grouped_rewrites": [r.to_dict() for r in self.grouped_rewrites] if self.grouped_rewrites else None,
            "highlight_match_pairs": self.highlight_match_pairs,
            "highlight_verts": self.highlight_verts,
            "highlight_edge_pairs": self.highlight_edge_pairs,
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

        pairs = d.get("highlight_match_pairs")
        if pairs is not None:
            pairs = [tuple(p) for p in pairs]
        edge_pairs = d.get("highlight_edge_pairs")
        if edge_pairs is not None:
            edge_pairs = [tuple(p) for p in edge_pairs]
        # Backward compat: old proofs may have highlight_unfuse_verts
        highlight_verts = d.get("highlight_verts") or d.get("highlight_unfuse_verts")

        return Rewrite(
            display_name=d.get("display_name", d["rule"]),  # Old proofs may not have display names
            rule=d["rule"],
            graph=graph,
            grouped_rewrites=[Rewrite.from_json(r) for r in grouped_rewrites] if grouped_rewrites else None,
            highlight_match_pairs=pairs,
            highlight_verts=highlight_verts,
            highlight_edge_pairs=edge_pairs,
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
            new_step = Rewrite(
                old_step.display_name,
                old_step.rule,
                graph,
                old_step.grouped_rewrites,
                old_step.highlight_match_pairs,
                old_step.highlight_verts,
                old_step.highlight_edge_pairs,
            )
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

    def rowCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on tree models, the
        # user has to specify the index of the parent. In a list, we always expect the
        # parent to be `None` or the empty `QModelIndex()`
        if not index or not index.isValid():
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
        self.steps[index] = Rewrite(
            name, old_step.rule, old_step.graph, old_step.grouped_rewrites,
            old_step.highlight_match_pairs, old_step.highlight_verts,
            old_step.highlight_edge_pairs,
        )

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index` with a new grouped step"""
        new_rewrite = Rewrite(
            "Grouped Steps: " + " 🡒 ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
            "Grouped",
            self.get_graph(end_index + 1),
            self.steps[start_index:end_index + 1],
            None, None, None,
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
        self.setUniformItemSizes(True)
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
        self.clearSelection()
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(idx)
        self.selectionModel().blockSignals(False)
        self.update(idx)
        g_current = self.model().get_graph(index)
        self.graph_view.set_graph(g_current)

        # Highlight the differences between this step and the *next* one.
        scene = self.graph_view.graph_scene
        num_steps = len(self.model().steps)

        # If highlighting is disabled in the settings, always clear any
        # existing rewrite highlight and return.
        if not display_setting.highlight_rewrites:
            scene.clear_rewrite_highlight()
            return

        # Last proof step: no "next" transition to highlight (forward-looking).
        if index >= num_steps:
            scene.clear_rewrite_highlight()
            return
        # There is a rewrite taking graph index -> index + 1.
        rewrite_meta = self.model().steps[index]
        _apply_rewrite_highlight(scene, rewrite_meta, g_current)

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
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:  # pylint: disable=too-many-branches
        painter.save()
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

        # Draw line
        is_last = index.row() == index.model().rowCount() - 1
        line_rect = QRect(
            self.line_padding,
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
            QPointF(self.line_padding + self.line_width / 2, option.rect.y() + option.rect.height() / 2),  # type: ignore[attr-defined]
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_height = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
        text_rect = QRect(
            int(option.rect.x() + self.line_width + 2 * self.line_padding),  # type: ignore[attr-defined]
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
        editor.setText(str(value))

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        step_view.rename_proof_step(editor.text(), index.row() - 1)
