import json
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union, Dict

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

from PySide6.QtCore import (QAbstractItemModel, QAbstractListModel,
                            QItemSelection, QModelIndex, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QSize, Qt)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QListView, QMenu,
                               QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QWidget)

from pyzx.graph.diff import GraphDiff
from .common import GraphT, ET
from .settings import display_setting


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str  # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # New graph after applying the rewrite
    grouped_rewrites: Optional[list['Rewrite']] = None  # Optional field to store the grouped rewrites
    # Optional semantic highlight information for this step. When present,
    # this is preferred over GraphDiff-based highlighting.
    #
    # - highlight_verts / highlight_edges:
    #     Legacy ID-based highlighting (vertex/edge IDs).
    # - highlight_coords:
    #     Coordinate-based highlighting using (qubit, row) pairs. This is
    #     robust against internal vertex ID reindexing.
    # - highlight_match_pairs:
    #     For MATCH_DOUBLE (e.g. Spider Fusion): [(v1, v2), ...] in the graph
    #     at step i; used for forward highlighting (only the edge between v1,v2).
    # - highlight_unfuse_verts:
    #     For unfuse operations: exact vertex IDs to highlight in the current graph
    #
    highlight_verts: Optional[list[int]] = None
    highlight_edges: Optional[list[ET]] = None
    highlight_coords: Optional[list[tuple[int, int]]] = None
    highlight_match_pairs: Optional[list[tuple[int, int]]] = None
    highlight_unfuse_verts: Optional[list[int]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the rewrite to Python dictionary."""
        return {
            "display_name": self.display_name,
            "rule": self.rule,
            "graph": self.graph.to_dict(),
            "grouped_rewrites": [r.to_dict() for r in self.grouped_rewrites] if self.grouped_rewrites else None,
            "highlight_verts": self.highlight_verts,
            "highlight_edges": self.highlight_edges,
            "highlight_coords": self.highlight_coords,
            "highlight_match_pairs": self.highlight_match_pairs,
            "highlight_unfuse_verts": self.highlight_unfuse_verts,
        }

    def to_json(self) -> str:
        """Serializes the rewrite to JSON."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(json_str: Union[str, Dict[str, Any]]) -> "Rewrite":
        """Deserializes the rewrite from JSON or Python dict."""
        if isinstance(json_str, str):
            d = json.loads(json_str)
        else:
            d = json_str
        grouped_rewrites = d.get("grouped_rewrites")
        graph = GraphT.from_json(d["graph"])
        assert isinstance(graph, GraphT)
        graph.set_auto_simplify(False)

        coords = d.get("highlight_coords")
        if coords is not None:
            # Stored as lists in JSON; convert to tuples for internal use.
            coords = [tuple(c) for c in coords]

        pairs = d.get("highlight_match_pairs")
        if pairs is not None:
            pairs = [tuple(p) for p in pairs]

        return Rewrite(
            display_name=d.get("display_name", d["rule"]),  # Old proofs may not have display names
            rule=d["rule"],
            graph=graph,
            grouped_rewrites=[Rewrite.from_json(r) for r in grouped_rewrites] if grouped_rewrites else None,
            highlight_verts=d.get("highlight_verts"),
            highlight_edges=d.get("highlight_edges"),
            highlight_coords=coords,
            highlight_match_pairs=pairs,
            highlight_unfuse_verts=d.get("highlight_unfuse_verts"),
        )


class ProofModel(QAbstractListModel):
    """List model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore, we store the
    rewrite that was used to go from one graph to next.
    """

    initial_graph: GraphT
    steps: list[Rewrite]

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.initial_graph = start_graph
        self.steps = []

    def set_graph(self, index: int, graph: GraphT) -> None:
        if index == 0:
            self.initial_graph = graph
        else:
            old_step = self.steps[index - 1]
            new_step = Rewrite(
                old_step.display_name,
                old_step.rule,
                graph,
                old_step.grouped_rewrites,
                old_step.highlight_verts,
                old_step.highlight_edges,
                old_step.highlight_coords,
                old_step.highlight_match_pairs,
            )
            self.steps[index - 1] = new_step

    def graphs(self) -> list[GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if index.row() >= len(self.steps) + 1 or index.column() >= 1:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.row() == 0:
                return "START"
            else:
                return self.steps[index.row() - 1].display_name
        elif role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)

    def flags(self, index: Union[QModelIndex, QPersistentModelIndex]) -> Qt.ItemFlag:
        if index.row() == 0:
            return super().flags(index)
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.headerData`.

        Indicates that this model doesn't have a header.
        """
        return None

    def columnCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of columns"""
        return 1

    def rowCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on tree models, the
        # user has to specify the index of the parent. In a list, we always expect the
        # parent to be `None` or the empty `QModelIndex()`
        if not index or not index.isValid():
            return len(self.steps) + 1
        else:
            return 0

    def add_rewrite(self, rewrite: Rewrite, position: Optional[int] = None) -> None:
        """Adds a rewrite step to the model."""
        if position is None:
            position = len(self.steps)
        self.beginInsertRows(QModelIndex(), position + 1, position + 1)
        self.steps.insert(position, rewrite)
        self.endInsertRows()

    def pop_rewrite(self, position: Optional[int] = None) -> tuple[Rewrite, GraphT]:
        """Removes the latest rewrite from the model.

        Returns the rewrite and the graph that previously resulted from this rewrite.
        """
        if position is None:
            position = len(self.steps) - 1
        self.beginRemoveRows(QModelIndex(), position + 1, position + 1)
        rewrite = self.steps.pop(position)
        self.endRemoveRows()
        return rewrite, rewrite.graph

    def get_graph(self, index: int) -> GraphT:
        """Returns the graph at a given position in the proof."""
        if index == 0:
            copy = self.initial_graph.copy()
        else:
            copy = self.steps[index - 1].graph.copy()
        assert isinstance(copy, GraphT)
        return copy

    def rename_step(self, index: int, name: str) -> None:
        """Change the display name"""
        old_step = self.steps[index]

        # Must create a new Rewrite object instead of modifying current object
        # since Rewrite inherits NamedTuple and is hence immutable
        self.steps[index] = Rewrite(
            name, old_step.rule, old_step.graph, old_step.grouped_rewrites,
            old_step.highlight_verts, old_step.highlight_edges, old_step.highlight_coords,
            old_step.highlight_match_pairs,
        )

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def group_steps(self, start_index: int, end_index: int) -> None:
        """Replace the individual steps from `start_index` to `end_index` with a new grouped step"""
        new_rewrite = Rewrite(
            "Grouped Steps: " + " 🡒 ".join(self.steps[i].display_name for i in range(start_index, end_index + 1)),
            "Grouped",
            self.get_graph(end_index + 1),
            self.steps[start_index:end_index + 1],
            None, None, None, None,
        )
        for _ in range(end_index - start_index + 1):
            self.pop_rewrite(start_index)[0]
        self.add_rewrite(new_rewrite, start_index)
        modelIndex = self.createIndex(start_index, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def ungroup_steps(self, index: int) -> None:
        """Replace the grouped step at `index` with the individual_steps"""
        individual_steps = self.steps[index].grouped_rewrites
        if individual_steps is None:
            raise ValueError("Step is not grouped")
        self.pop_rewrite(index)
        for i, step in enumerate(individual_steps):
            self.add_rewrite(step, index + i)
        self.dataChanged.emit(self.createIndex(index, 0),
                              self.createIndex(index + len(individual_steps), 0),
                              [])

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the model to Python dict."""
        initial_graph = self.initial_graph.to_dict()
        proof_steps = [step.to_dict() for step in self.steps]

        return {
            "initial_graph": initial_graph,
            "proof_steps": proof_steps
        }

    def to_json(self) -> str:
        """Serializes the model to JSON."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(json_str: Union[str, Dict[str, Any]]) -> "ProofModel":
        """Deserializes the model from JSON or Python dict."""
        if isinstance(json_str, str):
            d = json.loads(json_str)
        else:
            d = json_str
        initial_graph = GraphT.from_json(d["initial_graph"])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        if TYPE_CHECKING:
            assert isinstance(initial_graph, GraphT)
        initial_graph.set_auto_simplify(False)
        model = ProofModel(initial_graph)
        for step in d["proof_steps"]:
            rewrite = Rewrite.from_json(step)
            model.add_rewrite(rewrite)
        return model


class ProofStepView(QListView):
    """A view for displaying the steps in a proof."""

    def __init__(self, parent: 'ProofPanel'):
        super().__init__(parent)
        self.graph_view = parent.graph_view
        self.undo_stack = parent.undo_stack
        self.setModel(ProofModel(self.graph_view.graph_scene.g))
        self.setCurrentIndex(self.model().index(0, 0))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        # Set background color for dark mode (panel background)
        if display_setting.dark_mode:
            self.setStyleSheet("background-color: #23272e;")
        else:
            self.setStyleSheet("")
        # Set background color for dark mode
        pal = self.palette()
        if display_setting.dark_mode:
            pal.setColor(self.backgroundRole(), QColor(35, 39, 46))
            pal.setColor(self.viewport().backgroundRole(), QColor(35, 39, 46))
        else:
            pal.setColor(self.backgroundRole(), QColor(255, 255, 255))
            pal.setColor(self.viewport().backgroundRole(), QColor(255, 255, 255))
        self.setPalette(pal)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setAlternatingRowColors(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setItemDelegate(ProofStepItemDelegate(self))

    # overriding this method to change the return type and stop mypy from complaining
    def model(self) -> ProofModel:
        model = super().model()
        assert isinstance(model, ProofModel)
        return model

    def set_model(self, model: ProofModel) -> None:
        self.setModel(model)
        # it looks like the selectionModel is linked to the model, so after updating the model we need to reconnect the selectionModel signals.
        self.selectionModel().selectionChanged.connect(self.proof_step_selected)
        self.setCurrentIndex(model.index(len(model.steps), 0))

    def move_to_step(self, index: int) -> None:
        idx = self.model().index(index, 0, QModelIndex())
        self.clearSelection()
        self.selectionModel().blockSignals(True)
        self.setCurrentIndex(idx)
        self.selectionModel().blockSignals(False)
        self.update(idx)
        g_current = self.model().get_graph(index)
        self.graph_view.set_graph(g_current)

        # Highlight the differences between this step and the *next* one.
        scene = self.graph_view.graph_scene
        num_steps = len(self.model().steps)

        # If highlighting is disabled in the settings, always clear any
        # existing rewrite highlight and return.
        if not display_setting.highlight_rewrites:
            scene.clear_rewrite_highlight()
            return

        # Last proof step: no "next" transition to highlight.
        if index >= num_steps:
            scene.clear_rewrite_highlight()
            return
        # There is a rewrite taking graph index -> index + 1.
        rewrite_meta = self.model().steps[index]
        g_next = self.model().get_graph(index + 1)

        # 1) Match-based forward highlighting (MATCH_DOUBLE, e.g. Spider Fusion).
        #    Use the rule's match (v1, v2) to highlight only those vertices and
        #    the single edge between them. Find the edge via incident_edges(v1).
        highlight_match_pairs = getattr(rewrite_meta, "highlight_match_pairs", None)
        if highlight_match_pairs:
            highlight_verts = set()
            highlight_edges = set()
            for match in highlight_match_pairs:
                if isinstance(match, tuple) and len(match) == 2:
                    v1, v2 = match
                    v1, v2 = int(v1), int(v2)
                    if v1 not in list(g_current.vertices()) or v2 not in list(g_current.vertices()):
                        continue
                    highlight_verts.add(v1)
                    highlight_verts.add(v2)
                    for e in g_current.incident_edges(v1):
                        s, t = g_current.edge_st(e)
                        if (s == v1 and t == v2) or (s == v2 and t == v1):
                            highlight_edges.add(e)
            # --- DEBUG: log data sent to UI (match_pairs branch) ---
            print("\n=== GUI HIGHLIGHT DEBUG (match_pairs branch) ===")
            print("1. highlight_match_pairs (raw):", highlight_match_pairs)
            print("2. highlight_verts:", highlight_verts)
            print("3. highlight_edges:", highlight_edges)
            print("4. Each edge in highlight_edges -> edge_st(e):")
            for e in highlight_edges:
                print("   ", repr(e), "->", g_current.edge_st(e))
            print("5. All incident edges of each vertex in highlight_verts:")
            for v in highlight_verts:
                inc = g_current.incident_edges(v)
                print("   incident_edges({}) (n={}):".format(v, len(inc)))
                for e in inc:
                    print("     ", repr(e), "->", g_current.edge_st(e))
            print("================================================\n")
            # --- END DEBUG ---
            scene.set_rewrite_highlight(highlight_verts, highlight_edges)
            return

        # 2) Unfuse-specific highlighting. highlight_unfuse_verts contains the two
        # vertex IDs in the *next* graph (after split). In the *current* graph,
        # when viewing the step before unfuse only one exists; when viewing after, both exist.
        highlight_unfuse_verts = getattr(rewrite_meta, "highlight_unfuse_verts", None)
        if highlight_unfuse_verts and rewrite_meta.rule and "unfuse" in rewrite_meta.rule.lower():
            current_verts = set(g_current.vertices())
            highlight_verts = {v for v in highlight_unfuse_verts if v in current_verts}
            highlight_edges: set[ET] = set()
            # If both split vertices exist (viewing step after unfuse), highlight edge between them
            if len(highlight_verts) >= 2:
                vert_list = list(highlight_verts)
                for i in range(len(vert_list)):
                    v1 = vert_list[i]
                    for j in range(i + 1, len(vert_list)):
                        v2 = vert_list[j]
                        for e in g_current.incident_edges(v1):
                            s, t = g_current.edge_st(e)
                            if (s == v1 and t == v2) or (s == v2 and t == v1):
                                highlight_edges.add(e)
            scene.set_rewrite_highlight(highlight_verts, highlight_edges)
            return

        # 3) Coordinate-based semantic highlight (when no match pairs or unfuse verts).
        #    This maps stored (qubit, row) pairs onto the *current* graph's
        #    vertices and then highlights those vertices and their incident
        #    edges. This is robust to any internal vertex ID reindexing that
        #    might occur between rewrite application and rendering.
        highlight_coords = getattr(rewrite_meta, "highlight_coords", None)
        if highlight_coords:
            coord_set = {(int(q), int(r)) for (q, r) in highlight_coords}

            # Build a mapping from (qubit,row) -> set[vertex] for both the
            # current and next graphs so we can reason about structure in a
            # coordinate-stable way.
            def _coord_map(graph: GraphT) -> dict[tuple[int, int], set[int]]:
                mapping: dict[tuple[int, int], set[int]] = {}
                for v in graph.vertices():
                    try:
                        cq = int(graph.qubit(v))
                        cr = int(graph.row(v))
                    except Exception:
                        continue
                    mapping.setdefault((cq, cr), set()).add(v)
                return mapping

            coord_to_vs_current = _coord_map(g_current)
            
            # #region agent log
            print(f"[COORD_MAP DEBUG] Coordinate to vertex mapping for g_current:")
            for coord, verts in sorted(coord_to_vs_current.items()):
                print(f"  {coord} -> {verts}")
            print(f"[COORD_MAP DEBUG] Looking for coordinates: {coord_set}")
            # #endregion

            # Vertices to highlight: all vertices in the current graph whose
            # coordinates fall inside the semantic focus region.
            highlight_verts: set[int] = set()
            for c in coord_set:
                verts_at_coord = coord_to_vs_current.get(c, set())
                # #region agent log
                print(f"[COORD_MAP DEBUG] Coord {c} maps to vertices: {verts_at_coord}")
                # #endregion
                highlight_verts.update(verts_at_coord)

            # Edges to highlight depend on the rewrite:
            # - For Fuse spiders, we only highlight edges whose endpoints are
            #   both among the highlighted vertices (i.e., the fusion edge(s)).
            # - For other rewrites using coordinate metadata, we fall back to
            #   structural edge changes near the focus region.
            rule_name = (rewrite_meta.rule or "").lower()
            # Treat as fuse when we have exactly two vertices (the two spiders being
            # fused) or when rule name clearly indicates fuse; then only highlight
            # the edge between those two, not all incident edges.
            is_fuse_like = (
                len(highlight_verts) == 2
                or ("fuse" in rule_name and "spider" in rule_name)
            )

            highlight_edges: set[ET] = set()

            # DEBUG: why did we take fuse vs generic branch?
            print("[DEBUG coords] rule_name=%r is_fuse_like=%s len(highlight_verts)=%s"
                  % (rewrite_meta.rule, is_fuse_like, len(highlight_verts)))

            if is_fuse_like:
                # Only the edge(s) between the matched pair. Use incident_edges(v1)
                # so we get the same edge object as the scene's edge_map (avoids
                # any g.edges(v1,v2) return-value mismatch).
                vert_list = list(highlight_verts)
                for i in range(len(vert_list)):
                    for j in range(i + 1, len(vert_list)):
                        v1, v2 = vert_list[i], vert_list[j]
                        for e in g_current.incident_edges(v1):
                            s, t = g_current.edge_st(e)
                            if (s == v1 and t == v2) or (s == v2 and t == v1):
                                highlight_edges.add(e)
            else:
                # Generic path: only edges that are structurally changed between
                # g_current and g_next in the focus region.
                # #region agent log
                print(f"[PROOF_DEBUG else branch] rule_name='{rule_name}', entering generic edge highlighting")
                # #endregion
                
                # Original generic path for non-unfuse operations
                def _edge_signatures_near_coords(graph: GraphT) -> set[tuple[tuple[int, int], tuple[int, int], Any]]:
                    sigs: set[tuple[tuple[int, int], tuple[int, int], Any]] = set()
                    for e in graph.edges():
                        s, t = graph.edge_st(e)
                        try:
                            cs = (int(graph.qubit(s)), int(graph.row(s)))
                            ct = (int(graph.qubit(t)), int(graph.row(t)))
                        except Exception:
                            continue
                        # Only care about edges that touch the focus region.
                        if cs not in coord_set and ct not in coord_set:
                            continue
                        et = graph.edge_type(e)
                        if cs <= ct:
                            sig = (cs, ct, et)
                        else:
                            sig = (ct, cs, et)
                        sigs.add(sig)
                    return sigs

                sigs_next = _edge_signatures_near_coords(g_next)

                seen_edges: set[ET] = set()
                for v in highlight_verts:
                    for e in g_current.incident_edges(v):
                        if e in seen_edges:
                            continue
                        seen_edges.add(e)
                        s, t = g_current.edge_st(e)
                        try:
                            cs = (int(g_current.qubit(s)), int(g_current.row(s)))
                            ct = (int(g_current.qubit(t)), int(g_current.row(t)))
                        except Exception:
                            continue
                        if cs not in coord_set and ct not in coord_set:
                            continue
                        et = g_current.edge_type(e)
                        if cs <= ct:
                            sig_cur = (cs, ct, et)
                        else:
                            sig_cur = (ct, cs, et)
                        # Only highlight edges that are structurally changed
                        # between g_current and g_next.
                        if sig_cur not in sigs_next:
                            highlight_edges.add(e)

            # --- DEBUG: log data sent to UI (coords branch) ---
            print("\n=== GUI HIGHLIGHT DEBUG (coords branch) ===")
            print("1. highlight_coords / coord_set:", coord_set)
            print("2. highlight_verts:", highlight_verts)
            print("3. highlight_edges:", highlight_edges)
            print("4. Each edge in highlight_edges -> edge_st(e):")
            for e in highlight_edges:
                print("   ", repr(e), "->", g_current.edge_st(e))
            print("5. All incident edges of each vertex in highlight_verts:")
            for v in highlight_verts:
                inc = g_current.incident_edges(v)
                print("   incident_edges({}) (n={}):".format(v, len(inc)))
                for e in inc:
                    print("     ", repr(e), "->", g_current.edge_st(e))
            print("============================================\n")
            # --- END DEBUG ---
            scene.set_rewrite_highlight(highlight_verts, highlight_edges)
            return

        # 3) Fallback: structural diff-based highlighting for steps that do
        #    not carry explicit semantic metadata.
        diff = GraphDiff(g_current, g_next)

        # Vertices: include those whose type or phase changes, as well as
        # vertices that are about to be removed.
        highlight_verts = set(diff.removed_verts)
        highlight_verts.update(diff.changed_vertex_types)
        highlight_verts.update(diff.changed_phases)

        # Edges: only those that are structurally or semantically changed
        # (created, removed, or with changed data/type). New edges only exist
        # in the next graph so they cannot be highlighted on the current one.
        highlight_edges: set[ET] = set()

        for e in diff.removed_edges:
            highlight_edges.add(e)

        for e in diff.changed_edata:
            highlight_edges.add(e)

        for e in diff.changed_edge_types:
            highlight_edges.add(e)

        scene.set_rewrite_highlight(highlight_verts, highlight_edges)

    def show_context_menu(self, position: QPoint) -> None:
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return
        context_menu = QMenu(self)
        action_function_map = {}

        index = selected_indexes[0].row()
        if len(selected_indexes) > 1:
            group_action = context_menu.addAction("Group Steps")
            action_function_map[group_action] = self.group_selected_steps
        elif index != 0:
            rename_action = context_menu.addAction("Rename Step")
            action_function_map[rename_action] = lambda: self.edit(selected_indexes[0])
            if self.model().steps[index - 1].grouped_rewrites is not None:
                ungroup_action = context_menu.addAction("Ungroup Steps")
                action_function_map[ungroup_action] = self.ungroup_selected_step

        action = context_menu.exec_(self.mapToGlobal(position))
        if action in action_function_map:
            action_function_map[action]()

    def rename_proof_step(self, new_name: str, index: int) -> None:
        from .commands import UndoableChange
        old_name = self.model().steps[index].display_name
        cmd = UndoableChange(self.graph_view,
                             lambda: self.model().rename_step(index, old_name),
                             lambda: self.model().rename_step(index, new_name))
        self.undo_stack.push(cmd)

    def proof_step_selected(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        if not selected or not deselected:
            return
        step_index = selected.first().topLeft().row()
        self.move_to_step(step_index)

    def group_selected_steps(self) -> None:
        from .commands import GroupRewriteSteps
        from .dialogs import show_error_msg
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) < 2:
            raise ValueError("Can only group two or more steps")

        indices = sorted(index.row() for index in selected_indexes)
        if indices[-1] - indices[0] != len(indices) - 1:
            show_error_msg("Can only group contiguous steps")
            raise ValueError("Can only group contiguous steps")
        if indices[0] == 0:
            show_error_msg("Cannot group the first step")
            raise ValueError("Cannot group the first step")

        self.move_to_step(indices[-1] - 1)
        cmd = GroupRewriteSteps(self.graph_view, self, indices[0] - 1, indices[-1] - 1)
        self.undo_stack.push(cmd)

    def ungroup_selected_step(self) -> None:
        from .commands import UngroupRewriteSteps
        selected_indexes = self.selectedIndexes()
        if not selected_indexes or len(selected_indexes) != 1:
            raise ValueError("Can only ungroup one step")

        index = selected_indexes[0].row()
        if index == 0 or self.model().steps[index - 1].grouped_rewrites is None:
            raise ValueError("Step is not grouped")

        self.move_to_step(index - 1)
        cmd = UngroupRewriteSteps(self.graph_view, self, index - 1)
        self.undo_stack.push(cmd)


class ProofStepItemDelegate(QStyledItemDelegate):
    """This class controls the painting of items in the proof steps list view.

    We paint a "git-style" line with circles to denote individual steps in a proof.
    """

    line_width = 3
    line_padding = 13
    vert_padding = 10

    circle_radius = 4
    circle_radius_selected = 6
    circle_outline_width = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        painter.save()
        # Draw background
        painter.setPen(Qt.GlobalColor.transparent)
        if display_setting.dark_mode:
            if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
                painter.setBrush(QColor(60, 80, 120))
            elif option.state & QStyle.StateFlag.State_MouseOver:  # type: ignore[attr-defined]
                painter.setBrush(QColor(50, 60, 80))
            else:
                painter.setBrush(QColor(35, 39, 46))
        else:
            if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
                painter.setBrush(QColor(204, 232, 255))
            elif option.state & QStyle.StateFlag.State_MouseOver:  # type: ignore[attr-defined]
                painter.setBrush(QColor(229, 243, 255))
            else:
                painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(option.rect)  # type: ignore[attr-defined]

        # Draw line
        is_last = index.row() == index.model().rowCount() - 1
        line_rect = QRect(
            self.line_padding,
            int(option.rect.y()),  # type: ignore[attr-defined]
            self.line_width,
            int(option.rect.height() if not is_last else option.rect.height() / 2)  # type: ignore[attr-defined]
        )
        if display_setting.dark_mode:
            painter.setBrush(QColor(180, 180, 180))
        else:
            painter.setBrush(Qt.GlobalColor.black)
        painter.drawRect(line_rect)

        # Draw circle
        if display_setting.dark_mode:
            painter.setPen(QPen(QColor(180, 180, 180), self.circle_outline_width))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, self.circle_outline_width))
        painter.setBrush(display_setting.effective_colors["z_spider"])
        circle_radius = self.circle_radius_selected if option.state & QStyle.StateFlag.State_Selected else self.circle_radius  # type: ignore[attr-defined]
        painter.drawEllipse(
            QPointF(self.line_padding + self.line_width / 2, option.rect.y() + option.rect.height() / 2),  # type: ignore[attr-defined]
            circle_radius,
            circle_radius
        )

        # Draw text
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_height = QFontMetrics(option.font).height()  # type: ignore[attr-defined]
        text_rect = QRect(
            int(option.rect.x() + self.line_width + 2 * self.line_padding),  # type: ignore[attr-defined]
            int(option.rect.y() + option.rect.height() / 2 - text_height / 2),  # type: ignore[attr-defined]
            option.rect.width(),  # type: ignore[attr-defined]
            text_height
        )
        font = option.font  # type: ignore[attr-defined]
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]
            font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        if display_setting.dark_mode:
            painter.setPen(QColor(224, 224, 224))
            painter.setBrush(QColor(224, 224, 224))
        else:
            painter.setPen(Qt.GlobalColor.black)
            painter.setBrush(Qt.GlobalColor.black)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), size.height() + 2 * self.vert_padding)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QLineEdit:
        return QLineEdit(parent)

    def setEditorData(self, editor: QWidget, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        assert isinstance(editor, QLineEdit)
        value = index.model().data(index, Qt.ItemDataRole.DisplayRole)
        editor.setText(str(value))

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: Union[QModelIndex, QPersistentModelIndex]) -> None:
        step_view = self.parent()
        assert isinstance(step_view, ProofStepView)
        assert isinstance(editor, QLineEdit)
        step_view.rename_proof_step(editor.text(), index.row() - 1)
