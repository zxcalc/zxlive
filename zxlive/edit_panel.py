from dataclasses import dataclass

from PySide6.QtGui import QAction, QActionGroup, QUndoStack
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QButtonGroup, QPushButton
from pyzx import EdgeType, VertexType
from pyzx.graph.base import BaseGraph, VT

from .commands import AddEdge, AddNode, MoveNode
from .graphscene import EditGraphScene, GraphScene
from .graphview import GraphView


class GraphEditPanel(QWidget):
    """Panel for the edit mode of ZX live."""

    graph: BaseGraph
    graph_scene: EditGraphScene
    graph_view: GraphView

    toolbar: QToolBar
    undo_stack: QUndoStack

    _curr_ety: EdgeType = VertexType.Z
    _curr_vty: VertexType = EdgeType.SIMPLE

    def __init__(self, graph: BaseGraph) -> None:
        super().__init__()
        self.graph = graph

        # Use box layout that fills the entire tab
        self.setLayout(QVBoxLayout())
        # self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        self.undo_stack = QUndoStack(self)

        self.toolbar = QToolBar()
        self.layout().addWidget(self.toolbar)

        self.graph_scene = EditGraphScene(self._move_vert, self._add_vert, self._add_edge)
        self.graph_view = GraphView(self.graph_scene)
        self.graph_view.set_graph(self.graph)
        self.layout().addWidget(self.graph_view)

        self._populate_toolbar()

    def _populate_toolbar(self) -> None:
        undo = QToolButton(self, text="Undo")
        redo = QToolButton(self, text="Redo")
        undo.clicked.connect(self._undo_clicked)
        redo.clicked.connect(self._redo_clicked)
        for btn in (undo, redo):
            self.toolbar.addWidget(btn)

        self.toolbar.addSeparator()

        vty_group = QButtonGroup(self, exclusive=True)
        select_z = QToolButton(self, text="Z Spider", checkable=True, checked=True)  # Selected by default
        select_x = QToolButton(self, text="X Spider", checkable=True)
        select_boundary = QToolButton(self, text="Boundary", checkable=True)
        select_z.clicked.connect(lambda _: self._select_vty(VertexType.Z))
        select_x.clicked.connect(lambda _: self._select_vty(VertexType.X))
        select_boundary.clicked.connect(lambda _: self._select_vty(VertexType.BOUNDARY))
        for btn in (select_z, select_x, select_boundary):
            self.toolbar.addWidget(btn)
            vty_group.addButton(btn)

        self.toolbar.addSeparator()

        ety_group = QButtonGroup(self, exclusive=True)
        select_simple = QToolButton(self, text="Simple Edge", checkable=True, checked=True)  # Selected by default
        select_had = QToolButton(self, text="Had Edge", checkable=True)
        select_simple.clicked.connect(lambda _: self._select_ety(EdgeType.SIMPLE))
        select_had.clicked.connect(lambda _: self._select_ety(EdgeType.HADAMARD))
        for btn in (select_simple, select_had):
            self.toolbar.addWidget(btn)
            ety_group.addButton(btn)

        self.toolbar.addSeparator()

        export = QToolButton(self, text="Export")
        reset = QToolButton(self, text="Reset")
        for btn in (export, reset):
            self.toolbar.addWidget(btn)

    def _select_vty(self, vty: VertexType) -> None:
        self._curr_vty = vty

    def _select_ety(self, ety: EdgeType) -> None:
        self._curr_ety = ety
        self.graph_scene.curr_ety = ety

    def _undo_clicked(self):
        self.undo_stack.undo()

    def _redo_clicked(self):
        self.undo_stack.redo()

    def _add_vert(self, x: float, y: float) -> None:
        cmd = AddNode(self.graph_view.graph_scene, x, y, self._curr_vty)
        self.undo_stack.push(cmd)

    def _add_edge(self, u: VT, v: VT) -> None:
        cmd = AddEdge(self.graph_view.graph_scene, u, v, self._curr_ety)
        self.undo_stack.push(cmd)

    def _move_vert(self, v: VT, x: float, y: float):
        cmd = MoveNode(self.graph_view.graph_scene, v, x, y)
        self.undo_stack.push(cmd)

