from __future__ import annotations

from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

import zxlive.features
import zxlive.mainwindow
import zxlive.tutorial
from zxlive.common import new_graph
from zxlive.edit_panel import GraphEditPanel
from zxlive.editor_base_panel import vertices_data
from zxlive.features import (FAULT_EQUIVALENCE, FEATURES, PAULI_WEBS, ZW_CALCULUS,
                             has_seen_feature_picker, is_feature_enabled)
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteActionTreeModel
from zxlive.rewrite_data import FAULT_EQUIVALENT_GROUP
from zxlive.settings import feature_defaults
from zxlive.tutorial import TutorialController


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


def test_toggling_features_does_not_refresh_the_rewrite_tree(
    app: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = _start_derivation(app, qtbot)
    refreshes: list[int] = []
    monkeypatch.setattr(panel.rewrites_panel, "refresh_rewrites_model", lambda: refreshes.append(1))

    _set_feature(app, PAULI_WEBS, False)
    _set_feature(app, FAULT_EQUIVALENCE, True)

    assert refreshes == []


@pytest.mark.parametrize(("weight", "expected"), [(None, False), (2, True), (3, False)])
def test_fault_weight_filters_partially_fault_equivalent_rules(
    app: MainWindow, qtbot: QtBot, weight: int | None, expected: bool
) -> None:
    panel = _start_derivation(app, qtbot)
    _set_feature(app, FAULT_EQUIVALENCE, True)
    panel.fault_equivalent_mode.setChecked(True)
    panel.fault_equivalent_weight_value = weight

    fe_rules = panel.rewrites_panel.get_visible_action_groups()[FAULT_EQUIVALENT_GROUP]
    # "Unfuse-n Simp" is only fault-equivalent up to weight 2, so an unset weight (∞) excludes it.
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

    _set_feature(app, ZW_CALCULUS, False)
    assert set(vertices_data()) == {VertexType.Z, VertexType.X, VertexType.H_BOX, VertexType.BOUNDARY, VertexType.DUMMY}
    assert edit_panel._curr_vty == VertexType.Z

    _set_feature(app, ZW_CALCULUS, True)
    assert {VertexType.H_BOX, VertexType.Z_BOX, VertexType.W_OUTPUT} <= set(vertices_data())


def _selected_vty(edit_panel: GraphEditPanel) -> VertexType:
    item = edit_panel.vertex_list.currentItem()
    assert item is not None
    return cast(VertexType, item.data(Qt.ItemDataRole.UserRole))


def test_palette_highlight_stays_on_the_current_vertex_type(app: MainWindow) -> None:
    edit_panel = app.active_panel
    assert isinstance(edit_panel, GraphEditPanel)
    _set_feature(app, ZW_CALCULUS, True)
    edit_panel._vty_double_clicked(VertexType.W_OUTPUT)
    edit_panel.update_side_bar()
    assert _selected_vty(edit_panel) == VertexType.W_OUTPUT

    # Removing the W node must not leave the highlight on whatever took over its row.
    _set_feature(app, ZW_CALCULUS, False)
    assert edit_panel._curr_vty == VertexType.Z
    assert _selected_vty(edit_panel) == VertexType.Z

    edit_panel._vty_clicked(VertexType.X)
    edit_panel.update_side_bar()
    assert _selected_vty(edit_panel) == VertexType.X

    # Adding entries back shifts the later rows, so the highlight must follow the type.
    edit_panel._vty_clicked(VertexType.DUMMY)
    _set_feature(app, ZW_CALCULUS, True)
    assert _selected_vty(edit_panel) == VertexType.DUMMY


def test_all_features_are_disabled_by_default() -> None:
    assert not any(feature_defaults.values())


def _stub_picker(monkeypatch: pytest.MonkeyPatch,
                 selection: dict[str, bool] | None) -> list[int]:
    calls: list[int] = []

    def fake_picker(_parent: object) -> dict[str, bool] | None:
        calls.append(1)
        return selection

    monkeypatch.setattr(zxlive.mainwindow, "show_feature_picker", fake_picker)
    return calls


def test_feature_picker_applies_selection(app: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_picker(monkeypatch, {FAULT_EQUIVALENCE: True, PAULI_WEBS: True})
    app.maybe_show_feature_picker()

    assert is_feature_enabled(FAULT_EQUIVALENCE)
    assert app.feature_actions[FAULT_EQUIVALENCE].isChecked()
    edit_panel = app.active_panel
    assert isinstance(edit_panel, GraphEditPanel)
    assert edit_panel.is_toolbar_widget_visible(edit_panel.pauli_webs)


def test_feature_picker_is_only_offered_once(app: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_picker(monkeypatch, {})
    app.maybe_show_feature_picker()
    app.maybe_show_feature_picker()
    assert calls == [1]


def test_dismissing_the_picker_leaves_features_off(
    app: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_picker(monkeypatch, None)
    app.maybe_show_feature_picker()
    assert not any(is_feature_enabled(feature["id"]) for feature in FEATURES)
    assert has_seen_feature_picker()


def test_finishing_the_tutorial_offers_the_picker(
    app: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_picker(monkeypatch, {})
    app.tutorial_controller.finished.emit("tutorial/main-seen")
    qtbot.waitUntil(lambda: calls == [1], timeout=2000)


def test_picker_waits_for_a_follow_on_tutorial_section(
    app: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_picker(monkeypatch, {})
    monkeypatch.setattr(TutorialController, "active", property(lambda _self: True))
    app._offer_feature_picker()
    assert calls == []


def test_opening_a_proof_on_first_run_does_not_pre_empt_the_main_tutorial(
    app: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mirrors passing a proof file on the command line: the proof-mode section is
    # scheduled before the first-run tutorial, but the intro tour must win.
    tutorial_store: dict[str, bool] = {}
    monkeypatch.setattr(zxlive.tutorial, "get_settings_value",
                        lambda key, _type, default=None, settings=None: tutorial_store.get(key, default))
    monkeypatch.setattr(zxlive.tutorial, "set_settings_value",
                        lambda key, value, _type, settings=None: tutorial_store.__setitem__(key, value))
    started: list[str] = []
    monkeypatch.setattr(TutorialController, "start",
                        lambda _self, _steps, seen_key: started.append(seen_key))

    app.new_deriv(new_graph())
    app.maybe_show_tutorial_on_first_run()
    qtbot.waitUntil(lambda: started == ["tutorial/main-seen"], timeout=2000)
