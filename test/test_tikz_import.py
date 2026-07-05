#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for TikZ import with error tolerance (issue #351)."""

import pytest

from zxlive.common import find_unknown_tikz_styles, from_tikz


VALID_TIKZ = r"""
\begin{tikzpicture}
    \begin{pgfonlayer}{nodelayer}
        \node [style=Z dot] (0) at (0.00, 0.00) {};
        \node [style=X dot] (1) at (0.00, -1.00) {};
    \end{pgfonlayer}
    \begin{pgfonlayer}{edgelayer}
        \draw (0) to (1);
    \end{pgfonlayer}
\end{tikzpicture}
"""


# -- Strict parsing -----------------------------------------------------------

def test_valid_tikz_import() -> None:
    g = from_tikz(VALID_TIKZ)
    assert g.num_vertices() == 2
    assert g.num_edges() == 1


def test_invalid_phase_strict_raises() -> None:
    tikz = VALID_TIKZ.replace("(0) at (0.00, 0.00) {}", "(0) at (0.00, 0.00) {???}")
    with pytest.raises(ValueError):
        from_tikz(tikz)


def test_unparseable_node_strict_raises() -> None:
    tikz = VALID_TIKZ.replace(
        r"\node [style=X dot] (1)",
        r"\node [style=X dot] (1) at (0.00, -1.00) {};" + "\n        " + r"\node badformat",
    )
    with pytest.raises(ValueError):
        from_tikz(tikz)


def test_unknown_style_strict_raises() -> None:
    tikz = VALID_TIKZ.replace("style=X dot", "style=bogus_style")
    with pytest.raises(ValueError):
        from_tikz(tikz)


def test_overlapping_vertices_strict_raises() -> None:
    tikz = VALID_TIKZ.replace("(0.00, -1.00)", "(0.00, 0.00)")
    with pytest.raises(Warning):
        from_tikz(tikz)


def test_completely_broken_tikz_raises() -> None:
    with pytest.raises(Exception):
        from_tikz("this is not tikz at all")


# -- Tolerant parsing (ignore_errors=True) ------------------------------------

def test_invalid_phase_ignored() -> None:
    """An unrecognised phase label is replaced with the default phase."""
    tikz = VALID_TIKZ.replace("(0) at (0.00, 0.00) {}", "(0) at (0.00, 0.00) {???}")
    g = from_tikz(tikz, ignore_errors=True)
    assert g.num_vertices() == 2
    assert g.num_edges() == 1


def test_unparseable_node_ignored() -> None:
    """A malformed node definition is skipped, keeping the rest."""
    tikz = VALID_TIKZ.replace(
        r"\node [style=X dot] (1)",
        r"\node [style=X dot] (1) at (0.00, -1.00) {};" + "\n        " + r"\node badformat",
    )
    g = from_tikz(tikz, ignore_errors=True)
    assert g.num_vertices() == 2
    assert g.num_edges() == 1


def test_edge_referencing_missing_node_ignored() -> None:
    """An edge referencing a non-existent node is skipped."""
    tikz = VALID_TIKZ.replace(
        r"\draw (0) to (1);",
        r"\draw (0) to (1);" + "\n        " + r"\draw (0) to (99);",
    )
    g = from_tikz(tikz, ignore_errors=True)
    assert g.num_vertices() == 2
    assert g.num_edges() == 1


def test_unknown_node_style_ignored() -> None:
    """A node with an unrecognised style is imported as a boundary vertex."""
    tikz = VALID_TIKZ.replace("style=X dot", "style=bogus_style")
    g = from_tikz(tikz, ignore_errors=True)
    assert g.num_vertices() == 2
    assert g.num_edges() == 1


def test_overlapping_vertices_fused() -> None:
    """Two vertices at the same position are silently fused."""
    tikz = VALID_TIKZ.replace("(0.00, -1.00)", "(0.00, 0.00)")
    g = from_tikz(tikz, ignore_errors=True)
    assert g.num_vertices() == 1


# -- find_unknown_tikz_styles ------------------------------------------------

def test_find_unknown_styles_none() -> None:
    """Valid TikZ reports no unknown styles."""
    assert find_unknown_tikz_styles(VALID_TIKZ) == []


def test_find_unknown_styles_one() -> None:
    tikz = VALID_TIKZ.replace("style=X dot", "style=my_custom")
    assert find_unknown_tikz_styles(tikz) == ["my_custom"]


def test_find_unknown_styles_multiple() -> None:
    tikz = VALID_TIKZ.replace("style=Z dot", "style=foo").replace(
        "style=X dot", "style=bar")
    assert find_unknown_tikz_styles(tikz) == ["foo", "bar"]


def test_find_unknown_styles_deduplicates() -> None:
    tikz = VALID_TIKZ.replace("style=Z dot", "style=bogus").replace(
        "style=X dot", "style=bogus")
    assert find_unknown_tikz_styles(tikz) == ["bogus"]


def test_find_unknown_styles_case_insensitive() -> None:
    """A style that matches a known synonym in a different case is not unknown."""
    tikz = VALID_TIKZ.replace("style=Z dot", "style=Z DOT")
    assert find_unknown_tikz_styles(tikz) == []
