from typing import Tuple, Final
from typing_extensions import TypeAlias
import pyzx

VT: TypeAlias = int
ET: TypeAlias = Tuple[int,int]
GraphT: TypeAlias = pyzx.graph.graph_s.GraphS

from pyzx.graph.graph_s import GraphS as Graph

SCALE: Final = 60.0
OFFSET_X: Final = 20000.0
OFFSET_Y: Final = 20000.0

MIN_ZOOM = 0.05
MAX_ZOOM = 10.0

def pos_to_view(x:float,y: float) -> Tuple[float, float]:
    return (x * SCALE + OFFSET_X, y * SCALE + OFFSET_Y)

def pos_from_view(x:float,y: float) -> Tuple[float, float]:
    return ((x-OFFSET_X) / SCALE, (y-OFFSET_Y) / SCALE)

def pos_to_view_int(x:float,y: float) -> Tuple[int, int]:
    return (int(x * SCALE + OFFSET_X), int(y * SCALE + OFFSET_Y))

def pos_from_view_int(x:float,y: float) -> Tuple[int, int]:
    return (int((x - OFFSET_X) / SCALE), int((y - OFFSET_Y) / SCALE))

def view_to_length(width,height):
    return (width / SCALE, height / SCALE)