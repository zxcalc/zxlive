from enum import Enum
from PySide6.QtCore import QUrl
from typing import TYPE_CHECKING

from .common import get_data

if TYPE_CHECKING:
    from PySide6.QtMultimedia import QSoundEffect


class SFXEnum(Enum):
    BOOM_BOOM_BOOM = "boom-boom-boom.wav"
    IRANIAN_BUS = "iranian-bus.wav"
    OK_IM_GONNA_START = "ok-im-gonna-start.wav"
    THATS_A_SPIDER = "thats-a-spider.wav"
    THATS_JUST_WIRE_1 = "thats-just-wire-1.wav"
    THATS_JUST_WIRE_2 = "thats-just-wire-2.wav"
    THATS_SPIDER_FUSION = "thats-spider-fusion.wav"
    THEY_FALL_OFF = "they-fall-off.wav"
    WELCOME_EVERYBODY = "welcome-everybody.wav"


def load_sfx(e: SFXEnum) -> "QSoundEffect":
    """Load a sound effect from a file."""
    # Import QtMultimedia lazily to avoid importing / initializing multimedia
    # backends during module import (important for headless CI).
    from PySide6.QtMultimedia import QSoundEffect

    effect = QSoundEffect()
    fullpath = get_data("sfx/" + e.value)
    url = QUrl.fromLocalFile(fullpath)
    effect.setSource(url)

    return effect
