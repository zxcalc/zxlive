from __future__ import annotations

import importlib.util
from pathlib import Path


_module_path = Path(__file__).resolve().parents[1] / "zxlive" / "latex_to_html.py"
_spec = importlib.util.spec_from_file_location("latex_to_html", _module_path)
assert _spec and _spec.loader
_latex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_latex)

dummy_text_to_html = _latex.dummy_text_to_html


def test_plain_text_is_escaped() -> None:
    assert dummy_text_to_html("a < b") == "a &lt; b"


def test_inline_math_symbols() -> None:
    out = dummy_text_to_html("$\\alpha + x_1^2$")
    assert "α" in out
    assert "<sub>1</sub>" in out
    assert "<sup>2</sup>" in out


def test_fraction_renders() -> None:
    out = dummy_text_to_html("$\\frac{1}{2}$")
    assert "&frasl;" in out
    assert "<sup>1</sup>" in out
    assert "<sub>2</sub>" in out


def test_more_katex_commands_render() -> None:
    out = dummy_text_to_html(r"$\\int_0^1 x^2 dx + \\sum_{i=0}^{n} i + \\mathbb{R}$")
    assert "∫" in out
    assert "∑" in out
    assert "ℝ" in out
    assert "<sub>0</sub>" in out
    assert "<sup>1</sup>" in out


def test_mixed_text_and_math() -> None:
    out = dummy_text_to_html("phase $\\pi/2$ rad")
    assert out.startswith("phase ")
    assert "π/2" in out
    assert out.endswith(" rad")


def test_vec_renders() -> None:
    out = dummy_text_to_html(r"$\vec{x} + \vec{AB}$")
    assert "x⃗" in out
    assert "A⃗B⃗" in out


def test_quantum_ket_bra_commands_render() -> None:
    out = dummy_text_to_html(r"$\ket{\psi} + \bra{\phi} + \braket{0|1} + \ketbra{0}{1}$")
    assert "|ψ⟩" in out
    assert "⟨ϕ|" in out
    assert "⟨0|1⟩" in out
    assert "|0⟩⟨1|" in out
