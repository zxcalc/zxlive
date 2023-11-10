from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Sequence

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QSplitter,
                               QToolBar, QVBoxLayout, QWidget)

from .animations import AnimatedUndoStack
from .commands import SetGraph
from .common import GraphT
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

    graph_scene: GraphScene
    graph_view: GraphView

    toolbar: QToolBar
    undo_stack: AnimatedUndoStack
    file_path: Optional[str]
    file_type: Optional[FileFormat]

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
        empty_graph = GraphT()
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
        assert isinstance(copied_graph, GraphT)
        return copied_graph
