from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Iterator, Sequence, Optional

from PySide6.QtGui import QUndoStack, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QButtonGroup
from pyzx.graph import Graph

from .common import VT, ET, GraphT
from .graphscene import GraphScene
from .graphview import GraphView
from .vitem import DragState
from .commands import UpdateGraph
from .dialogs import FileFormat
from .animations import AnimatedUndoStack

import zxlive.animations as anims

import copy
import pyzx

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
    undo_stack: AnimatedUndoStack
    file_path: Optional[str]
    file_type: Optional[FileFormat]

    def __init__(self, graph: GraphT, graph_scene: GraphScene) -> None:
        super().__init__()
        self.graph_scene = graph_scene
        self.graph_view = GraphView(self.graph_scene)
        self.undo_stack = AnimatedUndoStack(self)

        # Use box layout that fills the entire tab
        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)

        self.toolbar = QToolBar()
        self.layout().addWidget(self.toolbar)
        self.layout().addWidget(self.graph_view)

        self.graph_view.set_graph(graph)
        self.file_path = None
        self.file_type = None

        self._populate_toolbar()

        self.graph_scene.vertex_dragged.connect(self._vertex_dragged)
        self.graph_scene.vertex_dropped_onto.connect(self._vertex_dropped_onto)

    @property
    def graph(self) -> GraphT:
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

    def select_all(self):
        self.graph_scene.select_all()

    def deselect_all(self):
        self.graph_scene.clearSelection()

    def _vertex_dragged(self, state: DragState, v: VT, w: VT) -> None:
        if state == DragState.Onto:
            if pyzx.basicrules.check_fuse(self.graph, v, w):
                anims.anticipate_fuse(self.graph_scene.vertex_map[w])
            elif pyzx.basicrules.check_strong_comp(self.graph, v, w):
                anims.anticipate_strong_comp(self.graph_scene.vertex_map[w])
        else:
            anims.back_to_default(self.graph_scene.vertex_map[w])

    def _vertex_dropped_onto(self, v: VT, w: VT) -> None:
        if pyzx.basicrules.check_fuse(self.graph, v, w):
            g = copy.deepcopy(self.graph)
            pyzx.basicrules.fuse(g, w, v)
            anim = anims.fuse(self.graph_scene.vertex_map[v], self.graph_scene.vertex_map[w])
            cmd = UpdateGraph(self.graph_view, g)
            self.undo_stack.push(cmd, anim_before=anim)
        elif pyzx.basicrules.check_strong_comp(self.graph, v, w):
            g = copy.deepcopy(self.graph)
            pyzx.basicrules.strong_comp(g, w, v)
            anim = anims.strong_comp(self.graph, g, w, self.graph_scene)
            cmd = UpdateGraph(self.graph_view, g)
            self.undo_stack.push(cmd, anim_after=anim)

    def copy_selection(self) -> GraphT:
        selection = list(self.graph_scene.selected_vertices)
        copied_graph = self.graph.subgraph_from_vertices(selection)
        return copied_graph