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

from typing import TYPE_CHECKING, Dict, Any, Optional

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QDialog, QFileDialog,
                               QFormLayout, QLineEdit,
                               QPushButton, QWidget,
                               QVBoxLayout, QSpinBox, QDoubleSpinBox,
                               QLabel, QHBoxLayout, QTabWidget,
                                QComboBox)

import pyzx

from .common import set_pyzx_tikz_settings, colors, setting, color_schemes, input_circuit_formats, defaults

if TYPE_CHECKING:
    from .mainwindow import MainWindow


class SettingsDialog(QDialog):
    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings")
        self.settings = QSettings("zxlive", "zxlive")
        self.value_dict: Dict[str,QWidget] = {}

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        ##### General settings #####
        panel_base_settings = QWidget()
        vlayout = QVBoxLayout()
        panel_base_settings.setLayout(vlayout)
        tab_widget.addTab(panel_base_settings, "General")
        vlayout.addWidget(QLabel("General ZXLive settings"))
        form_general = QFormLayout()
        w = QWidget()
        w.setLayout(form_general)
        vlayout.addWidget(w)
        self.add_setting(form_general, "path/custom-rules", "Custom rules path", 'folder')
        self.add_setting(form_general, "color-scheme", "Color scheme", 'combo',data=color_schemes)
        self.add_setting(form_general, "snap-granularity", "Snap-to-grid granularity", 'combo',
                         data = {'2': "2", '4': "4", '8': "8", '16': "16"})
        self.add_setting(form_general, "input-circuit-format", "Input Circuit as", 'combo', data=input_circuit_formats)
        self.prev_color_scheme = self.settings.value("color-scheme")
        vlayout.addStretch()

        ##### Tikz Export settings #####
        panel_tikz_export = QWidget()
        vlayout = QVBoxLayout()
        panel_tikz_export.setLayout(vlayout)
        tab_widget.addTab(panel_tikz_export, "Tikz export")

        vlayout.addWidget(QLabel("Tikz export settings"))
        vlayout.addWidget(QLabel("These are the class names that will be used when exporting to tikz."))

        form_export = QFormLayout()
        w = QWidget()
        w.setLayout(form_export)
        vlayout.addWidget(w)
        vlayout.addStretch()

        self.add_setting(form_export, "tikz/Z-spider-export", "Z-spider", 'str')
        self.add_setting(form_export, "tikz/Z-phase-export", "Z-spider with phase", 'str')
        self.add_setting(form_export, "tikz/X-spider-export", "X-spider", 'str')
        self.add_setting(form_export, "tikz/X-phase-export", "X-spider with phase", 'str')
        self.add_setting(form_export, "tikz/Hadamard-export", "Hadamard", 'str')
        self.add_setting(form_export, "tikz/boundary-export", "Boundary", 'str')
        self.add_setting(form_export, "tikz/edge-export", "Regular Edge", 'str')
        self.add_setting(form_export, "tikz/edge-H-export", "Hadamard edge", 'str')

        self.add_setting(form_export, "tikz/w-input-export", "W input", 'str')
        self.add_setting(form_export, "tikz/w-output-export", "W output", 'str')
        self.add_setting(form_export, "tikz/z-box-export", "Z box", 'str')
        self.add_setting(form_export, "tikz/edge-W-export", "W io edge", 'str')


        ##### Tikz Import settings #####
        panel_tikz_import = QWidget()
        vlayout = QVBoxLayout()
        panel_tikz_import.setLayout(vlayout)
        tab_widget.addTab(panel_tikz_import, "Tikz import")

        vlayout.addWidget(QLabel("Tikz import settings"))
        vlayout.addWidget(QLabel("These are the class names that are understood when importing from tikz."))

        form_import = QFormLayout()
        w = QWidget()
        w.setLayout(form_import)
        vlayout.addWidget(w)
        vlayout.addStretch()

        self.add_setting(form_import, "tikz/Z-spider-import", "Z-spider", 'str')
        self.add_setting(form_import, "tikz/X-spider-import", "X-spider", 'str')
        self.add_setting(form_import, "tikz/Hadamard-import", "Hadamard", 'str')
        self.add_setting(form_import, "tikz/boundary-import", "Boundary", 'str')
        self.add_setting(form_import, "tikz/edge-import", "Regular Edge", 'str')
        self.add_setting(form_import, "tikz/edge-H-import", "Hadamard edge", 'str')

        self.add_setting(form_import, "tikz/w-input-import", "W input", 'str')
        self.add_setting(form_import, "tikz/w-output-import", "W output", 'str')
        self.add_setting(form_import, "tikz/z-box-import", "Z box", 'str')
        self.add_setting(form_import, "tikz/edge-W-import", "W io edge", 'str')

        ##### Tikz Layout settings #####
        panel_tikz_layout = QWidget()
        vlayout = QVBoxLayout()
        panel_tikz_layout.setLayout(vlayout)
        tab_widget.addTab(panel_tikz_layout, "Tikz layout")

        vlayout.addWidget(QLabel("Tikz layout settings"))

        form_layout = QFormLayout()
        w = QWidget()
        w.setLayout(form_layout)
        vlayout.addWidget(w)
        vlayout.addStretch()

        self.add_setting(form_layout, "tikz/layout/hspace", "Horizontal spacing", "float")
        self.add_setting(form_layout, "tikz/layout/vspace", "Vertical spacing", "float")
        self.add_setting(form_layout, "tikz/layout/max-width", "Maximum width", 'float')


        ##### Tikz rule name settings #####
        panel_tikz_names = QWidget()
        vlayout = QVBoxLayout()
        panel_tikz_names.setLayout(vlayout)
        tab_widget.addTab(panel_tikz_names, "Tikz rule names")

        vlayout.addWidget(QLabel("Tikz rule name settings"))
        vlayout.addWidget(QLabel("Mapping of pyzx rule names to tikz display strings"))

        form_names = QFormLayout()
        w = QWidget()
        w.setLayout(form_names)
        vlayout.addWidget(w)
        vlayout.addStretch()

        self.add_setting(form_names, "tikz/names/fuse spiders", "fuse spiders", "str")
        self.add_setting(form_names, "tikz/names/bialgebra", "bialgebra", "str")
        self.add_setting(form_names, "tikz/names/change color to Z", "change color to Z", "str")
        self.add_setting(form_names, "tikz/names/change color to X", "change color to X", "str")
        self.add_setting(form_names, "tikz/names/remove identity", "remove identity", "str")
        self.add_setting(form_names, "tikz/names/Add Z identity", "add Z identity", "str")
        self.add_setting(form_names, "tikz/names/copy 0/pi spider", "copy 0/pi spider", "str")
        self.add_setting(form_names, "tikz/names/push Pauli", "push Pauli", "str")
        self.add_setting(form_names, "tikz/names/decompose hadamard", "decompose hadamard", "str")



        ##### Okay/Cancel Buttons #####
        w= QWidget()
        hlayout = QHBoxLayout()
        hlayout.addStretch()
        w.setLayout(hlayout)
        layout.addWidget(w)
        okay_button = QPushButton("Okay")
        okay_button.clicked.connect(self.okay)
        hlayout.addWidget(okay_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.cancel)
        hlayout.addWidget(cancel_button)


    def add_setting(self,form:QFormLayout, name:str, label:str, ty:str, data: Optional[dict[str, str]] = None) -> None:
        val = self.settings.value(name)
        widget: QWidget
        if val is None: val = defaults[name]
        if ty == 'str':
            widget = QLineEdit()
            val = str(val)
            widget.setText(val)
        elif ty == 'int':
            widget = QSpinBox()
            widget.setValue(int(val))  # type: ignore
        elif ty == 'float':
            widget = QDoubleSpinBox()
            widget.setValue(float(val))  # type: ignore
        elif ty == 'folder':
            widget = QWidget()
            hlayout = QHBoxLayout()
            widget.setLayout(hlayout)
            widget_line = QLineEdit()
            val = str(val)
            widget_line.setText(val)
            def browse() -> None:
                directory = QFileDialog.getExistingDirectory(self,"Pick folder",options=QFileDialog.Option.ShowDirsOnly)
                if directory:
                    widget_line.setText(directory)
                    setattr(widget, "text_value", directory)
            hlayout.addWidget(widget_line)
            button = QPushButton("Browse")
            button.clicked.connect(browse)
            hlayout.addWidget(button)
        elif ty == 'combo':
            widget = QComboBox()
            assert data is not None
            widget.addItems(list(data.values()))
            widget.setCurrentText(data[val])
            setattr(widget, "data", data)


        form.addRow(label, widget)
        self.value_dict[name] = widget

    def okay(self) -> None:
        for name,widget in self.value_dict.items():
            if isinstance(widget, QLineEdit):
                self.settings.setValue(name, widget.text())
            elif isinstance(widget, QSpinBox):
                self.settings.setValue(name, widget.value())
            elif isinstance(widget, QDoubleSpinBox):
                self.settings.setValue(name, widget.value())
            elif isinstance(widget, QComboBox):
                s = widget.currentText()
                assert hasattr(widget, "data")
                val = next(k for k in widget.data if widget.data[k] == s)
                self.settings.setValue(name, val)
            elif isinstance(widget, QWidget) and hasattr(widget, "text_value"):
                self.settings.setValue(name, widget.text_value)
        set_pyzx_tikz_settings()
        setting.update()
        if self.settings.value("color-scheme") != self.prev_color_scheme:
            theme = self.settings.value("color-scheme")
            assert isinstance(theme, str)
            colors.set_color_scheme(theme)
            self.main_window.update_colors()
        self.accept()

    def cancel(self) -> None:
        self.reject()




def open_settings_dialog(parent: MainWindow) -> None:
    dialog = SettingsDialog(parent)
    dialog.exec()
