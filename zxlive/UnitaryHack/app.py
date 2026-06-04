#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
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
from .tutorial import maybe_show_tutorial_on_first_run   # ← tutorial integration

# ---------------------------------------------------------------------------
# Windows taskbar icon hack
# See https://stackoverflow.com/a/1552105
# ---------------------------------------------------------------------------
if os.name == 'nt':
    import ctypes
    _appid = 'zxcalc.zxlive.zxlive.1.0.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_appid)  # type: ignore


class ZXLive(QApplication):
    """The main ZXLive application."""

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

        # ------------------------------------------------------------------
        # Update checker
        # ------------------------------------------------------------------
        self.update_checker = UpdateChecker(
            self.applicationVersion(), self.main_window.settings
        )
        self.update_checker.update_available.connect(self.on_update_available)
        if self.update_checker.should_check_for_updates():
            self.update_checker.check_for_updates_async()

        # ------------------------------------------------------------------
        # Command-line argument parsing
        # ------------------------------------------------------------------
        parser = QCommandLineParser()
        parser.setApplicationDescription(
            "ZXLive - An interactive tool for the ZX-calculus"
        )
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addPositionalArgument("files", "File(s) to open.", "[files...]")
        parser.process(self)

        # ------------------------------------------------------------------
        # Session / file restoration
        # ------------------------------------------------------------------
        session_restored = self.main_window._restore_session_state()

        if parser.positionalArguments():
            for f in parser.positionalArguments():
                self.main_window.open_file_from_path(f)
        elif not session_restored:
            self.main_window.open_demo_graph()

        # ------------------------------------------------------------------
        # Tutorial
        # ------------------------------------------------------------------
        # Auto-start the tutorial on first launch.  maybe_show_tutorial_on_first_run
        # is a no-op on all subsequent launches (guarded by a QSettings flag).
        maybe_show_tutorial_on_first_run(self.main_window)

    # ------------------------------------------------------------------
    # Update handling
    # ------------------------------------------------------------------

    def on_update_available(self, version: str, url: str) -> None:
        if self.main_window:
            show_update_available_dialog(
                self.applicationVersion(), version, url, self.main_window
            )

    # ------------------------------------------------------------------
    # Jupyter / notebook integration
    # ------------------------------------------------------------------

    def edit_graph(self, g: GraphT, name: str) -> None:
        """Open a ZXLive window from inside a Jupyter notebook to edit *g*."""
        if not self.main_window:
            self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.open_graph_from_notebook(g, name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        """Return a copy of the graph that has the given *name*."""
        assert self.main_window
        return self.main_window.get_copy_of_graph(name)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def get_embedded_app() -> ZXLive:
    """Entry point for ZXLive embedded inside a Jupyter notebook."""
    app = QApplication.instance() or ZXLive()
    app.__class__ = ZXLive
    return cast(ZXLive, app)


def get_version() -> str:
    """Return the application version string.

    Priority:
    1. Installed package metadata (``importlib.metadata``) — used in shipped builds.
    2. ``pyproject.toml`` in the project root           — used during development.
    3. Hard-coded fallback.
    """
    # 1. Installed package metadata
    try:
        from importlib.metadata import version
        return version('zxlive')
    except Exception:
        pass

    # 2. pyproject.toml (Python 3.11+ tomllib; fall back to tomli)
    for _tomllib in ('tomllib', 'tomli'):
        try:
            import importlib
            tomllib = importlib.import_module(_tomllib)
            current_dir  = os.path.dirname(__file__)
            project_root = os.path.dirname(current_dir)
            pyproject    = os.path.join(project_root, 'pyproject.toml')
            with open(pyproject, 'rb') as f:
                data = tomllib.load(f)
            return str(data['project']['version'])
        except Exception:
            continue

    # 3. Hard-coded fallback
    return '1.0.0'


def main() -> None:
    """Entry point for ZXLive as a standalone desktop application."""
    # Configure Windows theme before QApplication is created
    dark_mode = get_settings_value("dark-mode", str, "system")
    if os.name == 'nt':
        if dark_mode == "dark":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=2"
        elif dark_mode == "light":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=1"

    zxl = ZXLive()

    # macOS colour-scheme override
    if sys.platform == "darwin":
        if dark_mode == "dark":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        elif dark_mode == "light":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Light)

    zxl.exec_()
