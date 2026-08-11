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


import pytest
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from zxlive.editor_base_panel import create_list_widget, string_to_complex, vertices_data


def test_string_to_complex() -> None:
    # Test empty input clears the phase.
    assert string_to_complex('') == 0

    # Test a complex input.
    assert string_to_complex('-123+456j') == -123 + 456j

    # Test complex phase specified with variables (not supported).
    with pytest.raises(ValueError):
        string_to_complex('a+bj')

    # Test bad input.
    with pytest.raises(ValueError):
        string_to_complex('bad input')


def test_vertex_palette_is_uniform_and_fits_labels(qtbot: QtBot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    vertex_list = create_list_widget(parent, vertices_data(), lambda _: None, lambda _: None)  # type: ignore[arg-type]
    vertex_list.setFont(QFont("Arial", 30))
    vertex_list.resize(300, 300)
    vertex_list.show()

    items = [item for row in range(vertex_list.count())
             if (item := vertex_list.item(row)) is not None]
    boundary = next(item for item in items if item.text() == "boundary")

    # Every entry occupies the same, uniformly sized cell...
    grid = vertex_list.gridSize()
    assert grid.isValid()
    assert len({vertex_list.visualItemRect(item).height() for item in items}) == 1

    # ...while the longest label still has enough width to avoid being clipped.
    assert grid.width() >= QFontMetrics(vertex_list.font()).horizontalAdvance(boundary.text())
