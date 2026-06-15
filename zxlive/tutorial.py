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

"""A self-contained interactive onboarding tutorial.

The whole feature lives in this single module so that it can be enabled with
only a handful of hooks in the rest of the code base (see ``mainwindow.py`` and
``app.py``).  The design is a *guided tour*: a translucent overlay dims the
window, spotlights one widget at a time, and shows an explanatory card with
``Back`` / ``Next`` / ``Skip`` buttons.

Most steps are *passive*: the overlay is modal and swallows clicks so the tour
cannot get into an inconsistent state.  Steps marked ``interactive`` let the
user work in the spotlighted UI; ``Next`` stays disabled until an optional
``completion_check`` passes (diagram built, rewrite applied, …).

Three tours are defined:

* :func:`editor_steps` walks through the edit-mode canvas, tools and sidebars.
  It auto-starts the first time ZXLive is launched and can be replayed from the
  Help menu.
* :func:`proof_steps` walks through proof mode (magic wand, rewrites, proof
  steps).  It auto-starts the first time the user enters a derivation.
* :func:`learn_basics_steps` is an interactive lesson where the user builds
  three alternating CNOTs, enters proof mode, and rewrites the diagram to a
  SWAP.  Reference diagrams live in ``zxlive/examples/``.

Whether each tour has been seen is remembered in ``QSettings`` so returning
users are not pestered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, cast

import numpy as np
from networkx.algorithms.isomorphism import (GraphMatcher,
                                             categorical_edge_match,
                                             categorical_node_match)
from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QEvent, QObject,
                            QPoint, QRect, QRectF, QTimer, QVariantAnimation, Qt)
from PySide6.QtGui import (QColor, QKeyEvent, QMouseEvent, QPainter,
                           QPainterPath, QPaintEvent, QPalette, QPen, QPolygon,
                           QResizeEvent)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from .common import GraphT, get_settings_value, set_settings_value
from .construct import construct_swap, construct_three_cnots
from .custom_rule import to_networkx

if TYPE_CHECKING:
    from .mainwindow import MainWindow

# QSettings keys.  ``SHOW_ON_STARTUP`` gates the first-run editor tour and is
# exposed as a checkbox in Preferences; ``PROOF_TUTORIAL_SEEN`` is internal and
# records whether the proof-mode tour has been shown.
SHOW_ON_STARTUP = "tutorial/show-on-startup"
PROOF_TUTORIAL_SEEN = "tutorial/proof-seen"

# Visual constants for the overlay.
_DIM_ALPHA = 160          # 0-255, how strongly the rest of the UI is dimmed
_DIM_ALPHA_INTERACTIVE = 90  # lighter dim when the user needs to click through
_SPOTLIGHT_PAD = 8        # px of breathing room drawn around the target widget
_SPOTLIGHT_RADIUS = 10    # px corner radius of the spotlight cut-out
_CARD_WIDTH = 430         # px fixed width of the explanation card
_CARD_MARGIN = 18         # px gap between the spotlight and the card
_BEAK = 11                # px size of the little pointer from the card
_MIN_TARGET = 6           # px below which a target is treated as not visible


# A resolver maps the main window to the widget a step should spotlight.  It
# returns ``None`` to show a centred card with no spotlight (e.g. the welcome
# step, or when the target happens to be unavailable).
TargetResolver = Callable[["MainWindow"], Optional[QWidget]]
CompletionCheck = Callable[["MainWindow"], bool]
StepHook = Callable[["MainWindow"], None]


@dataclass
class TutorialStep:
    """A single page of a tour.

    ``full_only`` steps are the educational/explanatory ones that the condensed
    *Quick Start* tour skips. ``offer_quick`` / ``offer_learn`` mark the welcome
    step that lets the user drop into Quick Start or the interactive lesson.

    When ``interactive`` is set the overlay passes mouse events through to the
    UI beneath (except on the card).  If ``completion_check`` is also set,
    ``Next`` stays disabled until the check returns ``True``.
    """
    title: str
    text: str  # rich text (a small subset of HTML is supported by QLabel)
    target: Optional[TargetResolver] = None
    full_only: bool = False
    offer_quick: bool = False
    offer_learn: bool = False
    interactive: bool = False
    completion_check: Optional[CompletionCheck] = None
    on_enter: Optional[StepHook] = None


@dataclass
class TutorialSpec:
    """A complete tour.

    ``seen_key``, when set, is a boolean QSettings key flipped to ``True`` when
    the tour ends (finished, skipped, or the window closed mid-tour) so it is
    not auto-shown again. Tours whose first run is gated some other way (the
    editor tour, via :data:`SHOW_ON_STARTUP`) leave it ``None``.
    """
    steps: list[TutorialStep]
    seen_key: Optional[str] = None
    # Run before the first step is shown (e.g. make sure the right tab is up).
    on_start: Optional[Callable[["MainWindow"], None]] = None


# --------------------------------------------------------------------------- #
# Target resolvers
# --------------------------------------------------------------------------- #
# These are intentionally defensive: panels can be the wrong type or a widget
# can be missing (e.g. an optional sidebar), in which case we return ``None``
# and the step falls back to a centred card rather than crashing the tour.

def _toolbar_button(panel: QWidget, *needles: str) -> Optional[QWidget]:
    """Return the first toolbar button whose tooltip contains every needle.

    Toolbar buttons are created as locals in the panel code rather than stored
    as attributes, so we look them up by their (stable) tooltip text.
    """
    toolbar = getattr(panel, "toolbar", None)
    if toolbar is None:
        return None
    buttons: list[QToolButton] = toolbar.findChildren(QToolButton)
    for btn in buttons:
        tip = btn.toolTip().lower()
        if all(needle.lower() in tip for needle in needles):
            return btn
    return None


def _edit_panel(mw: MainWindow) -> Optional[QWidget]:
    from .edit_panel import GraphEditPanel
    panel = mw.active_panel
    return panel if isinstance(panel, GraphEditPanel) else None


def _proof_panel(mw: MainWindow) -> Optional[QWidget]:
    from .proof_panel import ProofPanel
    panel = mw.active_panel
    return panel if isinstance(panel, ProofPanel) else None


def _attr(mw: MainWindow, panel_resolver: TargetResolver, name: str) -> Optional[QWidget]:
    panel = panel_resolver(mw)
    if panel is None:
        return None
    widget = getattr(panel, name, None)
    return widget if isinstance(widget, QWidget) else None


# --------------------------------------------------------------------------- #
# Graph helpers (used by the interactive "Learn the basics" lesson)
# --------------------------------------------------------------------------- #

def _active_graph(mw: MainWindow) -> Optional[GraphT]:
    panel = mw.active_panel
    scene = getattr(panel, "graph_scene", None)
    if scene is None:
        return None
    return cast(GraphT, scene.g)


def graphs_match_ocm(a: Optional[GraphT], b: Optional[GraphT]) -> bool:
    """Return whether two diagrams match up to connectivity (OCM).

    Vertex positions are ignored; spider types, phases, boundary wiring and
    edge types must agree.
    """
    if a is None or b is None:
        return False
    Ga = to_networkx(a)
    Gb = to_networkx(b)
    node_match = categorical_node_match(["type", "phase", "boundary_index"], [1, 0, ""])
    edge_match = categorical_edge_match("type", 1)
    return bool(GraphMatcher(Ga, Gb, node_match=node_match, edge_match=edge_match).is_isomorphic())


def graphs_match_semantics(a: Optional[GraphT], b: Optional[GraphT]) -> bool:
    """Return whether two diagrams denote the same linear map."""
    if a is None or b is None:
        return False
    try:
        return bool(np.allclose(a.to_matrix(), b.to_matrix(), atol=1e-6))
    except Exception:
        return False


def matches_three_cnots(graph: Optional[GraphT]) -> bool:
    """Return whether *graph* is the three alternating CNOTs circuit."""
    ref = construct_three_cnots()
    return graphs_match_ocm(graph, ref) or graphs_match_semantics(graph, ref)


def matches_swap(graph: Optional[GraphT]) -> bool:
    """Return whether *graph* is the simplified SWAP reference diagram."""
    return graphs_match_ocm(graph, construct_swap())


def _canvas_cleared(mw: MainWindow) -> bool:
    graph = _active_graph(mw)
    return graph is not None and graph.num_vertices() == 0


def _in_proof_mode(mw: MainWindow) -> bool:
    from .proof_panel import ProofPanel
    return isinstance(mw.active_panel, ProofPanel)


def _proof_step_count(mw: MainWindow) -> int:
    from .proof_panel import ProofPanel
    panel = mw.active_panel
    if not isinstance(panel, ProofPanel):
        return 0
    return len(panel.proof_model.steps)


def _ensure_edit_panel(mw: MainWindow) -> None:
    from .edit_panel import GraphEditPanel
    if isinstance(mw.active_panel, GraphEditPanel):
        return
    mw.open_demo_graph()


# --------------------------------------------------------------------------- #
# Tour definitions
# --------------------------------------------------------------------------- #

def editor_steps(quick: bool = False) -> TutorialSpec:
    """The tour through edit mode.

    With ``quick=True`` the explanatory/educational steps (and the welcome
    chooser) are dropped, leaving a short functional orientation — the path a
    returning user takes to skip the teaching.
    """
    def graph_view(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def toolbar(mw: MainWindow) -> Optional[QWidget]:
        panel = _edit_panel(mw)
        return getattr(panel, "toolbar", None) if panel else None

    def add_vertex(mw: MainWindow) -> Optional[QWidget]:
        panel = _edit_panel(mw)
        return _toolbar_button(panel, "add vertex") if panel else None

    def add_edge(mw: MainWindow) -> Optional[QWidget]:
        panel = _edit_panel(mw)
        return _toolbar_button(panel, "add edge") if panel else None

    def vertices_sidebar(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "vertex_list")

    def edges_sidebar(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "edge_list")

    def start_derivation(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    steps = [
        TutorialStep(
            "Welcome to ZXLive!",
            "ZXLive is an interactive tool for building and rewriting diagrams "
            "in the <b>ZX-calculus</b>.<br><br>Take the <b>full tour</b> for a "
            "guided walk through the interface, or <b>Quick start</b> for a "
            "short functional overview. You can <b>Skip</b> at any time.",
            offer_quick=True,
            offer_learn=True,
        ),
        TutorialStep(
            "The canvas",
            "This is where your diagram lives. You can pan by dragging the "
            "background, zoom with the scroll wheel, and select vertices or "
            "edges by clicking them.",
            graph_view,
        ),
        TutorialStep(
            "The toolbar",
            "The toolbar holds the editing tools. The first group switches "
            "between <b>Select</b>, <b>Add Vertex</b> and <b>Add Edge</b> "
            "modes. Each tool also has a keyboard shortcut shown in its "
            "tooltip.",
            toolbar,
        ),
        TutorialStep(
            "Add Vertex tool (v)",
            "With the <b>Add Vertex</b> tool active, click anywhere on the "
            "canvas to drop a new spider. The kind of spider added is the one "
            "currently selected in the <i>Vertices</i> sidebar.",
            add_vertex,
        ),
        TutorialStep(
            "Add Edge tool (e)",
            "With the <b>Add Edge</b> tool active, drag from one vertex to "
            "another to connect them. Use the <i>Edges</i> sidebar to choose "
            "between a simple wire and a Hadamard edge.",
            add_edge,
        ),
        TutorialStep(
            "Vertices sidebar",
            "Pick which vertex type new vertices will be: Z spider, X spider, "
            "H box, and so on. <b>Double-clicking</b> a type here also changes "
            "the type of any currently selected vertices.",
            vertices_sidebar,
            full_only=True,
        ),
        TutorialStep(
            "Edges sidebar",
            "Choose the edge type for new connections. Double-clicking a type "
            "changes any selected edges between simple and Hadamard.",
            edges_sidebar,
            full_only=True,
        ),
        TutorialStep(
            "Adding a phase",
            "<b>Double-click a Z or X spider</b> on the canvas to set its "
            "phase (in multiples of π). This is how you turn a bare spider into "
            "a rotation.",
            graph_view,
            full_only=True,
        ),
        TutorialStep(
            "Start Derivation",
            "Once you have a diagram you like, click <b>Start Derivation</b> to "
            "enter <i>proof mode</i>, where you can rewrite the diagram step by "
            "step while preserving its meaning. A dedicated tour will appear "
            "the first time you do this.",
            start_derivation,
        ),
        TutorialStep(
            "You're all set!",
            "That covers the basics of building diagrams. You can replay this "
            "tour any time from <b>Help → Interactive Tutorial</b>.<br><br>"
            "Happy rewriting!",
        ),
    ]
    if quick:
        steps = [s for s in steps if not (s.full_only or s.offer_quick)]
    return TutorialSpec(steps)


def proof_steps() -> TutorialSpec:
    """The tour shown when the user first enters proof mode."""
    def rewrites(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def magic_wand(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "magic_wand")

    def identity_choice(mw: MainWindow) -> Optional[QWidget]:
        panel = _proof_panel(mw)
        choice = getattr(panel, "identity_choice", None) if panel else None
        if choice:
            first = choice[0]
            return first if isinstance(first, QWidget) else None
        return None

    def step_view(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    steps = [
        TutorialStep(
            "Welcome to proof mode!",
            "In proof mode you transform your diagram with sound ZX-calculus "
            "rewrites. The original diagram is preserved and every step is "
            "recorded, so you can always go back.",
        ),
        TutorialStep(
            "Rewrites panel",
            "This panel lists the rewrite rules that apply to your current "
            "selection. Select part of the diagram, then double-click a rule "
            "to apply it. With nothing selected, rules are matched against the "
            "whole diagram.",
            rewrites,
        ),
        TutorialStep(
            "The magic wand (w)",
            "The <b>magic wand</b> is the quickest way to rewrite. Drag it "
            "<i>through</i> a spider to unfuse it, through a wire to add an "
            "identity, or across parallel edges to cancel them. Drag through a "
            "degree-2 spider to remove it.",
            magic_wand,
        ),
        TutorialStep(
            "Spider colour for identities",
            "When the wand adds an identity spider, these buttons decide "
            "whether it is a <b>Z</b> or an <b>X</b> spider.",
            identity_choice,
        ),
        TutorialStep(
            "Proof steps",
            "Every rewrite you apply is appended here. Click any step to jump "
            "back to that point in the derivation — handy for reviewing or "
            "undoing part of a proof.",
            step_view,
        ),
        TutorialStep(
            "Go forth and prove!",
            "You can export a finished proof to TikZ or GIF from the "
            "<b>File</b> menu, or save it as a reusable rewrite from the "
            "<b>Rewrites</b> menu. Replay this tour any time from "
            "<b>Help → Interactive Tutorial</b>.",
        ),
    ]
    return TutorialSpec(steps, PROOF_TUTORIAL_SEEN)


def learn_basics_steps() -> TutorialSpec:
    """Interactive lesson: build three CNOTs and rewrite them to a SWAP."""

    def graph_view(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def add_vertex(mw: MainWindow) -> Optional[QWidget]:
        panel = _edit_panel(mw)
        return _toolbar_button(panel, "add vertex") if panel else None

    def add_edge(mw: MainWindow) -> Optional[QWidget]:
        panel = _edit_panel(mw)
        return _toolbar_button(panel, "add edge") if panel else None

    def vertices_sidebar(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "vertex_list")

    def start_derivation(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_graph_view(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    def proof_selection(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "selection")

    def proof_magic_wand(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "magic_wand")

    def proof_rewrites(mw: MainWindow) -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    steps = [
        TutorialStep(
            "Learn the basics: 3 CNOTs = SWAP",
            "In this hands-on lesson you will build the classic circuit of "
            "<b>three alternating CNOTs</b> on two qubits, then enter proof "
            "mode and rewrite it into a <b>SWAP</b>.<br><br>"
            "Follow the spotlights — <b>Next</b> unlocks once each task is done.",
        ),
        TutorialStep(
            "Clear the canvas",
            "First, remove the demo diagram. Press <b>Ctrl+A</b> to select "
            "everything, then <b>Delete</b>.",
            graph_view,
            interactive=True,
            completion_check=_canvas_cleared,
        ),
        TutorialStep(
            "Pick the Z spider",
            "Open the <i>Vertices</i> sidebar and click the <b>Z spider</b> "
            "type — new vertices you add will be green Z spiders.",
            vertices_sidebar,
            interactive=True,
        ),
        TutorialStep(
            "Place Z spiders",
            "Press <b>v</b> for the <b>Add Vertex</b> tool, then click the "
            "canvas to drop the Z spiders for the circuit.",
            add_vertex,
            interactive=True,
        ),
        TutorialStep(
            "Pick the X spider",
            "Switch to the <b>X spider</b> type in the <i>Vertices</i> sidebar.",
            vertices_sidebar,
            interactive=True,
        ),
        TutorialStep(
            "Wire the circuit",
            "Press <b>e</b> for the <b>Add Edge</b> tool. Add X spiders and "
            "boundary nodes, then connect them into <b>three alternating "
            "CNOTs</b> (control/target/control on the two qubit lines).",
            add_edge,
            interactive=True,
            completion_check=lambda mw: matches_three_cnots(_active_graph(mw)),
        ),
        TutorialStep(
            "Start Derivation",
            "Your circuit looks good! Click <b>Start Derivation</b> to enter "
            "proof mode, where rewrites preserve the meaning of the diagram.",
            start_derivation,
            interactive=True,
            completion_check=_in_proof_mode,
        ),
        TutorialStep(
            "Apply bialgebra",
            "Press <b>s</b> for Select mode, then <b>drag a Z spider onto a "
            "neighbouring X spider</b>. ZXLive applies the bialgebra rule "
            "automatically.",
            proof_selection,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),
        TutorialStep(
            "Fuse and remove identities",
            "Drag adjacent spiders of the same colour together to fuse them. "
            "Remove degree-2 identity spiders with the <b>magic wand</b> "
            "(<b>w</b>) or the <b>remove identity</b> rule in the rewrites "
            "panel.",
            proof_magic_wand,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 2,
        ),
        TutorialStep(
            "Reach the SWAP",
            "Keep simplifying — merge spiders and remove identities until the "
            "diagram is the compact <b>SWAP</b> on two qubits.",
            proof_graph_view,
            interactive=True,
            completion_check=lambda mw: matches_swap(_active_graph(mw)),
        ),
        TutorialStep(
            "Congratulations!",
            "You built three alternating CNOTs and rewrote them to a SWAP "
            "using the ZX-calculus. Replay this lesson any time from "
            "<b>Help → Interactive Tutorial → Learn the Basics</b>.",
        ),
    ]
    return TutorialSpec(steps, on_start=_ensure_edit_panel)


# --------------------------------------------------------------------------- #
# Overlay widget
# --------------------------------------------------------------------------- #

class TutorialOverlay(QWidget):
    """Full-window translucent overlay that dims everything but the spotlight.

    The overlay is a child of the main window and tracks its size. It swallows
    mouse clicks over the dimmed area so the tour controls the flow, while its
    own card buttons remain fully interactive.
    """

    def __init__(self, controller: "Tutorial", parent: QWidget) -> None:
        super().__init__(parent)
        self._controller = controller
        self._spotlight: Optional[QRect] = None
        self._pulse = 1.0
        self._interactive = False
        self._dim_alpha = _DIM_ALPHA

        # Paint our own background; let mouse events stop here (modal feel).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # A gently pulsing spotlight border to draw the eye to the target.
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(1100)
        self._pulse_anim.setKeyValueAt(0.0, 0.4)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.4)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)

        widgets = _build_card(self)
        self._card = widgets.frame
        self.title_label = widgets.title
        self.body_label = widgets.body
        self.progress_label = widgets.progress
        self.quick_button = widgets.quick
        self.learn_button = widgets.learn
        self.skip_button = widgets.skip
        self.back_button = widgets.back
        self.next_button = widgets.next

        self.quick_button.clicked.connect(self._controller.start_quick)
        self.learn_button.clicked.connect(self._controller.start_learn_basics)
        self.skip_button.clicked.connect(self._controller.skip)
        self.back_button.clicked.connect(self._controller.prev)
        self.next_button.clicked.connect(self._controller.next)

        self.setGeometry(parent.rect())

    def set_interactive(self, interactive: bool) -> None:
        """Toggle click-through mode for hands-on steps."""
        self._interactive = interactive
        self._dim_alpha = _DIM_ALPHA_INTERACTIVE if interactive else _DIM_ALPHA
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, interactive)
        self._card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.update()

    def set_step(self, title: str, body: str, spotlight: Optional[QRect],
                 step_index: int, step_count: int, *, offer_quick: bool = False,
                 offer_learn: bool = False, can_advance: bool = True) -> None:
        """Update the card contents and reposition relative to the spotlight."""
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.progress_label.setText(f"Step {step_index + 1} of {step_count}")
        # Hide (rather than just disable) Back on the first step so the welcome
        # step's wider Quick start / Full tour buttons aren't squeezed.
        self.back_button.setVisible(step_index > 0)
        is_last = step_index == step_count - 1
        self.next_button.setText("Finish" if is_last else ("Full tour" if offer_quick else "Next"))
        self.skip_button.setVisible(not is_last)
        self.quick_button.setVisible(offer_quick)
        self.learn_button.setVisible(offer_learn)
        self.set_next_enabled(can_advance)

        self._spotlight = spotlight
        self._position_card(spotlight)
        if spotlight is not None:
            if self._pulse_anim.state() != QAbstractAnimation.State.Running:
                self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
            self._pulse = 1.0
        self.update()

    def set_next_enabled(self, enabled: bool) -> None:
        self.next_button.setEnabled(enabled)
        if not enabled and self._interactive:
            self.next_button.setToolTip("Complete the highlighted task to continue.")
        else:
            self.next_button.setToolTip("")

    def _on_pulse(self, value: object) -> None:
        self._pulse = float(cast(float, value))
        if self._spotlight is not None:
            self.update()

    def _position_card(self, spotlight: Optional[QRect]) -> None:
        card = self._card
        card.setFixedWidth(_CARD_WIDTH)
        card.adjustSize()
        cw, ch = card.width(), card.height()
        ow, oh = self.width(), self.height()

        if spotlight is None or not spotlight.isValid():
            card.move((ow - cw) // 2, (oh - ch) // 2)
            return

        def clamp_x(x: int) -> int:
            return max(_CARD_MARGIN, min(x, ow - cw - _CARD_MARGIN))

        def clamp_y(y: int) -> int:
            return max(_CARD_MARGIN, min(y, oh - ch - _CARD_MARGIN))

        cx = clamp_x(spotlight.center().x() - cw // 2)
        # Prefer below the spotlight, then above, then beside, else centred.
        below_y = spotlight.bottom() + _CARD_MARGIN
        above_y = spotlight.top() - _CARD_MARGIN - ch
        if below_y + ch <= oh - _CARD_MARGIN:
            card.move(cx, below_y)
        elif above_y >= _CARD_MARGIN:
            card.move(cx, above_y)
        elif spotlight.right() + _CARD_MARGIN + cw <= ow - _CARD_MARGIN:
            card.move(spotlight.right() + _CARD_MARGIN, clamp_y(spotlight.center().y() - ch // 2))
        elif spotlight.left() - _CARD_MARGIN - cw >= _CARD_MARGIN:
            card.move(spotlight.left() - _CARD_MARGIN - cw, clamp_y(spotlight.center().y() - ch // 2))
        else:
            card.move((ow - cw) // 2, (oh - ch) // 2)

    # -- Qt event overrides -------------------------------------------------- #

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        # Fall back to an invalid rect when there is no spotlight, so the
        # branches below read off spot.isValid() without any Optional juggling.
        spot = self._spotlight if self._spotlight is not None else QRect()
        if spot.isValid():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(spot), _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
            path = path.subtracted(hole)

        painter.fillPath(path, QColor(0, 0, 0, self._dim_alpha))

        if spot.isValid():
            self._paint_beak(painter, spot)
            highlight = self.palette().highlight().color()
            highlight.setAlphaF(self._pulse)
            pen = QPen(highlight)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(spot, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)

    def _paint_beak(self, painter: QPainter, spot: QRect) -> None:
        """Draw a small triangular pointer from the card towards the spotlight.

        The beak only appears when the card sits cleanly on one side of the
        spotlight; when they overlap (e.g. a centred card) it is omitted.
        """
        card = self._card.geometry()
        cx = max(card.left() + _BEAK, min(spot.center().x(), card.right() - _BEAK))
        cy = max(card.top() + _BEAK, min(spot.center().y(), card.bottom() - _BEAK))
        if card.top() >= spot.bottom():        # card below spotlight, point up
            tri = [QPoint(cx - _BEAK, card.top()), QPoint(cx + _BEAK, card.top()),
                   QPoint(cx, card.top() - _BEAK)]
        elif card.bottom() <= spot.top():      # card above, point down
            tri = [QPoint(cx - _BEAK, card.bottom()), QPoint(cx + _BEAK, card.bottom()),
                   QPoint(cx, card.bottom() + _BEAK)]
        elif card.left() >= spot.right():      # card to the right, point left
            tri = [QPoint(card.left(), cy - _BEAK), QPoint(card.left(), cy + _BEAK),
                   QPoint(card.left() - _BEAK, cy)]
        elif card.right() <= spot.left():      # card to the left, point right
            tri = [QPoint(card.right(), cy - _BEAK), QPoint(card.right(), cy + _BEAK),
                   QPoint(card.right() + _BEAK, cy)]
        else:
            return
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.setBrush(self.palette().window().color())
        painter.drawPolygon(QPolygon(tri))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._controller.reposition()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._interactive:
            event.ignore()
            return
        # Swallow clicks on the dimmed area so the underlying UI stays inert.
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._controller.skip()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.next_button.isEnabled():
                self._controller.next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
            self._controller.prev()
        else:
            super().keyPressEvent(event)


def _muted_text_color(palette: QPalette) -> QColor:
    """A de-emphasised text colour that stays readable on any theme.

    Blends the window text colour 35% of the way towards the window background:
    since the text colour is guaranteed to contrast with the background, the
    result is softer than full text but never as low-contrast as a fixed mid
    tone, in either light or dark mode.
    """
    text = palette.color(QPalette.ColorRole.WindowText)
    bg = palette.color(QPalette.ColorRole.Window)
    t = 0.35
    return QColor(
        round(text.red() * (1 - t) + bg.red() * t),
        round(text.green() * (1 - t) + bg.green() * t),
        round(text.blue() * (1 - t) + bg.blue() * t),
    )


@dataclass
class _CardWidgets:
    """The explanation card frame and its child widgets, typed for direct use.

    Returned by :func:`_build_card` so the overlay can hold properly typed
    references instead of looking children up by name (which would force
    ``Optional`` returns and ``# type: ignore`` casts).
    """
    frame: QFrame
    title: QLabel
    body: QLabel
    progress: QLabel
    quick: QPushButton
    learn: QPushButton
    skip: QPushButton
    back: QPushButton
    next: QPushButton


def _build_card(parent: QWidget) -> _CardWidgets:
    """Create the explanation card (title, body, progress, buttons)."""
    card = QFrame(parent)
    card.setObjectName("tutorial_card")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setStyleSheet(
        """
        QFrame#tutorial_card {
            background: palette(window);
            border: 1px solid palette(mid);
            border-radius: 10px;
        }
        QLabel#tutorial_title { font-size: 16px; font-weight: bold; }
        """
    )

    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 14)
    layout.setSpacing(10)

    title = QLabel(card)
    title.setObjectName("tutorial_title")
    title.setWordWrap(True)
    layout.addWidget(title)

    body = QLabel(card)
    body.setWordWrap(True)
    body.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(body)

    controls = QHBoxLayout()
    controls.setSpacing(8)
    progress = QLabel(card)
    # Muted but readable: a fixed palette role (e.g. "mid") can sit too close to
    # the window background on some themes, so blend the actual text colour part
    # way towards the background. This keeps contrast in both light and dark.
    progress.setStyleSheet(f"color: {_muted_text_color(card.palette()).name()};")
    controls.addWidget(progress)
    controls.addStretch()

    quick = QPushButton("Quick start", card)
    learn = QPushButton("Learn the basics", card)
    skip = QPushButton("Skip", card)
    back = QPushButton("Back", card)
    nxt = QPushButton("Next", card)
    nxt.setDefault(True)
    for btn in (quick, learn, skip, back, nxt):
        controls.addWidget(btn)

    layout.addLayout(controls)
    return _CardWidgets(card, title, body, progress, quick, learn, skip, back, nxt)


# --------------------------------------------------------------------------- #
# Controller
# --------------------------------------------------------------------------- #

class Tutorial(QObject):
    """Drives a :class:`TutorialSpec` over the main window via an overlay."""

    def __init__(self, main_window: "MainWindow", spec: TutorialSpec) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.spec = spec
        self.index = 0
        self.overlay: Optional[TutorialOverlay] = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(400)
        self._poll_timer.timeout.connect(self._poll_completion)

    def start(self) -> None:
        if not self.spec.steps:
            return
        if self.spec.on_start is not None:
            self.spec.on_start(self.main_window)
        self.index = 0
        self.overlay = TutorialOverlay(self, self.main_window)
        # Follow the main window's size/position while the tour is running.
        self.main_window.installEventFilter(self)
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.show()
        self.overlay.raise_()
        # Take focus so the overlay's own Back/Next/arrow keys work. We
        # deliberately don't grabKeyboard(): that is an OS-level grab that eats
        # global shortcuts (alt-tab, the Super key, ...) far beyond this app.
        self.overlay.setFocus()
        self._show_step()

    def next(self) -> None:
        if self.index >= len(self.spec.steps) - 1:
            self._finish()
            return
        self.index += 1
        self._show_step()

    def prev(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._show_step()

    def skip(self) -> None:
        self._finish()

    def start_quick(self) -> None:
        """Switch from the welcome step into the condensed Quick Start tour."""
        self.spec = editor_steps(quick=True)
        self.index = 0
        self._show_step()

    def start_learn_basics(self) -> None:
        """Switch from the welcome step into the interactive lesson."""
        self.spec = learn_basics_steps()
        self.index = 0
        self._show_step()

    def reposition(self) -> None:
        """Re-resolve the current target and redraw (after a resize/move)."""
        if self.overlay is not None:
            self._show_step()

    # -- internals ----------------------------------------------------------- #

    def _show_step(self) -> None:
        if self.overlay is None:
            return
        step = self.spec.steps[self.index]
        if step.on_enter is not None:
            step.on_enter(self.main_window)
        can_advance = self._can_advance(step)
        if step.completion_check is not None and not can_advance:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()
        self.overlay.set_interactive(step.interactive)
        spotlight = self._resolve_spotlight(step)
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.set_step(step.title, step.text, spotlight,
                              self.index, len(self.spec.steps),
                              offer_quick=step.offer_quick,
                              offer_learn=step.offer_learn,
                              can_advance=can_advance)
        self.overlay.raise_()
        if step.interactive:
            self.main_window.setFocus()
        else:
            self.overlay.setFocus()

    def _can_advance(self, step: TutorialStep) -> bool:
        if step.completion_check is None:
            return True
        try:
            return step.completion_check(self.main_window)
        except Exception:
            logging.warning("Tutorial completion check for step %r failed; "
                            "keeping Next disabled.", step.title, exc_info=True)
            return False

    def _poll_completion(self) -> None:
        if self.overlay is None:
            return
        step = self.spec.steps[self.index]
        if step.completion_check is None:
            return
        can_advance = self._can_advance(step)
        self.overlay.set_next_enabled(can_advance)
        if can_advance:
            self._poll_timer.stop()

    def _resolve_spotlight(self, step: TutorialStep) -> Optional[QRect]:
        if step.target is None or self.overlay is None:
            return None
        try:
            widget = step.target(self.main_window)
        except Exception:
            # Fall back to a centred card, but surface the failure: a resolver
            # raising usually means a renamed attribute or an unexpected panel
            # type that should be fixed, not silently hidden.
            logging.warning("Tutorial target resolver for step %r failed; "
                            "showing a centred card instead.", step.title,
                            exc_info=True)
            widget = None
        if widget is None or not widget.isVisible():
            return None
        # Spotlight only the on-screen part of the widget: a widget collapsed or
        # clipped inside a splitter/scroll area is technically "visible" but its
        # occluded region shouldn't be highlighted. Fall back to a centred card
        # when too little of it is actually showing.
        visible = widget.visibleRegion().boundingRect()
        if visible.width() < _MIN_TARGET or visible.height() < _MIN_TARGET:
            return None
        top_left = widget.mapToGlobal(visible.topLeft())
        local = self.overlay.mapFromGlobal(top_left)
        rect = QRect(local, visible.size())
        rect = rect.adjusted(-_SPOTLIGHT_PAD, -_SPOTLIGHT_PAD,
                             _SPOTLIGHT_PAD, _SPOTLIGHT_PAD)
        # Clip to the overlay, and ignore targets scrolled entirely off-screen.
        rect = rect.intersected(self.overlay.rect())
        if rect.width() < _MIN_TARGET or rect.height() < _MIN_TARGET:
            return None
        return rect

    def _finish(self) -> None:
        if self.overlay is None:
            return  # already torn down (e.g. close + skip racing)
        self._poll_timer.stop()
        if self.spec.seen_key is not None:
            set_settings_value(self.spec.seen_key, True, bool)
        self.main_window.removeEventFilter(self)
        self.overlay.hide()
        self.overlay.deleteLater()
        self.overlay = None
        if self.main_window._active_tutorial is self:
            self.main_window._active_tutorial = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.main_window and self.overlay is not None:
            etype = event.type()
            if etype in (QEvent.Type.Resize, QEvent.Type.Move):
                self.overlay.setGeometry(self.main_window.rect())
                self.reposition()
            elif etype == QEvent.Type.Close:
                # Closing the window mid-tour counts as ending it, so it isn't
                # re-shown on the next launch.
                self._finish()
        return super().eventFilter(watched, event)


# --------------------------------------------------------------------------- #
# Public entry points (used by mainwindow.py / app.py)
# --------------------------------------------------------------------------- #
# A reference to the running tour is kept on the main window so it is not
# garbage-collected mid-tour and so only one runs at a time.

def _run(main_window: "MainWindow", spec: TutorialSpec) -> None:
    existing = main_window._active_tutorial
    if existing is not None:
        existing.skip()
    tutorial = Tutorial(main_window, spec)
    main_window._active_tutorial = tutorial
    tutorial.start()


def start_editor_tutorial(main_window: "MainWindow", quick: bool = False) -> None:
    """Start (or replay) the edit-mode tour. Used by the Help menu."""
    _run(main_window, editor_steps(quick=quick))


def start_proof_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the proof-mode tour."""
    _run(main_window, proof_steps())


def start_learn_basics_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the interactive 3 CNOTs → SWAP lesson."""
    _run(main_window, learn_basics_steps())


def maybe_start_first_run(main_window: "MainWindow") -> None:
    """Auto-start the editor tour on startup when enabled.

    Gated purely by the ``SHOW_ON_STARTUP`` preference (default on); the setting
    is left untouched, so the tour appears on every startup until the user turns
    it off under Preferences. This avoids the surprise of a tour vanishing for
    good just because the window was closed mid-way, and matches the usual
    "show on startup" behaviour. The Help menu is the way to replay it once.
    """
    if get_settings_value(SHOW_ON_STARTUP, bool, True):
        start_editor_tutorial(main_window)


def maybe_start_proof_tutorial(main_window: "MainWindow") -> None:
    """Auto-start the proof tour the first time the user enters proof mode."""
    if main_window._active_tutorial is not None:
        return
    if not get_settings_value(PROOF_TUTORIAL_SEEN, bool, False):
        start_proof_tutorial(main_window)
