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

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Dict, Any

from PySide6.QtGui import QIcon, QFontDatabase
from typing_extensions import TypedDict, NotRequired

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QLineEdit, QPushButton, QWidget,
    QVBoxLayout, QSpinBox, QDoubleSpinBox, QLabel, QHBoxLayout, QTabWidget,
    QComboBox, QApplication
)

from .common import get_settings_value, T, get_data
from .settings import (
    refresh_pyzx_tikz_settings, defaults, display_setting, color_schemes
)

if TYPE_CHECKING:
    from .mainwindow import MainWindow


class FormInputType(IntEnum):
    Str = 0
    Int = 1
    Float = 2
    Folder = 3
    Combo = 4


class SettingsData(TypedDict):
    id: str
    label: str
    type: FormInputType
    data: NotRequired[dict[Any, str]]


color_scheme_data = {
    id: scheme["label"] for id, scheme in color_schemes.items()
}

tab_positioning_data = {
    QTabWidget.TabPosition.North: "Top",
    QTabWidget.TabPosition.South: "Bottom",
    QTabWidget.TabPosition.West: "Left",
    QTabWidget.TabPosition.East: "Right"
}

snap_to_grid_data = {'2': "2", '4': "4", '8': "8", '16': "16"}

input_circuit_formats = {
    'openqasm': "standard OpenQASM",
    'sqasm': "Spider QASM",
    'sqasm-no-simplification': "Spider QASM (no simplification)",
}

combo_true_false = {
    'True': 'True',
    'False': 'False'
}


general_settings: list[SettingsData] = [
    {"id": "path/custom-rules", "label": "Custom rules path", "type": FormInputType.Folder},
    {"id": "color-scheme", "label": "Color scheme", "type": FormInputType.Combo, "data": color_scheme_data},
    {"id": "tab-bar-location", "label": "Tab bar location", "type": FormInputType.Combo, "data": tab_positioning_data},
    {"id": "snap-granularity", "label": "Snap-to-grid granularity", "type": FormInputType.Combo, "data": snap_to_grid_data},
    {"id": "input-circuit-format", "label": "Input Circuit as", "type": FormInputType.Combo, "data": input_circuit_formats},
    {"id": "previews-show", "label": "Show rewrite previews","type": FormInputType.Combo, "data": combo_true_false}
]


font_settings: list[SettingsData] = [
    {"id": "font/size", "label": "Font size", "type": FormInputType.Int},
    # Font families can be loaded after a QGuiApplication is constructed.
    # load_font_families needs to be called once a QGuiApplication is up.
    {"id": "font/family", "label": "Font family", "type": FormInputType.Combo, "data": {"Ariel": "Ariel"}},
]


def load_font_families() -> None:
    index = next(i for i, d in enumerate(font_settings) if d["id"] == "font/family")
    font_settings[index]["data"] |= {f: f for f in QFontDatabase.families()}


tikz_export_settings: list[SettingsData] = [
    {"id": "tikz/Z-spider-export", "label": "Z-spider", "type": FormInputType.Str},
    {"id": "tikz/Z-phase-export", "label": "Z-spider with phase", "type": FormInputType.Str},
    {"id": "tikz/X-spider-export", "label": "X-spider", "type": FormInputType.Str},
    {"id": "tikz/X-phase-export", "label": "X-spider with phase", "type": FormInputType.Str},
    {"id": "tikz/Hadamard-export", "label": "Hadamard", "type": FormInputType.Str},
    {"id": "tikz/w-input-export", "label": "W input", "type": FormInputType.Str},
    {"id": "tikz/w-output-export", "label": "W output", "type": FormInputType.Str},
    {"id": "tikz/z-box-export", "label": "Z box", "type": FormInputType.Str},
    {"id": "tikz/edge-W-export", "label": "W io edge", "type": FormInputType.Str},
]

tikz_import_settings: list[SettingsData] = [
    {"id": "tikz/Z-spider-import", "label": "Z-spider", "type": FormInputType.Str},
    {"id": "tikz/w-input-import", "label": "W input", "type": FormInputType.Str},
    {"id": "tikz/w-output-import", "label": "W output", "type": FormInputType.Str},
    {"id": "tikz/z-box-import", "label": "Z box", "type": FormInputType.Str},
    {"id": "tikz/edge-W-import", "label": "W io edge", "type": FormInputType.Str},
]

tikz_layout_settings: list[SettingsData] = [
    {"id": "tikz/layout/hspace", "label": "Horizontal spacing", "type": FormInputType.Float},
    {"id": "tikz/layout/vspace", "label": "Vertical spacing", "type": FormInputType.Float},
    {"id": "tikz/layout/max-width", "label": "Maximum width", "type": FormInputType.Float},
]

tikz_rule_name_settings: list[SettingsData] = [
    {"id": "tikz/names/fuse spiders", "label": "fuse spiders", "type": FormInputType.Str},
    {"id": "tikz/names/bialgebra", "label": "bialgebra", "type": FormInputType.Str},
    {"id": "tikz/names/change color to Z", "label": "change color to Z", "type": FormInputType.Str},
    {"id": "tikz/names/change color to X", "label": "change color to X", "type": FormInputType.Str},
    {"id": "tikz/names/remove identity", "label": "remove identity", "type": FormInputType.Str},
    {"id": "tikz/names/Add Z identity", "label": "add Z identity", "type": FormInputType.Str},
    {"id": "tikz/names/copy 0/pi spider", "label": "copy 0/pi spider", "type": FormInputType.Str},
    {"id": "tikz/names/push Pauli", "label": "push Pauli", "type": FormInputType.Str},
    {"id": "tikz/names/decompose hadamard", "label": "decompose hadamard", "type": FormInputType.Str},
]


class SettingsDialog(QDialog):
    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings")

        self.settings = QSettings("zxlive", "zxlive")
        self.value_dict: Dict[str, QWidget] = {}
        self.prev_color_scheme = self.get_settings_value("color-scheme", str)
        self.prev_tab_bar_location = self.get_settings_value("tab-bar-location", QTabWidget.TabPosition)
        load_font_families()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        self.add_settings_tab(tab_widget, "General", "General ZXLive settings", general_settings)
        self.add_settings_tab(tab_widget, "Font", "Font settings", font_settings)
        self.add_settings_tab(tab_widget, "Tikz rule names", "Tikz rule name settings", tikz_rule_name_settings)
        self.add_settings_tab(tab_widget, "Tikz export", "These are the class names that will be used when exporting to tikz.", tikz_export_settings)
        self.add_settings_tab(tab_widget, "Tikz import",  "These are the class names that are understood when importing from tikz.", tikz_import_settings)
        self.add_settings_tab(tab_widget, "Tikz layout",  "Tikz layout settings", tikz_layout_settings)

        self.init_okay_cancel_buttons(layout)

    def get_settings_value(self, arg: str, _type: type[T], default: T | None = None) -> T:
        return get_settings_value(arg, _type, default, self.settings)

    def get_settings_from_data(self, data: SettingsData, _type: type[T]) -> T:
        name = data["id"]
        assert isinstance(default := defaults[name], _type)
        return self.get_settings_value(name, _type, default)


    def add_settings_tab(self, tab_widget: QTabWidget, tab_name: str, label: str, data: list[SettingsData]) -> None:
        panel_tikz_names, vlayout = QWidget(), QVBoxLayout()
        panel_tikz_names.setLayout(vlayout)
        tab_widget.addTab(panel_tikz_names, tab_name)
        vlayout.addWidget(QLabel(label))
        form_names, w = QFormLayout(), QWidget()
        w.setLayout(form_names)
        vlayout.addWidget(w)
        vlayout.addStretch()
        for d in data:
            self.add_setting_to_form(form_names, d)

    def init_okay_cancel_buttons(self, layout: QVBoxLayout) -> None:
        w, hlayout = QWidget(), QHBoxLayout()
        hlayout.addStretch()
        w.setLayout(hlayout)
        layout.addWidget(w)
        okay_button = QPushButton("Okay")
        okay_button.clicked.connect(self.okay)
        hlayout.addWidget(okay_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.cancel)
        hlayout.addWidget(cancel_button)

    def make_str_form_input(self, data: SettingsData) -> QLineEdit:
        widget = QLineEdit()
        widget.setText(self.get_settings_from_data(data, str))
        return widget

    def make_int_form_input(self, data: SettingsData) -> QSpinBox:
        widget = QSpinBox()
        widget.setValue(self.get_settings_from_data(data, int))
        return widget

    def make_float_form_input(self, data: SettingsData) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setValue(self.get_settings_from_data(data, float))
        return widget

    def make_folder_form_input(self, data: SettingsData) -> QLineEdit:
        widget_line = QLineEdit()
        widget_line.setText(self.get_settings_from_data(data, str))

        def browse() -> None:
            directory = QFileDialog.getExistingDirectory(
                self,"Pick folder", options=QFileDialog.Option.ShowDirsOnly
            )
            if directory:
                widget_line.setText(directory)

        action = widget_line.addAction(
            QIcon(get_data("icons/folder.svg")), QLineEdit.ActionPosition.TrailingPosition
        )
        action.setToolTip("Browse...")
        action.triggered.connect(browse)
        # It would be nice to highlight the icon on hover

        return widget_line

    def make_combo_form_input(self, data: SettingsData) -> QComboBox:
        assert "data" in data
        name, _data = data["id"], data["data"]
        value = self.settings.value(name, defaults[name])
        widget = QComboBox()
        for k, v in _data.items():
            widget.addItem(v, userData=k)
        widget.setCurrentText(_data[value])
        return widget

    def add_setting_to_form(self, form: QFormLayout, settings_data: SettingsData) -> None:
        setting_maker = {
            FormInputType.Str: self.make_str_form_input,
            FormInputType.Int: self.make_int_form_input,
            FormInputType.Float: self.make_float_form_input,
            FormInputType.Folder: self.make_folder_form_input,
            FormInputType.Combo: self.make_combo_form_input,
        }
        setting_widget_maker = setting_maker[settings_data["type"]]
        widget: QWidget = setting_widget_maker(settings_data)

        form.addRow(settings_data["label"], widget)
        self.value_dict[settings_data["id"]] = widget

    def okay(self) -> None:
        self.update_global_settings()
        self.apply_global_settings()
        self.accept()

    def update_global_settings(self) -> None:
        for name, widget in self.value_dict.items():
            if isinstance(widget, QLineEdit):
                self.settings.setValue(name, widget.text())
            elif isinstance(widget, QSpinBox):
                self.settings.setValue(name, widget.value())
            elif isinstance(widget, QDoubleSpinBox):
                self.settings.setValue(name, widget.value())
            elif isinstance(widget, QComboBox):
                self.settings.setValue(name, widget.currentData())
        display_setting.update()

    def apply_global_settings(self) -> None:
        refresh_pyzx_tikz_settings()
        theme = self.get_settings_value("color-scheme", str)
        if theme != self.prev_color_scheme:
            display_setting.set_color_scheme(theme)
            self.main_window.update_colors()
        pos = self.get_settings_value("tab-bar-location", QTabWidget.TabPosition)
        if pos != self.prev_tab_bar_location:
            self.main_window.tab_widget.setTabPosition(pos)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setFont(display_setting.font)
        self.main_window.update_font()

    def cancel(self) -> None:
        self.reject()


def open_settings_dialog(parent: MainWindow) -> None:
    dialog = SettingsDialog(parent)
    dialog.exec()
