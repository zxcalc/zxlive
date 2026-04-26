"""Tests for TikZ proof export (zxlive.tikz)."""

from pyzx.utils import VertexType
from pytestqt.qtbot import QtBot

from zxlive.common import new_graph
from zxlive.proof import ProofModel, Rewrite
from zxlive.tikz import _escape_tex, proof_to_tikz


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
    g1 = new_graph()
    g1.add_vertex(VertexType.Z, qubit=0, row=0)
    g1.add_vertex(VertexType.Z, qubit=1, row=1)
    g2 = new_graph()
    g2.add_vertex(VertexType.Z, qubit=0, row=0)
    g2.add_vertex(VertexType.Z, qubit=1, row=1)

    # An adversarial rule name that would otherwise close the \mathit{...} block.
    proof = ProofModel(g1)
    proof.add_rewrite(Rewrite("evil}{x", "evil}{x", g2))

    tikz = proof_to_tikz(proof)
    # The raw "}{" must not appear in the output unescaped.
    assert "evil}{x" not in tikz
    assert r"evil\}\{x" in tikz
