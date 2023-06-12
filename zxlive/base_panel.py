from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Iterator, Sequence

from PySide6.QtGui import QUndoStack, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QButtonGroup
from pyzx.graph.base import BaseGraph, VT, ET
from pyzx.graph import Graph

from .graphscene import GraphScene
from .graphview import GraphView
from .commands import SetGraph


@dataclass
class ToolbarSection:
    """The data needed to construct a section in the panel toolbar.

    Contains a sequence of buttons that should be added in the section.
    If the buttons are checkable, we can optionally allow only one of them
    to be selected at any given time by setting `exclusive=True`."""
    buttons: Sequence[QToolButton]
    exclusive: bool = False

    def __init__(self, *args: QToolButton, exclusive: bool = False):
        self.buttons = args
        self.exclusive = exclusive


class BasePanelMeta(type(QWidget), type(ABC)):
    """Dummy metaclass to enable `BasePanel` to inherit from both `QWidget`
    and `ABC`.

    This avoids Python's infamous metaclass conflict issue.
    See http://www.phyast.pitt.edu/~micheles/python/metatype.html """
    pass


class BasePanel(QWidget, ABC, metaclass=BasePanelMeta):
    """Base class implementing functionality shared between the edit and
    proof panels."""

    graph_scene: GraphScene
    graph_view: GraphView

    toolbar: QToolBar
    undo_stack: QUndoStack

    def __init__(self, graph: BaseGraph, graph_scene: GraphScene) -> None:
        super().__init__()
        self.graph_scene = graph_scene
        self.graph_view = GraphView(self.graph_scene)
        self.undo_stack = QUndoStack(self)

        # Use box layout that fills the entire tab
        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)

        self.toolbar = QToolBar()
        self.layout().addWidget(self.toolbar)
        self.layout().addWidget(self.graph_view)

        self.graph_view.set_graph(graph)

        self._populate_toolbar()

    @property
    def graph(self) -> BaseGraph[VT, ET]:
        return self.graph_scene.g

    def _populate_toolbar(self) -> None:
        for section in self._toolbar_sections():
            group = QButtonGroup(self, exclusive=section.exclusive)
            for btn in section.buttons:
                self.toolbar.addWidget(btn)
                group.addButton(btn)
            self.toolbar.addSeparator()

    @abstractmethod
    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        pass

    def clear_graph(self):
        empty_graph = Graph()
        cmd = SetGraph(self.graph_view,empty_graph)
        self.undo_stack.push(cmd)

        