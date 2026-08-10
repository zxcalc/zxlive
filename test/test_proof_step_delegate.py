"""Tests for the proof-step list rendering (``ProofStepItemDelegate``).

Regression coverage for the issue where derivation steps overflow when the
application font is large: the row height must grow together with the font that
``paint()`` actually uses, otherwise descenders of the step labels are cut off.
"""

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtCore import QModelIndex
from pytestqt.qtbot import QtBot

from zxlive.proof import ProofStepItemDelegate


def _height_for_font(font: QFont) -> int:
    delegate = ProofStepItemDelegate()
    option = QStyleOptionViewItem()
    option.font = font
    return delegate.sizeHint(option, QModelIndex()).height()


def test_row_height_scales_with_font_size(qtbot: QtBot) -> None:
    """A larger font must yield a taller row so text is not clipped."""
    small = _height_for_font(QFont("Arial", 11))
    large = _height_for_font(QFont("Arial", 30))
    assert large > small


def test_row_height_fits_painted_text(qtbot: QtBot) -> None:
    """The row must be at least as tall as the text painted with that font."""
    for size in (11, 20, 30, 40):
        font = QFont("Arial", size)
        text_height = QFontMetrics(font).height()
        assert _height_for_font(font) >= text_height
