#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from PySide6.QtCore import QEvent
from pytestqt.qtbot import QtBot

from zxlive.common import get_settings_value, set_settings_value
from zxlive.edit_panel import GraphEditPanel
from zxlive.mainwindow import MainWindow
from zxlive.proof_panel import ProofPanel
from zxlive.tutorial import (PROOF_TUTORIAL_SEEN, SHOW_ON_STARTUP, Tutorial,
                             TutorialOverlay, editor_steps,
                             maybe_start_first_run, maybe_start_proof_tutorial,
                             proof_steps, start_editor_tutorial)


@pytest.fixture
def app(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.StandardButton.No)
    # Start from a clean "never seen" state for the tutorials.
    set_settings_value(SHOW_ON_STARTUP, True, bool)
    set_settings_value(PROOF_TUTORIAL_SEEN, False, bool)
    mw = MainWindow()
    mw.open_demo_graph()
    qtbot.addWidget(mw)
    return mw


def active_tutorial(mw: MainWindow) -> Tutorial:
    """Return the running tutorial, asserting one is active (for type narrowing)."""
    tut = mw._active_tutorial
    assert isinstance(tut, Tutorial)
    return tut


def overlay_of(tut: Tutorial) -> TutorialOverlay:
    """Return the tutorial's overlay, asserting it exists (for type narrowing)."""
    assert tut.overlay is not None
    return tut.overlay


def test_help_menu_has_tutorial_action(app: MainWindow) -> None:
    actions = [a.text() for a in app.menuBar().actions()]
    assert "&Help" in actions


def test_editor_tour_navigation(app: MainWindow) -> None:
    start_editor_tutorial(app)
    tut = active_tutorial(app)
    ov = overlay_of(tut)
    assert ov.isVisible()

    n = len(tut.spec.steps)
    assert tut.index == 0
    # Back is hidden (not just disabled) on the first step.
    assert not ov.back_button.isVisible()

    # Walk forward to the end.
    for expected in range(1, n):
        tut.next()
        assert tut.index == expected
        assert ov.back_button.isVisible()
    assert ov.next_button.text() == "Finish"

    # Going back works.
    tut.prev()
    assert tut.index == n - 2

    # Stepping forward off the last page finishes the tour and clears it.
    tut.index = n - 1
    tut.next()
    assert tut.overlay is None
    assert app._active_tutorial is None


def test_skip_closes_the_tour(app: MainWindow) -> None:
    start_editor_tutorial(app)
    tut = active_tutorial(app)
    assert tut.overlay is not None
    tut.skip()
    assert tut.overlay is None


def test_first_run_respects_startup_setting(app: MainWindow) -> None:
    set_settings_value(SHOW_ON_STARTUP, False, bool)
    maybe_start_first_run(app)
    assert app._active_tutorial is None

    set_settings_value(SHOW_ON_STARTUP, True, bool)
    maybe_start_first_run(app)
    assert app._active_tutorial is not None
    # The setting is left untouched, so the tour keeps showing on each startup
    # until the user disables it in Preferences.
    assert get_settings_value(SHOW_ON_STARTUP, bool, True) is True


def test_proof_tour_autostarts_and_targets_resolve(app: MainWindow) -> None:
    # Entering proof mode auto-starts the proof tour on first entry.
    app.new_deriv(app.active_panel.graph)  # type: ignore[union-attr]
    tut = active_tutorial(app)
    assert tut.spec.seen_key == PROOF_TUTORIAL_SEEN

    # Exercise the spotlight resolver for every step without crashing.
    for i in range(len(tut.spec.steps)):
        tut.index = i
        tut._show_step()
    tut.skip()
    assert get_settings_value(PROOF_TUTORIAL_SEEN, bool, False) is True


def test_proof_tour_skipped_when_seen(app: MainWindow) -> None:
    set_settings_value(PROOF_TUTORIAL_SEEN, True, bool)
    maybe_start_proof_tutorial(app)
    assert app._active_tutorial is None


def test_closing_window_mid_tour_marks_seen(app: MainWindow) -> None:
    app.new_deriv(app.active_panel.graph)  # type: ignore[union-attr]
    tut = active_tutorial(app)
    assert tut.overlay is not None
    # Simulate the main window being closed while the proof tour is running.
    tut.eventFilter(app, QEvent(QEvent.Type.Close))
    assert tut.overlay is None
    assert get_settings_value(PROOF_TUTORIAL_SEEN, bool, False) is True


def test_starting_a_tour_cancels_the_previous(app: MainWindow) -> None:
    start_editor_tutorial(app)
    first = active_tutorial(app)
    start_editor_tutorial(app)
    second = active_tutorial(app)
    assert first is not second
    assert first.overlay is None
    assert second.overlay is not None


def test_quick_tour_is_a_functional_subset() -> None:
    full = editor_steps(quick=False)
    quick = editor_steps(quick=True)
    assert 0 < len(quick.steps) < len(full.steps)
    # The condensed tour drops the educational steps and the welcome chooser.
    assert not any(s.full_only or s.offer_quick for s in quick.steps)
    # Exactly one welcome step in the full tour offers Quick Start.
    assert sum(s.offer_quick for s in full.steps) == 1


def test_welcome_offers_quick_then_start_quick_switches(app: MainWindow) -> None:
    start_editor_tutorial(app, quick=False)
    tut = active_tutorial(app)
    ov = overlay_of(tut)
    assert tut.spec.steps[0].offer_quick
    assert ov.quick_button.isVisible()

    full_len = len(tut.spec.steps)
    tut.start_quick()
    assert tut.index == 0
    assert len(tut.spec.steps) < full_len
    # The Quick Start button is only shown on the full tour's welcome step.
    assert not ov.quick_button.isVisible()


def test_quick_tour_from_menu(app: MainWindow) -> None:
    start_editor_tutorial(app, quick=True)
    tut = active_tutorial(app)
    ov = overlay_of(tut)
    assert not tut.spec.steps[0].offer_quick
    assert not ov.quick_button.isVisible()


def test_proof_tour_from_menu(app: MainWindow) -> None:
    # The proof-mode tour can be replayed from the Help menu.
    app.new_deriv(app.active_panel.graph)  # type: ignore[union-attr]
    active_tutorial(app).skip()  # dismiss the auto-started tour
    app.start_proof_tutorial()
    tut = active_tutorial(app)
    assert tut.spec.seen_key == PROOF_TUTORIAL_SEEN
    tut.skip()


def test_proof_tour_action_enabled_only_in_proof_mode(app: MainWindow) -> None:
    # In edit mode (demo graph) the proof-tour menu entry is disabled...
    assert isinstance(app.active_panel, GraphEditPanel)
    assert not app.proof_tour_action.isEnabled()
    # ...and enabled once a proof tab is active.
    app.new_deriv(app.active_panel.graph)
    active_tutorial(app).skip()
    assert isinstance(app.active_panel, ProofPanel)
    assert app.proof_tour_action.isEnabled()


def test_step_specs_are_well_formed() -> None:
    for spec in (editor_steps(), editor_steps(quick=True), proof_steps()):
        assert spec.steps
        for step in spec.steps:
            assert step.title
            assert step.text
