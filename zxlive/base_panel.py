from dataclasses import dataclass
from typing import Iterator, Sequence, Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QButtonGroup, \
    QSplitter, QAbstractButton
from pyzx.graph import Graph
from pyzx.graph.graph_s import GraphS

from .common import GraphT
from .graphscene import GraphScene
from .graphview import GraphView
from .commands import SetGraph
from .dialogs import FileFormat
from .animations import AnimatedUndoStack


@dataclass
class ToolbarSection:
    """The data needed to construct a section in the panel toolbar.

    Contains a sequence of buttons that should be added in the section.
    If the buttons are checkable, we can optionally allow only one of them
    to be selected at any given time by setting `exclusive=True`."""
    buttons: Sequence[QToolButton]
    exclusive: bool = False

    def __init__(self, *args: QToolButton, exclusive: bool = False) -> None:
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
        self.graph_scene = None
        self.graph_view = None
        self.actions = actions
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
            group = QButtonGroup(self, exclusive=section.exclusive)
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
        empty_graph = Graph()
        assert isinstance(empty_graph, GraphS)
        cmd = SetGraph(self.graph_view, empty_graph)
        self.undo_stack.push(cmd)

    def select_all(self) -> None:
        self.graph_scene.select_all()

    def deselect_all(self) -> None:
        self.graph_scene.clearSelection()

    def copy_selection(self) -> GraphT:
        selection = list(self.graph_scene.selected_vertices)
        copied_graph = self.graph.subgraph_from_vertices(selection)
        assert isinstance(copied_graph, GraphS)
        return copied_graph
