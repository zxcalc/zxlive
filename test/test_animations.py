from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

import zxlive.rewrite_action as rewrite_action_module
from zxlive.animations import make_animation
from zxlive.common import GraphT, VT, new_graph, set_settings_value
from zxlive.proof_panel import ProofPanel
from zxlive.rewrite_action import RewriteAction
from zxlive.rewrite_data import rules_basic


def _push_pauli_graph(num_paulis: int) -> tuple[GraphT, list[VT]]:
    """Return a graph with ``num_paulis`` independent X(pi) -> Z(pi/4) pairs, and the X(pi) vertices."""
    g = new_graph()
    paulis = []
    for i in range(num_paulis):
        q = 2 * i
        b_in = g.add_vertex(VertexType.BOUNDARY, qubit=q, row=0)
        # Spider before Pauli: the lower index must be the spider until #617 is merged.
        spider = g.add_vertex(VertexType.Z, qubit=q, row=2, phase=Fraction(1, 4))
        pauli = g.add_vertex(VertexType.X, qubit=q, row=1, phase=Fraction(1))
        b_out1 = g.add_vertex(VertexType.BOUNDARY, qubit=q, row=3)
        b_out2 = g.add_vertex(VertexType.BOUNDARY, qubit=q + 1, row=3)
        for v, w in ((b_in, pauli), (pauli, spider), (spider, b_out1), (spider, b_out2)):
            g.add_edge((v, w))
        paulis.append(pauli)
    return g, paulis


def _apply_push_pauli(qtbot: QtBot, g: GraphT) -> ProofPanel:
    """Apply Push Pauli to the whole graph with rewrite animations enabled."""
    set_settings_value("rewrite-animations", True, bool)
    panel = ProofPanel(g)
    qtbot.addWidget(panel)
    action = RewriteAction.from_rewrite_data(rules_basic["pauli"])
    action.update_active(panel.graph, [], [])
    assert action.enabled
    action.do_rewrite(panel)
    return panel


def _record_animations(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    """Return a list that collects every (anim_before, anim_after) built by make_animation."""
    recorded: list[tuple[Any, Any]] = []

    def record(*args: Any) -> tuple[Any, Any]:
        recorded.append(make_animation(*args))
        return recorded[-1]
    monkeypatch.setattr(rewrite_action_module, "make_animation", record)
    return recorded


@pytest.mark.parametrize("num_paulis", [1, 2])
def test_push_pauli_with_animation_adds_rewrite_step(qtbot: QtBot, num_paulis: int) -> None:
    g, paulis = _push_pauli_graph(num_paulis)

    panel = _apply_push_pauli(qtbot, g)

    # The step is only pushed once the "before" animation has finished.
    qtbot.waitUntil(lambda: panel.undo_stack.count() == 1)
    assert not set(paulis) & set(panel.graph.vertices())


@pytest.mark.parametrize("num_paulis", [1, 2])
def test_push_pauli_animation_covers_every_match(
        qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, num_paulis: int) -> None:
    g, _ = _push_pauli_graph(num_paulis)
    recorded = _record_animations(monkeypatch)

    _apply_push_pauli(qtbot, g)

    anim_before, anim_after = recorded[0]
    assert anim_before.animationCount() == num_paulis
    assert anim_after.animationCount() == num_paulis
