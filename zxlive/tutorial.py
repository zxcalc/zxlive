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
the user to actually do the action before advancing (revisiting a completed
step via Back does not require redoing it).

MainWindow owns a TutorialController instance; the rest of the app only calls
start_main_tutorial (Help menu), maybe_show_tutorial_on_first_run (first
launch) and maybe_start_proof_tutorial (first time proof mode opens).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, TYPE_CHECKING, Union

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation,
                            QRect, QRectF, Qt, QTimer, QVariantAnimation, SignalInstance)
from PySide6.QtGui import (QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPen,
                           QRegion)
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGraphicsItem,
                               QHBoxLayout, QLabel, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)
from pyzx.utils import VertexType

from .common import GraphT, get_settings_value, new_graph, set_settings_value
from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .settings import display_setting

if TYPE_CHECKING:
    from .base_panel import BasePanel
    from .graphview import GraphView
    from .mainwindow import MainWindow


# Settings keys recording whether each part of the tutorial has been seen.
_MAIN_SEEN = "tutorial/main-seen"
_PROOF_SEEN = "tutorial/proof-seen"

# Visual constants.
ACCENT = "#8a63ff"
_HOLE_PADDING = 8
_CARD_WIDTH = 340

# A step can spotlight widgets and/or graphics items (e.g. a VItem in the scene).
TargetItem = Union[QWidget, QGraphicsItem]
TargetSpec = Union[TargetItem, Sequence[Optional[TargetItem]], None]


# Step definition

@dataclass
class Step:
    """One stop in the tutorial.

    ``target`` returns the widget(s) / graphics item(s) to spotlight.
    ``on_enter`` runs an optional ghost demo. ``await_event`` returns a Qt
    signal that, when emitted, means the user completed the step's action --
    the tutorial then auto-advances.
    """
    title: str
    text: str
    target: Optional[Callable[["TutorialController"], TargetSpec]] = None
    on_enter: Optional[Callable[["TutorialController"], None]] = None
    await_event: Optional[Callable[["TutorialController"], Optional[SignalInstance]]] = None
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
        self.hide()

    @property
    def holes(self) -> list[QRect]:
        return self._holes

    def _on_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    def set_holes(self, holes: list[QRect]) -> None:
        self._holes = [h.adjusted(-_HOLE_PADDING, -_HOLE_PADDING,
                                  _HOLE_PADDING, _HOLE_PADDING) for h in holes]
        # Punch the holes out of the widget so clicks pass through to the real UI.
        mask = QRegion(self.rect())
        for h in self._holes:
            mask = mask.subtracted(QRegion(h, QRegion.RegionType.Rectangle))
        self.setMask(mask)
        if not self._holes:
            # No target: dim the whole window, no pulsing ring needed.
            self.clearMask()
            self._pulse_anim.stop()
        elif self._pulse_anim.state() != QVariantAnimation.State.Running:
            self._pulse_anim.start()
        # Changing the mask exposes previously covered widgets; repaint the
        # whole window so they don't show stale pixels until clicked.
        parent = self.parentWidget()
        if parent is not None:
            parent.update()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
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
        self.hide()

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
        self._stroke_callback: Optional[Callable[[QPoint], None]] = None

        # Both animations are created once and reused, so replaying the
        # tutorial doesn't accumulate QObjects.
        self._ping_anim = QVariantAnimation(self)
        self._ping_anim.setStartValue(0.0)
        self._ping_anim.setEndValue(1.0)
        self._ping_anim.setDuration(750)
        self._ping_anim.valueChanged.connect(self._on_phase)
        self._ping_anim.finished.connect(self._on_ping_finished)

        self._move_anim = QPropertyAnimation(self, b"pos", self)
        self._move_anim.setDuration(900)
        self._move_anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutCubic))
        self._move_anim.valueChanged.connect(self._on_stroke_step)
        self._move_anim.finished.connect(self.hide)
        self.hide()

    def _ping(self, loops: int) -> None:
        self._ping_anim.stop()
        self._ping_anim.setLoopCount(loops)
        self._ping_anim.start()

    def _on_ping_finished(self) -> None:
        # Don't hide mid-stroke; the move animation hides the pointer itself.
        if self._move_anim.state() != QPropertyAnimation.State.Running:
            self.hide()

    def _on_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    def _on_stroke_step(self, value: object) -> None:
        if self._stroke_callback is not None:
            center = self.pos() + QPoint(self.width() // 2, self.height() // 2)
            self._stroke_callback(center)

    def _center_on(self, point: QPoint) -> None:
        self.move(point - QPoint(self.width() // 2, self.height() // 2))

    def tap(self, point: QPoint) -> None:
        self._move_anim.stop()
        self._center_on(point)
        self.show()
        self.raise_()
        self._ping(loops=3)

    def stroke(self, start: QPoint, end: QPoint,
               on_step: Optional[Callable[[QPoint], None]] = None) -> None:
        self._move_anim.stop()
        self._stroke_callback = on_step
        self._center_on(start)
        self.show()
        self.raise_()
        self._ping(loops=1)
        offset = QPoint(self.width() // 2, self.height() // 2)
        self._move_anim.setStartValue(start - offset)
        self._move_anim.setEndValue(end - offset)
        self._move_anim.start()

    def paintEvent(self, event: QPaintEvent) -> None:
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
    """Drives a sequence of Steps over the live MainWindow."""

    def __init__(self, win: MainWindow) -> None:
        super().__init__(win)
        self.win = win
        self._steps: list[Step] = []
        self._index = 0
        self._completed: set[int] = set()
        self._seen_key = _MAIN_SEEN
        self._awaiting = False
        self._await_signal: Optional[SignalInstance] = None
        self.overlay = _SpotlightOverlay(win)
        self.coachmark = _Coachmark(win, self._prev, self._next, self._skip)
        self.ghost = _GhostPointer(win)

        self._slide_anim = QPropertyAnimation(self.coachmark, b"pos", self)
        self._slide_anim.setDuration(180)
        self._slide_anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))

    # -- public API --------------------------------------------------------

    def start(self, steps: list[Step], seen_key: str) -> None:
        if not steps:
            return
        self._steps = steps
        self._seen_key = seen_key
        self._index = 0
        self._completed = set()
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

    @property
    def seen_key(self) -> str:
        return self._seen_key

    def finish(self) -> None:
        self._disconnect_await()
        set_settings_value(self._seen_key, True, bool)
        self.win.removeEventFilter(self)
        self.ghost.hide()
        self.overlay.hide()
        self.coachmark.hide()

    # -- navigation --------------------------------------------------------

    def _next(self) -> None:
        if self._index + 1 >= len(self._steps):
            self.finish()
        else:
            self._index += 1
            self._show_step()

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_step()

    def _skip(self) -> None:
        self.finish()

    # -- step rendering ----------------------------------------------------

    def _show_step(self) -> None:
        self._disconnect_await()
        step = self._steps[self._index]
        self._apply_visuals(step)

        # Steps the user already completed once don't have to be redone when
        # revisited via Back/Next.
        self._awaiting = False
        if step.await_event is not None and self._index not in self._completed:
            signal = step.await_event(self)
            if signal is not None:
                signal.connect(self._on_await)
                self._await_signal = signal
                self._awaiting = True

        self.coachmark.populate(
            step, self._index, len(self._steps),
            self._awaiting, self._index + 1 == len(self._steps))
        self._place_coachmark()

        if step.on_enter is not None:
            # Defer so the overlay/coachmark are laid out before the demo runs.
            QTimer.singleShot(120, lambda: self._run_on_enter(step))

    def _run_on_enter(self, step: Step) -> None:
        if (self.active and self._steps[self._index] is step
                and step.on_enter is not None):
            step.on_enter(self)

    def _apply_visuals(self, step: Step) -> None:
        self.overlay.setGeometry(self.win.rect())
        self.overlay.set_holes(self._resolve_targets(step))
        self.overlay.raise_()
        self.coachmark.raise_()

    def _resolve_targets(self, step: Step) -> list[QRect]:
        if step.target is None:
            return []
        result = step.target(self)
        if result is None:
            return []
        items: Sequence[Optional[TargetItem]]
        if isinstance(result, (QWidget, QGraphicsItem)):
            items = [result]
        else:
            items = result
        rects: list[QRect] = []
        for item in items:
            if item is None:
                continue
            rect = self._rect_for(item)
            if rect is not None and rect.width() > 0 and rect.height() > 0:
                rects.append(rect)
        return rects

    def _rect_for(self, item: TargetItem) -> Optional[QRect]:
        if isinstance(item, QWidget):
            if not item.isVisible():
                return None
            top_left = item.mapTo(self.win, QPoint(0, 0))
            return QRect(top_left, item.size())
        # A QGraphicsItem (e.g. a VItem) in the active panel's view.
        panel = self.win.active_panel
        if panel is None:
            return None
        view = panel.graph_view
        poly = view.mapFromScene(item.sceneBoundingRect())
        vrect = poly.boundingRect()
        top_left = view.viewport().mapTo(self.win, vrect.topLeft())
        return QRect(top_left, vrect.size())

    def _place_coachmark(self) -> None:
        margin = 18
        win_rect = self.win.rect()
        card = self.coachmark
        card.adjustSize()
        cw, ch = card.width(), card.height()
        holes = self.overlay.holes

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

        # Slide gently into place (one reused animation, not a new one per step).
        self._slide_anim.stop()
        self._slide_anim.setStartValue(target + QPoint(0, 14))
        self._slide_anim.setEndValue(target)
        self._slide_anim.start()

    # -- "your turn" handling ---------------------------------------------

    def _on_await(self) -> None:
        if not self._awaiting:
            return
        self._awaiting = False
        self._completed.add(self._index)
        self._disconnect_await()
        self.coachmark.flash_done()
        self.celebrate()
        completed_index = self._index
        QTimer.singleShot(750, lambda: self._auto_advance(completed_index))

    def _auto_advance(self, from_index: int) -> None:
        # The user may have clicked Next (or Back) before the timer fired;
        # only advance if we are still sitting on the step that was completed.
        if self.active and self._index == from_index and not self._awaiting:
            self._next()

    def _disconnect_await(self) -> None:
        if self._await_signal is not None:
            try:
                self._await_signal.disconnect(self._on_await)
            except RuntimeError:
                pass  # the emitting object may already be gone
            self._await_signal = None

    # -- ghost-demo helpers (used by step definitions) ---------------------

    def fit_view(self) -> None:
        panel = self.win.active_panel
        if panel is not None and panel.graph_scene.g.num_vertices() > 0:
            panel.graph_view.fit_view()

    def _viewport_point(self, dx: int = 0, dy: int = 0) -> Optional[QPoint]:
        panel = self.win.active_panel
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
            panel = self.win.active_panel
            if panel is not None:
                _stop_sparkles_soon(panel.graph_view)

    def _sparkle_at_window_point(self, win_point: QPoint) -> None:
        panel = self.win.active_panel
        if panel is None:
            return
        view = panel.graph_view
        vp_point = view.viewport().mapFrom(self.win, win_point)
        view.sparkles.emit_sparkles(view.mapToScene(vp_point), 2)

    def celebrate(self) -> None:
        panel = self.win.active_panel
        if panel is None:
            return
        view = panel.graph_view
        center = view.mapToScene(view.viewport().rect().center())
        view.sparkles.emit_sparkles(center, 25)
        _stop_sparkles_soon(view)

    # -- keep everything aligned when the window moves/resizes --------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.win and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move) and self.active:
            self._apply_visuals(self._steps[self._index])
            self._place_coachmark()
        return super().eventFilter(obj, event)


def _stop_sparkles_soon(view: GraphView) -> None:
    # emit_sparkles starts a repaint timer that only the magic wand normally
    # stops; shut it down once the burst has faded.
    def stop() -> None:
        if view.sparkles.timer_id is not None:
            view.sparkles.stop()
    QTimer.singleShot(1600, stop)


# Target accessors (resolve real widgets / signals at step-enter time).
# These are total functions returning None when the active panel isn't the
# expected kind, so the steps can be revisited even after switching tabs.

def _edit_panel(c: TutorialController) -> Optional[GraphEditPanel]:
    panel = c.win.active_panel
    return panel if isinstance(panel, GraphEditPanel) else None


def _proof_panel(c: TutorialController) -> Optional[ProofPanel]:
    panel = c.win.active_panel
    return panel if isinstance(panel, ProofPanel) else None


def _canvas(c: TutorialController) -> Optional[QWidget]:
    panel = c.win.active_panel
    return panel.graph_view if panel is not None else None


def _tool_button(panel: Optional[BasePanel], tooltip_substr: str) -> Optional[QToolButton]:
    """Find a toolbar button by (a substring of) its tooltip.

    The edit-mode Select/Vertex/Edge buttons are local variables in
    ``editor_base_panel``, so we locate them through the toolbar rather than
    requiring those panels to expose new attributes.
    """
    if panel is None:
        return None
    for button in panel.toolbar.findChildren(QToolButton):
        if tooltip_substr.lower() in button.toolTip().lower():
            return button
    return None


def _vertex_list(c: TutorialController) -> Optional[QWidget]:
    panel = _edit_panel(c)
    return panel.vertex_list if panel is not None else None


def _edge_list(c: TutorialController) -> Optional[QWidget]:
    panel = _edit_panel(c)
    return panel.edge_list if panel is not None else None


def _start_derivation_button(c: TutorialController) -> Optional[QWidget]:
    panel = _edit_panel(c)
    return panel.start_derivation if panel is not None else None


def _step_view(c: TutorialController) -> Optional[QWidget]:
    panel = _proof_panel(c)
    return panel.step_view if panel is not None else None


def _rewrites_panel(c: TutorialController) -> Optional[QWidget]:
    panel = _proof_panel(c)
    return panel.rewrites_panel if panel is not None else None


def _magic_wand_button(c: TutorialController) -> Optional[QWidget]:
    panel = _proof_panel(c)
    return panel.magic_wand if panel is not None else None


def _identity_choice_button(c: TutorialController) -> Optional[QWidget]:
    panel = _proof_panel(c)
    return panel.identity_choice[0] if panel is not None else None


def _first_spider(c: TutorialController) -> Optional[TargetItem]:
    panel = c.win.active_panel
    if panel is None:
        return None
    g = panel.graph_scene.g
    for v, item in panel.graph_scene.vertex_map.items():
        if g.type(v) in (VertexType.Z, VertexType.X):
            return item
    return panel.graph_view


def _vertex_added_signal(c: TutorialController) -> Optional[SignalInstance]:
    panel = _edit_panel(c)
    return panel.graph_scene.vertex_added if panel is not None else None


def _edge_added_signal(c: TutorialController) -> Optional[SignalInstance]:
    panel = _edit_panel(c)
    return panel.graph_scene.edge_added if panel is not None else None


def _vertex_double_clicked_signal(c: TutorialController) -> Optional[SignalInstance]:
    panel = _edit_panel(c)
    return panel.graph_scene.vertex_double_clicked if panel is not None else None


def _wand_trace_finished_signal(c: TutorialController) -> Optional[SignalInstance]:
    panel = _proof_panel(c)
    return panel.graph_view.wand_trace_finished if panel is not None else None


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
            text="This is your diagram (a small CNOT to get you started). "
                 "<b>Scroll</b> to pan, <b>Ctrl + scroll</b> to zoom, and press "
                 "<b>C</b> to fit everything in view.",
            target=_canvas,
            on_enter=lambda c: c.fit_view(),
        ),
        Step(
            title="Vertices sidebar",
            text="Pick what kind of node you'll draw here: <b>Z</b> and <b>X</b> "
                 "spiders, <b>Hadamard</b> boxes, <b>W</b> nodes, boundaries and "
                 "more. The highlighted type is what the Add Vertex tool drops.",
            target=_vertex_list,
        ),
        Step(
            title="Edges sidebar",
            text="Choose the wire type: a plain <b>Simple</b> edge or a dashed "
                 "<b>Hadamard</b> edge. Double-click a type to recolour selected "
                 "edges.",
            target=_edge_list,
        ),
        Step(
            title="Add a vertex",
            text="Select the <b>Add Vertex</b> tool (shortcut <b>V</b>), then "
                 "click an empty spot on the canvas to drop a spider.",
            target=lambda c: [_tool_button(c.win.active_panel, "Add Vertex"), _canvas(c)],
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=_vertex_added_signal,
            hint="Your turn — drop a vertex on the canvas.",
        ),
        Step(
            title="Connect with an edge",
            text="Switch to the <b>Add Edge</b> tool (<b>E</b>) and drag from one "
                 "spider to another to wire them together.",
            target=lambda c: [_tool_button(c.win.active_panel, "Add Edge"), _canvas(c)],
            await_event=_edge_added_signal,
            hint="Your turn — draw an edge between two spiders.",
        ),
        Step(
            title="Give a spider a phase",
            text="<b>Double-click</b> a Z or X spider to set its phase (try "
                 "<i>pi/2</i>). The phase is the angle that makes spiders "
                 "interesting!",
            target=_first_spider,
            on_enter=lambda c: c.ghost_tap_canvas(),
            await_event=_vertex_double_clicked_signal,
            hint="Your turn — double-click the highlighted spider.",
        ),
        Step(
            title="Start a proof",
            text="Happy with your diagram? Hit <b>Start Derivation</b> to enter "
                 "<b>proof mode</b>, where you transform it step by step. I'll "
                 "pop back in to show you around when you get there!",
            target=_start_derivation_button,
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
            target=_step_view,
        ),
        Step(
            title="Rewrites",
            text="These are the rules you can apply: fuse spiders, change "
                 "colours, remove identities and more. Hover a rule to preview "
                 "it, and click to apply it to your selection.",
            target=_rewrites_panel,
        ),
        Step(
            title="The magic wand 🪄",
            text="The wand is the fast way to rewrite. Pick it (<b>W</b>) and "
                 "<b>draw a stroke</b> through a spider to unfuse it, through a "
                 "wire to drop in an identity, or across parallel edges to cancel "
                 "them. It figures out the rule for you.",
            target=lambda c: [_magic_wand_button(c), _canvas(c)],
            on_enter=lambda c: c.ghost_stroke_canvas(),
            await_event=_wand_trace_finished_signal,
            hint="Your turn — pick the wand and slice through the diagram.",
        ),
        Step(
            title="Identity colour",
            text="When the wand adds an identity spider, this picks whether it's "
                 "a <b>Z</b> or an <b>X</b>. Small detail, big convenience.",
            target=_identity_choice_button,
        ),
        Step(
            title="You're all set! 🎉",
            text="That's the whole loop: <b>draw</b>, <b>derive</b>, <b>prove</b>. "
                 "You can replay this tour any time from <b>Help → Tutorial</b>. "
                 "Have fun rewriting!",
            on_enter=lambda c: c.celebrate(),
        ),
    ]


# Entry points (the only things the rest of the app calls)

def _starter_graph() -> GraphT:
    """A small CNOT diagram so the tour has something to point at."""
    g = new_graph()
    in0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=0)
    in1 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=0)
    z = g.add_vertex(VertexType.Z, qubit=0, row=1)
    x = g.add_vertex(VertexType.X, qubit=1, row=1)
    out0 = g.add_vertex(VertexType.BOUNDARY, qubit=0, row=2)
    out1 = g.add_vertex(VertexType.BOUNDARY, qubit=1, row=2)
    for s, t in ((in0, z), (in1, x), (z, x), (z, out0), (x, out1)):
        g.add_edge((s, t))
    g.set_inputs((in0, in1))
    g.set_outputs((out0, out1))
    return g


def _prepare_canvas(win: MainWindow) -> None:
    """Put the starter diagram on an edit canvas before the tour begins.

    Reuses the current tab if it's an empty graph editor, otherwise opens a
    new one so the user's work is left alone.
    """
    panel = win.active_panel
    if isinstance(panel, GraphEditPanel) and panel.graph_scene.g.num_vertices() == 0:
        panel.replace_graph(_starter_graph())
    else:
        win.new_graph(_starter_graph(), "Tutorial")


def start_main_tutorial(win: MainWindow) -> None:
    """Start (or replay) the full tutorial. Wired to Help -> Tutorial."""
    controller = win.tutorial_controller
    if controller.active:
        return
    # Replaying the main tour also re-arms the proof-mode section.
    set_settings_value(_PROOF_SEEN, False, bool)
    _prepare_canvas(win)
    controller.start(build_main_steps(), _MAIN_SEEN)


def maybe_show_tutorial_on_first_run(win: MainWindow) -> None:
    """Auto-start the tutorial the very first time ZXLive is opened."""
    if get_settings_value(_MAIN_SEEN, bool, False):
        return
    if win.active_panel is None:
        return
    QTimer.singleShot(400, lambda: start_main_tutorial(win))


def maybe_start_proof_tutorial(win: MainWindow) -> None:
    """Show the proof-mode section the first time the user enters proof mode."""
    if get_settings_value(_PROOF_SEEN, bool, False):
        return

    def go() -> None:
        controller = win.tutorial_controller
        if not isinstance(win.active_panel, ProofPanel):
            return
        if controller.active:
            # The user clicked Start Derivation from the main tour's last step;
            # hand over to the proof-mode section.
            if controller.seen_key != _MAIN_SEEN:
                return
            controller.finish()
        controller.start(build_proof_steps(), _PROOF_SEEN)

    QTimer.singleShot(300, go)
