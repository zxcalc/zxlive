import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel, QAbstractListModel,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QListView, QMenu,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QWidget)

from .common import GraphT
from .graphscene import GraphScene
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

        model_index = self.createIndex(index, 0)
        self.dataChanged.emit(model_index, model_index, [])

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
        self.steps[index] = Rewrite(name, old_step.rule, old_step.graph, old_step.grouped_rewrites)

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
        self._step_preview_cache: dict[tuple[int, int, int], QPixmap] = {}
        self._preview_aspect_ratio_cache: dict[int, float] = {}
        self._previews_visible = bool(display_setting.previews_show)
        self._preview_hidden_rows: set[int] = set()
        self._connected_model: Optional[ProofModel] = None
        self._resize_layout_timer = QTimer(self)
        self._resize_layout_timer.setSingleShot(True)
        self._resize_layout_timer.timeout.connect(self._finish_resize_layout)
        self._connect_model_signals(self.model())

    # overriding this method to change the return type and stop mypy from complaining
    def model(self) -> ProofModel:
        model = super().model()
        assert isinstance(model, ProofModel)
        return model

    def set_model(self, model: ProofModel) -> None:
        self.setModel(model)
        self._preview_hidden_rows.clear()
        self._clear_step_preview_cache()
        # it looks like the selectionModel is linked to the model, so after updating the model we need to reconnect the selectionModel signals.
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self._connect_model_signals(model)
        self.setCurrentIndex(model.index(len(model.steps), 0))

    def _connect_model_signals(self, model: ProofModel) -> None:
        if self._connected_model is not None:
            self._disconnect_model_signals(self._connected_model)
        model.rowsInserted.connect(self._on_rows_inserted)
        model.rowsRemoved.connect(self._on_rows_removed)
        model.dataChanged.connect(self._on_data_changed)
        self._connected_model = model

    def _disconnect_model_signals(self, model: ProofModel) -> None:
        model.rowsInserted.disconnect(self._on_rows_inserted)
        model.rowsRemoved.disconnect(self._on_rows_removed)
        model.dataChanged.disconnect(self._on_data_changed)

    def _on_rows_inserted(self, _parent: QModelIndex, first: int, last: int) -> None:
        shift_by = last - first + 1
        shifted_hidden_rows = set()
        for row in self._preview_hidden_rows:
            if row >= first:
                shifted_hidden_rows.add(row + shift_by)
            else:
                shifted_hidden_rows.add(row)
        self._preview_hidden_rows = shifted_hidden_rows
        self._clear_step_preview_cache()

    def _on_rows_removed(self, _parent: QModelIndex, first: int, last: int) -> None:
        removed_count = last - first + 1
        shifted_hidden_rows = set()
        for row in self._preview_hidden_rows:
            if first <= row <= last:
                continue
            if row > last:
                shifted_hidden_rows.add(row - removed_count)
            else:
                shifted_hidden_rows.add(row)
        self._preview_hidden_rows = shifted_hidden_rows
        self._clear_step_preview_cache()

    def _on_data_changed(self, *_: Any) -> None:
        self._clear_step_preview_cache()

    def _clear_step_preview_cache(self) -> None:
        self._step_preview_cache.clear()
        self._preview_aspect_ratio_cache.clear()
        self.viewport().update()

    def resizeEvent(self, event: Any) -> None:
        """Clear preview caches and relayout items when the view is resized."""
        super().resizeEvent(event)
        self._clear_step_preview_cache()
        # Defer expensive relayout until resize settles to avoid repaint storms/crashes.
        self._resize_layout_timer.start(50)

    def _finish_resize_layout(self) -> None:
        self.doItemsLayout()

    def previews_enabled(self) -> bool:
        return self._previews_visible

    def all_previews_visible(self) -> bool:
        return self._previews_visible and not self._preview_hidden_rows

    def set_previews_enabled(self, visible: bool) -> None:
        """Enable or disable diagram previews globally."""
        changed = self._previews_visible != visible
        self._previews_visible = visible
        if not changed:
            return
        self._clear_step_preview_cache()
        self.doItemsLayout()

    def set_all_previews_visible(self) -> None:
        """Force all step previews visible."""
        changed = (not self._previews_visible) or bool(self._preview_hidden_rows)
        self._previews_visible = True
        self._preview_hidden_rows.clear()
        if not changed:
            return
        self._clear_step_preview_cache()
        self.doItemsLayout()

    def preview_visible_for_index(self, index: int) -> bool:
        if not self._previews_visible:
            return False
        return index not in self._preview_hidden_rows

    def set_preview_visibility_for_indexes(self, indexes: list[int], visible: bool) -> None:
        changed = False
        for index in indexes:
            if visible and index in self._preview_hidden_rows:
                self._preview_hidden_rows.remove(index)
                changed = True
            if not visible and index not in self._preview_hidden_rows:
                self._preview_hidden_rows.add(index)
                changed = True
        if not changed:
            return
        self._clear_step_preview_cache()
        self.doItemsLayout()

    def show_only_selected_previews(self, indexes: list[int]) -> None:
        """Show previews only for selected rows, even if global previews are currently hidden."""
        row_count = self.model().rowCount()
        selected = {row for row in indexes if 0 <= row < row_count}
        if not selected:
            return
        self._previews_visible = True
        self._preview_hidden_rows = {row for row in range(row_count) if row not in selected}
        self._clear_step_preview_cache()
        self.doItemsLayout()

    def _preview_aspect_ratio(self, index: int) -> float:
        if index not in self._preview_aspect_ratio_cache:
            graph = self.model().get_graph(index)
            scene = GraphScene()
            scene.set_graph(graph)
            source_rect = scene.itemsBoundingRect().adjusted(-25, -25, 25, 25)
            if source_rect.isNull() or source_rect.width() < 1 or source_rect.height() < 1:
                source_rect = QRectF(0, 0, 1, 1)
            self._preview_aspect_ratio_cache[index] = source_rect.height() / source_rect.width()
        return self._preview_aspect_ratio_cache[index]

    def preview_size(self, index: int) -> QSize:
        """Return an adaptive preview thumbnail size for a proof-step index."""
        available_width = max(80, self.viewport().width() - 2 * ProofStepItemDelegate.line_padding - 28)
        min_thumb_height = 70
        max_thumb_height = 280
        min_height_width_ratio = 0.3
        max_height_width_ratio = 1.25

        adaptive_ratio = self._preview_aspect_ratio(index)
        bounded_ratio = max(min_height_width_ratio, min(max_height_width_ratio, adaptive_ratio))

        thumb_width = available_width
        thumb_height = int(thumb_width * bounded_ratio)

        if thumb_height > max_thumb_height:
            thumb_height = max_thumb_height
            thumb_width = max(80, min(available_width, int(thumb_height / bounded_ratio)))
        elif thumb_height < min_thumb_height:
            thumb_height = min_thumb_height
            thumb_width = max(80, min(available_width, int(thumb_height / bounded_ratio)))

        return QSize(thumb_width, thumb_height)

    def _render_preview_image(self, index: int, size: QSize) -> QPixmap:
        graph = self.model().get_graph(index)
        scene = GraphScene()
        scene.set_graph(graph)

        device_pixel_ratio = max(1.0, self.devicePixelRatioF())
        render_width = max(1, int(size.width() * device_pixel_ratio))
        render_height = max(1, int(size.height() * device_pixel_ratio))
        pixmap = QPixmap(render_width, render_height)
        pixmap.setDevicePixelRatio(device_pixel_ratio)

        if display_setting.dark_mode:
            background_color = QColor(32, 35, 41)
        else:
            background_color = QColor(252, 252, 252)
        pixmap.fill(background_color)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        source_rect = scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)
        if source_rect.isNull() or source_rect.width() < 1 or source_rect.height() < 1:
            source_rect = QRectF(0, 0, 1, 1)

        scale = min(size.width() / source_rect.width(), size.height() / source_rect.height())
        target_width = source_rect.width() * scale
        target_height = source_rect.height() * scale
        target_rect = QRectF(
            (size.width() - target_width) / 2,
            (size.height() - target_height) / 2,
            target_width,
            target_height,
        )

        scene.render(
            painter,
            target_rect,
            source_rect,
            Qt.AspectRatioMode.IgnoreAspectRatio,
        )
        painter.end()
        return pixmap

    def preview_image(self, index: int, size: QSize) -> QPixmap:
        if index < 0 or index >= self.model().rowCount() or size.width() <= 0 or size.height() <= 0:
            return QPixmap(max(1, size.width()), max(1, size.height()))
        key = (index, size.width(), size.height())
        if key not in self._step_preview_cache:
            self._step_preview_cache[key] = self._render_preview_image(index, size)
        return self._step_preview_cache[key]

    def move_to_step(self, index: int) -> None:
        idx = self.model().index(index, 0, QModelIndex())
        self.clearSelection()
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(idx)
        self.selectionModel().blockSignals(False)
        self.update(idx)
        g = self.model().get_graph(index)
        self.graph_view.set_graph(g)

    def _add_step_edit_actions(self, context_menu: QMenu, selected_indexes: list[QModelIndex],
                               action_function_map: dict[Any, Any]) -> None:
        if not selected_indexes:
            return

        index = selected_indexes[0].row()
        if len(selected_indexes) > 1:
            group_action = context_menu.addAction("Group Steps")
            action_function_map[group_action] = self.group_selected_steps
            return

        if index == 0:
            return

        rename_action = context_menu.addAction("Rename Step")
        action_function_map[rename_action] = lambda: self.edit(selected_indexes[0])
        if self.model().steps[index - 1].grouped_rewrites is not None:
            ungroup_action = context_menu.addAction("Ungroup Steps")
            action_function_map[ungroup_action] = self.ungroup_selected_step

    def _add_preview_actions(self, context_menu: QMenu, selected_indexes: list[QModelIndex],
                             action_function_map: dict[Any, Any]) -> None:
        toggle_preview_action = context_menu.addAction("Show All Step Previews")
        toggle_preview_action.setCheckable(True)
        toggle_preview_action.setChecked(self.all_previews_visible())
        action_function_map[toggle_preview_action] = self.toggle_diagram_previews

        if not selected_indexes:
            return

        selected_rows = [selected_index.row() for selected_index in selected_indexes]
        selected_previews_are_visible = all(self.preview_visible_for_index(row) for row in selected_rows)
        if selected_previews_are_visible:
            toggle_selected_preview_action = context_menu.addAction("Hide Selected Step Previews")
            action_function_map[toggle_selected_preview_action] = lambda: self.set_preview_visibility_for_indexes(selected_rows, False)
            return

        toggle_selected_preview_action = context_menu.addAction("Show Only Selected Step Previews")
        if self.previews_enabled():
            action_function_map[toggle_selected_preview_action] = lambda: self.set_preview_visibility_for_indexes(selected_rows, True)
        else:
            action_function_map[toggle_selected_preview_action] = lambda: self.show_only_selected_previews(selected_rows)

    def show_context_menu(self, position: QPoint) -> None:
        selected_indexes = self.selectedIndexes()
        context_menu = QMenu(self)
        action_function_map: dict[Any, Any] = {}

        self._add_step_edit_actions(context_menu, selected_indexes, action_function_map)
        if selected_indexes:
            context_menu.addSeparator()
        self._add_preview_actions(context_menu, selected_indexes, action_function_map)

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_function_map:
            action_function_map[action]()

    def toggle_diagram_previews(self) -> None:
        if self.all_previews_visible():
            self.set_previews_enabled(False)
        else:
            self.set_all_previews_visible()

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
    """
    This class controls the painting of items in the proof steps list view.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        show_preview_image = step_view.preview_visible_for_index(index.row())
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
        text_y = int(option.rect.y() + option.rect.height() / 2 - text_height / 2)  # type: ignore[attr-defined]

        if show_preview_image:
            image_size = step_view.preview_size(index.row())
            image_available_width = max(80, step_view.viewport().width() - 2 * self.line_padding - 28)
            image_left = int(
                option.rect.x() + self.line_width + 2 * self.line_padding + max(0, (image_available_width - image_size.width()) / 2)
            )  # type: ignore[attr-defined]
            image_top = int(option.rect.y() + self.vert_padding)  # type: ignore[attr-defined]
            preview_pixmap = step_view.preview_image(index.row(), image_size)
            painter.drawPixmap(image_left, image_top, preview_pixmap)
            text_y = image_top + image_size.height() + self.vert_padding

        text_rect = QRect(
            int(option.rect.x() + self.line_width + 2 * self.line_padding),  # type: ignore[attr-defined]
            text_y,
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
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        if step_view.preview_visible_for_index(index.row()):
            preview_block_height = step_view.preview_size(index.row()).height() + self.vert_padding
        else:
            preview_block_height = 0
        return QSize(size.width(), size.height() + 2 * self.vert_padding + preview_block_height)

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
