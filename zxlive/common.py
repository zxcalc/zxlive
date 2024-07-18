from __future__ import annotations

import os
from enum import IntEnum
from typing import Final, Optional, TypeVar, Type

from pyzx import EdgeType
from pyzx.graph.multigraph import Multigraph
from typing_extensions import TypeAlias

from PySide6.QtCore import QSettings

import pyzx

_ROOT = os.path.abspath(os.path.dirname(__file__))


T = TypeVar('T')

def get_data(path: str) -> str:
    return os.path.join(os.environ.get("_MEIPASS", _ROOT), path)

def set_settings_value(arg: str, val: T, _type: Type[T], settings: QSettings | None = None) -> None:
    _settings = settings or QSettings("zxlive", "zxlive")
    if not isinstance(val, _type):
        raise ValueError(f"Unexpected type for {arg}: expected {_type}, got {type(val)}")
    _settings.setValue(arg, val)

def get_settings_value(arg: str, _type: Type[T], default: T | None = None, settings: QSettings | None = None) -> T:
    _settings = settings or QSettings("zxlive", "zxlive")
    if _type == bool:
        val = _settings.value(arg, default)
        return str(val) == "True" or str(val) == "true"
    if _type == int:
        val = _settings.value(arg, default)
        return int(str(val))
    if not isinstance(val := _settings.value(arg, default), _type):
        if default is not None:
            return default
        raise ValueError(f"Unexpected type for {arg} ({val}): expected {_type}, got {type(val)}")
    return val

def get_custom_rules_path() -> str:
    settings = QSettings("zxlive", "zxlive")
    return str(settings.value('path/custom-rules'))


VT: TypeAlias = int
ET: TypeAlias = tuple[int, int, EdgeType]
GraphT: TypeAlias = Multigraph

def new_graph() -> GraphT:
    g = GraphT()
    g.set_auto_simplify(False)
    return g

class ToolType(IntEnum):
    SELECT = 0
    VERTEX = 1
    EDGE = 2

SCALE: Final = 64.0

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
