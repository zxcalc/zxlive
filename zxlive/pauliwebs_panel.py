from __future__ import annotations

import copy
from typing import Iterator, Optional
from typing_extensions import TypeAlias

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QBrush, QFont
from PySide6.QtWidgets import (QLabel, QListWidget,
                               QListWidgetItem, QSplitter, QVBoxLayout, QWidget, QToolButton)
from pyzx import EdgeType, VertexType, pauliweb
from zxlive.graphview import GraphView

from .base_panel import BasePanel, ToolbarSection
from .commands import UpdateGraph
from .common import ET, GraphT, get_settings_value
from .dialogs import show_error_msg
from .graphscene import GraphScene


import json
from pyzx.graph.jsonparser import json_to_graph
from pyzx.web import compute_pauli_webs


PauliWeb: TypeAlias = pauliweb.PauliWeb[int, tuple[int, int]]


class PauliWebsPanel(BasePanel):
    """write something here"""

    graph_scene: GraphScene
    sidebar: QSplitter

    _curr_ety: EdgeType
    _curr_vty: VertexType
    snap_vertex_edge = True
    patterns_folder: Optional[str] = None

    def __init__(self,  graph: GraphT, *actions: QAction) -> None:
        super().__init__(*actions)
        self.graph_scene = GraphScene()

        self.graph_scene.edge_double_clicked.connect(self.edge_double_clicked)
        self.graph_scene.background_double_clicked.connect(self.on_background_double_clicked)
        self._curr_vty = VertexType.Z
        self._curr_ety = EdgeType.SIMPLE
        self.patterns_folder = get_settings_value("patterns-folder", str)

        self.graph_view = GraphView(self.graph_scene)
        self.splitter.addWidget(self.graph_view)
        self.graph_view.set_graph(graph)

        self.web_container, self.web_list = create_titled_list_container("Pauli Webs")
        self.splitter.addWidget(self.web_container)
        self.web_list.itemSelectionChanged.connect(self._on_web_selection_changed)

        self._pauli_webs: list[PauliWeb] = []
        self._pauli_web_index: list[int] = []
        self._compute_pauli_webs()

        self.edge_clicked = False

    def _compute_pauli_webs(self) -> None:
        # First convert the graph to a simple graph so that pyzx can compute the pauli webs
        graph_json = json.loads(self.graph_scene.g.to_json())

        try:
            edge_pairs = [tuple(sorted(edge[:2])) for edge in graph_json.get("edges", [])]
            unique_pairs = set(edge_pairs)
            has_duplicate_edges = len(edge_pairs) != len(unique_pairs)

            if has_duplicate_edges:
                raise ValueError("Graph is a multigraph. Pauli web computation requires a simple graph.")

        except ValueError as ve:
            show_error_msg(str(ve), parent=self)
            return

        simple_g = json_to_graph(graph_json, backend="simple")

        try:
            stabs, regions = compute_pauli_webs(simple_g)
        except Exception as err:
            show_error_msg("Failed to compute Pauli webs", str(err), parent=self)
            return

        # Store the webs
        self._pauli_webs = stabs + regions

        inputs = ()
        outputs = ()
        try:
            self.graph.auto_detect_io()
            inputs = self.graph.inputs()
            outputs = self.graph.outputs()
        except Exception:
            show_error_msg("Warning: Could not auto-detect inputs/outputs for Pauli web computation", parent=self)

        priority_map = {
            "Logical": 0,
            "Co-stabiliser": 1,
            "Stabiliser": 2,
            "Detecting Region": 3,
            "Pauli Web": 4
        }

        # 1. Map every web to its type and current object
        annotated_webs: list[tuple[str, PauliWeb]] = []
        for i, web in enumerate(self._pauli_webs):
            is_region = i >= len(stabs)
            is_stab = any(e[0] in outputs or e[1] in outputs for e in web.half_edges())
            is_costab = any(e[0] in inputs or e[1] in inputs for e in web.half_edges())

            web_type = (
                "Detecting Region" if is_region
                else "Logical" if is_stab and is_costab
                else "Co-stabiliser" if is_costab
                else "Stabiliser" if is_stab
                else "Pauli Web"
            )
            annotated_webs.append((web_type, web))

        # 2. Sort the annotated list based on priority_map
        annotated_webs.sort(key=lambda x: priority_map[x[0]])

        # 3. OVERWRITE the actual data list with the new order
        self._pauli_webs = [item[1] for item in annotated_webs]

        # 4. Populate the UI using the now-sorted self._pauli_webs
        self.web_list.clear()
        type_counts = {name: 0 for name in priority_map.keys()}

        for i, web in enumerate(self._pauli_webs):
            # Re-identify type (since we just sorted them, they are grouped)
            # We use the same logic or just grab it from our sorted list
            current_type = annotated_webs[i][0]

            type_counts[current_type] += 1
            label = f"{current_type} #{type_counts[current_type]}"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i)  # Index now matches the new list order
            self.web_list.addItem(item)
        if self._pauli_webs:
            self.web_list.setCurrentRow(-1)
            self._pauli_web_index = []
            self._show_current_pauli_web()

    def _show_current_pauli_web(self) -> None:
        new_g = copy.deepcopy(self.graph_scene.g)
        for e in new_g.edges():
            new_g.set_edata(e, "xweb0", False)
            new_g.set_edata(e, "zweb0", False)
            new_g.set_edata(e, "xweb1", False)
            new_g.set_edata(e, "zweb1", False)

        if self._pauli_web_index:
            web = self._pauli_webs[self._pauli_web_index[0]]
            for i in self._pauli_web_index[1:]:
                web *= self._pauli_webs[i]

            for (s, t), pauli in web.half_edges().items():
                try:
                    edge = new_g.edge(s, t)
                except Exception:
                    continue

                if pauli in ("X", "Y") and s < t:
                    new_g.set_edata(edge, "xweb0", True)
                if pauli in ("X", "Y") and s > t:
                    new_g.set_edata(edge, "xweb1", True)
                if pauli in ("Z", "Y") and s < t:
                    new_g.set_edata(edge, "zweb0", True)
                if pauli in ("Z", "Y") and s > t:
                    new_g.set_edata(edge, "zweb1", True)

        self.undo_stack.push(UpdateGraph(self.graph_view, new_g))  # or SetGraph if you don't want undo entries
        self.graph_scene.invalidate()  # TODO: invalidating the whole scene might be overkill

    def _on_web_selection_changed(self) -> None:
        selected_items = self.web_list.selectedItems()
        if not selected_items:
            self._pauli_web_index = []
        else:
            self._pauli_web_index = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        self._show_current_pauli_web()

    def _toolbar_sections(self) -> Iterator[ToolbarSection]:
        self.clear_pauli_webs = QToolButton(self)
        self.clear_pauli_webs.setText("Clear Pauli Webs")
        self.clear_pauli_webs.clicked.connect(self._clear_pauli_webs)
        yield ToolbarSection(self.clear_pauli_webs)

    def _clear_pauli_webs(self) -> None:
        self._pauli_web_index = []
        self.web_list.clearSelection()
        self._show_current_pauli_web()

    def edge_double_clicked(self, e: ET) -> None:
        for edge in self.graph_scene.g.edges():
            self.graph_scene.g.set_edata(edge, "highlight", False)

        self.graph_scene.g.set_edata(e, "highlight", True)

        for i, web in enumerate(self._pauli_webs):
            item = self.web_list.item(i)
            item.setForeground(QBrush())
            item.setFont(QFont())
            if (e[0], e[1]) in web.half_edges():
                if item:
                    item.setForeground(QColor("#FFC107"))
                    font = QFont()
                    font.setBold(True)
                    font.setPointSize(10)  # Optional: Make it larger too
                    item.setFont(font)
        self.graph_scene.invalidate()

    def on_background_double_clicked(self) -> None:
        for edge in self.graph_scene.g.edges():
            self.graph_scene.g.set_edata(edge, "highlight", False)

        for i in range(self.web_list.count()):
            item = self.web_list.item(i)
            item.setForeground(QBrush())
            item.setFont(QFont())


def create_titled_list_container(title: str) -> tuple[QWidget, QListWidget]:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # Title Label
    title_label = QLabel(title)
    title_label.setStyleSheet("font-weight: bold; padding: 4px")
    layout.addWidget(title_label)

    # The List Widget
    list_widget = QListWidget()
    # Optional: remove border to make it look integrated
    list_widget.setStyleSheet("QListWidget { border: none; }")
    list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    layout.addWidget(list_widget)

    return container, list_widget
