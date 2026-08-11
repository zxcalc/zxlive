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
from pathlib import Path
from typing import cast

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType

from zxlive.common import new_graph
from zxlive.editor_base_panel import EditorBasePanel, PatternsListWidget, string_to_complex
from zxlive.settings import display_setting


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


def _patterns_widget(qtbot: QtBot, tmp_path: Path) -> tuple[QWidget, PatternsListWidget]:
    graph = new_graph()
    graph.add_vertex(VertexType.Z, row=0, qubit=0)
    (tmp_path / "example.zxg").write_text(graph.to_json(), encoding="utf-8")
    parent = QWidget()
    qtbot.addWidget(parent)
    widget = PatternsListWidget(cast(EditorBasePanel, parent), str(tmp_path))
    qtbot.addWidget(widget)
    return parent, widget


def test_pattern_tooltip_contains_diagram_preview(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type(display_setting), "previews_show", property(lambda _self: True))
    _parent, widget = _patterns_widget(qtbot, tmp_path)
    item = widget.item(0)

    assert widget.hasMouseTracking()
    assert item.toolTip() == ""
    widget._set_pattern_tooltip(item)

    assert item.toolTip().startswith('<img src="data:image/png;base64,')


def test_pattern_tooltip_respects_preview_setting(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type(display_setting), "previews_show", property(lambda _self: False))
    _parent, widget = _patterns_widget(qtbot, tmp_path)
    item = widget.item(0)

    widget._set_pattern_tooltip(item)

    assert item.toolTip() == ""


def test_invalid_pattern_does_not_get_tooltip(
        qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type(display_setting), "previews_show", property(lambda _self: True))
    _parent, widget = _patterns_widget(qtbot, tmp_path)
    (tmp_path / "example.zxg").write_text("invalid", encoding="utf-8")
    item = widget.item(0)

    widget._set_pattern_tooltip(item)

    assert item.toolTip() == ""
