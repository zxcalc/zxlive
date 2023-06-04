from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Iterator, Sequence

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QButtonGroup
from pyzx.graph.base import BaseGraph, VT, ET

from .graphscene import GraphScene
from .graphview import GraphView


@dataclass
class ToolbarSection:
    """The data needed to construct a section in the panel toolbar.

    Contains a sequence of buttons that should be added in the section.
    If the buttons are checkable, we can optionally allow only one of them
    to be selected at any given time by setting `exclusive=True`."""
    buttons: Sequence[QToolButton]
    exclusive: bool = False


class BasePanelMeta(type(QWidget), type(ABC)):
    """Dummy metaclass to enable `BasePanel` to inherit from both `QWidget`
    and `ABC`.

    This avoids Python's infamous metaclass conflict issue.
    See http://www.phyast.pitt.edu/~micheles/python/metatype.html """
    pass


class BasePanel(QWidget, ABC, metaclass=BasePanelMeta):
    """Base class implementing functionality shared between the edit and
    proof panels."""

    graph: BaseGraph[VT, ET]
    graph_scene: GraphScene
    graph_view: GraphView

    toolbar: QToolBar
    undo_stack: QUndoStack

    def __init__(self, graph: BaseGraph, graph_scene: GraphScene) -> None:
        super().__init__()
        self.graph = graph
        self.graph_scene = graph_scene
        self.graph_view = GraphView(self.graph_scene)
        self.undo_stack = QUndoStack(self)

        # Use box layout that fills the entire tab
        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)

        self.toolbar = QToolBar()
        self.layout().addWidget(self.toolbar)
        self.layout().addWidget(self.graph_view)

        self.graph_view.set_graph(self.graph)

        self._populate_toolbar()

    def update_graph_view(self):
        """Call this function whenever the graph has been updated."""
        self.graph_view.set_graph(self.graph)

    def _populate_toolbar(self) -> None:
        undo = QToolButton(self, text="Undo")
        redo = QToolButton(self, text="Redo")
        undo.clicked.connect(self._undo_clicked)
        redo.clicked.connect(self._redo_clicked)
        for btn in (undo, redo):
            self.toolbar.addWidget(btn)
        self.toolbar.addSeparator()

        for section in self._toolbar_sections():
            group = QButtonGroup(self, exclusive=section.exclusive)
            for btn in section.buttons:
                self.toolbar.addWidget(btn)
                group.addButton(btn)
            self.toolbar.addSeparator()

    @abstractmethod
    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        pass

    def _undo_clicked(self):
        self.undo_stack.undo()

    def _redo_clicked(self):
        self.undo_stack.redo()

