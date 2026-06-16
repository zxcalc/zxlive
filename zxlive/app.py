# zxlive - An interactive tool for the ZX-calculus
# Copyright (C) 2023 - Aleks Kissinger
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

from PySide6.QtCore import QCommandLineParser, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow
from .common import get_data, GraphT, get_settings_value
from .settings import display_setting
from .update_checker import UpdateChecker
from .dialogs import show_update_available_dialog

# Windows taskbar icon fix.
# See https://stackoverflow.com/a/1552105
if os.name == "nt":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore
        "zxcalc.zxlive.zxlive.1.0.0")


class ZXLive(QApplication):
    """The main ZXLive application."""

    main_window: Optional[MainWindow] = None

    def __init__(self, *, standalone: bool = True) -> None:
        # In embedded mode pass only the program name so we don't conflict with
        # the host application's CLI argument parser.
        super().__init__(sys.argv if standalone else sys.argv[:1])
        self._apply_base_settings()
        main_window = self._ensure_main_window()

        self.lastWindowClosed.connect(self.quit)

        if not standalone:
            return

        # Update checker — runs asynchronously in the background.
        self.update_checker = UpdateChecker(
            self.applicationVersion(), main_window.settings)
        self.update_checker.update_available.connect(self.on_update_available)
        if self.update_checker.should_check_for_updates():
            self.update_checker.check_for_updates_async()

        # Parse CLI arguments.
        parser = QCommandLineParser()
        parser.setApplicationDescription(
            "ZXLive - An interactive tool for the ZX-calculus")
        parser.addHelpOption()
        parser.addVersionOption()
        parser.addPositionalArgument("files", "File(s) to open.", "[files...]")
        parser.process(self)

        # Try to restore the previous session first.
        session_restored = main_window._restore_session_state()

        if parser.positionalArguments():
            # Files supplied on the command line take priority.
            for f in parser.positionalArguments():
                main_window.open_file_from_path(f)
        elif not session_restored:
            # Nothing to restore and no CLI files → open the demo graph.
            main_window.open_demo_graph()

        # Auto-start the onboarding tutorial on first launch.
        # Deferred by one event-loop tick so the main window is fully laid out
        # (splitters sized, panels shown) before the overlay measures itself.
        from .tutorial import maybe_start_first_run
        QTimer.singleShot(0, lambda: maybe_start_first_run(
            cast(MainWindow, self.main_window)))

    def _apply_base_settings(self) -> None:
        """Set application font, name and version metadata."""
        self.setFont(display_setting.font)
        self.setApplicationName("ZXLive")
        self.setDesktopFileName("ZXLive")
        self.setApplicationVersion(get_version())

    def _ensure_main_window(self) -> MainWindow:
        """Create and show the main window if it does not already exist."""
        if not self.main_window:
            self.main_window = MainWindow()
            self.main_window.setWindowIcon(QIcon(get_data("icons/logo.png")))
            self.setWindowIcon(self.main_window.windowIcon())
        return self.main_window

    def on_update_available(self, version: str, url: str) -> None:
        """Handle an update-available signal from the update checker."""
        if self.main_window:
            show_update_available_dialog(
                self.applicationVersion(), version, url, self.main_window)

    def edit_graph(self, g: GraphT, name: str) -> None:
        """Open a ZXLive window to edit a graph interactively (embedded use)."""
        win = self._ensure_main_window()
        win.show()
        win.open_graph_for_editing(g, name)

    def get_copy_of_graph(self, name: str) -> Optional[GraphT]:
        """Return a copy of the graph that has the given tab name."""
        assert self.main_window
        return self.main_window.get_copy_of_graph(name)


def get_embedded_app() -> ZXLive:
    """Return a ZXLive instance for use as an embedded graph editor.

    Works from Jupyter notebooks, standalone scripts, or any Python context.
    Reuses an existing QApplication if one is running (e.g. after ``%gui qt6``
    in Jupyter); otherwise creates a new one with minimal initialisation,
    skipping CLI parsing, session restore and update checks.
    """
    app = QApplication.instance()
    if app is not None:
        if type(app) is not QApplication:
            raise TypeError(
                f"Cannot embed ZXLive into an existing {type(app).__name__} "
                "application; only a plain QApplication is supported.")
        app.__class__ = ZXLive
        zxl = cast(ZXLive, app)
        zxl._apply_base_settings()
        return zxl
    return ZXLive(standalone=False)


def get_version() -> str:
    """Return the application version from package metadata or pyproject.toml."""
    try:
        from importlib.metadata import version
        return version("zxlive")
    except Exception:
        pass

    try:
        import tomllib
        current_dir  = os.path.dirname(__file__)
        project_root = os.path.dirname(current_dir)
        with open(os.path.join(project_root, "pyproject.toml"), "rb") as f:
            data = tomllib.load(f)
            return str(data["project"]["version"])
    except (FileNotFoundError, IOError, ImportError, KeyError):
        return "1.0.0"


def main() -> None:
    """Main entry point for ZXLive as a standalone application."""
    # Configure the Windows platform dark-mode hint *before* creating
    # QApplication so the native window frame matches the chosen theme.
    dark_mode_setting = get_settings_value("dark-mode", str, "system")
    if os.name == "nt":
        if dark_mode_setting == "dark":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=2"
        elif dark_mode_setting == "light":
            os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=1"
        # "system" → let Qt auto-detect; don't set the variable.

    zxl = ZXLive()

    if sys.platform == "darwin":
        if dark_mode_setting == "dark":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        elif dark_mode_setting == "light":
            zxl.styleHints().setColorScheme(Qt.ColorScheme.Light)
        # "system" → Qt auto-detects.

    zxl.exec()
