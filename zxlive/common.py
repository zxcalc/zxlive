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

def from_tikz(s: str, ignore_nonzx: bool = False, fuse_overlap: bool = True, 
              warn_overlap: bool = False, show_error_dialog: bool = True) -> Optional[GraphT]:
    """Import a graph from TikZ string.
    
    Args:
        s: TikZ string to import
        ignore_nonzx: If True, ignore unknown vertex/edge types and invalid labels
        fuse_overlap: If True, merge vertices with the same position
        warn_overlap: If True, warn about overlapping vertices (only has effect if fuse_overlap is False)
        show_error_dialog: If True, show error dialog with retry options on failure
    
    Returns:
        The imported graph or None if import failed
    """
    try:
        g = pyzx.tikz.tikz_to_graph(s, backend='multigraph', 
                                     ignore_nonzx=ignore_nonzx,
                                     fuse_overlap=fuse_overlap,
                                     warn_overlap=warn_overlap)
        assert isinstance(g, GraphT)
        return g
    except Exception as e:
        if show_error_dialog:
            from . import dialogs
            # Show error with retry options
            options = dialogs.show_tikz_error_with_options(str(e))
            if options is not None:
                # Retry with user-selected options
                return from_tikz(s, 
                               ignore_nonzx=options['ignore_nonzx'],
                               fuse_overlap=options['fuse_overlap'],
                               warn_overlap=not options['ignore_overlap_warning'],
                               show_error_dialog=False)  # Don't show dialog again on retry
            return None
        else:
            # If not showing dialog, just raise the error or return None
            from . import dialogs
            dialogs.show_error_msg("Tikz import error", f"Error while importing tikz: {e}")
            return None
