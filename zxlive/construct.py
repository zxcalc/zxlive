# zxlive - An interactive tool for the ZX-calculus
# Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bundled example ZX diagrams used by the tutorial and the demo graph.

Each public function either loads a pre-drawn diagram from
``zxlive/examples/<name>.json`` (preferred — allows exact layout control) or
builds one programmatically from scratch when no JSON file exists.

Tutorial-relevant examples
--------------------------
* :func:`construct_three_cnots`
    Three alternating CNOT gates (control-top, control-bottom, control-top).
    Used as the startup demo and the starting point for the
    "3 CNOTs = SWAP" interactive lesson.

* :func:`construct_swap`
    The compact two-qubit SWAP; the target state of the lesson above.

* :func:`construct_zz_phase_gadget`
    A ZZ(α) phase gadget on two qubits — a single Z-rotation entangling gate
    widely used in variational quantum algorithms (e.g. QAOA, VQE).
    Demonstrates how a multi-qubit rotation decomposes into spiders and
    Hadamard edges.

* :func:`construct_graph_state`
    A three-qubit linear cluster / graph state.  Illustrates how graph states
    are represented in ZX as Z spiders connected by Hadamard edges, and how
    single-qubit measurements implement MBQC corrections.

* :func:`construct_teleportation`
    Quantum state teleportation on three wires (source + Bell pair).
    Shows the Bell measurement, classical correction X/Z gates and the
    "yanking" identity that collapses the protocol to an identity wire.

* :func:`construct_cnot_teleportation`
    CNOT-gate teleportation: implementing a logical CNOT between two
    non-adjacent qubits via a shared Bell pair and local operations.

* :func:`construct_magic_state_injection`
    Magic state injection circuit: T gate applied fault-tolerantly to a
    logical qubit by consuming a single-qubit magic state |T⟩ = T|+⟩ via
    a Bell measurement and an S-gate correction.

Legacy example
--------------
* :func:`construct_circuit`
    The original arbitrary 4-qubit circuit kept for backward compatibility.
"""

from __future__ import annotations

import math
from fractions import Fraction

from pyzx.utils import EdgeType, VertexType

from .common import GraphT, get_data, new_graph


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_example(name: str) -> GraphT:
    """Load a bundled example diagram from ``zxlive/examples/<name>.json``.

    Falls back gracefully: if the file is absent the calling function should
    construct the diagram programmatically.
    """
    import os
    path = get_data(f"examples/{name}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Example file not found: {path}")
    with open(path) as fh:
        g: GraphT = GraphT.from_json(fh.read())  # type: ignore[misc]
        g.set_auto_simplify(False)
        return g


def _try_load(name: str) -> GraphT | None:
    """Return the loaded example or *None* if the file is missing."""
    try:
        return _load_example(name)
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tutorial / demo examples
# ─────────────────────────────────────────────────────────────────────────────

def construct_three_cnots() -> GraphT:
    """Three alternating CNOTs on two qubits (the '3 CNOTs = SWAP' circuit).

    In ZX-calculus a CNOT gate is represented as a Z spider on the control
    wire connected by a plain wire to an X spider on the target wire.
    Alternating three CNOTs simplifies to a SWAP via spider fusion, bialgebra
    and identity removal — one of the most elegant results in the calculus.

    This diagram is the startup demo and the starting point of the interactive
    "Learn the basics" tutorial lesson.

    Layout (left-to-right):
    ::

        ─── Z ─── X ─── Z ───      (qubit 0, control / target alternates)
              |         |
        ─── X ─── Z ─── X ───      (qubit 1)
    """
    cached = _try_load("three_cnots")
    if cached is not None:
        return cached

    # Build programmatically when the JSON file is absent.
    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    # Boundaries
    in0  = g.add_vertex(B, 0, 0);  in1  = g.add_vertex(B, 1, 0)
    out0 = g.add_vertex(B, 0, 8);  out1 = g.add_vertex(B, 1, 8)

    # CNOT-1: control on qubit-0 (Z), target on qubit-1 (X)
    c1 = g.add_vertex(Z, 0, 2);  t1 = g.add_vertex(X, 1, 2)
    # CNOT-2: control on qubit-1 (Z), target on qubit-0 (X)
    c2 = g.add_vertex(Z, 1, 4);  t2 = g.add_vertex(X, 0, 4)
    # CNOT-3: control on qubit-0 (Z), target on qubit-1 (X)
    c3 = g.add_vertex(Z, 0, 6);  t3 = g.add_vertex(X, 1, 6)

    g.add_edges([(in0, c1), (c1, t2), (t2, c3), (c3, out0)], S)
    g.add_edges([(in1, t1), (t1, c2), (c2, t3), (t3, out1)], S)
    g.add_edge((c1, t1), S)
    g.add_edge((c2, t2), S)
    g.add_edge((c3, t3), S)

    g.set_inputs((in0, in1))
    g.set_outputs((out0, out1))
    return g


def construct_swap() -> GraphT:
    """The compact two-qubit SWAP diagram.

    This is the *target* state of the interactive "3 CNOTs = SWAP" tutorial
    lesson.  The lesson's completion check compares the user's current diagram
    against this reference using both structural isomorphism and matrix
    equality.

    A SWAP in ZX-calculus is most elegantly expressed as three Hadamard edges
    arranged in a crossing pattern, but the simplest form recognisable by the
    structural check is just crossing wires with no spiders.
    """
    cached = _try_load("swap")
    if cached is not None:
        return cached

    g = new_graph()
    B = VertexType.BOUNDARY
    S = EdgeType.SIMPLE

    in0  = g.add_vertex(B, 0, 0);  in1  = g.add_vertex(B, 1, 0)
    out0 = g.add_vertex(B, 0, 2);  out1 = g.add_vertex(B, 1, 2)

    # SWAP = cross the wires
    g.add_edge((in0, out1), S)
    g.add_edge((in1, out0), S)

    g.set_inputs((in0, in1))
    g.set_outputs((out0, out1))
    return g


def construct_zz_phase_gadget(alpha: Fraction = Fraction(1, 4)) -> GraphT:
    """A ZZ(α) phase gadget on two qubits.

    The phase gadget ZZ(α) applies a diagonal phase e^{iα Z⊗Z} to a two-qubit
    system.  It appears ubiquitously in variational quantum algorithms (QAOA,
    VQE, Trotterised Hamiltonians).

    In ZX-calculus it decomposes as::

        ─── H ─── Z(α) ─── H ───
                  |
        ─── H ─── Z ─── H ───

    where the central Z(α) spider carries the full phase and the flanking
    Hadamard edges convert between the Z and X bases.

    Pedagogical value
    -----------------
    * Illustrates how a *multi-qubit* phase is captured by a *single* spider.
    * Shows Hadamard edges (yellow boxes) in context.
    * A natural target for the colour-change and Euler decomposition rules.

    Parameters
    ----------
    alpha:
        Phase angle as a fraction of π.  Defaults to π/4 (the T-gate analogue).
    """
    cached = _try_load("zz_phase_gadget")
    if cached is not None:
        return cached

    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    in0  = g.add_vertex(B, 0, 0);  in1  = g.add_vertex(B, 1, 0)
    out0 = g.add_vertex(B, 0, 6);  out1 = g.add_vertex(B, 1, 6)

    # Gadget body: phase spider flanked by Hadamard edges on each qubit
    ph = g.add_vertex(Z, 0, 3)   # the lone phase spider
    g.set_phase(ph, alpha)

    leg0 = g.add_vertex(Z, 0, 3)  # dummy pass-through for qubit-0 wire
    leg1 = g.add_vertex(Z, 1, 3)  # connection point on qubit-1

    # qubit-0 wire
    g.add_edge((in0,  leg0), S)
    g.add_edge((leg0, out0), S)

    # qubit-1 wire
    g.add_edge((in1,  leg1), S)
    g.add_edge((leg1, out1), S)

    # The phase gadget "arm" hangs off qubit-1 via a Hadamard edge
    g.add_vertex(Z, 0.5, 3)   # just layout; actual structure is one central Z
    # Simplified construction: central Z(alpha) connected to both qubit wires
    # via Hadamard edges (standard phase-gadget form)
    centre = g.add_vertex(Z, 0.5, 3)
    g.set_phase(centre, alpha)
    g.add_edge((leg0, centre), H)
    g.add_edge((leg1, centre), H)

    g.set_inputs((in0, in1))
    g.set_outputs((out0, out1))
    return g


def construct_graph_state() -> GraphT:
    """A three-qubit linear cluster / graph state.

    Graph states are stabiliser states defined by an underlying graph G:
    starting from |+⟩^⊗n, apply a CZ gate between every edge (i,j) of G.
    In ZX-calculus a graph state is simply a collection of Z spiders (one per
    qubit) connected by Hadamard edges matching the graph's edges.

    The linear three-qubit cluster state is::

        |+⟩ ── H ── Z ── H ── Z ── H ── Z ── (output)
                    |         |         |
                   (0)       (1)       (2)

    — i.e. three Z spiders in a line, each pair connected by a Hadamard edge.

    Pedagogical value
    -----------------
    * Shows how graph states arise naturally in ZX as "green spider networks".
    * The single-qubit measurement pattern demonstrates MBQC: measuring qubit 0
      in the X basis (angle 0) implements an identity up to Pauli corrections
      on qubits 1–2.
    * Colour-change rule: X spiders on measured qubits become Z after applying
      H gates.
    """
    cached = _try_load("graph_state")
    if cached is not None:
        return cached

    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    # Inputs — three qubits initialised in |+⟩ (represented as open inputs)
    in0 = g.add_vertex(B, 0, 0)
    in1 = g.add_vertex(B, 1, 0)
    in2 = g.add_vertex(B, 2, 0)

    # Graph-state spiders (Z, zero phase ≡ |+⟩ after fusion)
    s0 = g.add_vertex(Z, 0, 2)
    s1 = g.add_vertex(Z, 1, 2)
    s2 = g.add_vertex(Z, 2, 2)

    # Outputs
    out0 = g.add_vertex(B, 0, 4)
    out1 = g.add_vertex(B, 1, 4)
    out2 = g.add_vertex(B, 2, 4)

    # Wire inputs to spiders and spiders to outputs
    g.add_edges([(in0, s0), (in1, s1), (in2, s2)], S)
    g.add_edges([(s0, out0), (s1, out1), (s2, out2)], S)

    # CZ ≡ Hadamard edge between spiders
    g.add_edge((s0, s1), H)
    g.add_edge((s1, s2), H)

    g.set_inputs((in0, in1, in2))
    g.set_outputs((out0, out1, out2))
    return g


def construct_teleportation() -> GraphT:
    """Quantum state teleportation on three wires.

    The standard teleportation circuit uses a Bell pair shared between Alice
    and Bob.  After Alice's Bell measurement and Bob's classical corrections
    (X and Z gates), the source state is recreated on Bob's qubit.

    In ZX-calculus the entire protocol simplifies to a bent wire (the
    "yanking" identity), which is one of the most striking results showing the
    power of diagrammatic rewriting.

    Layout (three qubit wires):
    ::

        wire 0 (Alice source):  |ψ⟩ ─── Z ───────── [measured]
                                        |
        wire 1 (Alice half):    |0⟩ ─── X ─── Z ─── [measured]
                                              |
        wire 2 (Bob):           |0⟩ ──────── X ─── Z(corr) ─── X(corr) ─── |ψ⟩

    Pedagogical value
    -----------------
    * Demonstrates the cup/cap (Bell state / measurement) structure in ZX.
    * The yanking lemma = identity removal + spider fusion collapses the
      diagram to a single wire.
    * Shows how classical control (X/Z corrections) appears as spiders with
      π-phase.
    """
    cached = _try_load("teleportation")
    if cached is not None:
        return cached

    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    # ── Wire 0 (source qubit, Alice) ──────────────────────────────────────
    in0   = g.add_vertex(B, 0, 0)
    src   = g.add_vertex(Z, 0, 2)   # CNOT control (entangles with Bell pair)

    # ── Wire 1 (Alice's half of Bell pair) ────────────────────────────────
    in1   = g.add_vertex(B, 1, 0)
    bell1 = g.add_vertex(X, 1, 2)   # CNOT target / Bell measurement
    hada  = g.add_vertex(Z, 1, 4)   # H before measurement (basis change)

    # ── Wire 2 (Bob's qubit) ─────────────────────────────────────────────
    in2   = g.add_vertex(B, 2, 0)
    bell2 = g.add_vertex(Z, 2, 1)   # Hadamard + CNOT creating Bell pair
    xcorr = g.add_vertex(X, 2, 6)   # X correction (π phase)
    zcorr = g.add_vertex(Z, 2, 8)   # Z correction (π phase)
    out2  = g.add_vertex(B, 2, 10)

    g.set_phase(xcorr, Fraction(1))  # X gate = X spider with phase π
    g.set_phase(zcorr, Fraction(1))  # Z gate = Z spider with phase π

    # Alice's side
    g.add_edge((in0,  src),   S)
    g.add_edge((src,  bell1), S)   # CNOT: control–target
    g.add_edge((in1,  bell1), S)
    g.add_edge((bell1, hada), S)

    # Bell pair creation on wires 1–2
    g.add_edge((in2,  bell2), S)
    g.add_edge((bell2, bell1), H)  # Hadamard edge = CZ component of Bell pair

    # Bob's corrections
    g.add_edge((bell2, xcorr), S)
    g.add_edge((xcorr, zcorr), S)
    g.add_edge((zcorr, out2),  S)

    # Classical measurement outcomes feed into corrections (shown as wires)
    g.add_edge((src,  zcorr), H)   # Z-basis measurement → Z correction
    g.add_edge((hada, xcorr), H)   # X-basis measurement → X correction

    g.set_inputs((in0, in1, in2))
    g.set_outputs((out2,))
    return g


def construct_cnot_teleportation() -> GraphT:
    """CNOT-gate teleportation via a shared Bell pair.

    Gate teleportation implements a logical two-qubit gate between non-adjacent
    qubits using only local operations and a pre-shared entangled resource.

    For a CNOT the resource is a Bell pair |Φ+⟩ = (|00⟩+|11⟩)/√2.  After
    local Bell measurements on both sides and classical communication, the
    effect of a CNOT is transferred to the logical qubits.

    In ZX-calculus this simplifies to the bialgebra rule: the "copy" structure
    of the CNOT is exactly the spider-fusion / copy law for Z–X pairs.

    Layout (four wires: two logical + two resource):
    ::

        wire 0 (logical ctrl):  ─── Z ─────────────── [ctrl out]
                                    |
        wire 1 (resource ctrl): |0⟩─ X ─── Z ─── [meas]
                                        |
        wire 2 (resource tgt):  |0⟩─── X ─── [meas]
                                    |
        wire 3 (logical tgt):   ─── Z ─────────────── [tgt out]

    Pedagogical value
    -----------------
    * Shows gate teleportation as a "copy" of the CNOT structure.
    * Demonstrates the bialgebra rule in a physically motivated setting.
    * Connects to fault-tolerant quantum computation (magic state injection).
    """
    cached = _try_load("cnot_teleportation")
    if cached is not None:
        return cached

    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    # Logical input/output boundaries
    in0  = g.add_vertex(B, 0, 0);  out0 = g.add_vertex(B, 0, 10)
    in3  = g.add_vertex(B, 3, 0);  out3 = g.add_vertex(B, 3, 10)

    # Resource qubit boundaries (prepared as |0⟩)
    in1  = g.add_vertex(B, 1, 0)
    in2  = g.add_vertex(B, 2, 0)

    # Logical CNOT applied via the resource
    ctrl_z  = g.add_vertex(Z, 0, 3)   # control copy
    tgt_x   = g.add_vertex(X, 3, 3)   # target copy

    # Resource Bell pair
    r_ctrl  = g.add_vertex(X, 1, 2)
    r_tgt   = g.add_vertex(Z, 2, 2)
    g.add_edge((r_ctrl, r_tgt), H)    # CZ = Hadamard edge

    # Local Bell measurements on resource qubits
    meas1   = g.add_vertex(Z, 1, 6)
    meas2   = g.add_vertex(X, 2, 6)

    # Classical corrections
    corr0   = g.add_vertex(X, 0, 7)   # X correction on ctrl
    corr3   = g.add_vertex(Z, 3, 7)   # Z correction on tgt
    g.set_phase(corr0, Fraction(1))
    g.set_phase(corr3, Fraction(1))

    # Wire up
    g.add_edge((in0,   ctrl_z), S)
    g.add_edge((ctrl_z, corr0), S)
    g.add_edge((corr0,  out0),  S)

    g.add_edge((in3,   tgt_x),  S)
    g.add_edge((tgt_x, corr3),  S)
    g.add_edge((corr3,  out3),  S)

    g.add_edge((in1,   r_ctrl), S)
    g.add_edge((r_ctrl, meas1), S)

    g.add_edge((in2,   r_tgt),  S)
    g.add_edge((r_tgt,  meas2), S)

    # CNOT structure: ctrl copies into resource, resource copies into tgt
    g.add_edge((ctrl_z, r_ctrl), S)
    g.add_edge((r_tgt,  tgt_x),  S)

    # Measurement outcomes feed corrections
    g.add_edge((meas1, corr3), H)
    g.add_edge((meas2, corr0), H)

    g.set_inputs((in0, in1, in2, in3))
    g.set_outputs((out0, out3))
    return g


# ── NEW ──────────────────────────────────────────────────────────────────────

def construct_magic_state_injection() -> GraphT:
    """Magic state injection: T gate via |T⟩ resource state.

    Magic state injection is the standard fault-tolerant technique for applying
    a non-Clifford T gate (phase π/4).  A single-qubit magic state
    |T⟩ = T|+⟩ is prepared offline and then consumed by Clifford operations
    to effectively apply T to a logical qubit.

    In ZX-calculus the injection circuit is a Z(π/4) spider (the magic state)
    linked to the logical qubit wire via a Bell measurement and an S-gate
    correction (Z(π/2) spider).

    Layout (two wires):
    ::

        wire 0 (logical qubit):  ─── Z ─── Z(π/2 corr) ─── out
                                      |
        wire 1 (ancilla / magic): |T⟩ = Z(π/4) ──── Bell meas ──── [discard]

    The key rewrite path (tutorial steps):
    1. Fuse the Z(π/4) spider with the neighbouring logical wire spider
       (phase kickback — the T phase moves onto the logical wire).
    2. Fuse the resulting spider with the S-correction spider Z(π/2)
       (π/4 + π/2 = 3π/4, or just π/4 when outcome is |0⟩).
    3. Remove any remaining zero-phase degree-2 identity spiders.

    Pedagogical value
    -----------------
    * Shows that a non-Clifford gate lives in a *single* spider phase.
    * Phase kickback = spider fusion in ZX.
    * Connects to fault-tolerant universal quantum computation:
      Clifford gates keep stabiliser structure; magic states inject the
      non-Clifford resource.
    """
    cached = _try_load("magic_state_injection")
    if cached is not None:
        return cached

    g = new_graph()
    Z, X = VertexType.Z, VertexType.X
    B    = VertexType.BOUNDARY
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    # ── Wire 0: logical qubit ─────────────────────────────────────────────
    in0    = g.add_vertex(B, 0, 0)
    # Pass-through spider on the logical wire (will fuse with magic state)
    logic  = g.add_vertex(Z, 0, 3)
    # S-gate correction (Z(π/2)) applied after kickback
    s_corr = g.add_vertex(Z, 0, 6)
    g.set_phase(s_corr, Fraction(1, 2))  # π/2
    out0   = g.add_vertex(B, 0, 9)

    # ── Wire 1: ancilla carrying the magic state ──────────────────────────
    in1    = g.add_vertex(B, 1, 0)
    # Magic state spider Z(π/4) — |T⟩ = T|+⟩
    magic  = g.add_vertex(Z, 1, 2)
    g.set_phase(magic, Fraction(1, 4))   # π/4  (T-gate phase)
    # Bell measurement: CNOT (X spider on ancilla) then H (basis change)
    bell_x = g.add_vertex(X, 1, 4)      # CNOT target on ancilla
    meas_h = g.add_vertex(Z, 1, 6)      # H before Z-basis measurement
    # Ancilla measurement outcome drives the S correction:
    # outcome |0⟩ → no correction, outcome |1⟩ → apply S.
    # In the ZX diagram the outcome wire is a Hadamard edge into s_corr.
    out1   = g.add_vertex(B, 1, 9)

    # Logical qubit wire
    g.add_edge((in0,    logic),  S)
    g.add_edge((logic,  s_corr), S)
    g.add_edge((s_corr, out0),   S)

    # Ancilla wire
    g.add_edge((in1,    magic),  S)
    g.add_edge((magic,  bell_x), S)
    g.add_edge((bell_x, meas_h), S)
    g.add_edge((meas_h, out1),   S)

    # Bell measurement couples the ancilla into the logical wire.
    # CNOT control is on the logical wire (Z spider), target on the ancilla
    # X spider — the standard CNOT ZX decomposition.
    g.add_edge((logic,  bell_x), S)   # control → target coupling

    # Measurement outcome feeds the S correction via Hadamard edge
    # (H edge = classical bit controlling a quantum correction in ZX).
    g.add_edge((meas_h, s_corr), H)

    g.set_inputs((in0, in1))
    g.set_outputs((out0, out1))
    return g


# ─────────────────────────────────────────────────────────────────────────────
# Legacy example  (kept for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def construct_circuit() -> GraphT:
    """Build an arbitrary 4-qubit ZX circuit programmatically.

    This was the original startup demo graph.  It is still importable for any
    code that references it directly, but the preferred startup demo is now
    :func:`construct_three_cnots`, which is a more pedagogically meaningful
    example tied directly into the interactive tutorial.
    """
    qubits = 4
    Z, X = VertexType.Z, VertexType.X
    S, H = EdgeType.SIMPLE, EdgeType.HADAMARD

    vlist = [
        (0,  0, Z), (1,  1, X), (2,  2, Z), (3,  3, Z),
        (4,  0, Z), (5,  1, Z), (6,  2, X), (7,  3, Z),
        (8,  0, Z), (9,  1, X), (10, 2, Z), (11, 3, Z),
        (12, 0, X), (13, 1, X), (14, 2, Z), (15, 3, X),
    ]
    elist = [
        (0,  1,  S), (0,  4,  S), (1,  5,  S), (1,  6,  S),
        (2,  6,  S), (3,  7,  S), (4,  8,  S), (5,  9,  H),
        (6,  10, S), (7,  11, S), (8,  12, S), (8,  13, S),
        (9,  13, H), (9,  14, H), (10, 13, S), (10, 14, S),
        (11, 14, S), (11, 15, S),
    ]

    nvertices = len(vlist) + 2 * qubits
    full_vlist: list[tuple[int, int, VertexType]] = []
    for i in range(qubits):
        full_vlist.append((i, i, VertexType.BOUNDARY))
    for local_id, qubit, vtype in vlist:
        full_vlist.append((local_id + qubits, qubit, vtype))
    for i in range(qubits):
        full_vlist.append((nvertices - qubits + i, i, VertexType.BOUNDARY))

    full_elist: list[tuple[int, int, EdgeType]] = [
        (u + qubits, v + qubits, et) for u, v, et in elist
    ]
    for i in range(qubits):
        full_elist.append((i, i + qubits, S))
        full_elist.append((nvertices - qubits + i, nvertices - 2 * qubits + i, S))

    g = new_graph()
    cur_row = [1] * qubits
    for _, qubit, vtype in full_vlist:
        g.add_vertex(vtype, qubit, cur_row[qubit])
        cur_row[qubit] += 1

    simple_edges   = [(u, v) for u, v, et in full_elist if et == S]
    hadamard_edges = [(u, v) for u, v, et in full_elist if et == H]
    g.add_edges(simple_edges,   S)
    g.add_edges(hadamard_edges, H)
    g.set_inputs(tuple(range(qubits)))
    g.set_outputs(tuple(range(nvertices - qubits, nvertices)))
    return g
