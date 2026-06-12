#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
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

"""Interactive onboarding tutorial.

Overlays the existing UI instead of touching the panels: a dimming spotlight
punches click-through holes around the real toolbar buttons, sidebars and
vertices, and a coachmark walks through them.  On the "your turn" steps it
waits for the user to actually perform the action before auto-advancing.

Public API (the only symbols the rest of the app ever imports):

    start_main_tutorial(win)              – wired to Help → Tutorial
    maybe_show_tutorial_on_first_run(win) – called once at startup in app.py
    maybe_start_proof_tutorial(win)       – called once when proof mode opens

Everything else is private to this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation,
    QRect, QRectF, Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QPolygon, QRegion,
)
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from .common import get_settings_value, set_settings_value
from .settings import display_setting

if TYPE_CHECKING:
    from .base_panel import BasePanel
    from .mainwindow import MainWindow



# Settings keys 

_MAIN_SEEN  = "tutorial/main-seen"
_PROOF_SEEN = "tutorial/proof-seen"


# Visual constants

ACCENT       = "#8a63ff"   # purple highlight used for spotlight ring / card border
_HOLE_PAD    = 10          # px of padding added around each spotlight target
_CARD_WIDTH  = 340         # fixed coachmark width in pixels
_SLIDE_MS    = 200         # coachmark slide-in animation duration
_ADVANCE_MS  = 700         # delay after a user completes an action before auto-advance
_FIRST_MS    = 420         # delay before auto-starting on first run



# Step definition

@dataclass
class Step:
    """One stop in the tutorial.

    Fields
    ------
    title       : bold heading shown in the coachmark.
    text        : HTML body copy.
    target      : callable(controller) → widget / VItem / list thereof, or None.
    on_enter    : optional callable run after the step is displayed (ghost demo etc.).
    await_event : callable(controller) → Qt signal.  When the signal fires the user
                  has completed the action and the tutorial auto-advances.
    hint        : short italic prompt shown in accent colour (e.g. "Your turn …").
    """
    title:       str
    text:        str
    target:      Optional[Callable[["TutorialController"], object]] = None
    on_enter:    Optional[Callable[["TutorialController"], None]]   = None
    await_event: Optional[Callable[["TutorialController"], object]] = None
    hint:        str = ""



# Spotlight overlay

class _SpotlightOverlay(QWidget):
    """Full-window dim layer with click-through holes punched around targets."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._holes:  list[QRect] = []
        self._pulse:  float       = 0.0

        # Pulsing ring animation
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.SineCurve))
        self._pulse_anim.valueChanged.connect(self._on_pulse)

    # ------------------------------------------------------------------

    def _on_pulse(self, value: float) -> None:
        self._pulse = float(value)
        self.update()

    def set_holes(self, holes: list[QRect]) -> None:
        self._holes = [
            h.adjusted(-_HOLE_PAD, -_HOLE_PAD, _HOLE_PAD, _HOLE_PAD)
            for h in holes
        ]
        # Punch the holes out so mouse events reach the real controls.
        mask = QRegion(self.rect())
        for h in self._holes:
            mask = mask.subtracted(QRegion(h, QRegion.RegionType.Rectangle))
        if self._holes:
            self.setMask(mask)
            if self._pulse_anim.state() != QVariantAnimation.State.Running:
                self._pulse_anim.start()
        else:
            self.clearMask()
            self._pulse_anim.stop()
        self.update()

    # ------------------------------------------------------------------

    def paintEvent(self, _event: QEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dim everything
        dim_alpha = 165 if display_setting.dark_mode else 130
        painter.fillRect(self.rect(), QColor(0, 0, 0, dim_alpha))

        # Pulsing accent ring around each hole
        for h in self._holes:
            spread = 2.0 + 5.0 * self._pulse
            ring = QColor(ACCENT)
            ring.setAlpha(int(210 * (1.0 - 0.55 * self._pulse)))
            painter.setPen(QPen(ring, 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(h).adjusted(-spread, -spread, spread, spread), 10, 10
            )

    def mousePressEvent(self, event: QEvent) -> None:  # type: ignore[override]
        # Swallow clicks on the dimmed area so users can't accidentally interact.
        event.accept()

    def resizeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update()



# Coachmark (speech bubble with navigation controls)

class _Coachmark(QFrame):
    """Speech-bubble card: title + body + optional hint + Prev/Next/Skip."""

    def __init__(
        self,
        parent: QWidget,
        on_prev: Callable[[], None],
        on_next: Callable[[], None],
        on_skip: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setFixedWidth(_CARD_WIDTH)
        self.setObjectName("tutorialCoachmark")
        self._apply_stylesheet()

        # Drop shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(8)

        # Title
        self._title = QLabel()
        title_font = QFont(display_setting.font)
        title_font.setBold(True)
        title_font.setPointSize(max(title_font.pointSize() + 2, 12))
        self._title.setFont(title_font)
        self._title.setWordWrap(True)
        root.addWidget(self._title)

        # Body
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._body)

        # Hint (accent-coloured, italic)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {ACCENT}; font-style: italic;")
        root.addWidget(self._hint)

        # Navigation row
        nav = QHBoxLayout()
        nav.setSpacing(6)

        self._skip = QPushButton("Skip tutorial")
        self._skip.setFlat(True)
        self._skip.setStyleSheet(
            "QPushButton { color: palette(mid); }"
            "QPushButton:hover { color: palette(text); }"
        )
        self._skip.clicked.connect(on_skip)
        nav.addWidget(self._skip)

        nav.addStretch(1)

        self._progress = QLabel()
        self._progress.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 12px;")
        nav.addWidget(self._progress)

        self._prev = QPushButton("← Back")
        self._prev.setFixedWidth(72)
        self._prev.clicked.connect(on_prev)
        nav.addWidget(self._prev)

        self._next = QPushButton("Next →")
        self._next.setFixedWidth(80)
        self._next.setDefault(True)
        self._next.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; border-radius: 5px; }}"
            f"QPushButton:hover {{ background: #9d7dff; }}"
            f"QPushButton:disabled {{ background: palette(mid); color: palette(midlight); }}"
        )
        self._next.clicked.connect(on_next)
        nav.addWidget(self._next)

        root.addLayout(nav)

    # ------------------------------------------------------------------

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#tutorialCoachmark {{
                background: palette(window);
                border: 2px solid {ACCENT};
                border-radius: 14px;
            }}
            """
        )

    def populate(
        self,
        step: Step,
        index: int,
        total: int,
        awaiting: bool,
        is_last: bool,
    ) -> None:
        self._title.setText(step.title)
        self._body.setText(step.text)
        self._hint.setText(step.hint)
        self._hint.setVisible(bool(step.hint))
        self._progress.setText(f"{index + 1} / {total}")
        self._prev.setEnabled(index > 0)
        if awaiting:
            self._next.setText("Try it ↑")
            self._next.setEnabled(False)
        elif is_last:
            self._next.setText("Finish ✓")
            self._next.setEnabled(True)
        else:
            self._next.setText("Next →")
            self._next.setEnabled(True)
        self.adjustSize()

    def unlock_next(self, is_last: bool) -> None:
        """Called once the user completes an await_event action."""
        self._next.setText("Finish ✓" if is_last else "Next →")
        self._next.setEnabled(True)
        # Brief green flash to celebrate
        self._next.setStyleSheet(
            "QPushButton { background: #2da860; color: white; border-radius: 5px; }"
        )
        QTimer.singleShot(
            600,
            lambda: self._next.setStyleSheet(
                f"QPushButton {{ background: {ACCENT}; color: white; border-radius: 5px; }}"
                f"QPushButton:hover {{ background: #9d7dff; }}"
                f"QPushButton:disabled {{ background: palette(mid); color: palette(midlight); }}"
            ),
        )



# Ghost pointer 

class _GhostPointer(QWidget):
    """Translucent animated dot that demos where to click or drag."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(56, 56)
        self._phase: float = 0.0
        self._phase_anim: Optional[QVariantAnimation]   = None
        self._move_anim:  Optional[QPropertyAnimation]  = None
        self.hide()

    # ------------------------------------------------------------------

    def _start_phase(self, loops: int = 3) -> None:
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(700)
        anim.setLoopCount(loops)
        anim.valueChanged.connect(self._set_phase)
        anim.finished.connect(self.hide)
        anim.start()
        self._phase_anim = anim

    def _set_phase(self, value: float) -> None:
        self._phase = float(value)
        self.update()

    def _center_on(self, point: QPoint) -> None:
        self.move(point - QPoint(self.width() // 2, self.height() // 2))

    # ------------------------------------------------------------------

    def tap(self, point: QPoint) -> None:
        """Show a pulsing tap at *point* (in parent/window coordinates)."""
        self._center_on(point)
        self.show()
        self.raise_()
        self._start_phase(loops=3)

    def stroke(
        self,
        start: QPoint,
        end:   QPoint,
        on_step: Optional[Callable[[QPoint], None]] = None,
    ) -> None:
        """Animate a drag from *start* to *end*."""
        self._center_on(start)
        self.show()
        self.raise_()
        self._start_phase(loops=1)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setStartValue(start - QPoint(self.width() // 2, self.height() // 2))
        anim.setEndValue(end   - QPoint(self.width() // 2, self.height() // 2))
        anim.setDuration(950)
        anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutCubic))
        if on_step is not None:
            anim.valueChanged.connect(
                lambda _: on_step(
                    self.pos() + QPoint(self.width() // 2, self.height() // 2)
                )
            )
        anim.finished.connect(self.hide)
        anim.start()
        self._move_anim = anim

    # ------------------------------------------------------------------

    def paintEvent(self, _event: QEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()

        # Expanding ring
        radius = 7 + 17 * self._phase
        ring = QColor(ACCENT)
        ring.setAlpha(int(210 * (1.0 - self._phase)))
        painter.setPen(QPen(ring, 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, int(radius), int(radius))

        # Solid centre dot
        dot = QColor(ACCENT)
        dot.setAlpha(235)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(center, 7, 7)


# ---------------------------------------------------------------------------
# Tutorial controller
# ---------------------------------------------------------------------------

class TutorialController(QObject):
    """Drives a sequence of :class:`Step` objects over the live ``MainWindow``.

    Lifecycle
    ---------
    1. ``start(steps, seen_key)`` — installs the overlay, shows step 0.
    2. User clicks Next / Prev / Skip, or completes an ``await_event`` action.
    3. ``_finish()`` — tears down the overlay and records the seen-flag.
    """

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.win = win
        self._steps:      list[Step]  = []
        self._index:      int         = 0
        self._seen_key:   str         = _MAIN_SEEN
        self._awaiting:   bool        = False
        self._await_obj:  object      = None

        self.overlay   = _SpotlightOverlay(win)
        self.coachmark = _Coachmark(win, self._prev, self._next, self._skip)
        self.coachmark.hide()
        self.ghost     = _GhostPointer(win)

        self._slide_anim: Optional[QPropertyAnimation] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, steps: list[Step], seen_key: str) -> None:
        if not steps:
            return
        self._steps    = steps
        self._seen_key = seen_key
        self._index    = 0

        self.win.installEventFilter(self)
        self.overlay.setGeometry(self.win.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.coachmark.show()
        self.coachmark.raise_()
        self._show_step()

    @property
    def active(self) -> bool:
        return self.overlay.isVisible()

    def panel(self) -> Optional["BasePanel"]:
        return self.win.active_panel

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _next(self) -> None:
        if self._index + 1 >= len(self._steps):
            self._finish()
        else:
            self._index += 1
            self._show_step()

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_step()

    def _skip(self) -> None:
        self._finish()

    def _finish(self) -> None:
        self._disconnect_await()
        set_settings_value(self._seen_key, True, bool)
        self.win.removeEventFilter(self)
        self.ghost.hide()
        self.overlay.hide()
        self.coachmark.hide()

    # ------------------------------------------------------------------
    # Step rendering
    # ------------------------------------------------------------------

    def _show_step(self) -> None:
        self._disconnect_await()
        step = self._steps[self._index]

        # Spotlight + overlay geometry
        self._apply_visuals(step)

        # Wire up the "your turn" signal if present
        self._awaiting = step.await_event is not None
        if self._awaiting:
            try:
                signal = step.await_event(self)
            except Exception:
                signal = None
            if signal is not None:
                signal.connect(self._on_await)
                self._await_obj = signal
            else:
                self._awaiting = False

        is_last = self._index + 1 == len(self._steps)
        self.coachmark.populate(step, self._index, len(self._steps), self._awaiting, is_last)
        self._place_coachmark()

        # Ghost demo is deferred so the overlay is painted first
        if step.on_enter is not None:
            QTimer.singleShot(130, lambda: self._run_on_enter(step))

    def _run_on_enter(self, step: Step) -> None:
        if self._steps and self._steps[self._index] is step and step.on_enter:
            try:
                step.on_enter(self)
            except Exception:
                pass

    def _apply_visuals(self, step: Step) -> None:
        self.overlay.setGeometry(self.win.rect())
        holes = self._resolve_targets(step)
        self.overlay.set_holes(holes)
        self.overlay.raise_()
        self.coachmark.raise_()

    def _resolve_targets(self, step: Step) -> list[QRect]:
        if step.target is None:
            return []
        try:
            result = step.target(self)
        except Exception:
            return []
        if result is None:
            return []
        items = result if isinstance(result, (list, tuple)) else [result]
        rects: list[QRect] = []
        for it in items:
            r = self._rect_for(it)
            if r is not None and r.width() > 0 and r.height() > 0:
                rects.append(r)
        return rects

    def _rect_for(self, item: object) -> Optional[QRect]:
        """Convert a widget or QGraphicsItem to a QRect in window coordinates."""
        if isinstance(item, QWidget):
            if not item.isVisible():
                return None
            top_left = item.mapTo(self.win, QPoint(0, 0))
            return QRect(top_left, item.size())

        # Assume a QGraphicsItem in the active panel's scene
        panel = self.panel()
        if panel is None:
            return None
        view = panel.graph_view
        try:
            scene_rect: QRectF = item.sceneBoundingRect()   # type: ignore[attr-defined]
        except Exception:
            return None
        poly: QPolygon = view.mapFromScene(scene_rect)
        vrect = poly.boundingRect()
        top_left = view.viewport().mapTo(self.win, vrect.topLeft())
        return QRect(top_left, vrect.size())

    # ------------------------------------------------------------------
    # Coachmark placement
    # ------------------------------------------------------------------

    def _place_coachmark(self) -> None:
        margin   = 18
        win_rect = self.win.rect()
        card     = self.coachmark
        card.adjustSize()
        cw, ch = card.width(), card.height()
        holes  = self.overlay._holes

        if not holes:
            target = QPoint(
                (win_rect.width()  - cw) // 2,
                (win_rect.height() - ch) // 2,
            )
        else:
            union = holes[0]
            for h in holes[1:]:
                union = union.united(h)

            # Prefer: right → left → below → above
            if union.right() + margin + cw <= win_rect.width():
                x = union.right() + margin
                y = union.center().y() - ch // 2
            elif union.left() - margin - cw >= 0:
                x = union.left() - margin - cw
                y = union.center().y() - ch // 2
            elif union.bottom() + margin + ch <= win_rect.height():
                x = union.center().x() - cw // 2
                y = union.bottom() + margin
            else:
                x = union.center().x() - cw // 2
                y = union.top() - margin - ch

            x = max(margin, min(x, win_rect.width()  - cw - margin))
            y = max(margin, min(y, win_rect.height() - ch - margin))
            target = QPoint(x, y)

        # Gentle slide-in from slightly below
        start = target + QPoint(0, 16)
        anim  = QPropertyAnimation(card, b"pos", self)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setDuration(_SLIDE_MS)
        anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        anim.start()
        self._slide_anim = anim

    # ------------------------------------------------------------------
    # "Your turn" handling
    # ------------------------------------------------------------------

    def _on_await(self, *_args: object) -> None:
        if not self._awaiting:
            return
        self._awaiting = False
        self._disconnect_await()
        is_last = self._index + 1 == len(self._steps)
        self.coachmark.unlock_next(is_last)
        self._celebrate()
        QTimer.singleShot(_ADVANCE_MS, self._auto_advance)

    def _auto_advance(self) -> None:
        if self.active and not self._awaiting:
            self._next()

    def _disconnect_await(self) -> None:
        if self._await_obj is not None:
            try:
                self._await_obj.disconnect(self._on_await)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._await_obj = None

    # ------------------------------------------------------------------
    # Ghost-demo helpers (called from step on_enter lambdas)
    # ------------------------------------------------------------------

    def fit_view(self) -> None:
        panel = self.panel()
        if panel is not None and panel.graph_scene.g.num_vertices() > 0:
            try:
                panel.graph_view.fit_view()
            except Exception:
                pass

    def _viewport_center(self, dx: int = 0, dy: int = 0) -> Optional[QPoint]:
        panel = self.panel()
        if panel is None:
            return None
        view   = panel.graph_view
        center = view.viewport().rect().center() + QPoint(dx, dy)
        return view.viewport().mapTo(self.win, center)

    def ghost_tap_canvas(self) -> None:
        pt = self._viewport_center()
        if pt is not None:
            self.ghost.tap(pt)

    def ghost_stroke_canvas(self) -> None:
        start = self._viewport_center(-80, -50)
        end   = self._viewport_center( 80,  50)
        if start is not None and end is not None:
            self.ghost.stroke(start, end, on_step=self._sparkle_along_stroke)

    def _sparkle_along_stroke(self, win_point: QPoint) -> None:
        panel = self.panel()
        if panel is None:
            return
        view = panel.graph_view
        try:
            vp_pt    = view.viewport().mapFrom(self.win, win_point)
            scene_pt = view.mapToScene(vp_pt)
            view.sparkles.emit_sparkles(scene_pt, 2)
        except Exception:
            pass

    def _celebrate(self) -> None:
        panel = self.panel()
        if panel is None:
            return
        view = panel.graph_view
        try:
            scene_center = view.mapToScene(view.viewport().rect().center())
            view.sparkles.emit_sparkles(scene_center, 30)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Keep overlay aligned when the window resizes / moves
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            obj is self.win
            and event.type() in (QEvent.Type.Resize, QEvent.Type.Move)
            and self.active
        ):
            self.overlay.setGeometry(self.win.rect())
            step = self._steps[self._index]
            self.overlay.set_holes(self._resolve_targets(step))
            self._place_coachmark()
        return super().eventFilter(obj, event)


# ---------------------------------------------------------------------------
# Target accessors
# ---------------------------------------------------------------------------

def _tool_button(panel: "BasePanel", tooltip_substr: str) -> Optional[QWidget]:
    """Find a toolbar QToolButton by a substring of its tooltip text."""
    from PySide6.QtWidgets import QToolButton
    for btn in panel.toolbar.findChildren(QToolButton):
        if tooltip_substr.lower() in btn.toolTip().lower():
            return btn
    return None


def _canvas(c: TutorialController) -> Optional[QWidget]:
    panel = c.panel()
    return panel.graph_view if panel is not None else None


def _first_vertex(c: TutorialController) -> object:
    panel = c.panel()
    if panel is None:
        return None
    vmap = panel.graph_scene.vertex_map
    return next(iter(vmap.values()), None) or panel.graph_view


def _attr(c: TutorialController, name: str) -> object:
    return getattr(c.panel(), name, None)


# ---------------------------------------------------------------------------
# Main-tutorial step list
# ---------------------------------------------------------------------------

def build_main_steps() -> list[Step]:
    """Steps for the initial build-along walkthrough."""
    return [
        # ------------------------------------------------------------------
        # 0 – Welcome
        # ------------------------------------------------------------------
        Step(
            title="Welcome to ZXLive 👋",
            text=(
                "ZXLive lets you <b>draw</b> ZX-diagrams and then <b>prove</b> "
                "things about them using rewrite rules from the ZX-calculus.<br><br>"
                "This quick tour takes about a minute — hit <i>Skip tutorial</i> any time."
            ),
        ),
        # ------------------------------------------------------------------
        # 1 – Canvas overview
        # ------------------------------------------------------------------
        Step(
            title="The canvas",
            text=(
                "This is your diagram workspace. <b>Drag</b> the background to pan, "
                "<b>Ctrl + scroll</b> (or pinch) to zoom, and press <b>C</b> to fit "
                "everything back into view."
            ),
            target=_canvas,
            on_enter=lambda c: c.fit_view(),
        ),
        # ------------------------------------------------------------------
        # 2 – Vertex type sidebar
        # ------------------------------------------------------------------
        Step(
            title="Vertex types",
            text=(
                "This sidebar lists every node type you can draw: "
                "<b>Z-spiders</b> (green), <b>X-spiders</b> (red), "
                "<b>Hadamard</b> boxes, <b>W-nodes</b>, boundary inputs/outputs, "
                "and more.<br><br>"
                "The highlighted entry is what the <i>Add Vertex</i> tool will drop."
            ),
            target=lambda c: _attr(c, "vertex_list"),
        ),
        # ------------------------------------------------------------------
        # 3 – Edge type sidebar
        # ------------------------------------------------------------------
        Step(
            title="Edge types",
            text=(
                "Choose the wire style here: a plain <b>Simple</b> edge or a "
                "dashed <b>Hadamard</b> edge (equivalent to putting a Hadamard "
                "box on the wire).<br><br>"
                "Double-click a type to recolour all <i>selected</i> edges at once."
            ),
            target=lambda c: _attr(c, "edge_list"),
        ),
        # ------------------------------------------------------------------
        # 4 – Add Vertex (interactive)
        # ------------------------------------------------------------------
        Step(
            title="Add a vertex",
            text=(
                "Select the <b>Add Vertex</b> tool from the toolbar — or press "
                "<b>v</b> — then click an empty spot on the canvas to place a spider."
            ),
            target=lambda c: [
                _tool_button(c.panel(), "Add Vertex"),
                _canvas(c),
            ],
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=lambda c: c.panel().graph_scene.vertex_added,
            hint="Your turn — drop a vertex somewhere on the canvas.",
        ),
        # ------------------------------------------------------------------
        # 5 – Add Edge (interactive)
        # ------------------------------------------------------------------
        Step(
            title="Connect with an edge",
            text=(
                "Switch to the <b>Add Edge</b> tool (<b>e</b>) and drag from one "
                "spider to another to wire them together."
            ),
            target=lambda c: [
                _tool_button(c.panel(), "Add Edge"),
                _canvas(c),
            ],
            await_event=lambda c: c.panel().graph_scene.edge_added,
            hint="Your turn — draw an edge between two spiders.",
        ),
        # ------------------------------------------------------------------
        # 6 – Set a phase (interactive)
        # ------------------------------------------------------------------
        Step(
            title="Give a spider a phase",
            text=(
                "<b>Double-click</b> any Z or X spider to open the phase editor. "
                "Type a value like <code>pi/2</code> or <code>3*pi/4</code>.<br><br>"
                "Phases are what give spiders their computational meaning in the "
                "ZX-calculus."
            ),
            target=_first_vertex,
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=lambda c: c.panel().graph_scene.vertex_double_clicked,
            hint="Your turn — double-click a spider to set its phase.",
        ),
        # ------------------------------------------------------------------
        # 7 – Select tool
        # ------------------------------------------------------------------
        Step(
            title="Selecting and moving",
            text=(
                "The <b>Select</b> tool (<b>s</b> or <b>Esc</b>) lets you click or "
                "rubber-band-select vertices, then drag them around.<br><br>"
                "<b>Delete</b> removes the selection; <b>Ctrl+Z</b> undoes."
            ),
            target=lambda c: _tool_button(c.panel(), "Select"),
        ),
        # ------------------------------------------------------------------
        # 8 – Start Derivation
        # ------------------------------------------------------------------
        Step(
            title="Start a proof",
            text=(
                "Happy with your diagram? Hit <b>Start Derivation</b> to enter "
                "<b>proof mode</b>.<br><br>"
                "Every rewrite you apply is recorded as a reversible step, so "
                "nothing is ever lost. I'll pop back to show you around proof "
                "mode when you get there!"
            ),
            target=lambda c: _attr(c, "start_derivation"),
        ),
    ]


# ---------------------------------------------------------------------------
# Proof-mode tutorial step list
# ---------------------------------------------------------------------------

def build_proof_steps() -> list[Step]:
    """Steps shown the first time the user enters proof mode."""
    return [
        # ------------------------------------------------------------------
        # 0 – Proof mode intro
        # ------------------------------------------------------------------
        Step(
            title="Proof mode 🧪",
            text=(
                "You're now in derivation mode. The diagram on the left is still "
                "editable, but every change is <b>recorded</b> as a named, "
                "reversible step."
            ),
        ),
        # ------------------------------------------------------------------
        # 1 – Proof step list
        # ------------------------------------------------------------------
        Step(
            title="Proof steps",
            text=(
                "Every rewrite you apply appears here as a numbered step. "
                "Click any step to <b>jump back</b> to that point in your proof — "
                "future steps are preserved so you can explore branches freely."
            ),
            target=lambda c: _attr(c, "step_view"),
        ),
        # ------------------------------------------------------------------
        # 2 – Rewrites panel
        # ------------------------------------------------------------------
        Step(
            title="Rewrite rules",
            text=(
                "This panel lists every rule you can apply: spider fusion, colour "
                "change, identity removal, bialgebra, and more.<br><br>"
                "Hover a rule to <b>preview</b> the match highlights on the diagram. "
                "Right-click (or press Enter) to apply it to the current selection."
            ),
            target=lambda c: _attr(c, "rewrites_panel"),
        ),
        # ------------------------------------------------------------------
        # 3 – Magic wand (interactive)
        # ------------------------------------------------------------------
        Step(
            title="The magic wand 🪄",
            text=(
                "The wand is the fastest way to rewrite. Pick it (<b>w</b>) and "
                "<b>draw a stroke</b> through the diagram:<br>"
                "• <i>Through a spider</i> — unfuses it<br>"
                "• <i>Through a wire</i>   — inserts an identity<br>"
                "• <i>Across two parallel edges</i> — cancels them<br><br>"
                "The wand figures out the correct rule automatically."
            ),
            target=lambda c: [
                _attr(c, "magic_wand"),
                _canvas(c),
            ],
            on_enter=lambda c: c.ghost_stroke_canvas(),
            await_event=lambda c: c.panel().graph_view.wand_trace_finished,
            hint="Your turn — pick the wand and slice through the diagram.",
        ),
        # ------------------------------------------------------------------
        # 4 – Identity colour chooser
        # ------------------------------------------------------------------
        Step(
            title="Identity colour",
            text=(
                "When the wand inserts a new identity spider, this toggle lets "
                "you choose whether it should be a <b>Z-spider</b> or an "
                "<b>X-spider</b> — a small detail that matters for keeping your "
                "proof colour-consistent."
            ),
            target=lambda c: (
                _attr(c, "identity_choice") or [None]
            )[0],
        ),
        # ------------------------------------------------------------------
        # 5 – Finish
        # ------------------------------------------------------------------
        Step(
            title="You're all set! 🎉",
            text=(
                "That's the complete loop: <b>draw</b>, <b>derive</b>, "
                "<b>prove</b>.<br><br>"
                "You can replay this tour any time from "
                "<b>Help → Tutorial</b>. Have fun rewriting!"
            ),
            on_enter=lambda c: c._celebrate(),
        ),
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _controller(win: "MainWindow") -> TutorialController:
    """Return (or lazily create) the single TutorialController for *win*."""
    ctrl = getattr(win, "_tutorial_controller", None)
    if ctrl is None:
        ctrl = TutorialController(win)
        win._tutorial_controller = ctrl  # type: ignore[attr-defined]
    return ctrl


def _ensure_clean_canvas(win: "MainWindow") -> None:
    """Make sure the main tutorial runs on a fresh, empty edit canvas.

    The build-along steps ("add a vertex", "draw an edge") only make sense on
    a blank slate, so if the current tab is not an empty graph editor we open
    one before starting.
    """
    from .edit_panel import GraphEditPanel
    panel = win.active_panel
    if (
        not isinstance(panel, GraphEditPanel)
        or panel.graph_scene.g.num_vertices() > 0
    ):
        win.new_graph(None, "Tutorial")


# ---------------------------------------------------------------------------
# Public entry points  ← the only things the rest of the app ever calls
# ---------------------------------------------------------------------------

def start_main_tutorial(win: "MainWindow") -> None:
    """Start (or replay) the full build-along tutorial.

    Wired to **Help → Tutorial** in the menu.
    Re-arms the proof-mode section so it will play again the next time
    the user enters proof mode.
    """
    ctrl = _controller(win)
    if ctrl.active:
        return
    # Re-arm the proof section so it plays again on the next derivation.
    set_settings_value(_PROOF_SEEN, False, bool)
    _ensure_clean_canvas(win)
    ctrl.start(build_main_steps(), _MAIN_SEEN)


def maybe_show_tutorial_on_first_run(win: "MainWindow") -> None:
    """Auto-start the tutorial the very first time ZXLive is launched.

    Called once from ``app.py`` after the main window is shown.
    Does nothing on subsequent runs.
    """
    if get_settings_value(_MAIN_SEEN, bool, False):
        return
    if win.active_panel is None:
        return
    QTimer.singleShot(_FIRST_MS, lambda: start_main_tutorial(win))


def maybe_start_proof_tutorial(win: "MainWindow") -> None:
    """Show the proof-mode walkthrough the first time the user enters proof mode.

    Called once from the proof panel after it finishes initialising.
    Does nothing if the proof section has already been seen, or if another
    tutorial section is currently active.
    """
    if get_settings_value(_PROOF_SEEN, bool, False):
        return
    ctrl = getattr(win, "_tutorial_controller", None)
    if ctrl is not None and ctrl.active:
        return  # Don't stack on top of the main tour

    def _go() -> None:
        c = _controller(win)
        if c.active:
            return
        from .proof_panel import ProofPanel
        if not isinstance(win.active_panel, ProofPanel):
            return
        c.start(build_proof_steps(), _PROOF_SEEN)

    QTimer.singleShot(320, _go)
