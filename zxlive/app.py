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

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCommandLineParser
import sys
from .mainwindow import MainWindow
from .common import GraphT
from typing import Optional

sys.path.insert(0, '../pyzx')  # So that it can find a local copy of pyzx


class ZXLive(QApplication):
    """The main ZXLive application

    ...
    """

    main_window: Optional[MainWindow] = None

    def __init__(self) -> None:
        super().__init__(sys.argv)
        self.setApplicationName('ZXLive')
        self.setDesktopFileName('ZXLive')
        self.setApplicationVersion('0.1')  # TODO: read this from pyproject.toml if possible
        self.main_window = MainWindow()

        self.lastWindowClosed.connect(self.quit)

        parser = QCommandLineParser()
        parser.setApplicationDescription("ZXLive - An interactive tool for the ZX-calculus")
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addPositionalArgument("files", "File(s) to open.", "[files...]")
        parser.process(self)
        for f in parser.positionalArguments():
            self.main_window.open_file_from_path(f)

    def edit_graph(self, g: GraphT, name: str) -> None:
        """Opens a ZXLive window from within a notebook to edit a graph."""
        if not self.main_window:
            self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.open_graph_from_notebook(g, name)

    def get_copy_of_graph(self, name: str) -> GraphT:
        """Returns a copy of the graph which has the given name."""
        return self.main_window.get_copy_of_graph(name)


def get_embedded_app() -> ZXLive:
    """Main entry point for ZXLive as an embedded app inside a jupyter notebook."""
    app = QApplication.instance() or ZXLive()
    app.__class__ = ZXLive
    return app


def main() -> None:
    """Main entry point for ZXLive as a standalone app."""
    zxl = ZXLive()
    zxl.exec_()
