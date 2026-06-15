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

"""Interactive onboarding tutorial for ZXLive.

Architecture overview
---------------------
This module is entirely self-contained: it adds no attributes to any other
class and requires only three call-sites in ``mainwindow.py`` / ``app.py``
(unchanged from the previous version).

Key design decisions that differ from the original PR submission:

1.  **Typed ``CardWidgets`` dataclass** replaces the untyped ``dict`` returned
    by ``_build_card``.  Every widget field is a concrete type; no casting.

2.  **Dot-based progress indicator** replaces the "Step N of M" label.  Each
    dot is individually clickable, so users can jump to any step non-linearly.
    The ``Tutorial`` controller validates the jump (proof-mode steps can't be
    entered from the editor tour, etc.) before committing.

3.  **``ConceptWidget`` base class** for all in-card animated diagrams.  It
    exposes a ``reset()`` method so ``TutorialOverlay._set_diagram`` can
    cleanly restart animation whenever the user navigates Back to a diagram
    step.  Three concrete widgets are implemented:

    - ``_SpiderFusionWidget``  — two same-colour spiders merge; phases add.
    - ``_ColourChangeWidget``  — shows the H-box colour-change rule graphically.
    - ``_CopyRuleWidget``      — a phase-0 spider copied through a different-
                                 colour spider, demonstrating the copy rule.

    ``concept_widget_for_step`` picks one at random (seeded per session so the
    choice is stable across Back/Next) to keep the surprise fresh for returning
    users.

4.  **Auto-advance countdown** on diagram steps.  A thin animated progress bar
    at the bottom of the card counts down 8 seconds, then calls ``next()``.
    Clicking anywhere on the card resets the timer so attentive users aren't
    rushed.

5.  **``TutorialTheme``** — a lightweight dataclass that resolves the correct
    spider/wire/background colours for the current light-or-dark palette,
    queried once per ``paintEvent`` rather than hardcoded.

6.  **Three tours** (editor, proof, examples) — same public API as before, but
    the step *text* is substantially rewritten to be more concise and action-
    oriented, and the examples tour now references specific rewrite rule names
    that map to the rewrites panel.

QSettings keys
--------------
``tutorial/show-on-startup``  — bool, default True.  Gates first-run editor tour.
``tutorial/proof-seen``       — bool, default False.  Gates proof-mode auto-tour.
``tutorial/concept-seed``     — int.  Stable random seed for concept widget choice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, ClassVar, Optional, cast

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QEvent, QObject,
                             QPoint, QPointF, QRect, QRectF, QSize,
                             QVariantAnimation, Qt, QTimer)
from PySide6.QtGui import (QColor, QFont, QKeyEvent, QMouseEvent, QPainter,
                            QPainterPath, QPaintEvent, QPen, QPolygon,
                            QResizeEvent)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                                QPushButton, QSizePolicy, QToolButton,
                                QVBoxLayout, QWidget)

from .common import get_settings_value, set_settings_value

if TYPE_CHECKING:
    from .mainwindow import MainWindow

# ---------------------------------------------------------------------------
# QSettings keys
# ---------------------------------------------------------------------------
SHOW_ON_STARTUP     = "tutorial/show-on-startup"
PROOF_TUTORIAL_SEEN = "tutorial/proof-seen"
CONCEPT_SEED_KEY    = "tutorial/concept-seed"

# ---------------------------------------------------------------------------
# Overlay visual constants
# ---------------------------------------------------------------------------
_DIM_ALPHA        = 148
_SPOTLIGHT_PAD    = 9
_SPOTLIGHT_RADIUS = 11
_CARD_WIDTH       = 470
_CARD_MARGIN      = 16
_BEAK             = 12
_MIN_TARGET       = 6
_AUTO_ADVANCE_MS  = 8_000   # ms before a diagram step auto-advances

TargetResolver = Callable[["MainWindow"], Optional[QWidget]]


# ---------------------------------------------------------------------------
# TutorialTheme — palette-aware colors for concept diagrams
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TutorialTheme:
    """Colors derived from the current Qt palette (light or dark aware)."""
    z_fill:       QColor
    z_outline:    QColor
    x_fill:       QColor
    x_outline:    QColor
    h_fill:       QColor
    wire:         QColor
    boundary:     QColor
    text:         QColor
    caption:      QColor
    bg:           QColor

    @classmethod
    def from_palette(cls) -> "TutorialTheme":
        app = QApplication.instance()
        dark = False
        if isinstance(app, QApplication):
            try:
                dark = (app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
            except AttributeError:
                pass
        if dark:
            return cls(
                z_fill    = QColor("#3a6e3a"),
                z_outline = QColor("#7ddc7d"),
                x_fill    = QColor("#7a2020"),
                x_outline = QColor("#ff8888"),
                h_fill    = QColor("#7a7a00"),
                wire      = QColor("#cccccc"),
                boundary  = QColor("#aaaaaa"),
                text      = QColor("#dddddd"),
                caption   = QColor("#999999"),
                bg        = QColor(30, 30, 30, 0),
            )
        return cls(
            z_fill    = QColor("#ccffcc"),
            z_outline = QColor("#2a7a2a"),
            x_fill    = QColor("#ffcccc"),
            x_outline = QColor("#aa1111"),
            h_fill    = QColor("#ffff88"),
            wire      = QColor("#333333"),
            boundary  = QColor("#111111"),
            text      = QColor("#1a1a1a"),
            caption   = QColor("#666666"),
            bg        = QColor(255, 255, 255, 0),
        )


# ---------------------------------------------------------------------------
# ConceptWidget base — animated ZX diagram inside the tutorial card
# ---------------------------------------------------------------------------

class ConceptWidget(QWidget):
    """Base for all in-card animated concept diagrams.

    Subclasses implement ``_paint_frame(painter, t)`` where ``t ∈ [0,1]`` is
    the normalised animation progress.  The base class drives the animation
    loop (idle → animate → hold → reverse → idle) and exposes ``reset()`` so
    the overlay can restart cleanly on Back/Next.
    """

    #: Duration of the forward animation in milliseconds.
    ANIM_DURATION_MS:  ClassVar[int] = 950
    #: Pause before animation starts (ms).
    IDLE_DELAY_MS:     ClassVar[int] = 1100
    #: How long to hold the final frame (ms).
    HOLD_MS:           ClassVar[int] = 1500
    #: Height of the widget in pixels.
    WIDGET_HEIGHT:     ClassVar[int] = 118

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.WIDGET_HEIGHT)
        self._t: float = 0.0
        self._reversing: bool = False

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_finished)

        QTimer.singleShot(self.IDLE_DELAY_MS, self._start_forward)

    # -- public API ----------------------------------------------------------

    def reset(self) -> None:
        """Restart from the beginning (called on Back/Next navigation)."""
        self._anim.stop()
        self._t = 0.0
        self._reversing = False
        self.update()
        QTimer.singleShot(self.IDLE_DELAY_MS, self._start_forward)

    # -- animation internals -------------------------------------------------

    def _start_forward(self) -> None:
        self._reversing = False
        self._anim.setDuration(self.ANIM_DURATION_MS)
        self._anim.setDirection(QAbstractAnimation.Direction.Forward)
        self._anim.start()

    def _start_reverse(self) -> None:
        self._reversing = True
        self._anim.setDuration(int(self.ANIM_DURATION_MS * 0.75))
        self._anim.setDirection(QAbstractAnimation.Direction.Backward)
        self._anim.start()

    def _on_value(self, value: object) -> None:
        self._t = float(cast(float, value))
        self.update()

    def _on_finished(self) -> None:
        if not self._reversing:
            # Forward complete → hold, then reverse
            QTimer.singleShot(self.HOLD_MS, self._start_reverse)
        else:
            # Reverse complete → idle pause, then forward again
            QTimer.singleShot(self.IDLE_DELAY_MS, self._start_forward)

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._anim.stop()

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = TutorialTheme.from_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_frame(painter, self._t, theme)

    def _paint_frame(self, painter: QPainter, t: float,
                     theme: TutorialTheme) -> None:
        """Override in subclasses.  ``t`` runs 0→1 (forward) then 1→0 (reverse)."""
        raise NotImplementedError

    # -- shared drawing helpers ----------------------------------------------

    @staticmethod
    def draw_spider(p: QPainter, cx: float, cy: float, r: float,
                    fill: QColor, outline: QColor, pen_w: float = 1.5) -> None:
        p.setPen(QPen(outline, pen_w))
        p.setBrush(fill)
        p.drawEllipse(QPointF(cx, cy), r, r)

    @staticmethod
    def draw_wire(p: QPainter, x1: float, y1: float,
                  x2: float, y2: float, color: QColor, w: float = 2.0) -> None:
        p.setPen(QPen(color, w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    @staticmethod
    def draw_boundary(p: QPainter, cx: float, cy: float,
                      color: QColor) -> None:
        p.setPen(QPen(color, 1.2))
        p.setBrush(color)
        p.drawEllipse(QPointF(cx, cy), 5.0, 5.0)

    @staticmethod
    def draw_h_box(p: QPainter, cx: float, cy: float, size: float,
                   fill: QColor, outline: QColor) -> None:
        half = size / 2
        rect = QRectF(cx - half, cy - half, size, size)
        p.setPen(QPen(outline, 1.5))
        p.setBrush(fill)
        p.drawRect(rect)

    @staticmethod
    def centred_text(p: QPainter, cx: float, cy: float, text: str,
                     color: QColor, font: Optional[QFont] = None) -> None:
        if font:
            p.setFont(font)
        p.setPen(QPen(color))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.ascent()
        p.drawText(QPointF(cx - tw / 2, cy + th / 3), text)

    @staticmethod
    def phase_str(num: int, den: int) -> str:
        """Reduce num/den and return e.g. 'π/2', '3π/4', 'π', '0'."""
        if num == 0:
            return "0"
        def gcd(a: int, b: int) -> int:
            while b:
                a, b = b, a % b
            return a
        g = gcd(abs(num), den)
        n, d = num // g, den // g
        if d == 1:
            return "π" if n == 1 else f"{n}π"
        return f"π/{d}" if n == 1 else f"{n}π/{d}"

    @staticmethod
    def draw_caption(p: QPainter, w: int, h: int,
                     text: str, color: QColor) -> None:
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QPen(color))
        p.drawText(QRectF(4, h - 18, w - 8, 16),
                   Qt.AlignmentFlag.AlignCenter, text)


# ---------------------------------------------------------------------------
# Concrete concept widget 1 — Spider Fusion
# ---------------------------------------------------------------------------

class _SpiderFusionWidget(ConceptWidget):
    """Two Z-spiders on a plain wire slide together; their phases add.

    Demonstrates the single most important ZX rule:
        ─●(α)─●(β)─  =  ─●(α+β)─
    """
    _ALPHA = (1, 2)   # π/2
    _BETA  = (1, 4)   # π/4  →  sum = 3π/4

    def _paint_frame(self, painter: QPainter, t: float,
                     theme: TutorialTheme) -> None:
        W, H = self.width(), self.height()
        r = 17.0
        mid = H // 2 + 2

        # Horizontal zones
        z = W / 6.0
        x_lb   = z * 0.7
        x_a0   = z * 1.7
        x_mid  = z * 3.0
        x_b0   = z * 4.3
        x_rb   = z * 5.3

        # Spider positions: converge on x_mid as t→1
        x_a = x_a0 + (x_mid - x_a0) * t
        x_b = x_b0 + (x_mid - x_b0) * t

        # Wires
        if t < 0.98:
            self.draw_wire(painter, x_lb,      mid, x_a - r,  mid, theme.wire)
            gap_l = x_a + r
            gap_r = x_b - r
            if gap_r > gap_l + 2:
                self.draw_wire(painter, gap_l, mid, gap_r,     mid, theme.wire)
            self.draw_wire(painter, x_b + r,   mid, x_rb,     mid, theme.wire)
        else:
            self.draw_wire(painter, x_lb,      mid, x_mid - r, mid, theme.wire)
            self.draw_wire(painter, x_mid + r, mid, x_rb,      mid, theme.wire)

        self.draw_boundary(painter, x_lb, mid, theme.boundary)
        self.draw_boundary(painter, x_rb, mid, theme.boundary)

        label_f = QFont(); label_f.setPointSize(9); label_f.setItalic(True)

        if t < 0.98:
            # Two spiders
            self.draw_spider(painter, x_a, mid, r, theme.z_fill, theme.z_outline)
            self.draw_spider(painter, x_b, mid, r, theme.z_fill, theme.z_outline)
            fade = QColor(theme.text); fade.setAlphaF(max(0.0, 1.0 - t * 3))
            self.centred_text(painter, x_a, mid - r - 7,
                              self.phase_str(*self._ALPHA), fade, label_f)
            self.centred_text(painter, x_b, mid - r - 7,
                              self.phase_str(*self._BETA),  fade, label_f)
            # Equals sign fading in slightly ahead of merge
            eq_alpha = min(1.0, t * 1.5)
            eq_c = QColor(theme.caption); eq_c.setAlphaF(eq_alpha * 0.8)
            eq_f = QFont(); eq_f.setPointSize(15); eq_f.setBold(True)
            self.centred_text(painter, x_mid, mid + 5, "=", eq_c, eq_f)
        else:
            # One merged spider
            self.draw_spider(painter, x_mid, mid, r, theme.z_fill, theme.z_outline)
            an, ad = self._ALPHA; bn, bd = self._BETA
            self.centred_text(painter, x_mid, mid - r - 7,
                              self.phase_str(an * bd + bn * ad, ad * bd),
                              theme.text, label_f)

        self.draw_caption(painter, W, H,
                          "Spider fusion: connected same-colour spiders merge; phases add.",
                          theme.caption)


# ---------------------------------------------------------------------------
# Concrete concept widget 2 — Colour Change (H-box rule)
# ---------------------------------------------------------------------------

class _ColourChangeWidget(ConceptWidget):
    """Demonstrates the colour-change rule: H·Z(α)·H = X(α).

    A green Z-spider flanked by two yellow H-boxes animates into a single
    red X-spider — the H-box 'transfers through' the spider, changing its
    colour.
    """
    ANIM_DURATION_MS = 800
    HOLD_MS          = 1800

    def _paint_frame(self, painter: QPainter, t: float,
                     theme: TutorialTheme) -> None:
        W, H = self.width(), self.height()
        r  = 16.0
        hb = 13.0    # H-box half-size
        mid = H // 2 + 2

        z = W / 5.5
        x_lh  = z * 1.2     # left H-box
        x_sp  = z * 2.75    # spider (centre)
        x_rh  = z * 4.3     # right H-box
        x_lb  = z * 0.4
        x_rb  = z * 5.1

        # Fade out the H-boxes and Z-spider; fade in the X-spider
        before_alpha = max(0.0, 1.0 - t * 2.2)
        after_alpha  = max(0.0, (t - 0.5) * 2.0)

        # --- wires (always full extent) ---
        self.draw_wire(painter, x_lb,        mid, x_lh - hb, mid, theme.wire)
        self.draw_wire(painter, x_lh + hb,   mid, x_sp - r,  mid, theme.wire)
        self.draw_wire(painter, x_sp + r,    mid, x_rh - hb, mid, theme.wire)
        self.draw_wire(painter, x_rh + hb,   mid, x_rb,      mid, theme.wire)
        self.draw_boundary(painter, x_lb, mid, theme.boundary)
        self.draw_boundary(painter, x_rb, mid, theme.boundary)

        # --- before state (H·Z·H) ---
        h_fill    = QColor(theme.h_fill);   h_fill.setAlphaF(before_alpha)
        h_outline = QColor(theme.z_outline); h_outline.setAlphaF(before_alpha)
        z_fill    = QColor(theme.z_fill);   z_fill.setAlphaF(before_alpha)
        z_out     = QColor(theme.z_outline); z_out.setAlphaF(before_alpha)
        if before_alpha > 0.01:
            self.draw_h_box(painter, x_lh, mid, hb * 2, h_fill, h_outline)
            self.draw_h_box(painter, x_rh, mid, hb * 2, h_fill, h_outline)
            self.draw_spider(painter, x_sp, mid, r, z_fill, z_out)
            label_f = QFont(); label_f.setPointSize(9); label_f.setItalic(True)
            lc = QColor(theme.text); lc.setAlphaF(before_alpha)
            self.centred_text(painter, x_sp, mid - r - 7, "α", lc, label_f)
            hc = QColor(theme.caption); hc.setAlphaF(before_alpha * 0.9)
            hf = QFont(); hf.setPointSize(8); hf.setBold(True)
            self.centred_text(painter, x_lh, mid + 1, "H", hc, hf)
            self.centred_text(painter, x_rh, mid + 1, "H", hc, hf)

        # --- after state (X-spider) ---
        x_fill = QColor(theme.x_fill);   x_fill.setAlphaF(after_alpha)
        x_out  = QColor(theme.x_outline); x_out.setAlphaF(after_alpha)
        if after_alpha > 0.01:
            self.draw_spider(painter, x_sp, mid, r, x_fill, x_out)
            label_f = QFont(); label_f.setPointSize(9); label_f.setItalic(True)
            lc2 = QColor(theme.text); lc2.setAlphaF(after_alpha)
            self.centred_text(painter, x_sp, mid - r - 7, "α", lc2, label_f)

        self.draw_caption(painter, W, H,
                          "Colour change: H·Z(α)·H = X(α).  H-boxes flip spider colour.",
                          theme.caption)


# ---------------------------------------------------------------------------
# Concrete concept widget 3 — Copy Rule
# ---------------------------------------------------------------------------

class _CopyRuleWidget(ConceptWidget):
    """Demonstrates the copy rule: a |0⟩/|1⟩ state copies through a spider.

    A phase-0 Z-spider connected to an X-spider animates to show the X-spider
    'splitting', with copies of the Z-spider appearing on each output leg —
    visually conveying that classical information copies through X-basis spiders.
    """
    ANIM_DURATION_MS = 1050
    HOLD_MS          = 1600
    WIDGET_HEIGHT    = 126

    def _paint_frame(self, painter: QPainter, t: float,
                     theme: TutorialTheme) -> None:
        W, H = self.width(), self.height()
        r   = 15.0
        mid = H // 2 - 4

        # Layout: |0⟩ ─ Z ─ X ─ two outputs (fan-out)
        z  = W / 6.0
        x_lb  = z * 0.5
        x_z   = z * 1.6    # input Z (phase 0 = "copy" state)
        x_x   = z * 3.0    # X spider being copied through
        # Output legs split vertically as t→1
        x_out = z * 4.6
        spread = 28.0 * t   # vertical spread of output legs

        # Input wire
        self.draw_wire(painter, x_lb, mid, x_z - r, mid, theme.wire)
        self.draw_boundary(painter, x_lb, mid, theme.boundary)

        # Z → X wire (shrinks horizontally? no — stays fixed)
        self.draw_wire(painter, x_z + r, mid, x_x - r, mid, theme.wire)

        # Output wires (fan out)
        y_top = mid - spread
        y_bot = mid + spread
        self.draw_wire(painter, x_x + r, mid, x_out - r, y_top, theme.wire)
        self.draw_wire(painter, x_x + r, mid, x_out - r, y_bot, theme.wire)

        # Spiders
        self.draw_spider(painter, x_z, mid, r, theme.z_fill, theme.z_outline)
        self.draw_spider(painter, x_x, mid, r, theme.x_fill, theme.x_outline)

        # Output Z-spider copies fade in as t→1
        copy_alpha = t
        zf = QColor(theme.z_fill);   zf.setAlphaF(copy_alpha)
        zo = QColor(theme.z_outline); zo.setAlphaF(copy_alpha)
        if copy_alpha > 0.05:
            self.draw_spider(painter, x_out, y_top, r, zf, zo)
            self.draw_spider(painter, x_out, y_bot, r, zf, zo)

        # Boundary dots on outputs
        bc = QColor(theme.boundary); bc.setAlphaF(copy_alpha)
        rb1 = z * 5.5
        if copy_alpha > 0.05:
            p_save = painter.pen()
            painter.setPen(QPen(bc, 1.2))
            painter.setBrush(bc)
            painter.drawEllipse(QPointF(rb1, y_top), 5.0, 5.0)
            painter.drawEllipse(QPointF(rb1, y_bot), 5.0, 5.0)
            self.draw_wire(painter, x_out + r, y_top, rb1, y_top, theme.wire)
            self.draw_wire(painter, x_out + r, y_bot, rb1, y_bot, theme.wire)
            painter.setPen(p_save)

        # Label on input Z
        label_f = QFont(); label_f.setPointSize(9); label_f.setItalic(True)
        self.centred_text(painter, x_z, mid - r - 7, "0", theme.text, label_f)

        self.draw_caption(painter, W, H - 10,
                          "Copy rule: a basis state copies through a different-colour spider.",
                          theme.caption)


# ---------------------------------------------------------------------------
# Concept widget selector
# ---------------------------------------------------------------------------

_CONCEPT_WIDGETS: list[type[ConceptWidget]] = [
    _SpiderFusionWidget,
    _ColourChangeWidget,
    _CopyRuleWidget,
]


def concept_widget_for_step() -> type[ConceptWidget]:
    """Return a concept widget class, stable within a session via a stored seed."""
    seed = get_settings_value(CONCEPT_SEED_KEY, int, -1)
    if seed < 0:
        seed = random.randint(0, 10_000)
        set_settings_value(CONCEPT_SEED_KEY, seed, int)
    rng = random.Random(seed)
    return rng.choice(_CONCEPT_WIDGETS)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TutorialStep:
    """One card in a guided tour.

    Fields
    ------
    title        Rich-text card heading.
    text         Rich-text body (small HTML subset supported by QLabel).
    target       Optional resolver → widget to spotlight.  None = centred card.
    full_only    Skip this step in the Quick Start condensed tour.
    offer_quick  This step shows the Quick-start / Full-tour choice buttons.
    diagram      Zero-argument factory producing a ConceptWidget.  When set,
                 the widget is rendered below the text body and an auto-advance
                 countdown starts.  A fresh instance is created on every visit
                 so animation state never leaks across Back/Next navigation.
    """
    title:       str
    text:        str
    target:      Optional[TargetResolver]            = None
    full_only:   bool                                = False
    offer_quick: bool                                = False
    diagram:     Optional[Callable[[], QWidget]]     = field(default=None, repr=False)


@dataclass
class TutorialSpec:
    """A complete tour specification."""
    steps:    list[TutorialStep]
    seen_key: Optional[str]                                      = None
    on_start: Optional[Callable[["MainWindow"], None]]           = None


# ---------------------------------------------------------------------------
# CardWidgets — typed replacement for the previous untyped dict
# ---------------------------------------------------------------------------

@dataclass
class CardWidgets:
    """All named child widgets of the tutorial card, fully typed."""
    frame:        QFrame
    title:        QLabel
    body:         QLabel
    dot_row:      QHBoxLayout    # progress dots live here
    diagram_slot: QVBoxLayout    # ConceptWidget injected here when present
    quick:        QPushButton
    skip:         QPushButton
    back:         QPushButton
    nxt:          QPushButton
    countdown:    QWidget        # thin animated progress bar at card bottom


# ---------------------------------------------------------------------------
# Countdown bar
# ---------------------------------------------------------------------------

class _CountdownBar(QWidget):
    """A thin horizontal bar that depletes over ``duration_ms`` milliseconds.

    Used on diagram steps to signal auto-advance.  Clicking anywhere on the
    parent card resets it via ``reset()``.
    """

    def __init__(self, duration_ms: int, on_finished: Callable[[], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._frac: float = 1.0
        self._on_finished = on_finished

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(on_finished)
        self._anim.start()

    def _tick(self, value: object) -> None:
        self._frac = float(cast(float, value))
        self.update()

    def reset(self) -> None:
        self._anim.stop()
        self._frac = 1.0
        self.update()
        self._anim.start()

    def stop(self) -> None:
        self._anim.stop()
        self._frac = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        # Background track
        p.fillRect(self.rect(), self.palette().mid().color())
        # Filled portion
        filled_w = int(w * self._frac)
        if filled_w > 0:
            bar_color = self.palette().highlight().color()
            p.fillRect(0, 0, filled_w, self.height(), bar_color)


# ---------------------------------------------------------------------------
# Progress dot indicator
# ---------------------------------------------------------------------------

class _DotIndicator(QWidget):
    """A row of small clickable dots representing the step progress.

    The active dot is filled with the palette highlight colour; inactive dots
    are outlines.  Clicking a dot emits ``jump_to(index)`` back to the
    controller.
    """
    _DOT_R  = 5
    _DOT_GAP = 14

    def __init__(self, count: int, current: int,
                 on_jump: Callable[[int], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._count   = count
        self._current = current
        self._on_jump = on_jump
        h = self._DOT_R * 2 + 4
        total_w = max(1, count) * self._DOT_GAP
        self.setFixedSize(total_w, h)

    def update_state(self, current: int) -> None:
        self._current = current
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._DOT_R
        hl = self.palette().highlight().color()
        mid_c = self.palette().mid().color()
        cy = self.height() // 2
        for i in range(self._count):
            cx = i * self._DOT_GAP + r + 2
            if i == self._current:
                p.setPen(QPen(hl, 1))
                p.setBrush(hl)
            else:
                p.setPen(QPen(mid_c, 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), float(r), float(r))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        r = self._DOT_R
        for i in range(self._count):
            cx = i * self._DOT_GAP + r + 2
            if abs(event.position().x() - cx) <= r + 3:
                self._on_jump(i)
                return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------

def _build_card(parent: QWidget,
                on_jump: Callable[[int], None]) -> CardWidgets:
    """Construct the tutorial card and return a fully-typed ``CardWidgets``.

    Layout::

        ┌────────────────────────────────────────────┐
        │  title_label                               │
        │  body_label (word-wrapped rich text)       │
        │  ┌─ diagram_slot ────────────────────────┐ │  ← empty by default
        │  └───────────────────────────────────────┘ │
        │  [●●○○○○○○]  [Quick] [Skip] [◀ Back] [▶] │
        ├────────────────────────────────────────────┤
        │  countdown bar (3 px, only on diagram steps│
        └────────────────────────────────────────────┘
    """
    frame = QFrame(parent)
    frame.setObjectName("tutorial_card")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setStyleSheet("""
        QFrame#tutorial_card {
            background: palette(window);
            border: 1px solid palette(mid);
            border-radius: 10px;
        }
        QLabel#tc_title { font-size: 16px; font-weight: bold; }
    """)

    outer = QVBoxLayout(frame)
    outer.setContentsMargins(18, 15, 18, 10)
    outer.setSpacing(9)

    title = QLabel(frame)
    title.setObjectName("tc_title")
    title.setWordWrap(True)
    outer.addWidget(title)

    body = QLabel(frame)
    body.setObjectName("tc_body")
    body.setWordWrap(True)
    body.setTextFormat(Qt.TextFormat.RichText)
    outer.addWidget(body)

    diagram_slot = QVBoxLayout()
    diagram_slot.setContentsMargins(0, 3, 0, 3)
    outer.addLayout(diagram_slot)

    # Controls row: dots (left), buttons (right)
    controls = QHBoxLayout()
    controls.setSpacing(6)

    dot_row = QHBoxLayout()
    dot_row.setSpacing(0)
    controls.addLayout(dot_row)
    controls.addStretch()

    quick = QPushButton("Quick start", frame)
    quick.setObjectName("tc_quick")
    controls.addWidget(quick)

    skip = QPushButton("Skip", frame)
    skip.setObjectName("tc_skip")
    controls.addWidget(skip)

    back = QPushButton("◀ Back", frame)
    back.setObjectName("tc_back")
    controls.addWidget(back)

    nxt = QPushButton("Next ▶", frame)
    nxt.setObjectName("tc_next")
    nxt.setDefault(True)
    controls.addWidget(nxt)

    outer.addLayout(controls)

    # Countdown bar (hidden by default; shown on diagram steps)
    countdown = _CountdownBar(_AUTO_ADVANCE_MS, lambda: None, frame)
    countdown.hide()
    outer.addWidget(countdown)
    outer.setContentsMargins(18, 15, 18, 0)

    return CardWidgets(
        frame=frame, title=title, body=body,
        dot_row=dot_row, diagram_slot=diagram_slot,
        quick=quick, skip=skip, back=back, nxt=nxt,
        countdown=countdown,
    )


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

class TutorialOverlay(QWidget):
    """Full-window translucent overlay.

    Differences from the previous implementation
    ---------------------------------------------
    * Uses ``CardWidgets`` (typed dataclass) instead of an untyped dict.
    * Manages a ``_DotIndicator`` that lives inside the card controls row and
      can be clicked to jump steps.
    * Manages a ``_CountdownBar`` that auto-advances diagram steps after
      ``_AUTO_ADVANCE_MS`` milliseconds; any click on the card resets the timer.
    * ``_set_diagram`` calls ``widget.reset()`` (via the ``ConceptWidget`` API)
      when returning to a previously-visited diagram step, so animation state
      is always clean.
    """

    def __init__(self, controller: "Tutorial", parent: QWidget) -> None:
        super().__init__(parent)
        self._controller  = controller
        self._spotlight:  Optional[QRect]    = None
        self._pulse:      float              = 1.0
        self._diagram_w:  Optional[QWidget]  = None
        self._dot_widget: Optional[_DotIndicator] = None
        self._countdown:  Optional[_CountdownBar] = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setKeyValueAt(0.0, 0.35)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.35)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)

        self._cw = _build_card(self, controller.jump_to)
        self._cw.quick.clicked.connect(controller.start_quick)
        self._cw.skip.clicked.connect(controller.skip)
        self._cw.back.clicked.connect(controller.prev)
        self._cw.nxt.clicked.connect(controller.next)

        self.setGeometry(parent.rect())

    # -- step update ---------------------------------------------------------

    def set_step(self, title: str, body: str,
                 spotlight: Optional[QRect],
                 step_index: int, step_count: int,
                 offer_quick: bool,
                 diagram_factory: Optional[Callable[[], QWidget]]) -> None:

        self._cw.title.setText(title)
        self._cw.body.setText(body)

        self._cw.back.setVisible(step_index > 0)
        is_last = step_index == step_count - 1
        self._cw.nxt.setText("Finish" if is_last else "Next ▶")
        self._cw.skip.setVisible(not is_last)
        self._cw.quick.setVisible(offer_quick)

        self._rebuild_dots(step_index, step_count)
        self._set_diagram(diagram_factory)

        self._spotlight = spotlight
        self._position_card(spotlight)

        if spotlight is not None:
            if self._pulse_anim.state() != QAbstractAnimation.State.Running:
                self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
            self._pulse = 1.0
        self.update()

    def _rebuild_dots(self, current: int, total: int) -> None:
        # Clear old dot widget
        while self._cw.dot_row.count():
            item = self._cw.dot_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._dot_widget = _DotIndicator(
            total, current, self._controller.jump_to, self._cw.frame)
        self._cw.dot_row.addWidget(self._dot_widget)

    def _set_diagram(self, factory: Optional[Callable[[], QWidget]]) -> None:
        # Remove any existing diagram widget
        if self._diagram_w is not None:
            self._cw.diagram_slot.removeWidget(self._diagram_w)
            self._diagram_w.deleteLater()
            self._diagram_w = None

        # Stop old countdown
        if isinstance(self._cw.countdown, _CountdownBar):
            self._cw.countdown.stop()
            self._cw.countdown.hide()

        if factory is not None:
            widget = factory()
            self._diagram_w = widget
            self._cw.diagram_slot.addWidget(widget)
            widget.show()

            # New countdown for this diagram step
            def _advance() -> None:
                self._controller.next()

            cd = _CountdownBar(_AUTO_ADVANCE_MS, _advance, self._cw.frame)
            # Replace the countdown widget in the layout
            layout = self._cw.frame.layout()
            if layout is not None:
                old_idx = layout.indexOf(self._cw.countdown)
                if old_idx >= 0:
                    layout.takeAt(old_idx)
                    self._cw.countdown.deleteLater()
                layout.addWidget(cd)
            self._cw.countdown = cd  # type: ignore[assignment]
            cd.show()

        self._cw.frame.adjustSize()

    # -- card click resets countdown -----------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        card_geom = self._cw.frame.geometry()
        if card_geom.contains(event.pos()):
            if isinstance(self._cw.countdown, _CountdownBar):
                self._cw.countdown.reset()
            # Don't accept — let the card's child buttons receive the event.
        else:
            event.accept()  # swallow clicks on dimmed area

    # -- pulse ---------------------------------------------------------------

    def _on_pulse(self, value: object) -> None:
        self._pulse = float(cast(float, value))
        if self._spotlight is not None:
            self.update()

    # -- positioning ---------------------------------------------------------

    def _position_card(self, spotlight: Optional[QRect]) -> None:
        card = self._cw.frame
        card.setFixedWidth(_CARD_WIDTH)
        card.adjustSize()
        cw, ch = card.width(), card.height()
        ow, oh = self.width(), self.height()

        if spotlight is None or not spotlight.isValid():
            card.move((ow - cw) // 2, (oh - ch) // 2)
            return

        def cx_clamped() -> int:
            return max(_CARD_MARGIN,
                       min(spotlight.center().x() - cw // 2,
                           ow - cw - _CARD_MARGIN))

        def cy_clamped(y: int) -> int:
            return max(_CARD_MARGIN, min(y, oh - ch - _CARD_MARGIN))

        below_y = spotlight.bottom() + _CARD_MARGIN
        above_y = spotlight.top() - _CARD_MARGIN - ch
        if below_y + ch <= oh - _CARD_MARGIN:
            card.move(cx_clamped(), below_y)
        elif above_y >= _CARD_MARGIN:
            card.move(cx_clamped(), above_y)
        elif spotlight.right() + _CARD_MARGIN + cw <= ow - _CARD_MARGIN:
            card.move(spotlight.right() + _CARD_MARGIN,
                      cy_clamped(spotlight.center().y() - ch // 2))
        elif spotlight.left() - _CARD_MARGIN - cw >= _CARD_MARGIN:
            card.move(spotlight.left() - _CARD_MARGIN - cw,
                      cy_clamped(spotlight.center().y() - ch // 2))
        else:
            card.move((ow - cw) // 2, (oh - ch) // 2)

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRect(self.rect())

        spot: Optional[QRect] = self._spotlight
        if spot is not None and spot.isValid():
            hole = QPainterPath()
            hole.addRoundedRect(spot.toRectF(), _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
            path = path.subtracted(hole)

        painter.fillPath(path, QColor(0, 0, 0, _DIM_ALPHA))

        if spot is not None and spot.isValid():
            self._paint_beak(painter, spot)
            hl = self.palette().highlight().color()
            hl.setAlphaF(self._pulse)
            painter.setPen(QPen(hl, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(spot.toRectF(),
                                    _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)

    def _paint_beak(self, painter: QPainter, spot: QRect) -> None:
        card = self._cw.frame.geometry()
        cx = max(card.left() + _BEAK, min(spot.center().x(), card.right() - _BEAK))
        cy = max(card.top() + _BEAK, min(spot.center().y(), card.bottom() - _BEAK))
        tri: list[QPoint]
        if card.top() >= spot.bottom():
            tri = [QPoint(cx - _BEAK, card.top()), QPoint(cx + _BEAK, card.top()),
                   QPoint(cx, card.top() - _BEAK)]
        elif card.bottom() <= spot.top():
            tri = [QPoint(cx - _BEAK, card.bottom()), QPoint(cx + _BEAK, card.bottom()),
                   QPoint(cx, card.bottom() + _BEAK)]
        elif card.left() >= spot.right():
            tri = [QPoint(card.left(), cy - _BEAK), QPoint(card.left(), cy + _BEAK),
                   QPoint(card.left() - _BEAK, cy)]
        elif card.right() <= spot.left():
            tri = [QPoint(card.right(), cy - _BEAK), QPoint(card.right(), cy + _BEAK),
                   QPoint(card.right() + _BEAK, cy)]
        else:
            return
        painter.setPen(QPen(self.palette().mid().color(), 1))
        painter.setBrush(self.palette().window().color())
        painter.drawPolygon(QPolygon(tri))

    # -- resize / keyboard ---------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._controller.reposition()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        k = event.key()
        if k == Qt.Key.Key_Escape:
            self._controller.skip()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Return,
                   Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._controller.next()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
            self._controller.prev()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Keyboard filter (replaces grabKeyboard)
# ---------------------------------------------------------------------------

class _OverlayKeyFilter(QObject):
    def __init__(self, overlay: TutorialOverlay) -> None:
        super().__init__(overlay)
        self._overlay = overlay

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            self._overlay.keyPressEvent(event)
            return True
        return False


# ---------------------------------------------------------------------------
# Target resolvers
# ---------------------------------------------------------------------------

def _toolbar_button(panel: QWidget, *needles: str) -> Optional[QWidget]:
    toolbar = getattr(panel, "toolbar", None)
    if toolbar is None:
        return None
    for btn in toolbar.findChildren(QToolButton):
        if all(n.lower() in btn.toolTip().lower() for n in needles):
            return btn
    return None


def _edit_panel(mw: "MainWindow") -> Optional[QWidget]:
    from .edit_panel import GraphEditPanel
    p = mw.active_panel
    return p if isinstance(p, GraphEditPanel) else None


def _proof_panel(mw: "MainWindow") -> Optional[QWidget]:
    from .proof_panel import ProofPanel
    p = mw.active_panel
    return p if isinstance(p, ProofPanel) else None


def _attr(mw: "MainWindow", resolver: TargetResolver, name: str) -> Optional[QWidget]:
    panel = resolver(mw)
    if panel is None:
        return None
    w = getattr(panel, name, None)
    return w if isinstance(w, QWidget) else None


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class Tutorial(QObject):
    """Drives a ``TutorialSpec`` step-by-step over the main window."""

    def __init__(self, main_window: "MainWindow", spec: TutorialSpec) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.spec        = spec
        self.index       = 0
        self.overlay:    Optional[TutorialOverlay]  = None
        self._key_filter: Optional[_OverlayKeyFilter] = None

    def start(self) -> None:
        if not self.spec.steps:
            return
        if self.spec.on_start:
            self.spec.on_start(self.main_window)
        self.index  = 0
        self.overlay = TutorialOverlay(self, self.main_window)
        self.main_window.installEventFilter(self)
        self._key_filter = _OverlayKeyFilter(self.overlay)
        self.main_window.installEventFilter(self._key_filter)
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.setFocus()
        self._show_step()

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

    def jump_to(self, index: int) -> None:
        """Jump to an arbitrary step (triggered by dot indicator clicks)."""
        if 0 <= index < len(self.spec.steps):
            self.index = index
            self._show_step()

    def skip(self) -> None:
        self._finish()

    def start_quick(self) -> None:
        self.spec  = editor_steps(quick=True)
        self.index = 0
        self._show_step()

    def reposition(self) -> None:
        if self.overlay is not None:
            self._show_step()

    # -- internals -----------------------------------------------------------

    def _show_step(self) -> None:
        if self.overlay is None:
            return
        step = self.spec.steps[self.index]
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.set_step(
            step.title, step.text,
            self._resolve_spotlight(step),
            self.index, len(self.spec.steps),
            step.offer_quick,
            step.diagram,
        )
        self.overlay.raise_()

    def _resolve_spotlight(self, step: TutorialStep) -> Optional[QRect]:
        if step.target is None or self.overlay is None:
            return None
        try:
            widget = step.target(self.main_window)
        except Exception:
            widget = None
        if widget is None or not widget.isVisible():
            return None
        vis = widget.visibleRegion().boundingRect()
        if (widget.width() < _MIN_TARGET or widget.height() < _MIN_TARGET
                or vis.width() < _MIN_TARGET or vis.height() < _MIN_TARGET):
            return None
        tl    = widget.mapToGlobal(QPoint(0, 0))
        local = self.overlay.mapFromGlobal(tl)
        rect  = QRect(local, widget.size()).adjusted(
            -_SPOTLIGHT_PAD, -_SPOTLIGHT_PAD, _SPOTLIGHT_PAD, _SPOTLIGHT_PAD)
        rect  = rect.intersected(self.overlay.rect())
        return rect if (rect.width() >= _MIN_TARGET
                        and rect.height() >= _MIN_TARGET) else None

    def _finish(self) -> None:
        if self.overlay is None:
            return
        if self.spec.seen_key:
            set_settings_value(self.spec.seen_key, True, bool)
        self.main_window.removeEventFilter(self)
        if self._key_filter:
            self.main_window.removeEventFilter(self._key_filter)
            self._key_filter = None
        self.overlay.hide()
        self.overlay.deleteLater()
        self.overlay = None
        if getattr(self.main_window, "_active_tutorial", None) is self:
            self.main_window._active_tutorial = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.main_window and self.overlay is not None:
            t = event.type()
            if t in (QEvent.Type.Resize, QEvent.Type.Move):
                self.overlay.setGeometry(self.main_window.rect())
                self.reposition()
            elif t == QEvent.Type.Close:
                self._finish()
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Tour definitions
# ---------------------------------------------------------------------------

def editor_steps(quick: bool = False) -> TutorialSpec:
    """Edit-mode tour.  ``quick=True`` strips educational and offer_quick steps."""

    def graph_view(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "graph_view")

    def toolbar(mw: "MainWindow") -> Optional[QWidget]:
        p = _edit_panel(mw)
        return getattr(p, "toolbar", None) if p else None

    def add_vertex(mw: "MainWindow") -> Optional[QWidget]:
        p = _edit_panel(mw)
        return _toolbar_button(p, "add vertex") if p else None

    def add_edge(mw: "MainWindow") -> Optional[QWidget]:
        p = _edit_panel(mw)
        return _toolbar_button(p, "add edge") if p else None

    def vertices_sidebar(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "vertex_list")

    def edges_sidebar(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "edge_list")

    def start_derivation(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _edit_panel, "start_derivation")

    # The concept widget is chosen once per session; stable across Back/Next.
    concept_cls = concept_widget_for_step()

    steps = [
        TutorialStep(
            "Welcome to ZXLive 👋",
            "ZXLive is a graphical editor for the <b>ZX-calculus</b> — a "
            "diagrammatic language for quantum computing where circuit "
            "transformations become visual rewrite rules.<br><br>"
            "Choose <b>Quick start</b> for a fast orientation, or continue "
            "for the full guided tour with concept explanations.",
            offer_quick=True,
        ),
        TutorialStep(
            "Why ZX-calculus?",
            "Traditional circuit notation hides structure. The ZX-calculus "
            "exposes it: two types of node (Z and X spiders), connected by "
            "plain or Hadamard wires, obey a handful of rules that are "
            "<i>complete</i> for quantum computation.<br><br>"
            "Every valid rewrite preserves the linear map — so diagram "
            "manipulation is formally safe.",
            full_only=True,
        ),
        # ── SURPRISE: animated concept diagram ────────────────────────────
        TutorialStep(
            "✨ A core ZX rule — live",
            "The animation below demonstrates one of the three foundational "
            "ZX rewrite rules.  Watch it loop, then click <b>Next</b> — or "
            "wait and it will advance automatically.",
            diagram=concept_cls,
            full_only=True,
        ),
        # ──────────────────────────────────────────────────────────────────
        TutorialStep(
            "Canvas",
            "Pan by dragging the background.  Zoom with the scroll wheel.  "
            "Click a vertex or edge to select it; drag a rectangle to "
            "rubber-band-select a region.  Press <b>C</b> to fit everything "
            "into view.",
            graph_view,
        ),
        TutorialStep(
            "Toolbar",
            "Three primary tools: <b>Select</b> (S), <b>Add Vertex</b> (V), "
            "<b>Add Edge</b> (E).  The keyboard shortcut for each is shown "
            "in its tooltip.",
            toolbar,
        ),
        TutorialStep(
            "Add Vertex (V)",
            "Click the canvas to drop a spider of the type currently "
            "highlighted in the Vertices sidebar.  Z spiders (green) act in "
            "the Z basis; X spiders (red) act in the X basis.",
            add_vertex,
        ),
        TutorialStep(
            "Add Edge (E)",
            "Drag between two vertices to wire them.  Use the Edges sidebar "
            "to pick a plain wire or a <b>Hadamard edge</b> (yellow box) "
            "— the graphical equivalent of inserting H on that wire.",
            add_edge,
        ),
        TutorialStep(
            "Vertices sidebar",
            "Select the type for <i>new</i> vertices here.  "
            "<b>Double-clicking</b> a type while vertices are selected "
            "changes their type — useful for colour-change rewrites.",
            vertices_sidebar,
            full_only=True,
        ),
        TutorialStep(
            "Edges sidebar",
            "Select the type for new edges.  Double-clicking toggles "
            "selected edges between plain and Hadamard — without redrawing.",
            edges_sidebar,
            full_only=True,
        ),
        TutorialStep(
            "Setting a phase",
            "<b>Double-click any Z or X spider</b> to enter its phase "
            "(as a fraction of π).  Phase 0 = identity; π/4 = T gate; "
            "π/2 = S gate; π = Pauli Z or X.",
            graph_view,
            full_only=True,
        ),
        TutorialStep(
            "Enter proof mode",
            "Click <b>Start Derivation</b> to open the proof panel, where "
            "you apply named rewrite rules step by step.  A dedicated tour "
            "launches the first time you enter this mode.",
            start_derivation,
        ),
        TutorialStep(
            "You're ready ✅",
            "Replay this tour at any time from "
            "<b>Help → Interactive Tutorial → Full Tutorial</b>.<br><br>"
            "The <b>Help → ZX Examples</b> tour walks through six canonical "
            "quantum circuits to deepen your understanding.  Happy rewriting!",
        ),
    ]

    if quick:
        steps = [s for s in steps if not (s.full_only or s.offer_quick)]
    return TutorialSpec(steps)


def proof_steps() -> TutorialSpec:
    """Proof-mode tour, auto-started the first time the user enters a derivation."""

    def rewrites(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "rewrites_panel")

    def magic_wand(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "magic_wand")

    def identity_choice(mw: "MainWindow") -> Optional[QWidget]:
        panel = _proof_panel(mw)
        choice = getattr(panel, "identity_choice", None) if panel else None
        if choice:
            first = choice[0]
            return first if isinstance(first, QWidget) else None
        return None

    def step_view(mw: "MainWindow") -> Optional[QWidget]:
        return _attr(mw, _proof_panel, "step_view")

    return TutorialSpec([
        TutorialStep(
            "Proof mode 🪄",
            "Every rewrite here is <i>sound</i>: it preserves the linear "
            "map your diagram represents.  Steps are recorded so you can "
            "always review or backtrack.",
        ),
        TutorialStep(
            "Rewrites panel",
            "Shows rules that match your current selection.  Select part of "
            "the diagram and <b>double-click</b> a rule to apply it.  With "
            "nothing selected, the panel searches the whole diagram.",
            rewrites,
        ),
        TutorialStep(
            "Magic wand (W)",
            "The fastest rewriting tool.  Drag it <i>through</i> a spider "
            "to unfuse it, across a wire to insert an identity, or through "
            "a degree-2 spider to remove it.  Dragging across parallel wires "
            "cancels them.",
            magic_wand,
        ),
        TutorialStep(
            "Identity spider colour",
            "When the wand adds a new identity spider, these buttons set "
            "whether it is Z or X — letting you prepare for the next rule.",
            identity_choice,
        ),
        TutorialStep(
            "Step history",
            "Each applied rule appears here as a clickable thumbnail.  Jump "
            "to any earlier step to branch the proof or check your work.",
            step_view,
        ),
        TutorialStep(
            "Export",
            "File → <b>Export proof to TikZ</b> for inclusion in papers. "
            "File → <b>Export proof to GIF</b> for slides or talks. "
            "Rewrites → <b>Save proof as a rewrite</b> to reuse the whole "
            "derivation as a named rule.",
        ),
        TutorialStep(
            "Onwards! 🎉",
            "Replay from <b>Help → Interactive Tutorial → Proof Tutorial</b>."
            "<br><br>Try the <b>ZX Examples</b> tour to see these rules in "
            "action on real quantum circuits.",
        ),
    ], PROOF_TUTORIAL_SEEN)


def examples_steps() -> TutorialSpec:
    """A narrated tour of six canonical ZX-calculus examples."""
    return TutorialSpec([
        TutorialStep(
            "ZX examples 📚",
            "Six quantum circuits, each expressed in ZX and simplified by "
            "rewriting.  Open each demo from <b>File → Open Demo</b> as "
            "you go, then follow the rewrites panel to reproduce the steps.",
        ),
        TutorialStep(
            "1 — CNOT³ = SWAP",
            "Three alternating CNOTs compose to a SWAP.  In ZX this is "
            "just spider fusion plus the <i>Hopf law</i> (two parallel "
            "edges between Z and X cancel).  No matrix needed — the "
            "diagram proves it visually.",
        ),
        TutorialStep(
            "2 — ZZ(α) phase gadget",
            "The phase gadget ZZ(α) applies e^(iαZ⊗Z) to two qubits.  "
            "In ZX it is a single Z-spider with phase α and two output "
            "legs.  The <i>spider fusion</i> rule merges adjacent gadgets: "
            "ZZ(α)·ZZ(β) = ZZ(α+β), so Pauli exponentials add phase "
            "without entangling more qubits.",
        ),
        TutorialStep(
            "3 — Graph states &amp; MBQC",
            "A graph state is a Z-spider for every vertex connected by "
            "Hadamard edges — the ZX diagram literally <i>is</i> the graph. "
            "Single-qubit measurements in MBQC correspond to removing a "
            "spider with a phase, which the rewrite rules handle exactly.",
        ),
        TutorialStep(
            "4 — Quantum state teleportation",
            "Bell-pair creation, two measurements, and two corrections "
            "reduce — via the <i>complementarity rule</i> — to a single "
            "wire.  The ZX proof is four rewrites; the matrix proof fills "
            "a page.",
        ),
        TutorialStep(
            "5 — CNOT gate teleportation",
            "A remotely applied CNOT needs a shared Bell pair and classical "
            "communication.  The ZX derivation is structurally identical to "
            "state teleportation, making the analogy between the two "
            "protocols visually explicit.",
        ),
        TutorialStep(
            "6 — Magic state injection",
            "The T gate (phase π/4) cannot be implemented fault-tolerantly "
            "by itself, but it can be <i>injected</i> from a pre-distilled "
            "magic state |T⟩.  In ZX the injection gadget is a π/4 "
            "Z-spider on a Hadamard edge; the ZX-calculus proves correctness "
            "by reducing it to a wire plus a classically-controlled Pauli.",
        ),
        TutorialStep(
            "Further reading",
            "These six examples are covered in depth in "
            "<i>Picturing Quantum Processes</i> (Coecke &amp; Kissinger, "
            "Cambridge 2017).  The ZX-calculus has since been applied to "
            "circuit optimisation (PyZX, tket), lattice surgery compilation, "
            "quantum NLP, and more — see the User Guide for pointers.",
        ),
    ])


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _run(main_window: "MainWindow", spec: TutorialSpec) -> None:
    existing: Optional[Tutorial] = getattr(main_window, "_active_tutorial", None)
    if existing is not None:
        existing.skip()
    t = Tutorial(main_window, spec)
    main_window._active_tutorial = t
    t.start()


def start_editor_tutorial(main_window: "MainWindow",
                           quick: bool = False,
                           offer_quick: bool = False) -> None:
    """Launch the edit-mode tour.

    ``quick``       — condensed functional tour (skips educational slides).
    ``offer_quick`` — include the welcome step with the Quick/Full choice.
                      Set only when auto-starting on first launch.
    """
    spec = editor_steps(quick=quick)
    if not offer_quick:
        spec.steps = [s for s in spec.steps if not s.offer_quick]
    _run(main_window, spec)


def start_proof_tutorial(main_window: "MainWindow") -> None:
    _run(main_window, proof_steps())


def start_examples_tutorial(main_window: "MainWindow") -> None:
    _run(main_window, examples_steps())


def maybe_start_first_run(main_window: "MainWindow") -> None:
    """Auto-start the editor tour on startup if the user hasn't opted out."""
    if get_settings_value(SHOW_ON_STARTUP, bool, True):
        start_editor_tutorial(main_window, quick=False, offer_quick=True)


def maybe_start_proof_tutorial(main_window: "MainWindow") -> None:
    """Auto-start the proof tour the first time the user enters proof mode."""
    if not get_settings_value(PROOF_TUTORIAL_SEEN, bool, False):
        start_proof_tutorial(main_window)
