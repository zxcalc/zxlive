from __future__ import annotations

from typing import Optional, TYPE_CHECKING, Union
from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSpinBox, QPushButton, QFrame,
                               QWidget)
from PySide6.QtGui import QKeyEvent, QColor
from fractions import Fraction
from pyzx.graph.jsonparser import string_to_phase
from pyzx.symbolic import Poly

from .common import VT, ET, GraphT
from .dialogs import show_error_msg
from .eitem import EItem


if TYPE_CHECKING:
    from .graphscene import GraphScene


class UnfusionDialog(QDialog):
    """Dialog for configuring the unfusion operation."""

    confirmed = Signal(int, object, object)  # num_edges, phase1, phase2
    cancelled = Signal()

    def __init__(
            self, original_phase: Union[Fraction, Poly, complex],
            graph: GraphT, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.original_phase = original_phase
        self.setWindowTitle("Unfuse Node Configuration")
        # Allow interaction with the graph behind the dialog
        self.setModal(False)
        self.setFixedSize(250, 250)
        # Keep dialog on top but allow interaction with parent
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self._updating_phases = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Click edges to assign to Node 1 (orange) or Node 2 (grey)")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(instructions)

        # Separator
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Edges between new nodes
        edges_layout = QHBoxLayout()
        edges_layout.addWidget(QLabel("Edges between new nodes:"))
        self.edges_spinbox = QSpinBox()
        self.edges_spinbox.setMinimum(1)
        self.edges_spinbox.setValue(1)
        edges_layout.addWidget(self.edges_spinbox)
        layout.addLayout(edges_layout)

        # Separator
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Phase inputs
        layout.addWidget(QLabel("Phase distribution:"))

        # Phase for Node 1
        phase1_layout = QHBoxLayout()
        phase1_layout.addWidget(QLabel("Phase for Node 1:"))
        self.phase1_edit = QLineEdit()
        self.phase1_edit.setText(str(self.original_phase))
        phase1_layout.addWidget(self.phase1_edit)
        layout.addLayout(phase1_layout)

        # Phase for Node 2
        phase2_layout = QHBoxLayout()
        phase2_layout.addWidget(QLabel("Phase for Node 2:"))
        self.phase2_edit = QLineEdit()
        self.phase2_edit.setText("0")
        phase2_layout.addWidget(self.phase2_edit)
        layout.addLayout(phase2_layout)

        self.phase1_edit.textChanged.connect(
            lambda: self._on_phase_changed(self.phase1_edit, self.phase2_edit))
        self.phase2_edit.textChanged.connect(
            lambda: self._on_phase_changed(self.phase2_edit, self.phase1_edit))

        # Info label
        self.info_label = QLabel("Original phase: " + str(self.original_phase))
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.info_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("Confirm")
        self.confirm_button.clicked.connect(self._confirm)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.confirm_button)
        layout.addLayout(button_layout)

        # Make confirm button default
        self.confirm_button.setDefault(True)

    def _on_phase_changed(
            self, source_edit: QLineEdit, target_edit: QLineEdit) -> None:
        """Update the target phase field when the source phase field
        changes."""
        if self._updating_phases:
            return
        self._updating_phases = True
        try:
            source_phase = string_to_phase(source_edit.text(), self.graph)
            target_phase = self.original_phase - source_phase
            target_edit.setText(str(target_phase))
        except (ValueError, TypeError):
            # Invalid input, don't update target phase
            pass
        finally:
            self._updating_phases = False

    def _confirm(self) -> None:
        try:
            num_edges = self.edges_spinbox.value()
            phase1 = string_to_phase(self.phase1_edit.text(), self.graph)
            phase2 = string_to_phase(self.phase2_edit.text(), self.graph)
            self.confirmed.emit(num_edges, phase1, phase2)
            self.accept()
        except (ValueError, TypeError) as e:
            show_error_msg("Invalid phase input", str(e), parent=self)

    def _cancel(self) -> None:
        self.cancelled.emit()
        self.reject()

    def keyPressEvent(self, arg__1: QKeyEvent) -> None:
        if arg__1.key() == Qt.Key.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(arg__1)


class UnfusionModeManager:
    """Manages the Direct Edge Selection Mode for unfusion."""

    def __init__(self, graph_scene: GraphScene, target_vertex: VT) -> None:
        self.graph_scene = graph_scene
        self.target_vertex = target_vertex
        self.selected_edges: set[EItem] = set()
        self.active = False

    def enter_mode(self) -> None:
        """Enter the Direct Edge Selection Mode."""
        self.active = True
        # Set incident edges to grey (unassigned)
        for edge in self.graph_scene.g.incident_edges(self.target_vertex):
            if edge in self.graph_scene.edge_map:
                for eitem in self.graph_scene.edge_map[edge].values():
                    eitem.color = QColor("#808080")
                    eitem.refresh()

    def exit_mode(self) -> None:
        """Exit the Direct Edge Selection Mode and restore original colors."""
        if not self.active:
            return
        self.active = False
        # Restore original edge colors by calling reset_color on each edge item
        if self.target_vertex in self.graph_scene.g.vertices():
            for edge in self.graph_scene.g.incident_edges(self.target_vertex):
                if edge in self.graph_scene.edge_map:
                    for eitem in self.graph_scene.edge_map[edge].values():
                        eitem.reset_color()
                        eitem.refresh()
        self.selected_edges.clear()

    def toggle_edge_selection(self, edge: EItem) -> None:
        """Toggle the selection state of an edge."""
        if not self.active:
            return
        if edge in self.selected_edges:
            # Deselect - change to grey (unassigned)
            self.selected_edges.remove(edge)
            edge.color = QColor("#808080")
        else:
            # Select - change to orange (selected for Node 1)
            self.selected_edges.add(edge)
            edge.color = QColor("#FFA500")
        edge.refresh()

    def get_edge_assignments(self) -> tuple[list[ET], list[ET]]:
        """Get the edge assignments for Node 1 and Node 2."""
        all_edges = list(self.graph_scene.g.incident_edges(self.target_vertex))
        node1_edges = [eitem.e for eitem in self.selected_edges]

        # Use Counter to handle multiplicities properly
        node2_edges_counter = Counter(all_edges) - Counter(node1_edges)
        node2_edges = []
        for edge, count in node2_edges_counter.items():
            node2_edges.extend([edge] * count)

        return node1_edges, node2_edges
