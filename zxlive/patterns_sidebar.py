from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem, QMessageBox, QWidget
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
import os
from typing import Callable

class PatternsSidebar(QDockWidget):
    def __init__(self, parent: QWidget, patterns_folder: str, on_pattern_selected: Callable[[str], None]) -> None:
        super().__init__("Patterns", parent)
        self.patterns_folder: str = patterns_folder
        self.on_pattern_selected: Callable[[str], None] = on_pattern_selected
        self.patterns_list: QListWidget = QListWidget()
        self.setWidget(self.patterns_list)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.patterns_list.itemDoubleClicked.connect(self.pattern_selected)
        self.refresh_patterns()

    def refresh_patterns(self) -> None:
        self.patterns_list.clear()
        if not os.path.isdir(self.patterns_folder):
            return
        for fname in os.listdir(self.patterns_folder):
            if fname.endswith(".zxg"):
                item = QListWidgetItem(fname)
                # Optionally, set an icon or preview here
                self.patterns_list.addItem(item)

    def pattern_selected(self, item: QListWidgetItem) -> None:
        pattern_path: str = os.path.join(self.patterns_folder, item.text())
        self.on_pattern_selected(pattern_path)
