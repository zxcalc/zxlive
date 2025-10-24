from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Sequence, Type

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QSplitter,
                               QToolBar, QVBoxLayout, QWidget)

from .animations import AnimatedUndoStack
from .commands import SetGraph
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

    def __init__(self, *args: QWidget | QAction,
                 exclusive: bool = False) -> None:
        self.buttons = args
        self.exclusive = exclusive


class BasePanel(QWidget):
    """Base class implementing functionality shared between the edit and
    proof panels."""
    splitter_sizes: dict[Type[BasePanel], list[int]] = dict()

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
        layout = self.layout()
        assert layout is not None  # for mypy
        layout.setSpacing(0)
        self.toolbar = QToolBar()
        layout.addWidget(self.toolbar)

        self.splitter = QSplitter(self)
        layout.addWidget(self.splitter)
        self.splitter.splitterMoved.connect(self.sync_splitter_sizes)

        self.file_path = None
        self.file_type = None

        self._populate_toolbar()

        self.show_matrix_action = QAction("Show matrix", self)
        self.show_matrix_action.setStatusTip("Show the matrix of the diagram")
        self.show_matrix_action.triggered.connect(self.show_matrix)
        self.toolbar.addAction(self.show_matrix_action)

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

    def delete_selection(self) -> None:
        pass

    def paste_selection(self, graph: GraphT) -> None:
        pass

    def paste_graph(self, graph: GraphT) -> None:
        pass

    def update_colors(self) -> None:
        self.graph_scene.update_colors()

    def sync_splitter_sizes(self) -> None:
        self.splitter_sizes[self.__class__] = self.splitter.sizes()

    def set_splitter_size(self) -> None:
        if self.__class__ in self.splitter_sizes:
            self.splitter.setSizes(self.splitter_sizes[self.__class__])

    def update_font(self) -> None:
        self.graph_view.update_font()

    def show_matrix(self) -> None:
        """Show the matrix of the current graph in a dialog."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (QSpinBox, QPushButton, QHBoxLayout,
                                       QDialog, QTableWidget,
                                       QTableWidgetItem)
        import pyperclip
        from .common import get_settings_value
        from .dialogs import show_error_msg
        precision: int = get_settings_value("matrix/precision", int, 4)

        def format_str(c: complex, p: int) -> str:
            tol = 1e-8
            if abs(c.real) < tol and abs(c.imag) < tol:
                return "0"
            if abs(c.imag) < tol:
                return f"{c.real:.{p}f}"
            if abs(c.real) < tol:
                return f"{c.imag:.{p}f}j"
            return f"{c.real:.{p}f} + {c.imag:.{p}f}j"

        try:
            self.graph.auto_detect_io()
            matrix = self.graph.to_matrix()
        except AttributeError:
            show_error_msg(
                "Can't show matrix",
                "Showing matrices for parametrized diagrams is not "
                "supported yet.", parent=self)
            return
        except Exception as e:
            show_error_msg("Can't show matrix", str(e), parent=self)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Matrix")
        layout = QVBoxLayout()
        table = QTableWidget(matrix.shape[0], matrix.shape[1])
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                entry = QTableWidgetItem(format_str(matrix[i, j], precision))
                entry.setFlags(entry.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(i, j, entry)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        layout.addWidget(table)
        controls_layout = QHBoxLayout()
        precision_spin = QSpinBox()
        precision_spin.setRange(0, 12)
        precision_spin.setValue(precision)
        precision_spin.setPrefix("Precision: ")
        controls_layout.addWidget(precision_spin)
        copy_btn = QPushButton("Copy to Clipboard")
        controls_layout.addWidget(copy_btn)
        layout.addLayout(controls_layout)
        dialog.setLayout(layout)

        def update_precision() -> None:
            p = precision_spin.value()
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    item = table.item(i, j)
                    if item is not None:
                        item.setText(format_str(matrix[i, j], p))

        precision_spin.valueChanged.connect(update_precision)

        def copy_matrix() -> None:
            p = precision_spin.value()
            rows = [
                "\t".join(format_str(matrix[i, j], p)
                          for j in range(matrix.shape[1]))
                for i in range(matrix.shape[0])
            ]
            pyperclip.copy("\n".join(rows))

        copy_btn.clicked.connect(copy_matrix)
        dialog.exec()
