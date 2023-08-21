import os
from enum import IntEnum
from typing import Final
from typing_extensions import TypeAlias
import pyzx

_ROOT = os.path.abspath(os.path.dirname(__file__))

def get_data(path: str) -> str:
    return os.path.join(_ROOT, path)


VT: TypeAlias = int
ET: TypeAlias = tuple[int,int]
GraphT: TypeAlias = pyzx.graph.graph_s.GraphS

class ToolType(IntEnum):
    SELECT = 0
    VERTEX = 1
    EDGE = 2

from pyzx.graph.graph_s import GraphS as Graph

SCALE: Final = 60.0

# Offsets should be a multiple of SCALE for grid snapping to work properly
OFFSET_X: Final = 300 * SCALE
OFFSET_Y: Final = 300 * SCALE

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

