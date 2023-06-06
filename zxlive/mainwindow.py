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

from enum import IntEnum

from .edit_panel import GraphEditPanel
from .proof_panel import ProofPanel
from .construct import *


class Tab(IntEnum):
    EditTab = 0
    ProofTab = 1


class MainWindow(QMainWindow):
    """A simple window containing a single `GraphView`
    This is just an example, and should be replaced with
    something more sophisticated.
    """

    edit_panel: GraphEditPanel
    proof_panel: ProofPanel

    current_tab: Tab = Tab.EditTab

    def __init__(self) -> None:
        super().__init__()
        conf = QSettings("zxlive", "zxlive")

        self.setWindowTitle("zxlive")

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        w.layout().setContentsMargins(0, 0, 0, 0)
        w.layout().setSpacing(0)
        self.resize(1200, 800)

        # restore the window from the last time it was opened
        geom = conf.value("main_window_geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        self.show()

        tab_widget = QTabWidget()
        w.layout().addWidget(tab_widget)
        tab_widget.currentChanged.connect(self._tab_changed)

        graph = construct_circuit()

        self.edit_panel = GraphEditPanel(graph)
        tab_widget.addTab(self.edit_panel, "Edit")

        self.proof_panel = ProofPanel(graph)
        tab_widget.addTab(self.proof_panel, "Rewrite")

    def _tab_changed(self, new_tab: Tab):
        # This method is also invoked on application launch, so check
        # if the tab has actually changed
        if self.current_tab != new_tab:
            old_panel = self.edit_panel if self.current_tab == Tab.EditTab else self.proof_panel
            new_panel = self.edit_panel if new_tab == Tab.EditTab else self.proof_panel
            new_panel.graph_view.set_graph(old_panel.graph)
            new_panel.graph_scene.select_vertices(list(old_panel.graph_scene.selected_vertices))
            # TODO: For now we always invalidate the undo stack when switching
            #  between tabs. In the future this should only happen if we've
            #  actually made changes to the graph before switching.
            new_panel.undo_stack.clear()
            self.current_tab = new_tab

    def closeEvent(self, e: QCloseEvent) -> None:
        # save the shape/size of this window on close
        conf = QSettings("zxlive", "zxlive")
        conf.setValue("main_window_geometry", self.saveGeometry())
        e.accept()
