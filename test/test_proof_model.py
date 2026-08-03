"""Self-check for ProofModel tree ops used by grouped rewrite expansion."""

from __future__ import annotations

from zxlive.common import GraphT, new_graph
from zxlive.proof import ProofModel, Rewrite


def _g() -> GraphT:
    return new_graph()


def test_rename_step_emits_row_offset_by_one() -> None:
    model = ProofModel(_g())
    model.add_rewrite(Rewrite("A", "A", _g()))
    # steps[0] lives at view row 1 (row 0 is START)
    assert model.data(model.index(1, 0)) == "A"
    model.rename_step(0, "Renamed")
    assert model.data(model.index(1, 0)) == "Renamed"


def test_set_sub_graph_updates_only_sub_step() -> None:
    model = ProofModel(_g())
    model.add_rewrite(Rewrite("A", "A", _g()))
    model.add_rewrite(Rewrite("B", "B", _g()))
    model.group_steps(0, 1)
    new_g = _g()
    new_g.add_vertex()
    model.set_sub_graph(0, 0, new_g)
    grouped = model.steps[0].grouped_rewrites
    assert grouped is not None
    assert grouped[0].graph.num_vertices() == 1
    assert grouped[1].graph.num_vertices() == 0


def test_truncate_group_ungroups_when_one_kept() -> None:
    model = ProofModel(_g())
    model.add_rewrite(Rewrite("A", "A", _g()))
    model.add_rewrite(Rewrite("B", "B", _g()))
    model.group_steps(0, 1)
    original = model.truncate_group(0, 1)
    assert original.grouped_rewrites is not None
    assert len(original.grouped_rewrites) == 2
    assert model.steps[0].grouped_rewrites is None
    assert model.steps[0].display_name == "A"
    model.restore_group(0, original)
    assert model.steps[0].grouped_rewrites is not None
    assert len(model.steps[0].grouped_rewrites) == 2
