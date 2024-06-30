import os
from enum import IntEnum
from typing import Final, Dict, Any
from typing_extensions import TypeAlias

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTabWidget

import pyzx

_ROOT = os.path.abspath(os.path.dirname(__file__))


def get_data(path: str) -> str:
    return os.path.join(os.environ.get("_MEIPASS", _ROOT), path)

def get_custom_rules_path() -> str:
    settings = QSettings("zxlive", "zxlive")
    return str(settings.value('path/custom-rules'))


VT: TypeAlias = int
ET: TypeAlias = tuple[int, int, int]
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


defaults: Dict[str,Any] = {
    "path/custom-rules": "lemmas/",
    "color-scheme": "modern-red-green",
    "tab-bar-location": QTabWidget.TabPosition.North,
    "snap-granularity": '4',
    "input-circuit-format": 'openqasm',

    "tikz/boundary-export": pyzx.settings.tikz_classes['boundary'],
    "tikz/Z-spider-export": pyzx.settings.tikz_classes['Z'],
    "tikz/X-spider-export": pyzx.settings.tikz_classes['X'],
    "tikz/Z-phase-export": pyzx.settings.tikz_classes['Z phase'],
    "tikz/X-phase-export": pyzx.settings.tikz_classes['X phase'],
    "tikz/z-box-export": pyzx.settings.tikz_classes['Z box'],
    "tikz/Hadamard-export": pyzx.settings.tikz_classes['H'],
    "tikz/w-output-export": pyzx.settings.tikz_classes['W'],
    "tikz/w-input-export": pyzx.settings.tikz_classes['W input'],
    "tikz/edge-export": pyzx.settings.tikz_classes['edge'],
    "tikz/edge-H-export": pyzx.settings.tikz_classes['H-edge'],
    "tikz/edge-W-export": pyzx.settings.tikz_classes['W-io-edge'],

    "tikz/boundary-import": ", ".join(pyzx.tikz.synonyms_boundary),
    "tikz/Z-spider-import": ", ".join(pyzx.tikz.synonyms_z),
    "tikz/X-spider-import": ", ".join(pyzx.tikz.synonyms_x),
    "tikz/Hadamard-import": ", ".join(pyzx.tikz.synonyms_hadamard),
    "tikz/w-input-import": ", ".join(pyzx.tikz.synonyms_w_input),
    "tikz/w-output-import": ", ".join(pyzx.tikz.synonyms_w_output),
    "tikz/z-box-import": ", ".join(pyzx.tikz.synonyms_z_box),
    "tikz/edge-import": ", ".join(pyzx.tikz.synonyms_edge),
    "tikz/edge-H-import": ", ".join(pyzx.tikz.synonyms_hedge),
    "tikz/edge-W-import": ", ".join(pyzx.tikz.synonyms_wedge),

    "tikz/layout/hspace": 2.0,
    "tikz/layout/vspace": 2.0,
    "tikz/layout/max-width": 10.0,

    "tikz/names/fuse spiders": "f",
    "tikz/names/bialgebra": "b",
    "tikz/names/change color to Z": "cc",
    "tikz/names/change color to X": "cc",
    "tikz/names/remove identity": "id",
    "tikz/names/Add Z identity": "id",
    "tikz/names/copy 0/pi spider": "cp",
    "tikz/names/push Pauli": "pi",
    "tikz/names/decompose hadamard": "eu",
}

color_schemes = {
    'modern-red-green': "Modern Red & Green",
    'classic-red-green': "Classic Red & Green",
    'white-grey': "Dodo book White & Grey",
    'gidney': "Gidney's Black & White",
}

input_circuit_formats = {
    'openqasm': "standard OpenQASM",
    'sqasm': "Spider QASM",
    'sqasm-no-simplification': "Spider QASM (no simplification)",
}

# Initialise settings
settings = QSettings("zxlive", "zxlive")
for key, value in defaults.items():
    if not settings.contains(key):
        settings.setValue(key, value)


class Settings(object):
    SNAP_DIVISION = 4  # Should be an integer dividing SCALE

    def __init__(self) -> None:
        self.update()

    def update(self) -> None:
        settings = QSettings("zxlive", "zxlive")
        self.SNAP_DIVISION = int(settings.value("snap-granularity"))
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


class Colors(object):
    z_spider: QColor = QColor("#ccffcc")
    z_spider_pressed: QColor = QColor("#64BC90")
    x_spider: QColor = QColor("#ff8888")
    x_spider_pressed: QColor = QColor("#bb0f0f")
    hadamard: QColor = QColor("#ffff00")
    hadamard_pressed: QColor = QColor("#f1c232")
    boundary: QColor = QColor("#000000")
    boundary_pressed: QColor = QColor("#444444")
    w_input: QColor = QColor("#000000")
    w_input_pressed: QColor = QColor("#444444")
    w_output: QColor = QColor("#000000")
    w_output_pressed: QColor = QColor("#444444")
    outline: QColor = QColor("#000000")

    def __init__(self, color_scheme:str):
        self.set_color_scheme(color_scheme)

    def set_color_scheme(self, color_scheme: str) -> None:
        if color_scheme == 'modern-red-green':
            self.z_spider = QColor("#ccffcc")
            self.z_spider_pressed = QColor("#64BC90")
            self.x_spider = QColor("#ff8888")
            self.x_spider_pressed = QColor("#bb0f0f")
            self.hadamard = QColor("#ffff00")
            self.hadamard_pressed = QColor("#f1c232")
            self.boundary = QColor("#000000")
        elif color_scheme == 'classic-red-green':
            self.z_spider = QColor("#00ff00")
            self.z_spider_pressed = QColor("#00dd00")
            self.x_spider = QColor("#ff0d00")
            self.x_spider_pressed = QColor("#dd0b00")
            self.hadamard = QColor("#ffff00")
            self.hadamard_pressed = QColor("#f1c232")
            self.boundary = QColor("#000000")
        elif color_scheme == 'white-grey':
            self.z_spider = QColor("#ffffff")
            self.z_spider_pressed = QColor("#eeeeee")
            self.x_spider = QColor("#b4b4b4")
            self.x_spider_pressed = QColor("#a0a0a0")
            self.hadamard = QColor("#ffffff")
            self.hadamard_pressed = QColor("#dddddd")
            self.boundary = QColor("#000000")
        elif color_scheme == 'gidney':
            self.z_spider = QColor("#000000")
            self.z_spider_pressed = QColor("#222222")
            self.x_spider = QColor("#ffffff")
            self.x_spider_pressed = QColor("#dddddd")
            self.hadamard = QColor("#ffffff")
            self.hadamard_pressed = QColor("#dddddd")
            self.boundary = QColor("#000000")
        else:
            raise ValueError(f"Unknown colour scheme {color_scheme}")


settings = QSettings("zxlive", "zxlive")
color_scheme = settings.value("color-scheme")
if color_scheme is None: color_scheme = str(defaults["color-scheme"])
else: color_scheme = str(color_scheme)
colors = Colors(color_scheme)


def set_pyzx_tikz_settings() -> None:
    tikz_classes = {
        'boundary': str(settings.value('tikz/boundary-export') or pyzx.settings.tikz_classes['boundary']),
        'Z': str(settings.value('tikz/Z-spider-export') or pyzx.settings.tikz_classes['Z']),
        'X': str(settings.value('tikz/X-spider-export') or pyzx.settings.tikz_classes['X']),
        'Z phase': str(settings.value('tikz/Z-phase-export') or pyzx.settings.tikz_classes['Z phase']),
        'X phase': str(settings.value('tikz/X-phase-export') or pyzx.settings.tikz_classes['X phase']),
        'Z box': str(settings.value('tikz/Z-box-export') or pyzx.settings.tikz_classes['Z box']),
        'H': str(settings.value('tikz/Hadamard-export') or pyzx.settings.tikz_classes['H']),
        'W': str(settings.value('tikz/W-output-export') or pyzx.settings.tikz_classes['W']),
        'W input': str(settings.value('tikz/W-input-export') or pyzx.settings.tikz_classes['W input']),
        'edge': str(settings.value('tikz/edge-export') or pyzx.settings.tikz_classes['edge']),
        'H-edge': str(settings.value('tikz/edge-H-export') or pyzx.settings.tikz_classes['H-edge']),
        'W-io-edge': str(settings.value('tikz/edge-W-export') or pyzx.settings.tikz_classes['W-io-edge']),
        }

    def _get_synonyms(key: str, default: list[str]) -> list[str]:
        val: object = settings.value(key)
        if not val:
            return default
        return [s.strip().lower() for s in str(val).split(',')]

    pyzx.settings.tikz_classes = tikz_classes
    pyzx.tikz.synonyms_boundary = _get_synonyms('tikz/boundary-import', pyzx.tikz.synonyms_boundary)
    pyzx.tikz.synonyms_z = _get_synonyms('tikz/Z-spider-import', pyzx.tikz.synonyms_z)
    pyzx.tikz.synonyms_x = _get_synonyms('tikz/X-spider-import', pyzx.tikz.synonyms_x)
    pyzx.tikz.synonyms_hadamard = _get_synonyms('tikz/Hadamard-import', pyzx.tikz.synonyms_hadamard)
    pyzx.tikz.synonyms_w_input = _get_synonyms('tikz/W-input-import', pyzx.tikz.synonyms_w_input)
    pyzx.tikz.synonyms_w_output = _get_synonyms('tikz/W-output-import', pyzx.tikz.synonyms_w_output)
    pyzx.tikz.synonyms_z_box = _get_synonyms('tikz/Z-box-import', pyzx.tikz.synonyms_z_box)
    pyzx.tikz.synonyms_edge = _get_synonyms('tikz/edge-import', pyzx.tikz.synonyms_edge)
    pyzx.tikz.synonyms_hedge = _get_synonyms('tikz/edge-H-import', pyzx.tikz.synonyms_hedge)
    pyzx.tikz.synonyms_wedge = _get_synonyms('tikz/edge-W-import', pyzx.tikz.synonyms_wedge)


set_pyzx_tikz_settings()  # Call it once on startup


def to_tikz(g: GraphT) -> str:
    return pyzx.tikz.to_tikz(g)  # type: ignore

def from_tikz(s: str) -> GraphT:
    try:
        return pyzx.tikz.tikz_to_graph(s)
    except Exception as e:
        from . import dialogs
        dialogs.show_error_msg("Tikz import error", f"Error while importing tikz: {e}")
        return None
