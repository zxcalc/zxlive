from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING, Any, Optional, cast, Union

import pyzx
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex, QPersistentModelIndex, Signal, QObject, QMetaObject
from concurrent.futures import ThreadPoolExecutor

from .animations import make_animation
from .commands import AddRewriteStep
from .common import ET, GraphT, VT
from .dialogs import show_error_msg
from .rewrite_data import is_rewrite_data, RewriteData, MatchType, MATCHES_VERTICES

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

operations = copy.deepcopy(pyzx.editor.operations)


@dataclass
class RewriteAction:
    name: str
    matcher: Callable[[GraphT, Callable], list]
    rule: Callable[[GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]]
    match_type: MatchType
    tooltip: str
    # Whether the graph should be copied before trying to test whether it matches.
    # Needed if the matcher changes the graph.
    copy_first: bool = field(default=False)
    # Whether the rule returns a new graph instead of returning the rewrite changes.
    returns_new_graph: bool = field(default=False)
    enabled: bool = field(default=False)

    @classmethod
    def from_rewrite_data(cls, d: RewriteData) -> RewriteAction:
        return cls(
            name=d['text'],
            matcher=d['matcher'],
            rule=d['rule'],
            match_type=d['type'],
            tooltip=d['tooltip'],
            copy_first=d.get('copy_first', False),
            returns_new_graph=d.get('returns_new_graph', False),
        )

    def do_rewrite(self, panel: ProofPanel) -> None:
        if not self.enabled:
            return

        g = copy.deepcopy(panel.graph_scene.g)
        verts, edges = panel.parse_selection()

        matches = self.matcher(g, lambda v: v in verts) \
            if self.match_type == MATCHES_VERTICES \
            else self.matcher(g, lambda e: e in edges)

        try:
            g, rem_verts = self.apply_rewrite(g, matches)
        except Exception as ex:
            show_error_msg('Error while applying rewrite rule', str(ex))
            return

        cmd = AddRewriteStep(panel.graph_view, g, panel.step_view, self.name)
        anim_before, anim_after = make_animation(self, panel, g, matches, rem_verts)
        panel.undo_stack.push(cmd, anim_before=anim_before, anim_after=anim_after)

    # TODO: Narrow down the type of the first return value.
    def apply_rewrite(self, g: GraphT, matches: list) -> tuple[Any, list[VT]]:
        if self.returns_new_graph:
            return self.rule(g, matches), []

        etab, rem_verts, rem_edges, check_isolated_vertices = self.rule(g, matches)
        g.remove_edges(rem_edges)
        g.remove_vertices(rem_verts)
        g.add_edge_table(etab)
        return g, rem_verts

    def update_active(self, g: GraphT, verts: list[VT], edges: list[ET]) -> None:
        if self.copy_first:
            g = copy.deepcopy(g)
        self.enabled = bool(
            self.matcher(g, lambda v: v in verts)
            if self.match_type == MATCHES_VERTICES
            else self.matcher(g, lambda e: e in edges)
        )


@dataclass
class RewriteActionTree:
    id: str
    rewrite: RewriteAction | None
    child_items: list[RewriteActionTree]
    parent: RewriteActionTree | None

    @property
    def is_rewrite(self) -> bool:
        return self.rewrite is not None

    @property
    def rewrite_action(self) -> RewriteAction:
        assert self.rewrite is not None
        return self.rewrite

    def append_child(self, child: RewriteActionTree) -> None:
        self.child_items.append(child)

    def child(self, row: int) -> RewriteActionTree:
        assert -len(self.child_items) <= row < len(self.child_items)
        return self.child_items[row]

    def child_count(self) -> int:
        return len(self.child_items)

    def row(self) -> int | None:
        return self.parent.child_items.index(self) if self.parent else None

    def header(self) -> str:
        return self.id if self.rewrite is None else self.rewrite.name

    def tooltip(self) -> str:
        return "" if self.rewrite is None else self.rewrite.tooltip

    def enabled(self) -> bool:
        return self.rewrite is None or self.rewrite.enabled

    @classmethod
    def from_dict(cls, d: dict, header: str = "", parent: RewriteActionTree | None = None) -> RewriteActionTree:
        if is_rewrite_data(d):
            return RewriteActionTree(
                header, RewriteAction.from_rewrite_data(cast(RewriteData, d)), [], parent
            )
        ret = RewriteActionTree(header, None, [], parent)
        for group, actions in d.items():
            ret.append_child(cls.from_dict(actions, group, ret))
        return ret

    def update_on_selection(self, g: GraphT, selection: list[VT], edges: list[ET]) -> None:
        for child in self.child_items:
            child.update_on_selection(g, selection, edges)
        if self.rewrite is not None:
            self.rewrite.update_active(g, selection, edges)


class SignalEmitter(QObject):
    finished = Signal()

class RewriteActionTreeModel(QAbstractItemModel):
    root_item: RewriteActionTree

    def __init__(self, data: RewriteActionTree, proof_panel: ProofPanel) -> None:
        super().__init__(proof_panel)
        self.proof_panel = proof_panel
        self.root_item = data
        self.emitter = SignalEmitter()
        self.emitter.finished.connect(lambda: self.dataChanged.emit(QModelIndex(), QModelIndex(), []))
        self.executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_dict(cls, d: dict, proof_panel: ProofPanel) -> RewriteActionTreeModel:
        return RewriteActionTreeModel(
            RewriteActionTree.from_dict(d),
            proof_panel
        )

    def index(self, row: int, column: int, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> \
            QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = cast(RewriteActionTree, parent.internalPointer()) if parent.isValid() else self.root_item

        if childItem := parent_item.child(row):
            return self.createIndex(row, column, childItem)
        return QModelIndex()

    def parent(self, index: QModelIndex | QPersistentModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        parent_item = cast(RewriteActionTree, index.internalPointer()).parent

        if parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        parent_item = cast(RewriteActionTree, parent.internalPointer()) if parent.isValid() else self.root_item
        return parent_item.child_count()

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 1

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if index.isValid():
            rewrite_action_tree = cast(RewriteActionTree, index.internalPointer())
            return Qt.ItemFlag.ItemIsEnabled if rewrite_action_tree.enabled() else Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> str | None:
        if not index.isValid():
            return self.root_item.header()
        rewrite_action_tree = cast(RewriteActionTree, index.internalPointer())
        if role == Qt.ItemDataRole.DisplayRole:
            return rewrite_action_tree.header()
        if role == Qt.ItemDataRole.ToolTipRole:
            return rewrite_action_tree.tooltip()
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> str:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.root_item.header()
        return ""

    def do_rewrite(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        node = cast(RewriteActionTree, index.internalPointer())
        if node.is_rewrite:
            node.rewrite_action.do_rewrite(self.proof_panel)

    def update_on_selection(self) -> None:
        selection, edges = self.proof_panel.parse_selection()
        g = self.proof_panel.graph_scene.g
        self.root_item.update_on_selection(g, selection, edges)
        QMetaObject.invokeMethod(self.emitter, "finished", Qt.ConnectionType.QueuedConnection)  # type: ignore
