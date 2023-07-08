import random

from PySide6.QtCore import QEasingCurve, QPointF, QAbstractAnimation
from zxlive.graphscene import VItem, VItemAnimation


def scale(it: VItem, target, duration, ease: QEasingCurve):
    anim = VItemAnimation(it, VItem.Properties.Scale)
    anim.setDuration(duration)
    anim.setStartValue(it.scale())
    # Important: end value must be a float, otherwise the animation doesn't work because
    # start and end have different types
    anim.setEndValue(float(target))
    anim.setEasingCurve(ease)
    anim.start()


def shake(it: VItem, amount: float, duration: float):
    center = it.pos()
    anim = VItemAnimation(it, VItem.Properties.Position, refresh=False)
    anim.setLoopCount(-1)  # Infinite looping
    anim.setEasingCurve(QEasingCurve.InOutExpo)
    anim.setDuration(duration)

    def set_random_params() -> None:
        dx = (2 * random.random() - 1) * amount
        dy = (2 * random.random() - 1) * amount
        anim.setStartValue(it.pos())
        anim.setEndValue(QPointF(center.x() + dx, center.y() + dy))

    def state_changed(state: QAbstractAnimation.State) -> None:
        if state == QAbstractAnimation.State.Stopped:
            it.setPos(center)

    set_random_params()
    anim.currentLoopChanged.connect(set_random_params)
    anim.stateChanged.connect(state_changed)
    anim.start()


def anticipate_fuse(it: VItem) -> None:
    """Animation that is played when a fuseable spider is dragged onto a vertex."""
    scale(it, target=1.25, duration=200, ease=QEasingCurve.OutInQuad)


def anticipate_strong_comp(it: VItem) -> None:
    """Animation that is played when a bialgebra-capable spider is dragged onto a
    vertex."""
    scale(it, target=1.25, duration=200, ease=QEasingCurve.OutInQuad)
    # shake(it, amount=1.0, duration=70)


def back_to_default(it: VItem) -> None:
    """Stops all running animations on an VItem and animates all properties back to
    their default values."""
    for anim in it.active_animations.copy():
        anim.stop()
    scale(it, target=1, duration=250, ease=QEasingCurve.InOutQuad)


