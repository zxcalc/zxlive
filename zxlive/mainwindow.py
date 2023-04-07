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
from PySide2.QtCore import QByteArray, Qt, QPointF, QRectF, QSettings
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from . import app
from .graphview import GraphView

import pyzx as zx

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        conf = QSettings('zxlive', 'zxlive')

        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        w.layout().setContentsMargins(0,0,0,0)
        w.layout().setSpacing(0)
        self.resize(1200, 800)
        
        geom = conf.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        self.graph_view = GraphView()
        w.layout().addWidget(self.graph_view)

        g = zx.generate.cliffords(8, 20)
        self.graph_view.set_graph(g)



    def closeEvent(self, e: QCloseEvent) -> None:
        conf = QSettings('zxlive', 'zxlive')
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()
