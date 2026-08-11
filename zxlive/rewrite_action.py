from __future__ import annotations

import copy
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast, Union, Optional
from concurrent.futures import ThreadPoolExecutor

from pyzx.ft_rewrite import RewriteSingleVertex_ft
from pyzx.rewrite import Rewrite, RewriteSingleVertex, RewriteDoubleVertex, RewriteSimpGraph

from PySide6.QtCore import (Qt, QAbstractItemModel, QModelIndex, QPersistentModelIndex,
                            Signal, QObject, QMetaObject, QPoint, QPointF, QLineF)
from PySide6.QtGui import QPixmap, QColor, QPen, QAction
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView, QMessageBox


from .animations import make_animation
from .commands import AddRewriteStep
from .common import ET, GraphT, VT, get_data, get_settings_value
from .dialogs import show_error_msg
from .features import FAULT_EQUIVALENCE, is_feature_enabled
from .rewrite_data import (is_rewrite_data, RewriteData,
                           MatchType, MATCH_SINGLE, MATCH_DOUBLE, MATCH_COMPOUND,
                           refresh_custom_rules, action_groups, rules_basic,
                           FAULT_EQUIVALENT_GROUP)
from .settings import display_setting
from .graphscene import GraphScene
from .graphview import GraphView, graph_preview_view, pixmap_to_tooltip
from .custom_rule import CustomRule

if TYPE_CHECKING:
    from .proof_panel import ProofPanel

# operations = copy.deepcopy(pyzx.editor.operations)


@dataclass
class RewriteAction:
    name: str
    # matcher: Callable[[GraphT, Callable], list]
    rule: Rewrite  # Callable[[GraphT, list], pyzx.rules.RewriteOutputType[VT, ET]] | Callable[[GraphT, list], GraphT]
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
    is_custom_rule: bool = field(default=False)
    file_path: Optional[str] = field(default=None)
    auto_simplify_multigraph: bool = field(default=False)

    supports_weight_parameter: bool = field(default=False)
    max_fault_equivalence: Optional[int] = field(default=None)
    disabled_by_fe_mode: bool = field(default=False)

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
            rule=d['rule'],
            match_type=d['type'],
            tooltip_str=d['tooltip'],
            picture_path=picture_path,
            lhs_graph=d.get('lhs', None),
            rhs_graph=d.get('rhs', None),
            copy_first=d.get('copy_first', False),
            returns_new_graph=d.get('returns_new_graph', False),
            repeat_rule_application=d.get('repeat_rule_application', False),
            is_custom_rule=d.get('custom_rule', False),
            file_path=d.get('file_path', None),
            supports_weight_parameter=d.get('supports_weight_parameter', False),
            max_fault_equivalence=d.get('max_fault_equivalence', None),
            auto_simplify_multigraph=d.get('auto_simplify_multigraph', False),
        )

    # TODO: Fix code complexity
    # noqa: complexipy
    def do_rewrite(self, panel: ProofPanel) -> None:  # noqa: PLR0912
        if not self.enabled:
            return

        # Special handling for unfusion rule, since this launches a dialog
        if self.name == rules_basic['unfuse']['text']:
            from .unfusion_rewrite import UnfusionRewriteAction
            verts, _ = panel.parse_selection()
            if len(verts) == 1:
                self.unfusion_action = UnfusionRewriteAction(panel)
                self.unfusion_action.start_unfusion(verts[0])
            return

        g = copy.deepcopy(panel.graph_scene.g)
        verts, edges = panel.parse_selection()
        weight = panel.fault_equivalent_weight_value
        if len(verts) == 0 and len(edges) == 0:
            verts = list(g.vertices())
            edges = list(g.edges())

        rem_verts_list: list[VT] = []
        matches_list: list[VT | tuple[VT, VT] | list[VT]] = []
        while True:
            matches: list[VT | tuple[VT, VT] | list[VT]] = []
            if isinstance(self.rule, CustomRule):
                matches = [self.rule.is_match(g, verts)]  # type: ignore
            elif self.match_type == MATCH_SINGLE:
                rule_sv = cast(RewriteSingleVertex, self.rule)
                matches = [v for v in verts if rule_sv.is_match(g, v)]
            elif self.match_type == MATCH_DOUBLE:
                rule_dv = cast(RewriteDoubleVertex, self.rule)
                matches = [g.edge_st(e) for e in edges
                           if g.edge_st(e)[0] != g.edge_st(e)[1]
                           and rule_dv.is_match(g, *g.edge_st(e))]
            elif self.match_type == MATCH_COMPOUND:  # We don't necessarily have a matcher in this case
                if len(verts) == 0:
                    matches = [list(g.vertices())]  # type: ignore
                else:
                    matches = [verts.copy()]  # type: ignore
            matches_list.extend(matches)
            if not matches:
                break
            current_auto_simplify_setting = g.get_auto_simplify()
            if self.auto_simplify_multigraph:
                g.set_auto_simplify(True)
            try:
                applied = False
                for m in matches:
                    if self.supports_weight_parameter:
                        if self.match_type == MATCH_SINGLE:
                            rule_sv_ft = cast(RewriteSingleVertex_ft, self.rule)
                            if rule_sv_ft.apply(g, cast(VT, m), weight=weight):
                                applied = True
                        else:
                            raise ValueError('Unknown fault-tolerant match type. Currently, only MATCH_SINGLE is supported.')
                    else:
                        if self.match_type == MATCH_DOUBLE:
                            rule_dv = cast(RewriteDoubleVertex, self.rule)
                            v1, v2 = cast(tuple[VT, VT], m)
                            if rule_dv.apply(g, v1, v2):
                                applied = True
                        elif self.match_type == MATCH_SINGLE:
                            rule_sv = cast(RewriteSingleVertex, self.rule)
                            if rule_sv.apply(g, cast(VT, m)):
                                applied = True
                        else:
                            rule_sg = cast(RewriteSimpGraph, self.rule)
                            if rule_sg.apply(g, cast(list[VT], m)):
                                applied = True

                # g, rem_verts = self.apply_rewrite(g, matches)
                # rem_verts_list.extend(rem_verts)
            except Exception as ex:
                show_error_msg('Error while applying rewrite rule', str(ex))
                return
            finally:
                if self.auto_simplify_multigraph:
                    g.set_auto_simplify(current_auto_simplify_setting)
            if not self.repeat_rule_application or not applied:
                break
        def set_weight_callback(w: int | None) -> None:
            panel.fault_equivalent_weight_value = w
            if panel.fault_equivalent_weight:
                panel.fault_equivalent_weight.blockSignals(True)
                panel.fault_equivalent_weight.setText("" if w is None else str(w))
                panel.fault_equivalent_weight.blockSignals(False)
        cmd = AddRewriteStep(
            graph_view=panel.graph_view,
            new_g=g,
            step_view=panel.step_view,
            name=self.name,
            saved_weight=weight,
            old_weight=panel.fault_equivalent_weight_value,
            weight_callback=set_weight_callback,
            refresh_rules_callback=panel.rewrites_panel.refresh_rewrites_model
        )
        anim_before, anim_after = make_animation(self, panel, g, matches_list, rem_verts_list)
        panel.undo_stack.push(cmd, anim_before=anim_before, anim_after=anim_after)

    # TODO: Fix code complexity
    # noqa: complexipy
    def update_active(self, g: GraphT, verts: list[VT], edges: list[ET]) -> None:  # noqa: PLR0912
        if self.disabled_by_fe_mode:
            self.enabled = False
            return
        if self.copy_first:
            g = copy.deepcopy(g)
        if len(verts) == 0 and len(edges) == 0:
            verts = list(g.vertices())
            edges = list(g.edges())
        if self.match_type == MATCH_SINGLE:
            rule_sv = cast(RewriteSingleVertex, self.rule)
            for v in verts:
                if rule_sv.is_match(g, v):
                    self.enabled = True
                    return
            self.enabled = False
            return
        elif self.match_type == MATCH_DOUBLE:
            rule_dv = cast(RewriteDoubleVertex, self.rule)
            for e in edges:
                s, t = g.edge_st(e)
                if s == t:
                    continue
                if rule_dv.is_match(g, s, t):
                    self.enabled = True
                    return
            self.enabled = False
            return
        elif self.match_type == MATCH_COMPOUND:
            try:
                self.enabled = bool(self.rule.is_match(g, verts)) # type: ignore
            except (AttributeError, TypeError):
                # No compatible matcher exists, so defer applicability checking until application.
                self.enabled = True
            return

    @property
    def tooltip(self) -> str:
        if self.picture_path is None or not display_setting.previews_show:
            return self.tooltip_str
        if self.picture_path == 'custom':
            # We will create a custom tooltip picture representing the custom rewrite
            graph_view_left = graph_preview_view(self.lhs_graph)
            graph_view_right = graph_preview_view(self.rhs_graph)
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
            new_scene.addLine(QLineF(QPointF(10, 40), QPointF(80, 40)), QPen(QColor("#000000"), 8))
            new_scene.addLine(QLineF(QPointF(10, 10), QPointF(80, 10)), QPen(QColor("#000000"), 8))
            new_view.setSceneRect(new_scene.itemsBoundingRect())
            new_view.viewport().render(pixmap, QPoint(lhs_size.width(), int(max(lhs_size.height(), rhs_size.height()) / 2 - 20)))

        else:
            pixmap = QPixmap()
            pixmap.load(get_data("tooltips/" + self.picture_path))
        self.tooltip_str = pixmap_to_tooltip(pixmap, self.tooltip_str)
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
        if self.rewrite is None:
            return ""
        if self.rewrite.disabled_by_fe_mode:
            return ("This rewrite is not fault-equivalent, so it is disabled while "
                    "fault-equivalent mode is active.")
        return self.rewrite.tooltip

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

    def set_disabled_by_fe_mode(self, disabled: bool) -> None:
        for child in self.child_items:
            child.set_disabled_by_fe_mode(disabled)
        if self.rewrite is not None:
            self.rewrite.disabled_by_fe_mode = disabled
            if disabled:
                self.rewrite.enabled = False

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
        self.emitter.finished.connect(self.layoutChanged.emit)
        self.executor = ThreadPoolExecutor(max_workers=1)

    def set_root(self, root: RewriteActionTree) -> None:
        self.beginResetModel()
        self.root_item = root
        self.endResetModel()

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
        try:
            selection, edges = self.proof_panel.parse_selection()
            g = self.proof_panel.graph_scene.g
            self.root_item.update_on_selection(g, selection, edges)
        finally:
            # If an exception happens while matching some rule, we still want to update the view
            QMetaObject.invokeMethod(self.emitter, "finished", Qt.ConnectionType.QueuedConnection)


class RewriteActionTreeView(QTreeView):
    def __init__(self, parent: 'ProofPanel'):
        super().__init__(parent)
        self.proof_panel = parent
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.reset_rewrite_panel_style()
        self.refresh_rewrites_model()

        self.clicked.connect(self.on_item_clicked)

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
        index = self.indexAt(position)
        context_menu = QMenu(self)

        # Check if the clicked item is a custom rule
        is_custom = False
        rewrite_action = None
        if index.isValid():
            node = cast(RewriteActionTree, index.internalPointer())
            if node.is_rewrite:
                rewrite_action = node.rewrite_action
                is_custom = rewrite_action.is_custom_rule

        if is_custom and rewrite_action and rewrite_action.file_path:
            # Add custom rule specific options
            edit_action = QAction("Edit", self)
            edit_action.triggered.connect(lambda: self._edit_custom_rule(rewrite_action.file_path))
            context_menu.addAction(edit_action)

            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(lambda: self._delete_custom_rule(rewrite_action))
            context_menu.addAction(delete_action)

            context_menu.addSeparator()

            show_in_folder_action = QAction("Show in folder", self)
            show_in_folder_action.triggered.connect(lambda: self._show_in_folder(rewrite_action.file_path))
            context_menu.addAction(show_in_folder_action)

            context_menu.addSeparator()

        refresh_rules = context_menu.addAction("Refresh rules")
        action = context_menu.exec_(self.mapToGlobal(position))
        if action == refresh_rules:
            self.refresh_rewrites_model()

    def _edit_custom_rule(self, file_path: Optional[str]) -> None:
        """Open the custom rule file for editing."""
        if not file_path or not os.path.exists(file_path):
            return
        main_window = self.proof_panel.window()
        if hasattr(main_window, 'open_file_from_path'):
            main_window.open_file_from_path(file_path)

    def _delete_custom_rule(self, rewrite_action: RewriteAction) -> None:
        """Delete the custom rule file after confirmation."""
        if not rewrite_action.file_path or not os.path.exists(rewrite_action.file_path):
            return

        rule_name = rewrite_action.name
        reply = QMessageBox.question(
            self,
            "Delete Custom Rule",
            f"Are you sure you want to delete the custom rule '{rule_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(rewrite_action.file_path)
                self.refresh_rewrites_model()
            except Exception as e:
                QMessageBox.warning(self, "Delete Failed", f"Could not delete custom rule: {str(e)}")

    def _show_in_folder(self, file_path: Optional[str]) -> None:
        """Open the folder containing the custom rule file in the system file explorer."""
        if not file_path or not os.path.exists(file_path):
            return

        folder_path = os.path.dirname(file_path)
        if not os.path.isdir(folder_path):
            return

        abs_path = os.path.abspath(folder_path)
        # Basic security check: ensure path is a real directory
        if not os.path.isdir(abs_path):
            return

        if sys.platform == "win32":
            os.startfile(abs_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", abs_path], check=False)
        else:
            subprocess.run(["xdg-open", abs_path], check=False)

    def on_item_clicked(self, index: QModelIndex) -> None:
        model = self.model()
        if hasattr(model,"do_rewrite"):
            model.do_rewrite(index)

    def _expanded_group_ids(self) -> list[str]:
        model = self.model()
        if model is None:
            return []
        expanded_group_ids = []
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if self.isExpanded(index):
                expanded_group_ids.append(cast(str, index.data()))
        return expanded_group_ids

    def refresh_rewrites_model(self) -> None:
        expanded_group_ids = self._expanded_group_ids()

        # Refresh the custom rules and update the model
        refresh_custom_rules()
        root_item = RewriteActionTree.from_dict(self.get_visible_action_groups())
        if self.fault_equivalent_mode_active():
            for group in root_item.child_items:
                group.set_disabled_by_fe_mode(group.id != FAULT_EQUIVALENT_GROUP)
            expanded_group_ids = [FAULT_EQUIVALENT_GROUP]

        # The model is reused so that its worker and signal connection are not duplicated.
        model = self.model()
        if isinstance(model, RewriteActionTreeModel):
            model.set_root(root_item)
        else:
            model = RewriteActionTreeModel(root_item, self.proof_panel)
            self.setModel(model)
            self.proof_panel.graph_scene.selection_changed_custom.connect(self._schedule_selection_update)

        expanded_any = False
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data() in expanded_group_ids:
                self.expand(index)
                expanded_any = True
        if not expanded_any:
            if get_settings_value("expand-rules-sidebar", bool):
                self.expandAll()
            else:
                self.expand(model.index(0, 0))

    def _schedule_selection_update(self) -> None:
        model = self.model()
        if isinstance(model, RewriteActionTreeModel):
            model.executor.submit(model.update_on_selection)

    def release_resources(self) -> None:
        model = self.model()
        if isinstance(model, RewriteActionTreeModel):
            self.proof_panel.graph_scene.selection_changed_custom.disconnect(self._schedule_selection_update)
            model.executor.shutdown(wait=True, cancel_futures=True)

    def fault_equivalent_mode_active(self) -> bool:
        return (is_feature_enabled(FAULT_EQUIVALENCE)
                and self.proof_panel.fault_equivalent_mode.isChecked())

    def get_visible_action_groups(self) -> dict[str, dict[str, RewriteData]]:
        """Return the rewrite groups to display in the tree.

        The fault-equivalent group is only shown in fault-equivalent mode, where it is
        listed first and its rules are additionally filtered by the selected fault
        weight: a rule is kept if it is fully fault-equivalent, or if a weight is set
        that does not exceed the weight up to which the rule stays fault-equivalent.
        An unset weight means w = ∞, so only fully fault-equivalent rules are kept.
        """
        fe_mode = self.fault_equivalent_mode_active()
        selected_weight = self.proof_panel.fault_equivalent_weight_value

        visible_groups: dict[str, dict[str, RewriteData]] = {}
        if fe_mode:
            visible_groups[FAULT_EQUIVALENT_GROUP] = {
                rule_name: rule
                for rule_name, rule in action_groups[FAULT_EQUIVALENT_GROUP].items()
                if (max_weight := rule.get("max_fault_equivalence", None)) is None
                or (selected_weight is not None and selected_weight <= max_weight)
            }
        for group_name, rules in action_groups.items():
            if group_name != FAULT_EQUIVALENT_GROUP:
                visible_groups[group_name] = rules
        return visible_groups
