"""Tests for TikZ proof export (zxlive.tikz)."""

import re
from typing import Iterator

import pytest
from PySide6.QtCore import QSettings
from pyzx.utils import VertexType
from pytestqt.qtbot import QtBot

from zxlive.common import GraphT, new_graph
from zxlive.proof import ProofModel, Rewrite
from zxlive.settings import refresh_pyzx_tikz_settings
from zxlive.tikz import _escape_tex, proof_to_tikz


# Known TikZ settings that the regexes and expected coordinates below assume.
# Without this, persisted user settings (e.g. a small max-width causing line
# wrapping, or a custom Z-spider style name) could make these tests flaky.
_TIKZ_LAYOUT: dict[str, float] = {
    "tikz/layout/hspace": 2.0,
    "tikz/layout/vspace": 2.0,
    "tikz/layout/max-width": 10.0,
}
_TIKZ_EXPORT: dict[str, str] = {
    "tikz/Z-spider-export": "Z dot",
}


@pytest.fixture(autouse=True)
def _isolate_tikz_settings() -> Iterator[None]:
    """Set known TikZ settings for the duration of each test."""
    settings = QSettings("zxlive", "zxlive")
    saved: dict[str, object] = {
        key: settings.value(key) if settings.contains(key) else None
        for key in {**_TIKZ_LAYOUT, **_TIKZ_EXPORT}
    }
    for key, value in {**_TIKZ_LAYOUT, **_TIKZ_EXPORT}.items():
        settings.setValue(key, value)
    # sync() so other QSettings instances (e.g. those created inside
    # proof_to_tikz()) observe the overrides.
    settings.sync()
    refresh_pyzx_tikz_settings()
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)
        settings.sync()
        refresh_pyzx_tikz_settings()


def _make_graph(qubit_min: float, qubit_max: float) -> GraphT:
    """Build a minimal graph spanning the given qubit range."""
    g = new_graph()
    g.add_vertex(VertexType.Z, qubit=qubit_min, row=0)
    g.add_vertex(VertexType.Z, qubit=qubit_max, row=1)
    return g


# Regex for the equal-sign nodes emitted by proof_to_tikz.
# Captures the y-coordinate as group 1.
_EQ_NODE_RE = re.compile(
    r"\\node \[style=none\] \(\d+\) at \([^,]+, (-?[\d.]+)\)"
)

# Regex for Z-spider vertex nodes. Captures (x, y) as groups 1 and 2.
_Z_NODE_RE = re.compile(
    r"\\node \[style=Z dot\] \(\d+\) at \((-?[\d.]+), (-?[\d.]+)\)"
)


def test_eq_sign_uses_max_height(qtbot: QtBot) -> None:
    """Equal sign between steps is centred using the taller of the two graphs."""
    tall = _make_graph(0, 4)   # height 4
    short = _make_graph(0, 1)  # height 1

    proof = ProofModel(tall)
    proof.add_rewrite(Rewrite("r", "r", short))

    tikz = proof_to_tikz(proof)
    eq_nodes = _EQ_NODE_RE.findall(tikz)
    assert len(eq_nodes) == 1

    y = float(eq_nodes[0])
    # yoffset starts at -10, so y = -(-10) - eq_height/2 = 10 - eq_height/2.
    # With the fix, eq_height = max(4, 1) = 4, giving y = 8.0.
    # Without the fix, eq_height = 1, giving y = 9.5.
    assert y == 8.0


def test_eq_sign_symmetric_heights(qtbot: QtBot) -> None:
    """When adjacent graphs have equal heights, eq_height equals that height."""
    g1 = _make_graph(0, 3)
    g2 = _make_graph(0, 3)

    proof = ProofModel(g1)
    proof.add_rewrite(Rewrite("r", "r", g2))

    tikz = proof_to_tikz(proof)
    eq_nodes = _EQ_NODE_RE.findall(tikz)
    assert len(eq_nodes) == 1

    y = float(eq_nodes[0])
    # eq_height = max(3, 3) = 3, so y = 10 - 1.5 = 8.5.
    assert y == 8.5


def test_eq_sign_short_then_tall(qtbot: QtBot) -> None:
    """Equal sign is still correct when the second graph is taller."""
    short = _make_graph(0, 1)  # height 1
    tall = _make_graph(0, 5)   # height 5

    proof = ProofModel(short)
    proof.add_rewrite(Rewrite("r", "r", tall))

    tikz = proof_to_tikz(proof)
    eq_nodes = _EQ_NODE_RE.findall(tikz)
    assert len(eq_nodes) == 1

    y = float(eq_nodes[0])
    # eq_height = max(1, 5) = 5, so y = 10 - 2.5 = 7.5.
    assert y == 7.5


def test_offset_graph_is_normalised(qtbot: QtBot) -> None:
    """Graphs drawn away from the origin are translated to start at qubit 0."""
    g = _make_graph(5, 8)  # height 3, but offset to qubit 5-8

    proof = ProofModel(g)
    tikz = proof_to_tikz(proof)

    ys = [float(y) for _, y in _Z_NODE_RE.findall(tikz)]
    # After normalisation the qubit span should be 0..3, mapped to
    # y-coordinates -yoffset .. -(yoffset+3) = 10 .. 7.
    assert min(ys) == 7.0
    assert max(ys) == 10.0


def test_offset_graphs_align_eq_sign(qtbot: QtBot) -> None:
    """Equal sign aligns correctly even when graphs are offset from the origin."""
    # Both graphs have height 2 but sit at different qubit offsets.
    g1 = _make_graph(10, 12)  # height 2, offset at qubit 10
    g2 = _make_graph(3, 5)    # height 2, offset at qubit 3

    proof = ProofModel(g1)
    proof.add_rewrite(Rewrite("r", "r", g2))

    tikz = proof_to_tikz(proof)
    eq_nodes = _EQ_NODE_RE.findall(tikz)
    assert len(eq_nodes) == 1

    y = float(eq_nodes[0])
    # Both heights are 2 after normalisation, so eq_height = 2, y = 10 - 1.0 = 9.0.
    assert y == 9.0


def test_eq_sign_after_wrap_ignores_prev_height(qtbot: QtBot) -> None:
    """After a row wrap, the equal sign is centred using only the current graph."""
    # Force every graph to wrap onto a new row.
    settings = QSettings("zxlive", "zxlive")
    settings.setValue("tikz/layout/max-width", 0.0)
    settings.sync()

    tall = _make_graph(0, 4)   # height 4
    short = _make_graph(0, 1)  # height 1

    proof = ProofModel(tall)
    proof.add_rewrite(Rewrite("r", "r", short))

    tikz = proof_to_tikz(proof)
    eq_nodes = _EQ_NODE_RE.findall(tikz)
    assert len(eq_nodes) == 1

    y = float(eq_nodes[0])
    # After the first graph wraps, yoffset becomes -10 + 4 + 2 = -4, so the eq
    # sign is at y = 4 - eq_height/2. Since the previous graph is on a different
    # row, eq_height should be only the current graph's height (1), giving 3.5.
    # If prev_height leaked across the wrap, eq_height would be max(4, 1) = 4,
    # giving 2.0.
    assert y == 3.5


def test_escape_tex_passes_safe_chars_through() -> None:
    assert _escape_tex("fuse spiders") == "fuse spiders"
    assert _escape_tex("ABC123") == "ABC123"


def test_escape_tex_escapes_special_chars() -> None:
    assert _escape_tex("a%b") == r"a\%b"
    assert _escape_tex("a#b") == r"a\#b"
    assert _escape_tex("a&b") == r"a\&b"
    assert _escape_tex("a$b") == r"a\$b"
    assert _escape_tex("a_b") == r"a\_b"
    assert _escape_tex("a{b}c") == r"a\{b\}c"
    assert _escape_tex(r"a\b") == r"a\backslash{}b"
    assert _escape_tex("a^b") == r"a\string^b"
    assert _escape_tex("a~b") == r"a\string~b"


def test_proof_to_tikz_escapes_rule_name(qtbot: QtBot) -> None:
    """A rule name with TeX-special characters does not break the eq label."""
    g1 = _make_graph(0, 1)
    g2 = _make_graph(0, 1)

    # An adversarial rule name that would otherwise close the \mathit{...} block.
    proof = ProofModel(g1)
    proof.add_rewrite(Rewrite("evil}{x", "evil}{x", g2))

    tikz = proof_to_tikz(proof)
    # The raw "}{" must not appear in the output unescaped.
    assert "evil}{x" not in tikz
    assert r"evil\}\{x" in tikz
