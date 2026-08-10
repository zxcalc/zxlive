from __future__ import annotations

from typing import Any, cast

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

import zxlive.features
from zxlive.edit_panel import GraphEditPanel
from zxlive.editor_base_panel import vertices_data
from zxlive.features import (FAULT_EQUIVALENCE, PAULI_WEBS, ZH_CALCULUS, ZW_CALCULUS,
                             is_feature_enabled)
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteActionTreeModel
from zxlive.rewrite_data import FAULT_EQUIVALENT_GROUP


@pytest.fixture(autouse=True)
def feature_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Back the feature flags by an in-memory store so the real settings are untouched."""
    store: dict[str, bool] = {}

    def fake_get(key: str, _type: Any, default: Any = None, settings: Any = None) -> Any:
        return store.get(key, default)

    def fake_set(key: str, value: bool, _type: Any, settings: Any = None) -> None:
        store[key] = value

    monkeypatch.setattr(zxlive.features, "get_settings_value", fake_get)
    monkeypatch.setattr(zxlive.features, "set_settings_value", fake_set)
    return store


@pytest.fixture
def app(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    mw = MainWindow()
    mw.open_demo_graph()
    qtbot.addWidget(mw)
    return mw


def _set_feature(app: MainWindow, feature_id: str, enabled: bool) -> None:
    action = app.feature_actions[feature_id]
    action.setChecked(enabled)
    app._toggle_feature(feature_id, enabled)


def _start_derivation(app: MainWindow, qtbot: QtBot) -> ProofPanel:
    from PySide6.QtCore import Qt
    edit_panel = app.active_panel
    assert isinstance(edit_panel, GraphEditPanel)
    qtbot.mouseClick(edit_panel.start_derivation, Qt.MouseButton.LeftButton)
    proof_panel = app.active_panel
    assert isinstance(proof_panel, ProofPanel)
    return proof_panel


def _group_names(panel: ProofPanel) -> list[str]:
    return list(panel.rewrites_panel.get_visible_action_groups().keys())


def test_fault_equivalence_is_off_by_default(app: MainWindow, qtbot: QtBot) -> None:
    assert not is_feature_enabled(FAULT_EQUIVALENCE)
    panel = _start_derivation(app, qtbot)
    assert not panel.is_toolbar_widget_visible(panel.fault_equivalent_mode)
    assert not panel.is_toolbar_widget_visible(panel.fe_weight_widget)
    assert FAULT_EQUIVALENT_GROUP not in _group_names(panel)


def test_enabling_feature_shows_the_toggle_but_not_the_weight(app: MainWindow, qtbot: QtBot) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    assert panel.is_toolbar_widget_visible(panel.fault_equivalent_mode)
    assert not panel.is_toolbar_widget_visible(panel.fe_weight_widget)
    assert panel.fe_banner.isHidden()
    assert FAULT_EQUIVALENT_GROUP not in _group_names(panel)


def test_fault_equivalent_mode_disables_other_rewrites(app: MainWindow, qtbot: QtBot) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)

    assert panel.is_toolbar_widget_visible(panel.fe_weight_widget)
    assert not panel.fe_banner.isHidden()
    assert FAULT_EQUIVALENT_GROUP in _group_names(panel)

    model = cast(RewriteActionTreeModel, panel.rewrites_panel.model())
    for group in model.root_item.child_items:
        expected = group.id != FAULT_EQUIVALENT_GROUP
        for child in group.child_items:
            assert child.rewrite_action.disabled_by_fe_mode is expected
            if expected:
                assert not child.enabled()


def test_fault_equivalent_group_is_first_and_alone_expanded(app: MainWindow, qtbot: QtBot) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)

    assert _group_names(panel)[0] == FAULT_EQUIVALENT_GROUP
    model = cast(RewriteActionTreeModel, panel.rewrites_panel.model())
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        assert panel.rewrites_panel.isExpanded(index) == (index.data() == FAULT_EQUIVALENT_GROUP)


def test_leaving_fault_equivalent_mode_re_enables_other_rewrites(app: MainWindow, qtbot: QtBot) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)
    panel.fault_equivalent_mode.setChecked(False)

    assert not panel.is_toolbar_widget_visible(panel.fe_weight_widget)
    assert panel.fe_banner.isHidden()
    model = cast(RewriteActionTreeModel, panel.rewrites_panel.model())
    for group in model.root_item.child_items:
        for child in group.child_items:
            assert not child.rewrite_action.disabled_by_fe_mode


def test_disabling_feature_leaves_fault_equivalent_mode(app: MainWindow, qtbot: QtBot) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)
    _set_feature(app, FAULT_EQUIVALENCE, False)

    assert not panel.fault_equivalent_mode.isChecked()
    assert not panel.is_toolbar_widget_visible(panel.fault_equivalent_mode)
    assert not panel.is_toolbar_widget_visible(panel.fe_weight_widget)
    assert FAULT_EQUIVALENT_GROUP not in _group_names(panel)


@pytest.mark.parametrize(("weight", "expected"), [(None, True), (2, True), (3, False)])
def test_fault_weight_filters_partially_fault_equivalent_rules(
    app: MainWindow, qtbot: QtBot, weight: int | None, expected: bool
) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)
    panel.fault_equivalent_weight_value = weight

    fe_rules = panel.rewrites_panel.get_visible_action_groups()[FAULT_EQUIVALENT_GROUP]
    # "Unfuse-n Simp" is only fault-equivalent up to weight 2.
    assert ("Unfuse-n Simp" in fe_rules) is expected


def test_pauli_webs_button_follows_its_feature(app: MainWindow, qtbot: QtBot) -> None:
    edit_panel = app.active_panel
    assert isinstance(edit_panel, GraphEditPanel)
    proof_panel = _start_derivation(app, qtbot)

    _set_feature(app, PAULI_WEBS, False)
    assert not edit_panel.is_toolbar_widget_visible(edit_panel.pauli_webs)
    assert not proof_panel.is_toolbar_widget_visible(proof_panel.pauli_webs)

    _set_feature(app, PAULI_WEBS, True)
    assert edit_panel.is_toolbar_widget_visible(edit_panel.pauli_webs)
    assert proof_panel.is_toolbar_widget_visible(proof_panel.pauli_webs)


def test_vertex_palette_follows_calculus_features(app: MainWindow) -> None:
    edit_panel = app.active_panel
    assert isinstance(edit_panel, GraphEditPanel)
    edit_panel._curr_vty = VertexType.W_OUTPUT

    _set_feature(app, ZH_CALCULUS, False)
    _set_feature(app, ZW_CALCULUS, False)
    assert set(vertices_data()) == {VertexType.Z, VertexType.X, VertexType.BOUNDARY, VertexType.DUMMY}
    assert edit_panel._curr_vty == VertexType.Z

    _set_feature(app, ZH_CALCULUS, True)
    assert VertexType.H_BOX in vertices_data()
    assert VertexType.Z_BOX not in vertices_data()

    _set_feature(app, ZW_CALCULUS, True)
    assert {VertexType.H_BOX, VertexType.Z_BOX, VertexType.W_OUTPUT} <= set(vertices_data())
