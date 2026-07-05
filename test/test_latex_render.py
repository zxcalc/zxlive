"""Unit tests for zxlive.latex_render module.

Covers is_latex detection, Dirac notation preprocessing (including the
two-argument \\braket{a}{b} form), SVG rendering, and fallback behaviour.
"""

from zxlive.latex_render import (
    is_latex,
    _preprocess_dirac,
    _fallback_svg,
    _svg_viewbox_empty,
    latex_to_svg,
)


# Tests to verify if a given string is correctly identified as LaTeX markup

class TestIsLatex:
    """Tests for the is_latex() detection function."""

    def test_empty_string(self) -> None:
        assert not is_latex("")

    def test_plain_text(self) -> None:
        assert not is_latex("hello world")

    def test_dollar_sign(self) -> None:
        assert is_latex("$x$")

    def test_backslash_command(self) -> None:
        assert is_latex(r"\alpha")

    def test_ket(self) -> None:
        assert is_latex(r"\ket{0}")

    def test_bra(self) -> None:
        assert is_latex(r"\bra{1}")

    def test_braket_single(self) -> None:
        assert is_latex(r"\braket{0}")

    def test_braket_double(self) -> None:
        assert is_latex(r"\braket{a}{b}")

    def test_superscript(self) -> None:
        assert is_latex("x^2")

    def test_subscript(self) -> None:
        assert is_latex("x_1")

    def test_frac(self) -> None:
        assert is_latex(r"\frac{1}{2}")


# Tests for expanding Dirac notation (ket, bra, braket) into standard LaTeX

class TestPreprocessDirac:
    """Tests for the _preprocess_dirac() Dirac notation expander."""

    def test_ket(self) -> None:
        result = _preprocess_dirac(r"\ket{0}")
        assert r"|{0}\rangle" == result

    def test_bra(self) -> None:
        result = _preprocess_dirac(r"\bra{1}")
        assert r"\langle{1}|" == result

    def test_braket_single_arg(self) -> None:
        """Single-argument form: \\braket{a} -> \\langle{a}\\rangle"""
        result = _preprocess_dirac(r"\braket{a}")
        assert r"\langle{a}\rangle" == result

    def test_braket_two_args(self) -> None:
        """Two-argument form: \\braket{a}{b} -> \\langle{a}|{b}\\rangle"""
        result = _preprocess_dirac(r"\braket{a}{b}")
        assert r"\langle{a}|{b}\rangle" == result

    def test_no_dirac(self) -> None:
        """Plain LaTeX should pass through unchanged."""
        text = r"\frac{1}{2}"
        assert _preprocess_dirac(text) == text


# Tests for the SVG fallback mechanism when LaTeX rendering fails

class TestFallbackSvg:
    """Tests for the _fallback_svg() fallback generator."""

    def test_returns_bytes(self) -> None:
        result = _fallback_svg("hello", "#000000", 24)
        assert isinstance(result, bytes)

    def test_valid_svg(self) -> None:
        result = _fallback_svg("hello", "#000000", 24)
        assert b"<svg" in result
        assert b"</svg>" in result

    def test_contains_text(self) -> None:
        result = _fallback_svg("hi", "#222222", 16)
        assert b"hi" in result

    def test_empty_text_produces_space(self) -> None:
        result = _fallback_svg("$  $", "#000000", 24)
        # After stripping $ and whitespace the escaped text should not be empty
        assert b"<text" in result

    def test_color_in_svg(self) -> None:
        result = _fallback_svg("x", "#ff0000", 12)
        assert b"#ff0000" in result


# Tests for detecting empty or invalid SVG viewBoxes

class TestSvgViewboxEmpty:
    """Tests for the _svg_viewbox_empty() helper."""

    def test_no_viewbox(self) -> None:
        assert _svg_viewbox_empty(b"<svg></svg>")

    def test_zero_dimensions(self) -> None:
        assert _svg_viewbox_empty(b'<svg viewBox="0 0 0 0"></svg>')

    def test_valid_viewbox(self) -> None:
        assert not _svg_viewbox_empty(b'<svg viewBox="0 0 100 50"></svg>')


# Tests for the main LaTeX-to-SVG conversion and rendering quality

class TestLatexToSvg:
    """Tests for the latex_to_svg() rendering function."""

    def test_returns_bytes(self) -> None:
        result = latex_to_svg(r"\alpha")
        assert isinstance(result, bytes)

    def test_valid_svg_output(self) -> None:
        result = latex_to_svg(r"\alpha")
        assert b"<svg" in result

    def test_invalid_mathtext_falls_back(self) -> None:
        """Deliberately invalid mathtext should not raise; it should return fallback SVG."""
        result = latex_to_svg(r"\notacommand{{{")
        assert isinstance(result, bytes)
        assert b"<svg" in result

    def test_dark_color(self) -> None:
        result = latex_to_svg(r"x^2", color="#e0e0e0")
        assert isinstance(result, bytes)

    def test_custom_size(self) -> None:
        result = latex_to_svg(r"y_1", size=32)
        assert isinstance(result, bytes)

    def test_ket_input(self) -> None:
        result = latex_to_svg(r"\ket{0}")
        assert isinstance(result, bytes)
        assert b"<svg" in result

    def test_braket_two_arg(self) -> None:
        result = latex_to_svg(r"\braket{a}{b}")
        assert isinstance(result, bytes)
        assert b"<svg" in result

    def test_complex_formula(self) -> None:
        """Test that a complex formula renders successfully without fallback."""
        formula = r"f(x) = \int_{-\infty}^{\infty} \hat{f}(\xi)\, e^{2\pi i \xi x}\, d\xi"
        result = latex_to_svg(formula)
        assert b"<svg" in result
        
        # Test whether the viewBox is valid (e.g. didn't silently fail)
        from zxlive.latex_render import _svg_viewbox_empty
        assert not _svg_viewbox_empty(result)

    def test_hello_and_math_hello_same_size(self) -> None:
        """'hello' and '$hello$' should render to similarly-sized SVGs.

        latex_to_svg() wraps bare text in $...$ before calling matplotlib, so
        both inputs go through the same math-mode renderer.  Because each call
        creates an independent matplotlib Figure the resulting SVG bytes differ
        by tiny floating-point layout values, but the *dimensions* (viewBox
        width and height) must be within a small tolerance.
        """
        import re

        def _viewbox(svg: bytes) -> tuple[float, float]:
            m = re.search(rb'viewBox\s*=\s*["\']([^"\']+)["\']', svg)
            assert m is not None, "No viewBox found in SVG"
            parts = m.group(1).strip().split()
            return float(parts[2]), float(parts[3])

        svg_plain = latex_to_svg("hello")
        svg_math  = latex_to_svg("$hello$")

        w1, h1 = _viewbox(svg_plain)
        w2, h2 = _viewbox(svg_math)

        # Widths and heights should match within 5 %
        assert abs(w1 - w2) / max(w1, w2) < 0.05, (
            f"Width mismatch: {w1:.2f} vs {w2:.2f}"
        )
        assert abs(h1 - h2) / max(h1, h2) < 0.05, (
            f"Height mismatch: {h1:.2f} vs {h2:.2f}"
        )
