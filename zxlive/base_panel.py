from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QSplitter,
                               QToolBar, QVBoxLayout, QWidget)

from .animations import AnimatedUndoStack
from .commands import ChangeEdgeCurve, SetGraph
from .common import GraphT, new_graph
from .dialogs import FileFormat
from .graphscene import GraphScene
from .graphview import GraphView


@dataclass
class ToolbarSection:
    """The data needed to construct a section in the panel toolbar.

    Contains a sequence of buttons that should be added in the section.
    If the buttons are checkable, we can optionally allow only one of them
    to be selected at any given time by setting `exclusive=True`."""
    buttons: Sequence[QWidget | QAction]
    exclusive: bool = False

    def __init__(self, *args: QWidget | QAction, exclusive: bool = False) -> None:
        self.buttons = args
        self.exclusive = exclusive


class BasePanel(QWidget):
    """Base class implementing functionality shared between the edit and
    proof panels."""
    splitter_sizes = dict()

    graph_scene: GraphScene
    graph_view: GraphView

    toolbar: QToolBar
    undo_stack: AnimatedUndoStack
    file_path: Optional[str]
    file_type: Optional[FileFormat]

    play_sound_signal = Signal(object)  # Actual type: SFXEnum

    def __init__(self, *actions: QAction) -> None:
        super().__init__()
        self.addActions(actions)
        self.undo_stack = AnimatedUndoStack(self)

        # Use box layout that fills the entire tab
        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)
        self.toolbar = QToolBar()
        self.layout().addWidget(self.toolbar)

        self.splitter = QSplitter(self)
        self.layout().addWidget(self.splitter)
        self.splitter.splitterMoved.connect(self.sync_splitter_sizes)

        self.file_path = None
        self.file_type = None

        self._populate_toolbar()

    @property
    def graph(self) -> GraphT:
        return self.graph_scene.g

    def _populate_toolbar(self) -> None:
        for section in self._toolbar_sections():
            group = QButtonGroup(self)
            group.setExclusive(section.exclusive)
            for btn in section.buttons:
                if isinstance(btn, QAbstractButton):
                    self.toolbar.addWidget(btn)
                    group.addButton(btn)
                elif isinstance(btn, QAction):
                    self.toolbar.addAction(btn)
                else:
                    self.toolbar.addWidget(btn)
            self.toolbar.addSeparator()

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        raise NotImplementedError

    def clear_graph(self) -> None:
        empty_graph = new_graph()
        cmd = SetGraph(self.graph_view, empty_graph)
        self.undo_stack.push(cmd)

    def replace_graph(self, graph: GraphT) -> None:
        cmd = SetGraph(self.graph_view, graph)
        self.undo_stack.push(cmd)

    def select_all(self) -> None:
        self.graph_scene.select_all()

    def deselect_all(self) -> None:
        self.graph_scene.clearSelection()

    def copy_selection(self) -> GraphT:
        selection = list(self.graph_scene.selected_vertices)
        copied_graph = self.graph.subgraph_from_vertices(selection)
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert isinstance(copied_graph, GraphT)  # type: ignore
        return copied_graph

    def update_colors(self) -> None:
        self.graph_scene.update_colors()

    def sync_splitter_sizes(self):
        self.splitter_sizes[self.__class__] = self.splitter.sizes()

    def set_splitter_size(self):
        if self.__class__ in self.splitter_sizes:
            self.splitter.setSizes(self.splitter_sizes[self.__class__])

    def change_edge_curves(self, eitem, new_distance, old_distance):
        self.undo_stack.push(ChangeEdgeCurve(self.graph_view, eitem, new_distance, old_distance))
