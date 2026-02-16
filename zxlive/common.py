from __future__ import annotations

import base64
import json
import os
import re
from enum import IntEnum
from typing import Final, Optional, TypeVar, Type

from pyzx.graph import EdgeType
from pyzx.graph.multigraph import Multigraph
from typing_extensions import TypeAlias

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

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
    tikz = pyzx.tikz.to_tikz(g)  # type: ignore
    payload = _encode_tikz_metadata(g)
    if payload is None:
        return tikz
    return f"{tikz}\n% zxlive-metadata: {payload}"


def from_tikz(s: str) -> Optional[GraphT]:
    try:
        s, variable_types = _extract_tikz_metadata(s)
        g = pyzx.tikz.tikz_to_graph(s, backend='multigraph')
        assert isinstance(g, GraphT)
        apply_variable_types(g, variable_types)
        return g
    except Exception as e:
        if QApplication.instance() is not None:
            from . import dialogs
            dialogs.show_error_msg("Tikz import error", f"Error while importing tikz: {e}")
        return None


def copy_variable_types(target: GraphT, source: GraphT, overwrite: bool = False,
                        names: Optional[set[str]] = None) -> None:
    """Copies variable type metadata from source to target graph."""
    if overwrite:
        existing_vars: set[str] = set()
    else:
        existing_vars = set(target.var_registry.vars())
    names_to_copy = names if names is not None else set(source.var_registry.vars())
    for name in names_to_copy:
        if name in existing_vars:
            continue
        target.var_registry.set_type(name, source.var_registry.get_type(name, default=False))


def apply_variable_types(graph: GraphT, variable_types: dict[str, bool]) -> None:
    """Applies variable type metadata to a graph."""
    for name, is_bool in variable_types.items():
        graph.var_registry.set_type(name, is_bool)


def _encode_tikz_metadata(graph: GraphT) -> Optional[str]:
    variable_types = {
        name: bool(graph.var_registry.get_type(name, default=False))
        for name in graph.var_registry.vars()
    }
    if not variable_types:
        return None
    payload = json.dumps({"variable_types": variable_types}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


_TIKZ_METADATA_RE = re.compile(r"^\s*%\s*zxlive-metadata:\s*(\S+)\s*$")


def _extract_tikz_metadata(s: str) -> tuple[str, dict[str, bool]]:
    match: Optional[re.Match[str]] = None
    line_index = -1
    lines = s.splitlines()
    for i, line in enumerate(lines):
        m = _TIKZ_METADATA_RE.match(line)
        if m is not None:
            match = m
            line_index = i
            break
    if match is None:
        return s, {}

    payload = match.group(1)
    del lines[line_index]
    tikz = "\n".join(lines)
    try:
        metadata = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        variable_types = metadata.get("variable_types", {})
        if isinstance(variable_types, dict):
            normalized = {str(name): bool(v) for name, v in variable_types.items()}
            return tikz, normalized
    except Exception:
        pass
    return tikz, {}
