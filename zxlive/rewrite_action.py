from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING, cast, Union, Optional
from concurrent.futures import ThreadPoolExecutor

import pyzx
from pyzx.utils import VertexType

from PySide6.QtCore import (Qt, QAbstractItemModel, QModelIndex, QPersistentModelIndex,
                            Signal, QObject, QMetaObject, QIODevice, QBuffer, QPoint, QPointF, QLineF)
from PySide6.QtGui import QPixmap, QColor, QPen
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView


from .animations import make_animation
from .commands import AddRewriteStep
from .common import ET, GraphT, VT, get_data
from .dialogs import show_error_msg
from .rewrite_data import is_rewrite_data, RewriteData, MatchType, MATCHES_VERTICES, refresh_custom_rules, action_groups
from .settings import display_setting
from .graphscene import GraphScene
from .graphview import GraphView

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

operations = copy.deepcopy(pyzx.editor.operations)


@dataclass
class RewriteAction:
    name: str
    matcher: Callable[[GraphT, Callable], list]
    rule: Callable[[GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]] | Callable[[GraphT, list], GraphT]
    match_type: MatchType
    tooltip_str: str
    picture_path: Optional[str] = field(default=None)
    lhs_graph: Optional[GraphT] = field(default=None)
    rhs_graph: Optional[GraphT] = field(default=None)
    # Whether the graph should be copied before trying to test whether it matches.
    # Needed if the matcher changes the graph.
    copy_first: bool = field(default=False)
    # Whether the rule returns a new graph instead of returning the rewrite changes.
    returns_new_graph: bool = field(default=False)
    enabled: bool = field(default=False)
    repeat_rule_application: bool = False

    @classmethod
    def from_rewrite_data(cls, d: RewriteData) -> RewriteAction:
        if 'custom_rule' in d:
            picture_path = 'custom'
        elif 'picture' in d:
            picture_path = d['picture']
        else:
            picture_path = None
        return cls(
            name=d['text'],
            matcher=d['matcher'],
            rule=d['rule'],
            match_type=d['type'],
            tooltip_str=d['tooltip'],
            picture_path = picture_path,
            lhs_graph = d.get('lhs', None),
            rhs_graph = d.get('rhs', None),
            copy_first=d.get('copy_first', False),
            returns_new_graph=d.get('returns_new_graph', False),
            repeat_rule_application=d.get('repeat_rule_application', False),
        )

    def do_rewrite(self, panel: ProofPanel) -> None:
        if not self.enabled:
            return

        # Special handling for unfusion rule
        if self.name == "unfuse":
            from .unfusion_rewrite import UnfusionRewriteAction
            verts, _ = panel.parse_selection()
            if len(verts) == 1:
                self.unfusion_action = UnfusionRewriteAction(panel)
                self.unfusion_action.start_unfusion(verts[0])
            return

        g = copy.deepcopy(panel.graph_scene.g)
        verts, edges = panel.parse_selection()

        rem_verts_list: list[VT] = []
        matches_list: list[VT | ET] = []
        while True:
            if self.match_type == MATCHES_VERTICES:
                matches = self.matcher(
                    g,
                    lambda v: v in verts and g.type(v) != VertexType.DUMMY
                )
            else:
                matches = self.matcher(
                    g,
                    lambda e: (
                        e in edges and
                        g.type(g.edge_s(e)) != VertexType.DUMMY and
                        g.type(g.edge_t(e)) != VertexType.DUMMY
                    )
                )
            matches_list.extend(matches)
            if not matches:
                break
            try:
                g, rem_verts = self.apply_rewrite(g, matches)
                rem_verts_list.extend(rem_verts)
            except Exception as ex:
                show_error_msg('Error while applying rewrite rule', str(ex))
                return
            if not self.repeat_rule_application:
                break

        cmd = AddRewriteStep(panel.graph_view, g, panel.step_view, self.name)
        anim_before, anim_after = make_animation(self, panel, g, matches_list, rem_verts_list)
        panel.undo_stack.push(cmd, anim_before=anim_before, anim_after=anim_after)

    # TODO: Narrow down the type of the first return value.
    def apply_rewrite(self, g: GraphT, matches: list) -> tuple[GraphT, list[VT]]:
        if self.returns_new_graph:
            graph = self.rule(g, matches)
            assert isinstance(graph, GraphT)
            return graph, []

        rewrite = self.rule(g, matches)
        assert isinstance(rewrite, tuple) and len(rewrite) == 4
        etab, rem_verts, rem_edges, check_isolated_vertices = rewrite
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

    @property
    def tooltip(self) -> str:
        if self.picture_path is None or display_setting.previews_show == False:
            return self.tooltip_str
        if self.picture_path == 'custom':
            # We will create a custom tooltip picture representing the custom rewrite
            graph_scene_left = GraphScene()
            graph_scene_right = GraphScene()
            graph_view_left = GraphView(graph_scene_left)
            graph_view_left.draw_background_lines = False
            if self.lhs_graph is not None:
                graph_view_left.set_graph(self.lhs_graph)
            graph_view_right = GraphView(graph_scene_right)
            graph_view_right.draw_background_lines = False
            if self.rhs_graph is not None:
                graph_view_right.set_graph(self.rhs_graph)
            graph_view_left.fit_view()
            graph_view_right.fit_view()
            graph_view_left.setSceneRect(graph_scene_left.itemsBoundingRect())
            graph_view_right.setSceneRect(graph_scene_right.itemsBoundingRect())
            lhs_size = graph_view_left.viewport().size()
            rhs_size = graph_view_right.viewport().size()
            # The picture needs to be wide enough to fit both of them and have some space for the = sign
            pixmap = QPixmap(lhs_size.width() + rhs_size.width() + 160, max(lhs_size.height(), rhs_size.height()))
            pixmap.fill(QColor("#ffffff"))
            graph_view_left.viewport().render(pixmap)
            graph_view_right.viewport().render(pixmap, QPoint(lhs_size.width() + 160, 0))
            # We create a new scene to render the = sign
            new_scene = GraphScene()
            new_view = GraphView(new_scene)
            new_view.draw_background_lines = False
            new_scene.addLine(QLineF(QPointF(10,40), QPointF(80,40)), QPen(QColor("#000000"), 8))
            new_scene.addLine(QLineF(QPointF(10,10), QPointF(80,10)), QPen(QColor("#000000"), 8))
            new_view.setSceneRect(new_scene.itemsBoundingRect())
            new_view.viewport().render(pixmap, QPoint(lhs_size.width(), int(max(lhs_size.height(), rhs_size.height())/2 - 20)))

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG", quality=100)
            image = bytes(buffer.data().toBase64()).decode() # type: ignore # This gives an overloading error, but QByteArray can be converted to bytes
        else:
            pixmap = QPixmap()
            pixmap.load(get_data("tooltips/"+self.picture_path))
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG", quality=100)
            image = bytes(buffer.data().toBase64()).decode() #type: ignore # This gives an overloading error, but QByteArray can be converted to bytes
        self.tooltip_str = '<img src="data:image/png;base64,{}" width="500">'.format(image) + self.tooltip_str
        self.picture_path = None
        return self.tooltip_str


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

    def parent(self, index: QModelIndex | QPersistentModelIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()

        parent_item = cast(RewriteActionTree, index.internalPointer()).parent
        row = parent_item is None or parent_item.row()

        if row is None or parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(row, 0, parent_item)

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
        else:
            self.proof_panel.rewrites_panel.setExpanded(
                index, not self.proof_panel.rewrites_panel.isExpanded(index)
            )

    def update_on_selection(self) -> None:
        selection, edges = self.proof_panel.parse_selection()
        g = self.proof_panel.graph_scene.g
        self.root_item.update_on_selection(g, selection, edges)
        QMetaObject.invokeMethod(self.emitter, "finished", Qt.ConnectionType.QueuedConnection)  # type: ignore

class RewriteActionTreeView(QTreeView):
    def __init__(self, parent: 'ProofPanel'):
        super().__init__(parent)
        self.proof_panel = parent
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.reset_rewrite_panel_style()
        self.refresh_rewrites_model()

    def reset_rewrite_panel_style(self) -> None:
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setStyleSheet(
            f'''
            QTreeView::Item:hover {{
                background-color: #e2f4ff;
            }}
            QTreeView::Item{{
                height:{display_setting.font.pointSizeF() * 2.5}px;
            }}
            QTreeView::Item:!enabled {{
                color: #c0c0c0;
            }}
            ''')

    def show_context_menu(self, position: QPoint) -> None:
        context_menu = QMenu(self)
        refresh_rules = context_menu.addAction("Refresh rules")
        action = context_menu.exec_(self.mapToGlobal(position))
        if action == refresh_rules:
            self.refresh_rewrites_model()

    def refresh_rewrites_model(self) -> None:
        refresh_custom_rules()
        model = RewriteActionTreeModel.from_dict(action_groups, self.proof_panel)
        self.setModel(model)
        self.expand(model.index(0,0))
        self.clicked.connect(model.do_rewrite)
        self.proof_panel.graph_scene.selection_changed_custom.connect(lambda: model.executor.submit(model.update_on_selection))
