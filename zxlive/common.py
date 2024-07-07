import os
from enum import IntEnum
from typing import Final, Optional

from pyzx import EdgeType
from typing_extensions import TypeAlias

from PySide6.QtCore import QSettings

import pyzx

_ROOT = os.path.abspath(os.path.dirname(__file__))


def get_data(path: str) -> str:
    return os.path.join(os.environ.get("_MEIPASS", _ROOT), path)

def get_custom_rules_path() -> str:
    settings = QSettings("zxlive", "zxlive")
    return str(settings.value('path/custom-rules'))


VT: TypeAlias = int
ET: TypeAlias = tuple[int, int, EdgeType]
GraphT: TypeAlias = pyzx.graph.multigraph.Multigraph

def new_graph() -> GraphT:
    g = GraphT()
    g.set_auto_simplify(False)
    return g

class ToolType(IntEnum):
    SELECT = 0
    VERTEX = 1
    EDGE = 2

SCALE: Final = 64.0


class Settings(object):
    SNAP_DIVISION = 4  # Should be an integer dividing SCALE

    def __init__(self) -> None:
        self.update()

    def update(self) -> None:
        self.SNAP_DIVISION = int(type_safe_settings_value("snap-granularity"))
        self.SNAP = SCALE / self.SNAP_DIVISION

setting = Settings()

# Offsets should be a multiple of SCALE for grid snapping to work properly
OFFSET_X: Final = 300 * SCALE
OFFSET_Y: Final = 300 * SCALE

W_INPUT_OFFSET: Final = 0.3

ANIMATION_DURATION: Final = 400

MIN_ZOOM = 0.05
MAX_ZOOM = 10.0


def pos_to_view(x:float,y: float) -> tuple[float, float]:
    return (x * SCALE + OFFSET_X, y * SCALE + OFFSET_Y)

def pos_from_view(x:float,y: float) -> tuple[float, float]:
    return ((x-OFFSET_X) / SCALE, (y-OFFSET_Y) / SCALE)

def pos_to_view_int(x:float,y: float) -> tuple[int, int]:
    return (int(x * SCALE + OFFSET_X), int(y * SCALE + OFFSET_Y))

def pos_from_view_int(x:float,y: float) -> tuple[int, int]:
    return (int((x - OFFSET_X) / SCALE), int((y - OFFSET_Y) / SCALE))

def view_to_length(width:float,height:float)-> tuple[float, float]:
    return (width / SCALE, height / SCALE)

def to_tikz(g: GraphT) -> str:
    return pyzx.tikz.to_tikz(g)  # type: ignore

def from_tikz(s: str) -> Optional[GraphT]:
    try:
        return pyzx.tikz.tikz_to_graph(s)
    except Exception as e:
        from . import dialogs
        dialogs.show_error_msg("Tikz import error", f"Error while importing tikz: {e}")
        return None
