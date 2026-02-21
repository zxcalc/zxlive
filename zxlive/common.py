from __future__ import annotations

import os
from enum import IntEnum
from typing import Final, Optional, TypeVar, Type

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
    return pyzx.tikz.to_tikz(g)  # type: ignore


def from_tikz(s: str) -> Optional[GraphT]:
    try:
        g = pyzx.tikz.tikz_to_graph(s, backend='multigraph')
        assert isinstance(g, GraphT)
        return g
    except Exception as e:
        from . import dialogs
        dialogs.show_error_msg("Tikz import error", f"Error while importing tikz: {e}")
        return None



def graph_variable_names(graph: GraphT) -> set[str]:
    """Return variable names that are actually used by phases in ``graph``."""
    names: set[str] = set()
    for v in graph.vertices():
        phase = graph.phase(v)
        free_vars = getattr(phase, "free_vars", None)
        if callable(free_vars):
            for var in free_vars():
                var_name = getattr(var, "name", None)
                if isinstance(var_name, str):
                    names.add(var_name)
                else:
                    names.add(str(var))
    return names


def merge_graphs_preserving_metadata(target: GraphT, source: GraphT) -> tuple[list[VT], list[ET]]:
    """Merge ``source`` into ``target`` while preserving per-vertex and variable metadata."""
    new_verts, new_edges = target.merge(source)

    for src_v, new_v in zip(source.vertices(), new_verts):
        target.set_vdata_dict(new_v, source.vdata_dict(src_v))

    var_registry_source = getattr(source, "var_registry", None)
    var_registry_target = getattr(target, "var_registry", None)
    if var_registry_source is not None and var_registry_target is not None:
        for name in graph_variable_names(source):
            var_registry_target.set_type(name, var_registry_source.get_type(name, default=False))

    return new_verts, new_edges
