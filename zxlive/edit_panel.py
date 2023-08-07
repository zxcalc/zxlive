from __future__ import annotations

import copy
from typing import Iterator

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QPalette
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout,
                               QInputDialog, QLabel, QScrollArea, QSizePolicy,
                               QSpacerItem, QToolButton, QWidget)
from pyzx import EdgeType, VertexType

from .base_panel import ToolbarSection
from .commands import ChangePhase
from .common import VT, GraphT
from .dialogs import show_error_msg
from .editor_base_panel import EditorBasePanel
from .graphscene import EditGraphScene
from .graphview import GraphView
from .parse_poly import parse
from .poly import Poly, new_var


class GraphEditPanel(EditorBasePanel):
    """Panel for the edit mode of ZX live."""

    graph_scene: EditGraphScene
    start_derivation_signal = Signal(object)

    _curr_ety: EdgeType.Type
    _curr_vty: VertexType.Type

    def __init__(self, graph: GraphT, *actions: QAction) -> None:
        super().__init__(*actions)
        self.graph_scene = EditGraphScene()
        self.graph_scene.vertices_moved.connect(self.vert_moved)
        self.graph_scene.vertex_double_clicked.connect(self.vert_double_clicked)
        self.graph_scene.vertex_added.connect(self.add_vert)
        self.graph_scene.edge_added.connect(self.add_edge)

        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE

        self.graph_view = GraphView(self.graph_scene)
        self.splitter.addWidget(self.graph_view)
        self.graph_view.set_graph(graph)

        self.sidebar = self.create_side_bar()
        self.splitter.addWidget(self.sidebar)

    def _populate_variables(self) -> None:
        self.variable_types = {}
        for vert in self.graph.vertices():
            phase = self.graph.phase(vert)
            if isinstance(phase, Poly):
                for var in phase.free_vars():
                    self.variable_types[var.name] = var.is_bool

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        yield from super()._toolbar_sections()

        self.start_derivation = QToolButton(self)
        self.start_derivation.setText("Start Derivation")
        self.start_derivation.clicked.connect(self._start_derivation)
        yield ToolbarSection(self.start_derivation)

    def _vert_double_clicked(self, v: VT) -> None:
        if self.graph.type(v) == VertexType.BOUNDARY:
            return

        input_, ok = QInputDialog.getText(
            self, "Input Dialog", "Enter Desired Phase Value:"
        )
        if not ok:
            return
        try:
            new_phase = parse(input_, self._new_var)
        except ValueError:
            show_error_msg("Wrong Input Type", "Please enter a valid input (e.g. 1/2, 2)")
            return
        cmd = ChangePhase(self.graph_view, v, new_phase)
        self.undo_stack.push(cmd)

    def _new_var(self, name: str) -> Poly:
        if name not in self.variable_types:
            self.variable_types[name] = False
            self.variable_viewer.add_item(name)
        return new_var(name, self.variable_types)

    def _start_derivation(self) -> None:
        new_g: GraphT = copy.deepcopy(self.graph_scene.g)
        for vert in new_g.vertices():
            phase = new_g.phase(vert)
            if isinstance(phase, Poly):
                phase.freeze()
        self.start_derivation_signal.emit(new_g)

class VariableViewer(QScrollArea):

    def __init__(self, variable_types: dict[str, bool]) -> None:
        super().__init__()

        self._variable_types = variable_types

        self._widget = QWidget()
        lpal = QApplication.palette("QListWidget")
        palette = QPalette()
        palette.setBrush(QPalette.ColorRole.Window, lpal.base())
        self._widget.setAutoFillBackground(True)
        self._widget.setPalette(palette)
        self._layout = QGridLayout(self._widget)
        self._layout.setColumnStretch(0, 1)
        self._layout.setColumnStretch(1, 0)
        self._layout.setColumnStretch(2, 0)
        cb = QComboBox()
        cb.insertItems(0, ["Parametric", "Boolean"])
        self._layout.setColumnMinimumWidth(2, cb.minimumSizeHint().width())
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._items = 0

        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(3)
        vline.setLineWidth(1)
        vline.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._layout.addWidget(vline, 0, 1, -1, 1)

        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFixedHeight(3)
        hline.setLineWidth(1)
        hline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(hline, 1, 0, 1, -1)

        vlabel = QLabel("Variable")
        vlabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(vlabel, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        tlabel = QLabel("Type")
        tlabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(tlabel, 0, 2, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding), 2, 2)

        for name in variable_types.keys():
            self.add_item(name)

        self.setWidget(self._widget)
        self.setWidgetResizable(True)
    
    def minimumSizeHint(self) -> QSize:
        if self._items == 0:
            return QSize(0, 0)
        else:
            return super().minimumSizeHint()
        
    def sizeHint(self) -> QSize:
        if self._items == 0:
            return QSize(0, 0)
        else:
            return super().sizeHint()

    def add_item(self, name: str) -> None:
        combobox = QComboBox()
        combobox.insertItems(0, ["Parametric", "Boolean"])
        if self._variable_types[name]:
            combobox.setCurrentIndex(1)
        else:
            combobox.setCurrentIndex(0)
        combobox.currentTextChanged.connect(lambda text: self._text_changed(name, text))
        item = self._layout.itemAtPosition(2 + self._items, 2)
        self._layout.removeItem(item)
        self._layout.addWidget(QLabel(f"<pre>{name}</pre>"), 2 + self._items, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._layout.addWidget(combobox, 2 + self._items, 2, Qt.AlignmentFlag.AlignCenter)
        self._layout.setRowStretch(2 + self._items, 0)
        self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding), 3 + self._items, 2)
        self._layout.setRowStretch(3 + self._items, 1)
        self._layout.update()
        self._items += 1
        self._widget.updateGeometry()

        if self._items == 1:
            self.updateGeometry()

    def _text_changed(self, name: str, text: str) -> None:
        if text == "Parametric":
            self._variable_types[name] = False
        elif text == "Boolean":
            self._variable_types[name] = True
