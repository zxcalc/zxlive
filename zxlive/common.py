import typing
from typing import Tuple
import pyzx

VT = typing.TypeVar("VT", bound=int)  # The type for vertex indices
ET = typing.TypeVar("ET", bound=Tuple[int,int])  # The type for edge indices
GraphT = typing.TypeVar("GraphT", bound=pyzx.graph.graph_s.GraphS)