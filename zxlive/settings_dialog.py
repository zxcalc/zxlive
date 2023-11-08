#     zxlive - An interactive tool for the ZX calculus
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

from typing import Optional,TYPE_CHECKING, Dict, Any

from PySide6.QtCore import QFile, QIODevice, QTextStream, QSettings
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QLineEdit, QMessageBox,
                               QPushButton, QTextEdit, QWidget,
                               QVBoxLayout, QSpinBox, QDoubleSpinBox,
                               QLabel, QHBoxLayout)

import pyzx

from .common import set_pyzx_tikz_settings

if TYPE_CHECKING:
    from .mainwindow import MainWindow

defaults: Dict[str,Any] = {
    "tikz/Z-spider-export": "Z dot",
    "tikz/Z-phase-export": "Z phase dot",
    "tikz/X-spider-export": "X dot",
    "tikz/X-phase-export": "X phase dot",
    "tikz/Hadamard-export": "hadamard",
    "tikz/boundary-export": "none",
    "tikz/w-input-export": "W input",
    "tikz/w-output-export": "W triangle",
    "tikz/z-box-export": "Z box",

    "tikz/Z-spider-import": ", ".join(pyzx.tikz.synonyms_z),
    "tikz/X-spider-import": ", ".join(pyzx.tikz.synonyms_x),
    "tikz/Hadamard-import": ", ".join(pyzx.tikz.synonyms_hadamard),
    "tikz/boundary-import": ", ".join(pyzx.tikz.synonyms_boundary),
    "tikz/w-input-import": ", ".join(pyzx.tikz.synonyms_w_input),
    "tikz/w-output-import": ", ".join(pyzx.tikz.synonyms_w_output),
    "tikz/z-box-import": ", ".join(pyzx.tikz.synonyms_z_box),

    "tikz/edge-export": "",
    "tikz/edge-H-export": "hadamard edge",
    "tikz/edge-W-export": "W io edge",
    "tikz/edge-import": ", ".join(pyzx.tikz.synonyms_edge),
    "tikz/edge-H-import": ", ".join(pyzx.tikz.synonyms_hedge),
    "tikz/edge-W-import": ", ".join(pyzx.tikz.synonyms_wedge),
}


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = QSettings("zxlive", "zxlive")
        self.value_dict: Dict[str,QWidget] = {}

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(QLabel("Tikz export settings"))
        layout.addWidget(QLabel("These are the class names that will be used when exporting to tikz."))

        form_export = QFormLayout()
        w = QWidget()
        w.setLayout(form_export)
        layout.addWidget(w)

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

        layout.addWidget(QLabel("Tikz import settings"))
        layout.addWidget(QLabel("These are the class names that are understood when importing from tikz."))

        form_import = QFormLayout()
        w = QWidget()
        w.setLayout(form_import)
        layout.addWidget(w)

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

        
    def add_setting(self,form:QFormLayout, name:str, label:str, ty:str) -> None:
        val = self.settings.value(name)
        if val is None: val = defaults[name]
        if ty == 'str':
            widget = QLineEdit()
            val = str(val)
            widget.setText(val)
        elif ty == 'int':
            widget = QSpinBox()
            val = int(val)
            widget.setValue(val)
        elif ty == 'float':
            widget = QDoubleSpinBox()
            val = float(val)
            widget.setValue(val)
        
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
        set_pyzx_tikz_settings()
        self.accept()

    def cancel(self) -> None:
        self.reject()




def open_settings_dialog() -> None:
    dialog = SettingsDialog()
    dialog.exec()
