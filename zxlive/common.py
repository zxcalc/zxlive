from __future__ import annotations

import json
import os
import re
from enum import IntEnum
from typing import Any, Final, TypeVar, Type, cast

from pyzx.graph import EdgeType
from pyzx.graph.multigraph import Multigraph
from pyzx.graph.jsonparser import string_to_phase
from pyzx.graph.scalar import Scalar
from pyzx.symbolic import VarRegistry
from pyzx.utils import VertexType
from typing_extensions import TypeAlias

from PySide6.QtCore import QSettings

import pyzx

_ROOT = os.path.abspath(os.path.dirname(__file__))

T = TypeVar('T') # TODO: remove this and use 3.12 generic syntax

DEFAULT_SETTINGS = QSettings("zxlive", "zxlive")

def get_data(path: str) -> str:
    return os.path.join(os.environ.get("_MEIPASS", _ROOT), path)


def set_settings_value[T](arg: str, val: T, _type: Type[T], settings: QSettings = DEFAULT_SETTINGS) -> None:
    if not isinstance(val, _type):
        raise ValueError(f"Unexpected type for {arg}: expected {_type}, got {type(val)}")
    settings.setValue(arg, val)


def get_settings_value[T](arg: str, _type: Type[T], default: T | None = None, settings: QSettings = DEFAULT_SETTINGS) -> T:
    try:
        val = settings.value(arg, default)
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
    return str(DEFAULT_SETTINGS.value('path/custom-rules'))


VT: TypeAlias = int
ET: TypeAlias = tuple[int, int, EdgeType]
GraphT: TypeAlias = Multigraph


def graph_from_json(data: str | dict[str, Any]) -> GraphT:
    """Load a graph from either current or legacy PyZX JSON."""
    graph_data = json.loads(data) if isinstance(data, str) else data
    try:
        graph = GraphT.from_json(graph_data)
    except ValueError:
        if "version" in graph_data or "node_vertices" not in graph_data:
            raise
        graph = _legacy_graph_from_dict(graph_data)
    graph.set_auto_simplify(False)
    return cast(GraphT, graph)


def _legacy_graph_from_dict(data: dict[str, Any]) -> GraphT:
    graph = GraphT()
    graph.var_registry = VarRegistry(data.get("variable_types", {}))
    graph.set_auto_simplify(False)
    names, hadamards = _legacy_add_nodes(graph, data)
    inputs, outputs = _legacy_add_wire_vertices(graph, data, names)
    graph.set_inputs(inputs)
    graph.set_outputs(outputs)

    edges: dict[tuple[VT, VT], list[int]] = {}
    for edge in data.get("undir_edges", {}).values():
        _legacy_add_edge(graph, edge, names, hadamards, edges)
    _legacy_add_hadamard_edges(hadamards, edges)
    _legacy_add_edges(graph, edges)

    if "scalar" in data:
        graph.scalar = Scalar.from_json(data["scalar"])
    return graph


def _legacy_add_nodes(graph: GraphT, data: dict[str, Any]) -> tuple[dict[str, VT], dict[str, list[VT]]]:
    names: dict[str, VT] = {}
    hadamards: dict[str, list[VT]] = {}
    for name, vertex_data in data.get("node_vertices", {}).items():
        attributes = vertex_data.get("data", {})
        if attributes.get("type") == "hadamard" and attributes.get("is_edge") == "true":
            hadamards[name] = []
        else:
            names[name] = _legacy_add_node(graph, name, vertex_data)
    return names, hadamards


def _legacy_add_node(graph: GraphT, name: str, data: dict[str, Any]) -> VT:
    vertex_types = {
        "Z": VertexType.Z,
        "X": VertexType.X,
        "hadamard": VertexType.H_BOX,
        "W_input": VertexType.W_INPUT,
        "W_output": VertexType.W_OUTPUT,
        "Z_box": VertexType.Z_BOX,
    }
    attributes = data.get("data", {})
    vertex_type = vertex_types.get(attributes.get("type", "Z"))
    if vertex_type is None:
        raise TypeError(f"unsupported type '{attributes['type']}'")

    annotation = data.get("annotation", {})
    qubit, row = _legacy_coordinates(annotation.get("coord", (0, 0)))
    vertex = graph.add_vertex(vertex_type, qubit=qubit, row=row)
    graph.set_vdata(vertex, "name", name)
    graph.set_phase(vertex, string_to_phase(str(attributes.get("value", 0)), graph))
    if attributes.get("ground", False):
        graph.set_ground(vertex)
    for key, value in annotation.items():
        if key == "coord":
            continue
        if key == "label" and not isinstance(value, complex):
            value = string_to_phase(str(value), graph)
        graph.set_vdata(vertex, key, value)
    return vertex


def _legacy_add_wire_vertices(graph: GraphT, data: dict[str, Any], names: dict[str, VT]) -> tuple[tuple[VT, ...], tuple[VT, ...]]:
    inputs: dict[VT, int] = {}
    outputs: dict[VT, int] = {}
    for name, vertex_data in data.get("wire_vertices", {}).items():
        annotation = vertex_data["annotation"]
        qubit, row = _legacy_coordinates(annotation["coord"])
        vertex = graph.add_vertex(VertexType.BOUNDARY, qubit=qubit, row=row)
        graph.set_vdata(vertex, "name", name)
        names[name] = vertex
        if "input" in annotation:
            inputs[vertex] = annotation["input"]
        if "output" in annotation:
            outputs[vertex] = annotation["output"]
        for key, value in annotation.items():
            if key not in ("boundary", "coord", "input", "output"):
                graph.set_vdata(vertex, key, value)
    return (
        tuple(sorted(inputs, key=inputs.__getitem__)),
        tuple(sorted(outputs, key=outputs.__getitem__)),
    )


def _legacy_coordinates(coordinates: tuple[float, float]) -> tuple[int | float, int | float]:
    x, y = coordinates
    qubit, row = -y, x
    if qubit == int(qubit):
        qubit = int(qubit)
    if row == int(row):
        row = int(row)
    return qubit, row


def _legacy_add_edge(
    graph: GraphT,
    edge: dict[str, Any],
    names: dict[str, VT],
    hadamards: dict[str, list[VT]],
    edges: dict[tuple[VT, VT], list[int]],
) -> None:
    source, target = edge["src"], edge["tgt"]
    if source in hadamards and target in hadamards:
        vertex = graph.add_vertex(VertexType.Z)
        name = f"v{len(names)}"
        graph.set_vdata(vertex, "name", name)
        names[name] = vertex
        hadamards[source].append(vertex)
        hadamards[target].append(vertex)
    elif source in hadamards:
        hadamards[source].append(names[target])
    elif target in hadamards:
        hadamards[target].append(names[source])
    elif edge.get("type") == "w_io":
        graph.add_edge((names[source], names[target]), EdgeType.W_IO)
    else:
        counts = edges.setdefault((names[source], names[target]), [0, 0])
        counts[0] += 1


def _legacy_add_hadamard_edges(hadamards: dict[str, list[VT]], edges: dict[tuple[VT, VT], list[int]]) -> None:
    for vertices in hadamards.values():
        if len(vertices) != 2:
            raise TypeError("Can't parse graphs with irregular Hadamard nodes")
        counts = edges.setdefault((vertices[0], vertices[1]), [0, 0])
        counts[1] += 1


def _legacy_add_edges(graph: GraphT, edges: dict[tuple[VT, VT], list[int]]) -> None:
    for (source, target), (simple_count, hadamard_count) in edges.items():
        for _ in range(simple_count):
            graph.add_edge((source, target), EdgeType.SIMPLE)
        for _ in range(hadamard_count):
            graph.add_edge((source, target), EdgeType.HADAMARD)


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
    return pyzx.tikz.to_tikz(g)


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
