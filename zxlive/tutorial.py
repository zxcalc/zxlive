# zxlive - An interactive tool for the ZX-calculus
# Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Self-contained interactive onboarding tutorial for ZXLive.

The entire feature lives here so that hooks elsewhere in the codebase remain
minimal — only ``mainwindow.py`` calling :func:`maybe_start_first_run` on
startup and :func:`maybe_start_proof_tutorial` when the user first enters
proof mode.

Tours defined
-------------
:func:`editor_steps`
    Guided walk through edit-mode tools and sidebars.  Auto-starts the first
    time ZXLive is launched; replayable from
    ``Help → Interactive Tutorial → Full Editor Tour``.
    ``quick=True`` drops educational paragraphs for returning users.

:func:`proof_steps`
    Walkthrough of the proof-mode UI (rewrites panel, magic wand, step list).
    Auto-starts the first time the user enters a derivation.

:func:`learn_basics_steps`
    Hands-on lesson: load the 3-CNOT circuit, enter proof mode, apply spider
    fusion / bialgebra / identity-removal to reach the SWAP diagram.

:func:`zz_gadget_steps`
    Interactive lesson on the ZZ(α) phase gadget: decompose it via the
    colour-change rule and Euler decomposition.

:func:`graph_state_steps`
    Lesson on three-qubit cluster / graph states and MBQC measurement patterns.

:func:`teleportation_steps`
    Lesson on quantum-state teleportation and the ZX "yanking" identity.

:func:`cnot_teleportation_steps`
    Lesson on CNOT-gate teleportation via a shared Bell pair.

:func:`magic_state_steps`
    Lesson on magic state injection (T-gate via |T⟩ state + Bell measurement).

How the overlay works
---------------------
A :class:`TutorialOverlay` child widget covers the entire main window.  In
*passive* steps it swallows mouse clicks outside the card so the UI stays
frozen.  In *interactive* steps (``TutorialStep.interactive = True``) it
becomes transparent and the user can work freely in the spotlighted area;
``Next`` stays disabled until an optional ``completion_check`` callable
returns ``True``, polled every 400 ms.

QSettings keys
--------------
``tutorial/show-on-startup``  (bool, default True)
    Gates the first-run editor tour.  Exposed as a checkbox in Preferences.
``tutorial/proof-seen``  (bool, default False)
    Set to ``True`` after the proof tour completes once.
``tutorial/zz-gadget-seen``  (bool, default False)
``tutorial/graph-state-seen``  (bool, default False)
``tutorial/teleportation-seen``  (bool, default False)
``tutorial/cnot-teleportation-seen``  (bool, default False)
``tutorial/magic-state-seen``  (bool, default False)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional, cast

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, QObject,
    QPoint, QRect, QRectF, QTimer, QVariantAnimation, Qt,
)
from PySide6.QtGui import (
    QColor, QKeyEvent, QMouseEvent, QPainter,
    QPainterPath, QPaintEvent, QPalette, QPen, QPolygon,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from .common import GraphT, get_settings_value, set_settings_value
from .construct import (
    construct_swap,
    construct_three_cnots,
    construct_zz_phase_gadget,
    construct_graph_state,
    construct_teleportation,
    construct_cnot_teleportation,
    construct_magic_state_injection,
)

if TYPE_CHECKING:
    from .mainwindow import MainWindow

# ── QSettings keys ─────────────────────────────────────────────────────────
SHOW_ON_STARTUP             = "tutorial/show-on-startup"
PROOF_TUTORIAL_SEEN         = "tutorial/proof-seen"
ZZ_GADGET_SEEN              = "tutorial/zz-gadget-seen"
GRAPH_STATE_SEEN            = "tutorial/graph-state-seen"
TELEPORTATION_SEEN          = "tutorial/teleportation-seen"
CNOT_TELEPORTATION_SEEN     = "tutorial/cnot-teleportation-seen"
MAGIC_STATE_SEEN            = "tutorial/magic-state-seen"

# ── Overlay visual constants ────────────────────────────────────────────────
_DIM_ALPHA             = 160   # 0-255 backdrop darkness in passive steps
_DIM_ALPHA_INTERACTIVE = 70    # lighter backdrop while the user works
_SPOTLIGHT_PAD         = 8     # px breathing-room around the spotlighted widget
_SPOTLIGHT_RADIUS      = 10    # px corner radius of the spotlight cut-out
_CARD_WIDTH            = 480   # px fixed width of the explanation card
_CARD_MARGIN           = 16    # px gap between spotlight edge and card
_BEAK                  = 11    # px triangular pointer from card to spotlight
_MIN_TARGET            = 6     # px below which a target is treated as invisible

# ── Type aliases ────────────────────────────────────────────────────────────
TargetResolver  = Callable[["MainWindow"], Optional[QWidget]]
CompletionCheck = Callable[["MainWindow"], bool]
StepHook        = Callable[["MainWindow"], None]


# ───────────────────────────────────────────────────────────────────────────
# Data structures
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class TutorialStep:
    """A single page of a tour.

    Attributes
    ----------
    title:
        Bold heading shown at the top of the card.
    text:
        Body text; a small subset of HTML supported by ``QLabel`` is accepted.
    target:
        ``(MainWindow) → QWidget | None`` — resolves which widget to spotlight.
        ``None`` → centred card with no spotlight.
    full_only:
        Omitted from the condensed *Quick Start* tour when ``True``.
    offer_quick:
        Marks the welcome step; shows the "Quick Start" button.
    offer_learn:
        Marks the welcome step; shows the "Learn the Basics" button.
    interactive:
        Lets mouse events through the overlay so the user can work in the
        spotlighted area.  The card itself always stays clickable.
    completion_check:
        If set, ``Next`` is kept disabled until this callable returns ``True``
        (polled every 400 ms).
    on_enter:
        Optional side-effect called when the tour arrives at this step.
    """
    title:            str
    text:             str
    target:           Optional[TargetResolver] = None
    full_only:        bool = False
    offer_quick:      bool = False
    offer_learn:      bool = False
    interactive:      bool = False
    completion_check: Optional[CompletionCheck] = None
    on_enter:         Optional[StepHook] = None


@dataclass
class TutorialSpec:
    """A complete tour: an ordered list of :class:`TutorialStep` objects.

    Attributes
    ----------
    steps:
        Ordered pages of the tour.
    seen_key:
        When set, this QSettings boolean key is flipped to ``True`` when the
        tour ends so it is not auto-shown again.
    on_start:
        Optional hook run once before the first step is displayed.
    """
    steps:    list[TutorialStep] = field(default_factory=list)
    seen_key: Optional[str]      = None
    on_start: Optional[Callable[["MainWindow"], None]] = None


# ───────────────────────────────────────────────────────────────────────────
# Target resolvers — defensive: missing attribute returns None (centred card)
# ───────────────────────────────────────────────────────────────────────────

def _edit_panel(mw: "MainWindow") -> Optional[QWidget]:
    from .edit_panel import GraphEditPanel
    return mw.active_panel if isinstance(mw.active_panel, GraphEditPanel) else None


def _proof_panel(mw: "MainWindow") -> Optional[QWidget]:
    from .proof_panel import ProofPanel
    return mw.active_panel if isinstance(mw.active_panel, ProofPanel) else None


def _attr(mw: "MainWindow",
          panel_fn: Callable[["MainWindow"], Optional[QWidget]],
          name: str) -> Optional[QWidget]:
    panel = panel_fn(mw)
    if panel is None:
        return None
    widget = getattr(panel, name, None)
    return widget if isinstance(widget, QWidget) else None


def _toolbar_button(panel: Optional[QWidget], *needles: str) -> Optional[QWidget]:
    """Return the first toolbar QToolButton whose tooltip contains every needle."""
    toolbar = getattr(panel, "toolbar", None)
    if toolbar is None:
        return None
    for btn in toolbar.findChildren(QToolButton):
        tip = btn.toolTip().lower()
        if all(n.lower() in tip for n in needles):
            return btn
    return None


# ───────────────────────────────────────────────────────────────────────────
# Graph helpers for completion checks
# ───────────────────────────────────────────────────────────────────────────

def _active_graph(mw: "MainWindow") -> Optional[GraphT]:
    panel = mw.active_panel
    scene = getattr(panel, "graph_scene", None)
    return cast(GraphT, scene.g) if scene is not None else None


def _graphs_match_semantics(a: Optional[GraphT], b: Optional[GraphT]) -> bool:
    """True when two diagrams represent the same linear map (matrix equality)."""
    if a is None or b is None:
        return False
    try:
        import numpy as np
        return bool(np.allclose(a.to_matrix(), b.to_matrix(), atol=1e-6))
    except Exception:
        return False


def _graphs_match_structure(a: Optional[GraphT], b: Optional[GraphT]) -> bool:
    """True when two diagrams are isomorphic up to vertex layout."""
    if a is None or b is None:
        return False
    try:
        from networkx.algorithms.isomorphism import (
            GraphMatcher, categorical_edge_match, categorical_node_match,
        )
        from .custom_rule import to_networkx
        Ga, Gb = to_networkx(a), to_networkx(b)
        nm = categorical_node_match(["type", "phase", "boundary_index"], [1, 0, ""])
        em = categorical_edge_match("type", 1)
        return bool(GraphMatcher(Ga, Gb, nm, em).is_isomorphic())
    except Exception:
        return False


def _matches_swap(mw: "MainWindow") -> bool:
    g   = _active_graph(mw)
    ref = construct_swap()
    return _graphs_match_structure(g, ref) or _graphs_match_semantics(g, ref)


def _in_proof_mode(mw: "MainWindow") -> bool:
    from .proof_panel import ProofPanel
    return isinstance(mw.active_panel, ProofPanel)


def _proof_step_count(mw: "MainWindow") -> int:
    from .proof_panel import ProofPanel
    if not isinstance(mw.active_panel, ProofPanel):
        return 0
    return len(mw.active_panel.proof_model.steps)


def _ensure_edit_panel(mw: "MainWindow") -> None:
    """Ensure the active panel is a graph-edit panel; open a new one if not."""
    from .edit_panel import GraphEditPanel
    if not isinstance(mw.active_panel, GraphEditPanel):
        mw.open_demo_graph()


def _replace_graph(mw: "MainWindow", g: GraphT) -> None:
    """Replace the active edit panel's graph, opening a new panel if needed."""
    from .edit_panel import GraphEditPanel
    _ensure_edit_panel(mw)
    panel = mw.active_panel
    if isinstance(panel, GraphEditPanel):
        panel.replace_graph(g)


def _load_three_cnots(mw: "MainWindow")       -> None: _replace_graph(mw, construct_three_cnots())
def _load_zz_gadget(mw: "MainWindow")         -> None: _replace_graph(mw, construct_zz_phase_gadget())
def _load_graph_state(mw: "MainWindow")       -> None: _replace_graph(mw, construct_graph_state())
def _load_teleportation(mw: "MainWindow")     -> None: _replace_graph(mw, construct_teleportation())
def _load_cnot_teleport(mw: "MainWindow")     -> None: _replace_graph(mw, construct_cnot_teleportation())
def _load_magic_state(mw: "MainWindow")       -> None: _replace_graph(mw, construct_magic_state_injection())


# ───────────────────────────────────────────────────────────────────────────
# Tour definitions
# ───────────────────────────────────────────────────────────────────────────

def editor_steps(quick: bool = False) -> TutorialSpec:
    """Tour through edit mode.

    ``quick=True`` drops educational / conceptual steps, giving returning users
    a fast functional orientation without ZX-calculus background paragraphs.
    """

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def toolbar(mw: "MainWindow") -> Optional[QWidget]:
        p = _edit_panel(mw)
        return getattr(p, "toolbar", None) if p else None

    def add_vertex_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _toolbar_button(_edit_panel(mw), "add vertex")

    def add_edge_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _toolbar_button(_edit_panel(mw), "add edge")

    def select_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _toolbar_button(_edit_panel(mw), "select")

    def vertices_sidebar(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "vertex_list")

    def edges_sidebar(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "edge_list")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    steps: list[TutorialStep] = [

        # ── Welcome ──────────────────────────────────────────────────────
        TutorialStep(
            "Welcome to ZXLive!",
            "ZXLive is an interactive tool for the <b>ZX-calculus</b> — a "
            "graphical language for quantum circuits and linear maps.<br><br>"
            "Choose a path, or <b>Skip</b> to jump straight in.<br><br>"
            "<b>Full Tour</b> — guided walk through the UI with ZX-calculus "
            "context (you are here).<br>"
            "<b>Quick Start</b> — short functional overview for returning "
            "users (skips theory).<br>"
            "<b>Learn the Basics</b> — hands-on: rewrite 3 CNOTs to a SWAP.",
            offer_quick=True,
            offer_learn=True,
        ),

        # ── ZX-calculus primer ───────────────────────────────────────────
        TutorialStep(
            "What is the ZX-calculus?",
            "The ZX-calculus is a <b>complete graphical language</b> for "
            "qubit quantum mechanics. Every ZX diagram represents a linear "
            "map, and two diagrams are provably equal if and only if one can "
            "be transformed into the other by a finite set of local "
            "<i>rewrite rules</i>.<br><br>"
            "Practical uses include:<br>"
            "• <b>Circuit optimisation</b> — reduce gate counts automatically.<br>"
            "• <b>Compilation</b> — translate between gate sets.<br>"
            "• <b>Error correction</b> — analyse stabiliser codes.<br>"
            "• <b>MBQC</b> — verify measurement-based quantum protocols.",
            canvas,
            full_only=True,
        ),

        # ── Canvas ───────────────────────────────────────────────────────
        TutorialStep(
            "The canvas",
            "This is where your ZX diagram lives.<br><br>"
            "• <b>Pan</b> — drag the background<br>"
            "• <b>Zoom</b> — scroll wheel (or pinch on trackpad)<br>"
            "• <b>Select</b> — click a vertex/edge or rubber-band drag<br>"
            "• <b>Fit view</b> — press <kbd>C</kbd> to re-centre<br><br>"
            "The diagram currently shown is 3 CNOTs — this simplifies to a "
            "SWAP and is the example used in the <i>Learn the Basics</i> lesson.",
            canvas,
        ),

        # ── Toolbar overview ─────────────────────────────────────────────
        TutorialStep(
            "The toolbar",
            "The toolbar spans the top of the canvas. The first group holds "
            "the three editing modes: <b>Select (S)</b>, <b>Add Vertex (V)</b> "
            "and <b>Add Edge (E)</b>. Further buttons handle undo/redo, zoom, "
            "and the <b>Start Derivation</b> button that enters proof mode.",
            toolbar,
        ),

        # ── Select tool ──────────────────────────────────────────────────
        TutorialStep(
            "Select tool  (S)",
            "In <b>Select</b> mode:<br>"
            "• Click a vertex or edge to select it.<br>"
            "• Drag to rubber-band-select a region.<br>"
            "• Drag selected vertices to reposition them (free — no rewrite step).<br>"
            "• Hold <kbd>Shift</kbd> to extend an existing selection.<br>"
            "• <kbd>Ctrl+A</kbd> selects everything; <kbd>Ctrl+D</kbd> deselects.",
            select_btn,
            full_only=True,
        ),

        # ── Add Vertex tool ──────────────────────────────────────────────
        TutorialStep(
            "Add Vertex tool  (V)",
            "With <b>Add Vertex</b> active, click anywhere on the canvas to "
            "place a new spider. The type of spider placed matches the "
            "currently selected type in the <i>Vertices</i> sidebar.<br><br>"
            "In ZX-calculus, <b>Z spiders</b> (green) and <b>X spiders</b> "
            "(red) each carry a phase angle and can have any number of legs. "
            "A phaseless Z spider with two legs is a plain wire.",
            add_vertex_btn,
        ),

        # ── Add Edge tool ─────────────────────────────────────────────────
        TutorialStep(
            "Add Edge tool  (E)",
            "With <b>Add Edge</b> active, drag from one vertex to another to "
            "connect them. The edge type is set in the <i>Edges</i> sidebar:<br><br>"
            "• <b>Simple wire</b> — a plain quantum wire.<br>"
            "• <b>Hadamard edge</b> — drawn as a yellow box; equivalent to "
            "inserting an H gate on the wire. Hadamard edges allow Z and X "
            "spiders to be freely interchanged via the colour-change rule.",
            add_edge_btn,
        ),

        # ── Vertices sidebar ─────────────────────────────────────────────
        TutorialStep(
            "Vertices sidebar",
            "Click a type to make new vertices use that type. "
            "<b>Double-click</b> a type to also change any currently-selected "
            "vertices on the canvas.<br><br>"
            "Available types:<br>"
            "• <b>Z spider</b> (green) — the primary building block.<br>"
            "• <b>X spider</b> (red) — dual to Z via Hadamard.<br>"
            "• <b>Hadamard box</b> (H) — explicit H-gate node.<br>"
            "• <b>W node</b> — used in W-calculus extensions.<br>"
            "• <b>Boundary</b> — marks input and output wires.",
            vertices_sidebar,
            full_only=True,
        ),

        # ── Edges sidebar ─────────────────────────────────────────────────
        TutorialStep(
            "Edges sidebar",
            "Choose between a <b>simple wire</b> and a <b>Hadamard edge</b> "
            "before drawing your next connection. Double-clicking a type here "
            "toggles any currently-selected edges between the two styles.<br><br>"
            "<i>Tip:</i> a diagram whose internal edges are all Hadamard edges "
            "represents a <b>graph state</b> — a key resource for MBQC and "
            "quantum error correction.",
            edges_sidebar,
            full_only=True,
        ),

        # ── Setting a phase ──────────────────────────────────────────────
        TutorialStep(
            "Setting a spider's phase",
            "<b>Double-click</b> any Z or X spider to open the phase editor "
            "and type its rotation angle as a multiple of π.<br><br>"
            "Common values:<br>"
            "• <code>0</code> — identity (no rotation)<br>"
            "• <code>1/4</code> — T gate phase (π/4)<br>"
            "• <code>1/2</code> — S gate phase (π/2)<br>"
            "• <code>1</code> — Pauli Z or X rotation (π)<br><br>"
            "Symbolic parameters (e.g. <code>a</code>, <code>2*b+1</code>) "
            "are also supported for parametric circuits.",
            canvas,
            full_only=True,
        ),

        # ── Core rewrite rules ───────────────────────────────────────────
        TutorialStep(
            "Core rewrite rules",
            "Four rules underpin most ZX proofs:<br><br>"
            "• <b>Spider fusion</b> — two same-colour connected spiders merge; "
            "phases add. Z(α)–Z(β) → Z(α+β).<br>"
            "• <b>Identity removal</b> — a degree-2 phaseless spider is a "
            "plain wire; delete it.<br>"
            "• <b>Bialgebra</b> — a Z spider \"copies\" across the legs of an "
            "X spider (and vice versa), introducing crossing spiders.<br>"
            "• <b>Colour change</b> — surround every leg with H to flip "
            "Z↔X (or vice versa).",
            canvas,
            full_only=True,
        ),

        # ── Start Derivation ─────────────────────────────────────────────
        TutorialStep(
            "Start Derivation",
            "Once your diagram is ready, click <b>Start Derivation</b> to "
            "enter <i>proof mode</i>.<br><br>"
            "Every rewrite applied in proof mode is <i>sound</i>: the "
            "diagram's linear-map interpretation is preserved at every step. "
            "A dedicated proof-mode tour launches the first time you do this.",
            start_derivation_btn,
        ),

        # ── Wrap-up ──────────────────────────────────────────────────────
        TutorialStep(
            "You're all set!",
            "That covers the editor. Replay this tour any time from "
            "<b>Help → Interactive Tutorial → Orientation Tours → Full Editor "
            "Tour</b>.<br><br>"
            "Ready for hands-on practice? Try "
            "<b>Help → Interactive Tutorial → Interactive Lessons → "
            "Learn the Basics</b> to prove that 3 CNOTs equal a SWAP.<br><br>"
            "Happy rewriting! 🕸️",
        ),
    ]

    if quick:
        steps = [s for s in steps if not (s.full_only or s.offer_quick)]

    return TutorialSpec(steps)


# ───────────────────────────────────────────────────────────────────────────

def proof_steps() -> TutorialSpec:
    """Tour shown automatically the first time the user enters proof mode."""

    def rewrites_panel(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def magic_wand_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "magic_wand")

    def identity_choice(mw: "MainWindow") -> Optional[QWidget]:
        panel   = _proof_panel(mw)
        choices = getattr(panel, "identity_choice", None) if panel else None
        if choices:
            first = choices[0]
            return first if isinstance(first, QWidget) else None
        return None

    def step_view(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "Welcome to proof mode!",
            "You are now in <b>proof mode</b>. Every rewrite you apply is "
            "<i>sound</i>: the diagram's linear-map interpretation is "
            "guaranteed to be preserved at every step.<br><br>"
            "The original diagram is kept; you can navigate back to any "
            "earlier state using the step list on the right.",
        ),

        TutorialStep(
            "Rewrites panel",
            "This panel lists the ZX-calculus rules that match your current "
            "selection.<br><br>"
            "Select part of the diagram (or nothing to match the whole "
            "diagram), then <b>double-click a rule</b> to apply it. "
            "Rules that do not match are greyed out.",
            rewrites_panel,
        ),

        TutorialStep(
            "The magic wand  (W)",
            "The <b>magic wand</b> applies common rewrites by gesture rather "
            "than via the panel:<br><br>"
            "• <b>Drag through a spider</b> — unfuse it (split into two).<br>"
            "• <b>Drag through a wire</b> — insert a pair of identity spiders.<br>"
            "• <b>Drag across two parallel edges</b> — cancel them (Hopf law).<br>"
            "• <b>Drag through a degree-2 phaseless spider</b> — remove it.",
            magic_wand_btn,
        ),

        TutorialStep(
            "Identity spider colour",
            "When the magic wand inserts a new identity spider, these buttons "
            "control whether it is a <b>Z spider</b> (green) or an "
            "<b>X spider</b> (red). Toggle before dragging when you need a "
            "specific colour for the next rewrite.",
            identity_choice,
        ),

        TutorialStep(
            "The proof canvas",
            "The canvas looks the same as the editor, but every structural "
            "change records a rewrite step.<br><br>"
            "You can still pan, zoom and select normally. Dragging selected "
            "vertices to rearrange their layout does <i>not</i> add a step — "
            "layout changes are always free.",
            proof_canvas,
        ),

        TutorialStep(
            "Proof step list",
            "Every rewrite is appended here with the rule name and a thumbnail "
            "of the resulting diagram. Click any entry to jump back to that "
            "point in the derivation — invaluable for reviewing or undoing part "
            "of a proof without losing the rest.",
            step_view,
        ),

        TutorialStep(
            "Exporting your proof",
            "When you are done, export from the <b>File</b> menu:<br><br>"
            "• <b>Export proof to TikZ</b> — single <code>.tikz</code> file "
            "with all steps, ready for LaTeX.<br>"
            "• <b>Export proof steps to TikZ files</b> — one file per step "
            "for Beamer slides.<br>"
            "• <b>Export proof to GIF</b> — animated rewrite sequence for "
            "talks or documentation.<br><br>"
            "You can also save the proof as a reusable custom rule via "
            "<b>Rewrites → Save proof as a rewrite</b>.",
        ),

        TutorialStep(
            "Go forth and prove!",
            "That is everything you need to know about proof mode. Replay "
            "this tour any time from "
            "<b>Help → Interactive Tutorial → Orientation Tours → "
            "Proof Mode Tour</b>.<br><br>"
            "Happy rewriting! 🕸️",
        ),
    ]

    return TutorialSpec(steps, seen_key=PROOF_TUTORIAL_SEEN)


# ───────────────────────────────────────────────────────────────────────────

def learn_basics_steps() -> TutorialSpec:
    """Interactive lesson: 3 CNOTs → SWAP via ZX-calculus rewrites."""

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def proof_magic_wand(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "magic_wand")

    def step_list(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "Learn the basics: 3 CNOTs = SWAP",
            "In this lesson you will prove the identity<br><br>"
            "<center><b>CNOT · CNOT<sub>rev</sub> · CNOT  ≡  SWAP</b></center><br>"
            "using the ZX-calculus. This is one of the most elegant results "
            "in the calculus: three quantum gates collapse into a single SWAP "
            "with just a handful of local rewrites — no matrix arithmetic "
            "required.<br><br>"
            "The 3-CNOT diagram will be loaded automatically. Follow the "
            "spotlights — <b>Next</b> unlocks once each task is complete.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The ZX picture of a CNOT",
            "In ZX-calculus a CNOT gate is drawn as a "
            "<b>Z spider</b> (green) on the <i>control</i> wire connected by "
            "a plain wire to an <b>X spider</b> (red) on the <i>target</i> "
            "wire.<br><br>"
            "Three alternating CNOTs (control-top, control-bottom, "
            "control-top) give the diagram now on your canvas. "
            "Notice the symmetric pattern: the middle CNOT is reversed.",
            canvas,
            on_enter=_load_three_cnots,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b> to enter proof mode. ZXLive will "
            "track every rewrite and guarantee that the diagram's linear-map "
            "interpretation is preserved at every step.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Step 1 — apply the bialgebra rule",
            "Select a <b>Z spider and a neighbouring X spider</b> "
            "(hold <kbd>Shift</kbd> to add the second to the selection), then "
            "double-click <b>bialgebra</b> in the rewrites panel.<br><br>"
            "The bialgebra rule lets a Z spider \"copy\" itself across the legs "
            "of an X spider, introducing new spiders at each crossing. This "
            "is the key step that untangles the three-CNOT structure.",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Step 2 — fuse same-colour spiders",
            "After bialgebra you will see new Z–Z and X–X neighbours. "
            "Select <b>two adjacent same-colour spiders</b> and double-click "
            "<b>fuse spiders</b> in the rewrites panel (or drag the "
            "<b>magic wand</b> from one spider to the other).<br><br>"
            "<i>Spider fusion</i>: two connected same-colour spiders merge "
            "into one and their phases add. Since all spiders here have zero "
            "phase, the fused spider also has zero phase.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 2,
        ),

        TutorialStep(
            "Step 3 — remove identity spiders",
            "A zero-phase degree-2 spider is a plain wire — it contributes "
            "nothing mathematically and can be deleted. Select such a spider "
            "and double-click <b>remove identity</b> in the rewrites panel, "
            "<i>or</i> drag the <b>magic wand</b> through it.<br><br>"
            "Tip: the magic wand is faster — just draw a stroke across the spider.",
            proof_magic_wand,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 3,
        ),

        TutorialStep(
            "Keep simplifying",
            "Continue fusing same-colour spiders and removing zero-phase "
            "degree-2 spiders until the diagram reduces to the compact "
            "<b>SWAP</b>: two crossing wires with no spiders.<br><br>"
            "The step list on the right records every move — click any entry "
            "to revisit that stage of the proof.",
            step_list,
            interactive=True,
            completion_check=_matches_swap,
        ),

        TutorialStep(
            "Congratulations! 🎉",
            "You have just proved that three alternating CNOTs equal a SWAP "
            "using only local, sound ZX rewrites — no matrices involved.<br><br>"
            "What to try next:<br>"
            "• <b>Export the proof to TikZ</b> (File menu) for a paper.<br>"
            "• Try the <b>ZZ Phase Gadget</b> lesson in the Tutorial menu.<br>"
            "• Explore <b>Teleportation</b> or <b>Graph States</b>.<br>"
            "• Build your own rewrite rules via "
            "<b>Rewrites → New rewrite</b>.",
        ),
    ]

    return TutorialSpec(steps, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────

def zz_gadget_steps() -> TutorialSpec:
    """Interactive lesson: ZZ(α) phase gadget structure and simplification."""

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "ZZ(α) phase gadget",
            "A <b>ZZ(α) phase gadget</b> applies the diagonal unitary "
            "e<sup>iαZ⊗Z</sup> to a two-qubit system. It appears as a "
            "primitive in:<br><br>"
            "• <b>QAOA</b> — the problem Hamiltonian layer.<br>"
            "• <b>VQE</b> — efficient parameterised ansätze.<br>"
            "• <b>Trotterisation</b> — simulation of Pauli Hamiltonians.<br><br>"
            "In ZX-calculus the gadget is a single Z(α) spider connected to "
            "both qubit wires via Hadamard edges. The diagram will be loaded "
            "for you automatically.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The gadget structure",
            "Look at the diagram now on your canvas. You should see:<br><br>"
            "• Two horizontal qubit wires running left-to-right.<br>"
            "• A central <b>Z(α) spider</b> (green, phase α) hanging "
            "vertically between the two wires.<br>"
            "• <b>Hadamard edges</b> (yellow boxes) connecting the central "
            "spider to each wire.<br><br>"
            "This is the standard <i>phase-gadget</i> form: one spider carries "
            "the entire entangling rotation.",
            canvas,
            on_enter=_load_zz_gadget,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b> to begin rewriting. We will use "
            "the <b>colour-change</b> rule to show that the same gadget can "
            "be expressed using X spiders instead of Z spiders — useful when "
            "compiling to hardware with a preferred basis.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Apply the colour-change rule",
            "Select the central Z(α) spider and double-click "
            "<b>colour change</b> in the rewrites panel.<br><br>"
            "The colour-change rule states: if every edge incident to a "
            "spider is a Hadamard edge, flipping the spider's colour (Z↔X) "
            "gives an equal diagram. This is because H·Z·H = X.",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Observe and simplify",
            "After the colour change the central spider is now an <b>X(α) "
            "spider</b> connected to both wires by Hadamard edges — this is "
            "the XX(α) gadget form, equivalent to e<sup>iαX⊗X</sup>.<br><br>"
            "Try applying <b>spider fusion</b> or <b>Euler decomposition</b> "
            "to continue simplifying. Each step is recorded in the step list.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 2,
        ),

        TutorialStep(
            "Phase gadgets in practice",
            "Well done! You have seen how a ZZ(α) gadget is represented and "
            "how the colour-change rule switches between ZZ and XX forms.<br><br>"
            "In practice ZXLive can automatically simplify networks of phase "
            "gadgets to a minimum number of two-qubit gates using the "
            "<b>Phase Gadget Optimiser</b> (Rewrites menu).<br><br>"
            "Next steps:<br>"
            "• Try the <b>Graph State</b> lesson for another gadget family.<br>"
            "• Explore <b>Teleportation</b> to see entanglement transfer.",
        ),
    ]

    return TutorialSpec(steps, seen_key=ZZ_GADGET_SEEN, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────

def graph_state_steps() -> TutorialSpec:
    """Interactive lesson: three-qubit cluster state and MBQC."""

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "Graph states and MBQC",
            "A <b>graph state</b> |G⟩ is a stabiliser state built from a "
            "graph G: start with |+⟩<sup>⊗n</sup> and apply a CZ gate for "
            "every edge.<br><br>"
            "In ZX-calculus a graph state is elegant: a collection of "
            "<b>Z spiders</b> (one per qubit) connected by <b>Hadamard "
            "edges</b> matching G's adjacency.<br><br>"
            "Graph states are the resource for <b>measurement-based quantum "
            "computation (MBQC)</b>: single-qubit measurements drive the "
            "computation and Pauli corrections undo the randomness.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The three-qubit cluster state",
            "A three-qubit linear cluster state has been loaded. You should "
            "see three Z spiders in a line, connected pairwise by Hadamard "
            "edges (yellow boxes).<br><br>"
            "Each Hadamard edge represents a CZ gate applied between two "
            "neighbouring qubits. The resulting state is entangled across "
            "all three qubits.",
            canvas,
            on_enter=_load_graph_state,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b> to begin rewriting. We will "
            "simulate a <i>measurement</i> on qubit 0 by applying spider "
            "fusion to collapse it into the graph.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Fuse the boundary into qubit 0",
            "Select the input boundary spider and the qubit-0 Z spider, then "
            "apply <b>fuse spiders</b>.<br><br>"
            "In MBQC terms, fusing the boundary corresponds to \"feeding\" the "
            "input state into the cluster. The fused spider now carries the "
            "combined phase of the input and the cluster node.",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Observe the correction structure",
            "After fusion, the Hadamard edges propagate the phase into "
            "neighbouring spiders. Continue applying <b>colour change</b> "
            "and <b>identity removal</b> to simplify the remaining "
            "structure.<br><br>"
            "Each step corresponds to a physical qubit being measured and "
            "its outcome fed forward as a Pauli correction.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 3,
        ),

        TutorialStep(
            "Graph states in ZX — summary",
            "You have seen how graph states arise naturally in ZX and how "
            "their measurement patterns simplify through local rewrites — "
            "exactly mirroring the physical process of MBQC.<br><br>"
            "Key takeaways:<br>"
            "• Graph state = Z spiders + Hadamard edges.<br>"
            "• Measurement = colour change + spider fusion + identity removal.<br>"
            "• Pauli corrections = π-phase spiders absorbed by fusion.<br><br>"
            "Try <b>Teleportation</b> next — the simplest MBQC protocol!",
        ),
    ]

    return TutorialSpec(steps, seen_key=GRAPH_STATE_SEEN, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────

def teleportation_steps() -> TutorialSpec:
    """Interactive lesson: quantum state teleportation and the yanking identity."""

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    def step_list(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "Quantum state teleportation",
            "Teleportation transfers an unknown state |ψ⟩ from Alice to Bob "
            "using a pre-shared Bell pair and two classical bits.<br><br>"
            "In ZX-calculus the entire protocol is just a bent wire — the "
            "<b>yanking identity</b> — which means classical corrections "
            "always perfectly undo measurement randomness.<br><br>"
            "This is one of the most striking demonstrations of diagrammatic "
            "rewriting: the proof takes fewer steps than a matrix calculation.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The teleportation diagram",
            "The teleportation circuit has been loaded. Identify the three "
            "components:<br><br>"
            "• <b>Wire 0</b> — Alice's source qubit carrying |ψ⟩.<br>"
            "• <b>Wires 1–2</b> — the shared Bell pair (entangled resource).<br>"
            "• <b>Z spider with π phase</b> — the Z correction Bob applies.<br>"
            "• <b>X spider with π phase</b> — the X correction Bob applies.<br><br>"
            "The Hadamard edges (yellow boxes) indicate the basis change in "
            "Alice's Bell measurement.",
            canvas,
            on_enter=_load_teleportation,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b>. We will apply spider fusion and "
            "the yanking identity to collapse the three-wire protocol into a "
            "single bent wire — proving Bob's qubit receives exactly |ψ⟩.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Fuse the Bell pair spiders",
            "Select the two Z spiders that form the Bell pair creation and "
            "the Bell measurement, then apply <b>fuse spiders</b>.<br><br>"
            "Fusion here represents that the Bell pair and Bell measurement "
            "'cancel' each other: creating then measuring in the Bell basis "
            "is effectively a wire (up to classical outcomes).",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Apply the yanking lemma",
            "After the Bell-pair fusion you should see a structure that looks "
            "like a cup–cap pair (a bent wire looping back). Select the "
            "relevant spiders and apply <b>identity removal</b> or "
            "<b>fuse spiders</b> until corrections absorb into the wire.<br><br>"
            "The π-phase X and Z spiders representing corrections cancel in "
            "pairs: X(π)·X(π) = I and Z(π)·Z(π) = I.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 3,
        ),

        TutorialStep(
            "The yanking identity",
            "Continue simplifying until the diagram reduces to a single "
            "straight wire from input to output. This is the "
            "<b>yanking identity</b>: unfolding a cup–cap pair gives a plain "
            "wire.<br><br>"
            "Physically this proves that teleportation is perfect: no matter "
            "what Bell-measurement outcome Alice gets, Bob's qubit ends up in "
            "exactly state |ψ⟩ after his corrections.",
            step_list,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 5,
        ),

        TutorialStep(
            "Teleportation — summary",
            "Excellent work! You have verified quantum state teleportation "
            "using nothing more than spider fusion and identity removal.<br><br>"
            "Key ideas in ZX:<br>"
            "• Bell pair = cup (bent wire heading right to left).<br>"
            "• Bell measurement = cap (bent wire heading left to right).<br>"
            "• Cup · cap = identity wire (yanking lemma).<br>"
            "• Classical corrections = π-phase spiders that cancel by fusion.<br><br>"
            "Try <b>CNOT-Gate Teleportation</b> next — the same ideas, "
            "but transferring an entire two-qubit gate!",
        ),
    ]

    return TutorialSpec(steps, seen_key=TELEPORTATION_SEEN, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────

def cnot_teleportation_steps() -> TutorialSpec:
    """Interactive lesson: CNOT-gate teleportation via a shared Bell pair.

    Teaches:
    - Gate teleportation as a "copy" of the CNOT structure.
    - Bialgebra rule in a physically motivated setting.
    - Connection to fault-tolerant computation (magic state injection).
    """

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    def step_list(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "CNOT-gate teleportation",
            "<b>Gate teleportation</b> implements a logical two-qubit gate "
            "between non-adjacent qubits using only local operations and a "
            "pre-shared entangled resource.<br><br>"
            "For a CNOT the resource is a Bell pair |Φ+⟩ = (|00⟩+|11⟩)/√2. "
            "After local Bell measurements and classical communication, the "
            "effect of a CNOT is transferred to the logical qubits.<br><br>"
            "In ZX-calculus this simplifies via the <b>bialgebra rule</b>: "
            "the CNOT's copy structure exactly matches the Z–X spider law.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The CNOT teleportation diagram",
            "The CNOT teleportation circuit has been loaded. You should see "
            "four wires:<br><br>"
            "• <b>Wire 0</b> — logical control qubit.<br>"
            "• <b>Wires 1–2</b> — two resource qubits (Bell pair).<br>"
            "• <b>Wire 3</b> — logical target qubit.<br><br>"
            "The central Z–X pair connected by a plain wire is the CNOT "
            "gate being teleported. The surrounding cups and caps form the "
            "Bell pair resource.",
            canvas,
            on_enter=_load_cnot_teleport,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b>. We will apply the bialgebra "
            "rule and spider fusion to collapse the four-wire circuit into "
            "a single two-qubit CNOT on the logical wires.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Step 1 — apply bialgebra",
            "Select a <b>Z spider and a neighbouring X spider</b> on the "
            "resource wires, then double-click <b>bialgebra</b> in the "
            "rewrites panel.<br><br>"
            "The bialgebra rule is the heart of gate teleportation: it "
            "shows that the CNOT structure \"copies\" through the Bell pair "
            "and appears on the logical wires.",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Step 2 — fuse and clean up",
            "After bialgebra, apply <b>spider fusion</b> on same-colour "
            "spiders that are now adjacent, and <b>identity removal</b> on "
            "any zero-phase degree-2 spiders.<br><br>"
            "Each fusion step eliminates a resource qubit and brings the "
            "diagram closer to the compact logical CNOT.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 2,
        ),

        TutorialStep(
            "Keep simplifying",
            "Continue applying fusion and identity removal. When fully "
            "simplified the resource wires disappear, leaving a single "
            "Z–X pair on the logical wires — exactly the original CNOT.<br><br>"
            "The step list on the right shows the complete derivation.",
            step_list,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 4,
        ),

        TutorialStep(
            "CNOT teleportation — summary",
            "You have proved CNOT-gate teleportation in ZX-calculus!<br><br>"
            "Key ideas:<br>"
            "• The Bell pair resource encodes a CNOT via the bialgebra rule.<br>"
            "• Bell measurements on resource qubits + Pauli corrections "
            "transfer the gate to logical qubits.<br>"
            "• The bialgebra rule is the same algebraic law underlying "
            "spider fusion — ZX makes the connection explicit.<br><br>"
            "Try <b>Magic State Injection</b> next to see how non-Clifford "
            "gates can be implemented fault-tolerantly.",
        ),
    ]

    return TutorialSpec(
        steps, seen_key=CNOT_TELEPORTATION_SEEN, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────

def magic_state_steps() -> TutorialSpec:
    """Interactive lesson: magic state injection — the T gate via |T⟩.

    Teaches:
    - Why magic states are needed (T gate is non-Clifford / non-stabiliser).
    - The injection circuit in ZX: |T⟩ = T|+⟩, Bell measurement, S correction.
    - How phase kickback (T-gate phase = π/4 spider) feeds into the logical wire.
    - Connection to fault-tolerant universal quantum computation.
    """

    def canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def proof_rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def start_derivation_btn(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    def proof_canvas(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "graph_view")

    steps: list[TutorialStep] = [

        TutorialStep(
            "Magic state injection",
            "Clifford gates alone are not universal for quantum computing — "
            "they can be efficiently simulated classically (Gottesman-Knill "
            "theorem). The <b>T gate</b> (phase π/4) makes the gate set "
            "universal but is expensive in fault-tolerant architectures.<br><br>"
            "<b>Magic state injection</b> is the standard technique: prepare "
            "a single-qubit state |T⟩ = T|+⟩ offline (\"distil\" it), then "
            "consume it with Clifford operations to apply a T gate "
            "fault-tolerantly.<br><br>"
            "In ZX-calculus the injection circuit is a π/4 Z spider linked "
            "to the logical wire via a Bell measurement.",
            on_enter=_ensure_edit_panel,
        ),

        TutorialStep(
            "The injection diagram",
            "The magic state injection circuit has been loaded. You should "
            "see:<br><br>"
            "• A horizontal <b>logical qubit wire</b> (top).<br>"
            "• A <b>Z(π/4) spider</b> — the magic state |T⟩.<br>"
            "• A <b>Bell measurement</b> (CNOT + H) consuming the magic "
            "state and kicking the T-gate phase into the logical qubit.<br>"
            "• An <b>S-gate correction</b> (Z(π/2) spider) conditioned on "
            "the measurement outcome.<br><br>"
            "The key ZX insight: the T gate's phase lives on a single spider "
            "— no ancilla network needed.",
            canvas,
            on_enter=_load_magic_state,
        ),

        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b>. We will use spider fusion and "
            "the phase-kickback identity to show that consuming |T⟩ applies "
            "a T gate (plus an S correction) to the logical qubit.",
            start_derivation_btn,
            interactive=True,
            completion_check=_in_proof_mode,
        ),

        TutorialStep(
            "Step 1 — phase kickback via spider fusion",
            "Select the <b>Z(π/4) magic-state spider</b> and the "
            "neighbouring spider on the logical wire, then apply "
            "<b>fuse spiders</b>.<br><br>"
            "Fusion transfers the π/4 phase onto the logical wire — this is "
            "phase kickback in ZX form. The π/4 spider on the logical qubit "
            "is exactly the T gate.",
            proof_rewrites,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 1,
        ),

        TutorialStep(
            "Step 2 — absorb the S correction",
            "After kickback you will see an <b>S-gate spider (Z(π/2))</b> "
            "adjacent to the newly created T-gate spider. Apply "
            "<b>fuse spiders</b> to merge them.<br><br>"
            "Fusing Z(π/4) and Z(π/2) gives Z(3π/4). Depending on the "
            "measurement outcome you will need either this angle or just "
            "Z(π/4). In both cases the result is a rotation local to the "
            "logical qubit — the injection has succeeded.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 2,
        ),

        TutorialStep(
            "Step 3 — remove identity spiders",
            "Any zero-phase degree-2 spiders remaining from the Bell "
            "measurement can be removed. Use <b>identity removal</b> in the "
            "rewrites panel or drag the <b>magic wand</b> through them.<br><br>"
            "When done, the diagram should reduce to the logical wire with a "
            "single Z(π/4) spider — the T gate — plus possibly a correction.",
            proof_canvas,
            interactive=True,
            completion_check=lambda mw: _proof_step_count(mw) >= 3,
        ),

        TutorialStep(
            "Magic state injection — summary",
            "You have verified magic state injection in ZX-calculus!<br><br>"
            "Key ideas:<br>"
            "• |T⟩ = Z(π/4)|+⟩ is a single-qubit resource state.<br>"
            "• Bell measurement + phase kickback = spider fusion in ZX.<br>"
            "• The T gate's phase (π/4) lives on one spider; fusion absorbs "
            "it into the logical wire.<br>"
            "• S correction = Z(π/2) spider fused in when the measurement "
            "outcome is |1⟩.<br><br>"
            "This is the ZX foundation of <b>fault-tolerant universal "
            "quantum computation</b>: Clifford gates keep the stabiliser "
            "structure; magic states inject the non-Clifford resource.",
        ),
    ]

    return TutorialSpec(
        steps, seen_key=MAGIC_STATE_SEEN, on_start=_ensure_edit_panel)


# ───────────────────────────────────────────────────────────────────────────
# Card widget helpers
# ───────────────────────────────────────────────────────────────────────────

def _muted_color(palette: QPalette) -> QColor:
    """De-emphasised text colour that works on any theme (light or dark)."""
    text = palette.color(QPalette.ColorRole.WindowText)
    bg   = palette.color(QPalette.ColorRole.Window)
    t = 0.35
    return QColor(
        round(text.red()   * (1 - t) + bg.red()   * t),
        round(text.green() * (1 - t) + bg.green() * t),
        round(text.blue()  * (1 - t) + bg.blue()  * t),
    )


@dataclass
class _CardWidgets:
    """Typed references to every child widget inside the explanation card."""
    frame:    QFrame
    title:    QLabel
    body:     QLabel
    progress: QLabel
    quick:    QPushButton
    learn:    QPushButton
    skip:     QPushButton
    back:     QPushButton
    next:     QPushButton


def _build_card(parent: QWidget) -> _CardWidgets:
    """Create and return the floating explanation card with all its children."""
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
        QLabel#tutorial_title {
            font-size: 16px;
            font-weight: bold;
        }
        """
    )

    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 14)
    layout.setSpacing(10)

    title_lbl = QLabel(card)
    title_lbl.setObjectName("tutorial_title")
    title_lbl.setWordWrap(True)
    layout.addWidget(title_lbl)

    body_lbl = QLabel(card)
    body_lbl.setWordWrap(True)
    body_lbl.setTextFormat(Qt.TextFormat.RichText)
    body_lbl.setOpenExternalLinks(True)
    layout.addWidget(body_lbl)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    progress_lbl = QLabel(card)
    progress_lbl.setStyleSheet(
        f"color: {_muted_color(card.palette()).name()};"
    )
    btn_row.addWidget(progress_lbl)
    btn_row.addStretch()

    quick_btn = QPushButton("Quick Start",      card)
    learn_btn = QPushButton("Learn the Basics", card)
    skip_btn  = QPushButton("Skip",             card)
    back_btn  = QPushButton("Back",             card)
    next_btn  = QPushButton("Next",             card)
    next_btn.setDefault(True)

    for btn in (quick_btn, learn_btn, skip_btn, back_btn, next_btn):
        btn_row.addWidget(btn)

    layout.addLayout(btn_row)

    return _CardWidgets(
        frame=card, title=title_lbl, body=body_lbl, progress=progress_lbl,
        quick=quick_btn, learn=learn_btn, skip=skip_btn,
        back=back_btn,  next=next_btn,
    )


# ───────────────────────────────────────────────────────────────────────────
# Overlay widget
# ───────────────────────────────────────────────────────────────────────────

class TutorialOverlay(QWidget):
    """Full-window translucent overlay that dims everything but the spotlight.

    The overlay is a direct child of the main window and tracks its size via
    the :class:`Tutorial` event filter.

    In *passive* steps it swallows mouse clicks over the dimmed area so the
    tour is the only way to proceed.  In *interactive* steps it becomes
    transparent to mouse events (``WA_TransparentForMouseEvents``), allowing
    the user to work freely in the spotlighted region; the card itself is
    always kept clickable.
    """

    def __init__(self, controller: "Tutorial", parent: QWidget) -> None:
        super().__init__(parent)
        self._controller   = controller
        self._spotlight:   Optional[QRect] = None
        self._pulse:       float = 1.0
        self._interactive: bool  = False
        self._dim_alpha:   int   = _DIM_ALPHA

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Pulsing spotlight border draws attention to the spotlighted widget.
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setKeyValueAt(0.0, 0.3)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.3)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)

        widgets = _build_card(self)
        self._card      = widgets.frame
        self._title     = widgets.title
        self._body      = widgets.body
        self._progress  = widgets.progress
        self._quick_btn = widgets.quick
        self._learn_btn = widgets.learn
        self._skip_btn  = widgets.skip
        self._back_btn  = widgets.back
        self._next_btn  = widgets.next

        self._quick_btn.clicked.connect(controller.start_quick)
        self._learn_btn.clicked.connect(controller.start_learn_basics)
        self._skip_btn.clicked.connect(controller.skip)
        self._back_btn.clicked.connect(controller.prev)
        self._next_btn.clicked.connect(controller.next)

        self.setGeometry(parent.rect())

    # ── Public API ─────────────────────────────────────────────────────────

    def set_interactive(self, interactive: bool) -> None:
        """Toggle click-through mode for hands-on interactive steps."""
        self._interactive = interactive
        self._dim_alpha   = _DIM_ALPHA_INTERACTIVE if interactive else _DIM_ALPHA
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, interactive)
        # The card must always remain clickable.
        self._card.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.update()

    def set_step(
        self,
        title:       str,
        body:        str,
        spotlight:   Optional[QRect],
        step_index:  int,
        step_count:  int,
        *,
        offer_quick: bool = False,
        offer_learn: bool = False,
        can_advance: bool = True,
    ) -> None:
        """Update the card content and reposition it relative to the spotlight."""
        self._title.setText(title)
        self._body.setText(body)
        self._progress.setText(f"Step {step_index + 1} of {step_count}")

        is_last = step_index == step_count - 1
        self._back_btn.setVisible(step_index > 0)
        self._next_btn.setText(
            "Finish" if is_last
            else ("Full Tour" if offer_quick else "Next")
        )
        self._skip_btn.setVisible(not is_last)
        self._quick_btn.setVisible(offer_quick)
        self._learn_btn.setVisible(offer_learn)
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
        self._next_btn.setEnabled(enabled)
        self._next_btn.setToolTip(
            "" if enabled else "Complete the highlighted task to continue.")

    # ── Qt overrides ───────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Full-window dim with a spotlight hole cut out.
        backdrop = QPainterPath()
        backdrop.addRect(QRectF(self.rect()))
        spot = self._spotlight if self._spotlight is not None else QRect()
        if spot.isValid():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(spot), _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
            backdrop = backdrop.subtracted(hole)

        painter.fillPath(backdrop, QColor(0, 0, 0, self._dim_alpha))

        if spot.isValid():
            self._paint_beak(painter, spot)
            highlight = self.palette().highlight().color()
            highlight.setAlphaF(self._pulse)
            pen = QPen(highlight)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(spot, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._controller.reposition()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # In interactive steps the overlay is WA_TransparentForMouseEvents,
        # so this handler is never reached.  In passive steps, eat the click.
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._controller.skip()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Return,
                     Qt.Key.Key_Enter,  Qt.Key.Key_Space):
            if self._next_btn.isEnabled():
                self._controller.next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
            self._controller.prev()
        else:
            super().keyPressEvent(event)

    # ── Private helpers ────────────────────────────────────────────────────

    def _on_pulse(self, value: object) -> None:
        self._pulse = float(cast(float, value))
        if self._spotlight is not None:
            self.update()

    def _position_card(self, spotlight: Optional[QRect]) -> None:
        """Place the card adjacent to the spotlight (below → above → side → centre)."""
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

        cx    = clamp_x(spotlight.center().x() - cw // 2)
        below = spotlight.bottom() + _CARD_MARGIN
        above = spotlight.top()    - _CARD_MARGIN - ch

        if below + ch <= oh - _CARD_MARGIN:
            card.move(cx, below)
        elif above >= _CARD_MARGIN:
            card.move(cx, above)
        elif spotlight.right() + _CARD_MARGIN + cw <= ow - _CARD_MARGIN:
            card.move(spotlight.right() + _CARD_MARGIN,
                      clamp_y(spotlight.center().y() - ch // 2))
        elif spotlight.left() - _CARD_MARGIN - cw >= _CARD_MARGIN:
            card.move(spotlight.left() - _CARD_MARGIN - cw,
                      clamp_y(spotlight.center().y() - ch // 2))
        else:
            card.move((ow - cw) // 2, (oh - ch) // 2)

    def _paint_beak(self, painter: QPainter, spot: QRect) -> None:
        """Draw a small triangular pointer from the card towards the spotlight."""
        card = self._card.geometry()
        cx   = max(card.left() + _BEAK, min(spot.center().x(), card.right()  - _BEAK))
        cy   = max(card.top()  + _BEAK, min(spot.center().y(), card.bottom() - _BEAK))

        if   card.top()    >= spot.bottom():
            tri = [QPoint(cx - _BEAK, card.top()),
                   QPoint(cx + _BEAK, card.top()),
                   QPoint(cx,         card.top() - _BEAK)]
        elif card.bottom() <= spot.top():
            tri = [QPoint(cx - _BEAK, card.bottom()),
                   QPoint(cx + _BEAK, card.bottom()),
                   QPoint(cx,         card.bottom() + _BEAK)]
        elif card.left()   >= spot.right():
            tri = [QPoint(card.left(),         cy - _BEAK),
                   QPoint(card.left(),         cy + _BEAK),
                   QPoint(card.left() - _BEAK, cy)]
        elif card.right()  <= spot.left():
            tri = [QPoint(card.right(),         cy - _BEAK),
                   QPoint(card.right(),         cy + _BEAK),
                   QPoint(card.right() + _BEAK, cy)]
        else:
            return  # card overlaps spotlight; no beak needed

        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.setBrush(self.palette().window().color())
        painter.drawPolygon(QPolygon(tri))


# ───────────────────────────────────────────────────────────────────────────
# Controller
# ───────────────────────────────────────────────────────────────────────────

class Tutorial(QObject):
    """Drives a :class:`TutorialSpec` over the main window via an overlay.

    A single instance is held on ``MainWindow._active_tutorial``; only one
    tour runs at a time.  Use the public entry points (``_run`` or the
    ``start_*`` functions below) rather than constructing this class directly.
    """

    def __init__(self, main_window: "MainWindow", spec: TutorialSpec) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.spec        = spec
        self.index       = 0
        self.overlay: Optional[TutorialOverlay] = None

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(400)
        self._poll_timer.timeout.connect(self._poll_completion)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self.spec.steps:
            return
        if self.spec.on_start is not None:
            self.spec.on_start(self.main_window)
        self.index   = 0
        self.overlay = TutorialOverlay(self, self.main_window)
        self.main_window.installEventFilter(self)
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.setFocus()
        self._show_step()

    # ── Navigation ─────────────────────────────────────────────────────────

    def next(self) -> None:
        if self.index >= len(self.spec.steps) - 1:
            self._finish()
        else:
            self.index += 1
            self._show_step()

    def prev(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._show_step()

    def skip(self) -> None:
        self._finish()

    def start_quick(self) -> None:
        """Switch to the condensed Quick Start tour from the welcome step."""
        self.spec  = editor_steps(quick=True)
        self.index = 0
        self._show_step()

    def start_learn_basics(self) -> None:
        """Switch to the 3 CNOTs → SWAP interactive lesson from the welcome step."""
        self.spec  = learn_basics_steps()
        self.index = 0
        if self.spec.on_start is not None:
            self.spec.on_start(self.main_window)
        self._show_step()

    def reposition(self) -> None:
        """Re-resolve the current spotlight and redraw (call on resize/move)."""
        if self.overlay is not None:
            self._show_step()

    # ── Qt event filter ────────────────────────────────────────────────────

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.main_window and self.overlay is not None:
            etype = event.type()
            if etype in (QEvent.Type.Resize, QEvent.Type.Move):
                self.overlay.setGeometry(self.main_window.rect())
                self.reposition()
            elif etype == QEvent.Type.Close:
                self._finish()
        return super().eventFilter(watched, event)

    # ── Private ────────────────────────────────────────────────────────────

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
        self.overlay.set_step(
            step.title, step.text, spotlight,
            self.index, len(self.spec.steps),
            offer_quick=step.offer_quick,
            offer_learn=step.offer_learn,
            can_advance=can_advance,
        )
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
            logging.warning(
                "Tutorial completion check for step %r raised; "
                "keeping Next disabled.",
                step.title, exc_info=True,
            )
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
        """Map ``step.target`` to a rectangle in overlay-local coordinates."""
        if step.target is None or self.overlay is None:
            return None
        try:
            widget = step.target(self.main_window)
        except Exception:
            logging.warning(
                "Tutorial target resolver for step %r raised; "
                "showing centred card.",
                step.title, exc_info=True,
            )
            widget = None

        if widget is None or not widget.isVisible():
            return None

        visible = widget.visibleRegion().boundingRect()
        if visible.width() < _MIN_TARGET or visible.height() < _MIN_TARGET:
            return None

        top_left = widget.mapToGlobal(visible.topLeft())
        local    = self.overlay.mapFromGlobal(top_left)
        rect     = QRect(local, visible.size()).adjusted(
            -_SPOTLIGHT_PAD, -_SPOTLIGHT_PAD,
             _SPOTLIGHT_PAD,  _SPOTLIGHT_PAD,
        )
        rect = rect.intersected(self.overlay.rect())
        if rect.width() < _MIN_TARGET or rect.height() < _MIN_TARGET:
            return None
        return rect

    def _finish(self) -> None:
        if self.overlay is None:
            return
        self._poll_timer.stop()
        if self.spec.seen_key is not None:
            set_settings_value(self.spec.seen_key, True, bool)
        self.main_window.removeEventFilter(self)
        self.overlay.hide()
        self.overlay.deleteLater()
        self.overlay = None
        if self.main_window._active_tutorial is self:
            self.main_window._active_tutorial = None


# ───────────────────────────────────────────────────────────────────────────
# Internal runner
# ───────────────────────────────────────────────────────────────────────────

def _run(main_window: "MainWindow", spec: TutorialSpec) -> None:
    """Tear down any running tour and start a fresh one."""
    existing = main_window._active_tutorial
    if existing is not None:
        existing.skip()
    tutorial = Tutorial(main_window, spec)
    main_window._active_tutorial = tutorial
    tutorial.start()


# ───────────────────────────────────────────────────────────────────────────
# Public entry points  (called by mainwindow.py and app.py)
# ───────────────────────────────────────────────────────────────────────────

def start_editor_tutorial(main_window: "MainWindow", quick: bool = False) -> None:
    """Start (or replay) the edit-mode tour.  Called from the Help menu."""
    _run(main_window, editor_steps(quick=quick))


def start_proof_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the proof-mode tour.  Called from the Help menu."""
    _run(main_window, proof_steps())


def start_learn_basics_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the interactive 3 CNOTs → SWAP lesson."""
    _run(main_window, learn_basics_steps())


def start_zz_gadget_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the ZZ(α) phase-gadget lesson."""
    _run(main_window, zz_gadget_steps())


def start_graph_state_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the three-qubit cluster-state / MBQC lesson."""
    _run(main_window, graph_state_steps())


def start_teleportation_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the quantum-state teleportation lesson."""
    _run(main_window, teleportation_steps())


def start_cnot_teleportation_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the CNOT-gate teleportation lesson."""
    _run(main_window, cnot_teleportation_steps())


def start_magic_state_tutorial(main_window: "MainWindow") -> None:
    """Start (or replay) the magic state injection lesson."""
    _run(main_window, magic_state_steps())


def maybe_start_first_run(main_window: "MainWindow") -> None:
    """Auto-start the editor tour on first launch.

    Gated by the ``SHOW_ON_STARTUP`` preference (default on).  The setting is
    left untouched after each run, so the tour keeps appearing until the user
    disables it in Preferences.  This matches the conventional "show on
    startup" checkbox behaviour and avoids permanently hiding the tour when the
    window is closed mid-way through.
    """
    if get_settings_value(SHOW_ON_STARTUP, bool, True):
        start_editor_tutorial(main_window)


def maybe_start_proof_tutorial(main_window: "MainWindow") -> None:
    """Auto-start the proof tour the first time the user enters proof mode.

    Silently skipped if another tour is already running or the proof tour has
    already been seen (``PROOF_TUTORIAL_SEEN`` is ``True``).
    """
    if main_window._active_tutorial is not None:
        return
    if not get_settings_value(PROOF_TUTORIAL_SEEN, bool, False):
        start_proof_tutorial(main_window)
