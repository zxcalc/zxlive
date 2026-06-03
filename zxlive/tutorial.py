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

"""Interactive onboarding tutorial.

Overlays the existing UI instead of touching the panels: a dimming spotlight
punches click-through holes around the real toolbar buttons, sidebars and
vertices, and a coachmark walks through them. On the build steps it waits for
the user to actually do the action before advancing.

The rest of the app only calls start_main_tutorial (Help menu),
maybe_show_tutorial_on_first_run (first launch) and maybe_start_proof_tutorial
(first time proof mode opens).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation,
                            QRect, QRectF, Qt, QTimer, QVariantAnimation)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygon
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from .common import get_settings_value, set_settings_value
from .settings import display_setting

if TYPE_CHECKING:
    from .base_panel import BasePanel
    from .mainwindow import MainWindow


# Settings keys recording whether each part of the tutorial has been seen.
_MAIN_SEEN = "tutorial/main-seen"
_PROOF_SEEN = "tutorial/proof-seen"

# Visual constants.
ACCENT = "#8a63ff"
_HOLE_PADDING = 8
_CARD_WIDTH = 340


# Step definition

@dataclass
class Step:
    """One stop in the tutorial.

    ``target`` returns the widget(s) / graphics item(s) to spotlight (a single
    object or a list).  ``on_enter`` runs an optional ghost demo.  ``await_event``
    returns a Qt signal that, when emitted, means the user completed the step's
    action -- the tutorial then auto-advances.
    """
    title: str
    text: str
    target: Optional[Callable[["TutorialController"], object]] = None
    on_enter: Optional[Callable[["TutorialController"], None]] = None
    await_event: Optional[Callable[["TutorialController"], object]] = None
    hint: str = ""


# Spotlight overlay

class _SpotlightOverlay(QWidget):
    """A full-window dim layer with click-through holes punched around targets."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._holes: list[QRect] = []
        self._pulse = 0.0

        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)

    def _on_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    def set_holes(self, holes: list[QRect]) -> None:
        self._holes = [h.adjusted(-_HOLE_PADDING, -_HOLE_PADDING,
                                  _HOLE_PADDING, _HOLE_PADDING) for h in holes]
        # Punch the holes out of the widget so clicks pass through to the real UI.
        region = self.rect()
        from PySide6.QtGui import QRegion
        mask = QRegion(region)
        for h in self._holes:
            mask = mask.subtracted(QRegion(h, QRegion.RegionType.Rectangle))
        self.setMask(mask)
        if not self._holes:
            # No target: dim the whole window, no pulsing ring needed.
            self.clearMask()
            self._pulse_anim.stop()
        elif self._pulse_anim.state() != QVariantAnimation.State.Running:
            self._pulse_anim.start()
        self.update()

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 165 if display_setting.dark_mode else 140
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))

        # Glowing, gently pulsing ring around each hole.
        for h in self._holes:
            spread = 2 + 4 * self._pulse
            ring = QColor(ACCENT)
            ring.setAlpha(int(200 * (1.0 - 0.5 * self._pulse)))
            painter.setPen(QPen(ring, 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(h).adjusted(-spread, -spread, spread, spread), 10, 10)

    def mousePressEvent(self, event: QEvent) -> None:
        # Swallow clicks on the dimmed area so the user can't fiddle with hidden UI.
        event.accept()


# Coachmark (the speech bubble with Prev / Next / Skip)

class _Coachmark(QFrame):

    def __init__(self, parent: QWidget,
                 on_prev: Callable[[], None],
                 on_next: Callable[[], None],
                 on_skip: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setFixedWidth(_CARD_WIDTH)
        self.setObjectName("tutorialCoachmark")
        self.setStyleSheet(f"""
            QFrame#tutorialCoachmark {{
                background: palette(window);
                border: 2px solid {ACCENT};
                border-radius: 12px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        self._title = QLabel()
        title_font = QFont(display_setting.font)
        title_font.setBold(True)
        title_font.setPointSize(max(title_font.pointSize() + 2, 12))
        self._title.setFont(title_font)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._body)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {ACCENT}; font-style: italic;")
        layout.addWidget(self._hint)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self._skip = QPushButton("Skip")
        self._skip.setFlat(True)
        self._skip.clicked.connect(on_skip)
        controls.addWidget(self._skip)
        controls.addStretch(1)
        self._progress = QLabel()
        self._progress.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
        controls.addWidget(self._progress)
        self._prev = QPushButton("← Back")
        self._prev.clicked.connect(on_prev)
        controls.addWidget(self._prev)
        self._next = QPushButton("Next →")
        self._next.setDefault(True)
        self._next.clicked.connect(on_next)
        controls.addWidget(self._next)
        layout.addLayout(controls)

    def populate(self, step: Step, index: int, total: int,
                 awaiting: bool, is_last: bool) -> None:
        self._title.setText(step.title)
        self._body.setText(step.text)
        self._hint.setText(step.hint)
        self._hint.setVisible(bool(step.hint))
        self._progress.setText(f"{index + 1} / {total}")
        self._prev.setEnabled(index > 0)
        if awaiting:
            self._next.setText("Try it!")
            self._next.setEnabled(False)
        else:
            self._next.setText("Finish ✓" if is_last else "Next →")
            self._next.setEnabled(True)
        self.adjustSize()

    def flash_done(self) -> None:
        """Briefly confirm the user completed an action, then enable Next."""
        self._next.setText("Next →")
        self._next.setEnabled(True)


# Ghost pointer (animated "do it like this" finger)

class _GhostPointer(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(54, 54)
        self._phase = 0.0
        self._anim: Optional[QVariantAnimation] = None
        self._move_anim: Optional[QPropertyAnimation] = None
        self.hide()

    def _ping(self, loops: int = 3) -> None:
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(750)
        anim.setLoopCount(loops)
        anim.valueChanged.connect(self._on_phase)
        anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    def _on_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    def _center_on(self, point: QPoint) -> None:
        self.move(point - QPoint(self.width() // 2, self.height() // 2))

    def tap(self, point: QPoint) -> None:
        self._center_on(point)
        self.show()
        self.raise_()
        self._ping()

    def stroke(self, start: QPoint, end: QPoint,
               on_step: Optional[Callable[[QPoint], None]] = None) -> None:
        self._center_on(start)
        self.show()
        self.raise_()
        self._ping(loops=1)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setStartValue(start - QPoint(self.width() // 2, self.height() // 2))
        anim.setEndValue(end - QPoint(self.width() // 2, self.height() // 2))
        anim.setDuration(900)
        anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutCubic))
        if on_step is not None:
            anim.valueChanged.connect(
                lambda _v: on_step(self.pos() + QPoint(self.width() // 2, self.height() // 2)))
        anim.finished.connect(self.hide)
        anim.start()
        self._move_anim = anim

    def paintEvent(self, _event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        # Expanding ring.
        radius = 6 + 18 * self._phase
        ring = QColor(ACCENT)
        ring.setAlpha(int(200 * (1.0 - self._phase)))
        painter.setPen(QPen(ring, 3.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius, radius)
        # Solid dot.
        dot = QColor(ACCENT)
        dot.setAlpha(230)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(center, 7, 7)


# Controller / driver

class TutorialController(QObject):
    """Drives a sequence of :class:`Step` over the live ``MainWindow``."""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.win = win
        self._steps: list[Step] = []
        self._index = 0
        self._seen_key = _MAIN_SEEN
        self._awaiting = False
        self._await_obj: object = None
        self.overlay = _SpotlightOverlay(win)
        self.coachmark = _Coachmark(win, self._prev, self._next, self._skip)
        self.coachmark.hide()
        self.ghost = _GhostPointer(win)
        self._slide_anim: Optional[QPropertyAnimation] = None

    # -- public API --------------------------------------------------------

    def start(self, steps: list[Step], seen_key: str) -> None:
        if not steps:
            return
        self._steps = steps
        self._seen_key = seen_key
        self._index = 0
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

    # -- navigation --------------------------------------------------------

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

    # -- step rendering ----------------------------------------------------

    def _show_step(self) -> None:
        self._disconnect_await()
        step = self._steps[self._index]
        self._apply_visuals(step)

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

        self.coachmark.populate(
            step, self._index, len(self._steps),
            self._awaiting, self._index + 1 == len(self._steps))
        self._place_coachmark()

        if step.on_enter is not None:
            # Defer so the overlay/coachmark are laid out before the demo runs.
            QTimer.singleShot(120, lambda: self._run_on_enter(step))

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
            rect = self._rect_for(it)
            if rect is not None and rect.width() > 0 and rect.height() > 0:
                rects.append(rect)
        return rects

    def _rect_for(self, item: object) -> Optional[QRect]:
        if isinstance(item, QWidget):
            if not item.isVisible():
                return None
            top_left = item.mapTo(self.win, QPoint(0, 0))
            return QRect(top_left, item.size())
        # Otherwise assume a QGraphicsItem (e.g. a VItem) in the active view.
        panel = self.panel()
        if panel is None:
            return None
        view = panel.graph_view
        try:
            scene_rect = item.sceneBoundingRect()  # type: ignore[attr-defined]
        except Exception:
            return None
        poly: QPolygon = view.mapFromScene(scene_rect)
        vrect = poly.boundingRect()
        top_left = view.viewport().mapTo(self.win, vrect.topLeft())
        return QRect(top_left, vrect.size())

    def _place_coachmark(self) -> None:
        margin = 18
        win_rect = self.win.rect()
        card = self.coachmark
        card.adjustSize()
        cw, ch = card.width(), card.height()
        holes = self.overlay._holes

        if not holes:
            target = QPoint((win_rect.width() - cw) // 2,
                            (win_rect.height() - ch) // 2)
        else:
            union = holes[0]
            for h in holes[1:]:
                union = union.united(h)
            # Prefer right, then left, then below, then above the spotlight.
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
            x = max(margin, min(x, win_rect.width() - cw - margin))
            y = max(margin, min(y, win_rect.height() - ch - margin))
            target = QPoint(x, y)

        # Slide gently into place.
        start = target + QPoint(0, 14)
        anim = QPropertyAnimation(card, b"pos", self)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        anim.start()
        self._slide_anim = anim

    # -- "your turn" handling ---------------------------------------------

    def _on_await(self, *_args: object) -> None:
        if not self._awaiting:
            return
        self._awaiting = False
        self._disconnect_await()
        self.coachmark.flash_done()
        self._celebrate()
        QTimer.singleShot(750, self._auto_advance)

    def _auto_advance(self) -> None:
        # Only advance if we're still on the same (now-completed) step.
        if self.active and not self._awaiting:
            self._next()

    def _disconnect_await(self) -> None:
        if self._await_obj is not None:
            try:
                self._await_obj.disconnect(self._on_await)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._await_obj = None

    # -- ghost-demo helpers (used by step definitions) ---------------------

    def fit_view(self) -> None:
        panel = self.panel()
        if panel is not None and panel.graph_scene.g.num_vertices() > 0:
            try:
                panel.graph_view.fit_view()
            except Exception:
                pass

    def _viewport_point(self, dx: int = 0, dy: int = 0) -> Optional[QPoint]:
        panel = self.panel()
        if panel is None:
            return None
        view = panel.graph_view
        center = view.viewport().rect().center() + QPoint(dx, dy)
        return view.viewport().mapTo(self.win, center)

    def ghost_tap_canvas(self) -> None:
        point = self._viewport_point()
        if point is not None:
            self.ghost.tap(point)

    def ghost_stroke_canvas(self) -> None:
        start = self._viewport_point(-70, -45)
        end = self._viewport_point(70, 45)
        if start is not None and end is not None:
            self.ghost.stroke(start, end, on_step=self._sparkle_at_window_point)

    def _sparkle_at_window_point(self, win_point: QPoint) -> None:
        panel = self.panel()
        if panel is None:
            return
        view = panel.graph_view
        try:
            vp_point = view.viewport().mapFrom(self.win, win_point)
            scene_point = view.mapToScene(vp_point)
            view.sparkles.emit_sparkles(scene_point, 2)
        except Exception:
            pass

    def _celebrate(self) -> None:
        panel = self.panel()
        if panel is None:
            return
        view = panel.graph_view
        try:
            scene_center = view.mapToScene(view.viewport().rect().center())
            view.sparkles.emit_sparkles(scene_center, 25)
        except Exception:
            pass

    # -- keep everything aligned when the window moves/resizes --------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.win and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move) and self.active:
            self.overlay.setGeometry(self.win.rect())
            step = self._steps[self._index]
            self.overlay.set_holes(self._resolve_targets(step))
            self._place_coachmark()
        return super().eventFilter(obj, event)


# Target accessors (resolve real widgets / items at step-enter time)

def _tool_button(panel: "BasePanel", tooltip_substr: str) -> Optional[QWidget]:
    """Find a toolbar button by (a substring of) its tooltip.

    The edit-mode Select/Vertex/Edge buttons are local variables in
    ``editor_base_panel``, so we locate them through the toolbar rather than
    requiring those panels to expose new attributes.
    """
    from PySide6.QtWidgets import QToolButton
    for button in panel.toolbar.findChildren(QToolButton):
        if tooltip_substr.lower() in button.toolTip().lower():
            return button
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


# Step lists

def build_main_steps() -> list[Step]:
    return [
        Step(
            title="Welcome to ZXLive 👋",
            text="ZXLive lets you <b>draw</b> ZX-diagrams and then <b>prove</b> "
                 "things about them. This quick tour takes about a minute — you "
                 "can hit <i>Skip</i> any time.",
        ),
        Step(
            title="The canvas",
            text="This is your diagram. Drag the background to pan, "
                 "<b>Ctrl + scroll</b> to zoom, and press <b>C</b> to fit "
                 "everything in view.",
            target=_canvas,
            on_enter=lambda c: c.fit_view(),
        ),
        Step(
            title="Vertices sidebar",
            text="Pick what kind of node you'll draw here: <b>Z</b> and <b>X</b> "
                 "spiders, <b>Hadamard</b> boxes, <b>W</b> nodes, boundaries and "
                 "more. The highlighted type is what the Add Vertex tool drops.",
            target=lambda c: _attr(c, "vertex_list"),
        ),
        Step(
            title="Edges sidebar",
            text="Choose the wire type: a plain <b>Simple</b> edge or a dashed "
                 "<b>Hadamard</b> edge. Double-click a type to recolour selected "
                 "edges.",
            target=lambda c: _attr(c, "edge_list"),
        ),
        Step(
            title="Add a vertex",
            text="Select the <b>Add Vertex</b> tool (shortcut <b>v</b>), then "
                 "click an empty spot on the canvas to drop a spider.",
            target=lambda c: [_tool_button(c.panel(), "Add Vertex"), _canvas(c)],
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=lambda c: c.panel().graph_scene.vertex_added,
            hint="Your turn — drop a vertex on the canvas.",
        ),
        Step(
            title="Connect with an edge",
            text="Switch to the <b>Add Edge</b> tool (<b>e</b>) and drag from one "
                 "spider to another to wire them together.",
            target=lambda c: [_tool_button(c.panel(), "Add Edge"), _canvas(c)],
            await_event=lambda c: c.panel().graph_scene.edge_added,
            hint="Your turn — draw an edge between two spiders.",
        ),
        Step(
            title="Give a spider a phase",
            text="<b>Double-click</b> a Z or X spider to set its phase (try "
                 "<i>pi/2</i>). The phase is the angle that makes spiders "
                 "interesting!",
            target=_first_vertex,
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=lambda c: c.panel().graph_scene.vertex_double_clicked,
            hint="Your turn — double-click a spider.",
        ),
        Step(
            title="Start a proof",
            text="Happy with your diagram? Hit <b>Start Derivation</b> to enter "
                 "<b>proof mode</b>, where you transform it step by step. I'll "
                 "pop back in to show you around when you get there!",
            target=lambda c: _attr(c, "start_derivation"),
        ),
    ]


def build_proof_steps() -> list[Step]:
    return [
        Step(
            title="Proof mode 🧪",
            text="You're now deriving. The diagram on the left stays editable, "
                 "but every change is recorded as a reversible <b>step</b>.",
        ),
        Step(
            title="Proof steps",
            text="Each rewrite you apply shows up here. Click any step to jump "
                 "back and forth through your proof — nothing is ever lost.",
            target=lambda c: _attr(c, "step_view"),
        ),
        Step(
            title="Rewrites",
            text="These are the rules you can apply: fuse spiders, change "
                 "colours, remove identities and more. Hover a rule to preview "
                 "it, and right-click to apply it to your selection.",
            target=lambda c: _attr(c, "rewrites_panel"),
        ),
        Step(
            title="The magic wand 🪄",
            text="The wand is the fast way to rewrite. Pick it (<b>w</b>) and "
                 "<b>draw a stroke</b> through a spider to unfuse it, through a "
                 "wire to drop in an identity, or across parallel edges to cancel "
                 "them. It figures out the rule for you.",
            target=lambda c: [_attr(c, "magic_wand"), _canvas(c)],
            on_enter=lambda c: c.ghost_stroke_canvas(),
            await_event=lambda c: c.panel().graph_view.wand_trace_finished,
            hint="Your turn — pick the wand and slice through the diagram.",
        ),
        Step(
            title="Identity colour",
            text="When the wand adds an identity spider, this picks whether it's "
                 "a <b>Z</b> or an <b>X</b>. Small detail, big convenience.",
            target=lambda c: (_attr(c, "identity_choice") or [None])[0],
        ),
        Step(
            title="You're all set! 🎉",
            text="That's the whole loop: <b>draw</b>, <b>derive</b>, <b>prove</b>. "
                 "You can replay this tour any time from <b>Help → Tutorial</b>. "
                 "Have fun rewriting!",
            on_enter=lambda c: c._celebrate(),
        ),
    ]


# Entry points (the only things the rest of the app calls)

def _controller(win: "MainWindow") -> TutorialController:
    controller = getattr(win, "_tutorial_controller", None)
    if controller is None:
        controller = TutorialController(win)
        win._tutorial_controller = controller  # type: ignore[attr-defined]
    return controller


def _ensure_clean_canvas(win: "MainWindow") -> None:
    """Make sure the tour runs on a fresh, empty edit canvas.

    The build-along steps ("add a vertex", "draw an edge") only make sense on a
    blank slate, so if the current tab isn't an empty graph editor we open one.
    """
    from .edit_panel import GraphEditPanel
    panel = win.active_panel
    if not isinstance(panel, GraphEditPanel) or panel.graph_scene.g.num_vertices() > 0:
        win.new_graph(None, "Tutorial")


def start_main_tutorial(win: "MainWindow") -> None:
    """Start (or replay) the full tutorial. Wired to Help -> Tutorial."""
    controller = _controller(win)
    if controller.active:
        return
    # Replaying the main tour also re-arms the proof-mode section.
    set_settings_value(_PROOF_SEEN, False, bool)
    _ensure_clean_canvas(win)
    controller.start(build_main_steps(), _MAIN_SEEN)


def maybe_show_tutorial_on_first_run(win: "MainWindow") -> None:
    """Auto-start the tutorial the very first time ZXLive is opened."""
    if get_settings_value(_MAIN_SEEN, bool, False):
        return
    if win.active_panel is None:
        return
    QTimer.singleShot(400, lambda: start_main_tutorial(win))


def maybe_start_proof_tutorial(win: "MainWindow") -> None:
    """Show the proof-mode section the first time the user enters proof mode."""
    if get_settings_value(_PROOF_SEEN, bool, False):
        return
    controller = getattr(win, "_tutorial_controller", None)
    if controller is not None and controller.active:
        return  # don't stack on top of the main tour

    def _go() -> None:
        ctrl = _controller(win)
        if ctrl.active:
            return
        from .proof_panel import ProofPanel
        if not isinstance(win.active_panel, ProofPanel):
            return
        ctrl.start(build_proof_steps(), _PROOF_SEEN)

    QTimer.singleShot(300, _go)
