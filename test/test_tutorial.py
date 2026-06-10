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
from zxlive.mainwindow import MainWindow
from zxlive.tutorial import (PROOF_TUTORIAL_SEEN, SHOW_ON_STARTUP, Tutorial,
                             editor_steps, maybe_start_first_run,
                             maybe_start_proof_tutorial, proof_steps,
                             start_editor_tutorial)


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


def test_help_menu_has_tutorial_action(app: MainWindow) -> None:
    actions = [a.text() for a in app.menuBar().actions()]
    assert "&Help" in actions


def test_editor_tour_navigation(app: MainWindow) -> None:
    start_editor_tutorial(app)
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert isinstance(tut, Tutorial)
    assert tut.overlay is not None
    assert tut.overlay.isVisible()

    n = len(tut.spec.steps)
    assert tut.index == 0
    # Back is hidden (not just disabled) on the first step.
    assert not tut.overlay.back_button.isVisible()

    # Walk forward to the end.
    for expected in range(1, n):
        tut.next()
        assert tut.index == expected
        assert tut.overlay.back_button.isVisible()
    assert tut.overlay.next_button.text() == "Finish"

    # Going back works.
    tut.prev()
    assert tut.index == n - 2

    # Stepping forward off the last page finishes the tour and clears it.
    tut.index = n - 1
    tut.next()
    assert tut.overlay is None
    assert getattr(app, "_active_tutorial", None) is None


def test_skip_closes_the_tour(app: MainWindow) -> None:
    start_editor_tutorial(app)
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert tut.overlay is not None
    tut.skip()
    assert tut.overlay is None


def test_first_run_respects_startup_setting(app: MainWindow) -> None:
    set_settings_value(SHOW_ON_STARTUP, False, bool)
    maybe_start_first_run(app)
    assert getattr(app, "_active_tutorial", None) is None

    set_settings_value(SHOW_ON_STARTUP, True, bool)
    maybe_start_first_run(app)
    assert app._active_tutorial is not None  # type: ignore[attr-defined]
    # The setting is consumed (one-shot) so it won't re-show next launch.
    assert get_settings_value(SHOW_ON_STARTUP, bool, True) is False


def test_proof_tour_autostarts_and_targets_resolve(app: MainWindow) -> None:
    # Entering proof mode auto-starts the proof tour on first entry.
    app.new_deriv(app.active_panel.graph)  # type: ignore[union-attr]
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert isinstance(tut, Tutorial)
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
    assert getattr(app, "_active_tutorial", None) is None


def test_closing_window_mid_tour_marks_seen(app: MainWindow) -> None:
    app.new_deriv(app.active_panel.graph)  # type: ignore[union-attr]
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert tut.overlay is not None
    # Simulate the main window being closed while the proof tour is running.
    tut.eventFilter(app, QEvent(QEvent.Type.Close))
    assert tut.overlay is None
    assert get_settings_value(PROOF_TUTORIAL_SEEN, bool, False) is True


def test_starting_a_tour_cancels_the_previous(app: MainWindow) -> None:
    start_editor_tutorial(app)
    first = app._active_tutorial  # type: ignore[attr-defined]
    start_editor_tutorial(app)
    second = app._active_tutorial  # type: ignore[attr-defined]
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
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert tut.spec.steps[0].offer_quick
    assert tut.overlay.quick_button.isVisible()

    full_len = len(tut.spec.steps)
    tut.start_quick()
    assert tut.index == 0
    assert len(tut.spec.steps) < full_len
    # The Quick Start button is only shown on the full tour's welcome step.
    assert not tut.overlay.quick_button.isVisible()


def test_quick_tour_from_menu(app: MainWindow) -> None:
    start_editor_tutorial(app, quick=True)
    tut = app._active_tutorial  # type: ignore[attr-defined]
    assert not tut.spec.steps[0].offer_quick
    assert not tut.overlay.quick_button.isVisible()


def test_step_specs_are_well_formed() -> None:
    for spec in (editor_steps(), editor_steps(quick=True), proof_steps()):
        assert spec.steps
        for step in spec.steps:
            assert step.title
            assert step.text
