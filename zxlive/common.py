from __future__ import annotations

import os
import re
from enum import IntEnum
from typing import Final, TypeVar, Type, cast

from pyzx.graph import EdgeType
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


# TODO: Fix code complexity
# noqa: complexipy
def get_settings_value(arg: str, _type: Type[T], default: T | None = None, settings: QSettings | None = None) -> T:
    _settings = settings or QSettings("zxlive", "zxlive")
    try:
        val = _settings.value(arg, default)
        if _type == bool:
            val = str(val) == "True" or str(val) == "true"
        if _type == int:
            val = int(str(val))
        if _type == float:
            val = float(str(val))
        if not isinstance(val, _type):
            if default is not None:
                return default
            raise ValueError(f"Unexpected type for {arg} ({val}): expected {_type}, got {type(val)}")
    except Exception as e:
        if default is not None:
            return default
        from .settings import defaults
        if arg in defaults:
            return defaults[arg]  # type: ignore
        raise e
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


def pos_to_view(x: float, y: float) -> tuple[float, float]:
    return (x * SCALE + OFFSET_X, y * SCALE + OFFSET_Y)


def pos_from_view(x: float, y: float) -> tuple[float, float]:
    return ((x - OFFSET_X) / SCALE, (y - OFFSET_Y) / SCALE)


def pos_to_view_int(x: float, y: float) -> tuple[int, int]:
    return (int(x * SCALE + OFFSET_X), int(y * SCALE + OFFSET_Y))


def pos_from_view_int(x: float, y: float) -> tuple[int, int]:
    return (int((x - OFFSET_X) / SCALE), int((y - OFFSET_Y) / SCALE))


def view_to_length(width: float, height: float) -> tuple[float, float]:
    return (width / SCALE, height / SCALE)


def to_tikz(g: GraphT) -> str:
    """Export graph to TikZ; PyZX includes variable type metadata when present."""
    return pyzx.tikz.to_tikz(g)  # type: ignore


def find_unknown_tikz_styles(tikz: str) -> list[str]:
    """Return vertex style names in *tikz* that PyZX does not recognise.

    Only node (vertex) styles are checked; edge styles are ignored.
    """
    known: set[str] = set()
    for syn_list in (pyzx.tikz.synonyms_z, pyzx.tikz.synonyms_x,
                     pyzx.tikz.synonyms_boundary, pyzx.tikz.synonyms_hadamard,
                     pyzx.tikz.synonyms_w_input, pyzx.tikz.synonyms_w_output,
                     pyzx.tikz.synonyms_z_box, pyzx.tikz.synonyms_none,
                     pyzx.tikz.synonyms_dummy):
        known.update(name.lower() for name in syn_list)

    unknown: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'\\node\s*\[style\s*=\s*([^\],]+)', tikz):
        style = m.group(1).strip()
        if style.lower() not in known and style.lower() not in seen:
            unknown.append(style)
            seen.add(style.lower())
    return unknown


def from_tikz(s: str, ignore_errors: bool = False) -> GraphT:
    """Import a graph from a TikZ string.

    When *ignore_errors* is ``True``, invalid phases, unparseable
    nodes/edges, unknown styles, and overlapping vertices are silently
    tolerated instead of raising.
    """
    extra_kwargs = dict(
        ignore_invalid_phases=True,
        ignore_parse_errors=True,
        ignore_nonzx=True,
        warn_overlap=False,
    ) if ignore_errors else {}
    g = cast(GraphT, pyzx.tikz.tikz_to_graph(s, backend='multigraph', **extra_kwargs))
    g.set_auto_simplify(False)
    return g
