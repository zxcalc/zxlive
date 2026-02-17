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

import os
import sys
from typing import Optional, cast

from PySide6.QtCore import QCommandLineParser, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow
from .common import get_data, GraphT, get_settings_value
from .settings import display_setting
from .update_checker import UpdateChecker
from .dialogs import show_update_available_dialog

# The following hack is needed on windows in order to show the icon in the taskbar
# See https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7/1552105#1552105
if os.name == 'nt':
    import ctypes
    myappid = 'zxcalc.zxlive.zxlive.1.0.0'  # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)  # type: ignore


class ZXLive(QApplication):
    """The main ZXLive application

    ...
    """

    main_window: Optional[MainWindow] = None

    def __init__(self) -> None:
        super().__init__(sys.argv)
        self.setFont(display_setting.font)
        self.setApplicationName('ZXLive')
        self.setDesktopFileName('ZXLive')
        self.setApplicationVersion(get_version())
        self.main_window = MainWindow()
        self.main_window.setWindowIcon(QIcon(get_data('icons/logo.png')))
        self.setWindowIcon(self.main_window.windowIcon())

        self.lastWindowClosed.connect(self.quit)

        # Initialize update checker
        self.update_checker = UpdateChecker(self.applicationVersion(), self.main_window.settings)
        self.update_checker.update_available.connect(self.on_update_available)

        # Check for updates in background if needed
        if self.update_checker.should_check_for_updates():
            self.update_checker.check_for_updates_async()

        parser = QCommandLineParser()
        parser.setApplicationDescription("ZXLive - An interactive tool for the ZX-calculus")
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addPositionalArgument("files", "File(s) to open.", "[files...]")
        parser.process(self)
        
        # Try to restore session state first
        session_restored = self.main_window._restore_session_state()
        
        # Handle command-line file arguments
        if parser.positionalArguments():
            # Open command-line files as additional tabs
            for f in parser.positionalArguments():
                self.main_window.open_file_from_path(f)
        elif not session_restored:
            # No files provided and no session restored - open demo graph
            self.main_window.open_demo_graph()

    def on_update_available(self, version: str, url: str) -> None:
        """Handle update available notification."""
        if self.main_window:
            show_update_available_dialog(self.applicationVersion(), version, url, self.main_window)

    def edit_graph(self, g: GraphT, name: str) -> None:
        """Opens a ZXLive window from within a notebook to edit a graph."""
        if not self.main_window:
            self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.open_graph_from_notebook(g, name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        """Returns a copy of the graph which has the given name."""
        assert self.main_window
        return self.main_window.get_copy_of_graph(name)


def get_embedded_app() -> ZXLive:
    """Main entry point for ZXLive as an embedded app inside a jupyter notebook."""
    app = QApplication.instance() or ZXLive()
    app.__class__ = ZXLive
    return cast(ZXLive, app)


def get_version() -> str:
    """Get the application version from installed package metadata or pyproject.toml."""
    # First, try to get version from installed package metadata (for shipped apps)
    try:
        from importlib.metadata import version
        return version('zxlive')
    except Exception:
        pass

    # Fallback: try to read from pyproject.toml (for development)
    try:
        # Try using tomllib (Python 3.11+) for proper TOML parsing
        import tomllib
        current_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(current_dir)
        pyproject_path = os.path.join(project_root, 'pyproject.toml')
        with open(pyproject_path, 'rb') as f:
            data = tomllib.load(f)
            return str(data['project']['version'])
    except (FileNotFoundError, IOError, ImportError, KeyError):
        # Final fallback to hardcoded version
        return '0.3.1'  # TODO: Update this for new releases


def main() -> None:
    """Main entry point for ZXLive as a standalone app."""
    # Configure Windows theme based on settings before creating QApplication
    dark_mode_setting = get_settings_value("dark-mode", str, "system")
    if os.name == 'nt':  # 'nt' is Windows
        if dark_mode_setting == "dark":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=2"
        elif dark_mode_setting == "light":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=1"
        # For "system", don't set the environment variable to let Qt auto-detect

    zxl = ZXLive()
    if sys.platform == "darwin":  # 'darwin' is macOS
        if dark_mode_setting == "dark":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        elif dark_mode_setting == "light":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Light)
        # For "system", don't set the color scheme to let Qt auto-detect
    zxl.exec_()
