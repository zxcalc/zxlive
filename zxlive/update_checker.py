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

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from packaging import version as pkg_version
from PySide6.QtCore import QObject, QSettings, QThread, Signal, Slot

from .common import get_settings_value, set_settings_value

GITHUB_API_URL = "https://api.github.com/repos/zxcalc/zxlive/releases/latest"
CHECK_INTERVAL_DAYS = 1  # Check for updates once per day


class UpdateCheckerWorker(QObject):
    """Worker thread for checking updates without blocking the UI."""

    update_available = Signal(str, str)  # version, url
    check_complete = Signal()
    error_occurred = Signal(str)

    def __init__(self, current_version: str) -> None:
        super().__init__()
        self.current_version = current_version

    @Slot()
    def check_for_updates(self) -> None:
        """Check GitHub API for the latest release."""
        try:
            req = urllib.request.Request(GITHUB_API_URL)
            req.add_header('Accept', 'application/vnd.github.v3+json')

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))

                latest_version = data.get('tag_name', '').lstrip('v')
                release_url = data.get('html_url', '')

                if latest_version and self._is_newer_version(latest_version):
                    self.update_available.emit(latest_version, release_url)
        except urllib.error.URLError as e:
            self.error_occurred.emit(f"Network error: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"Error checking for updates: {str(e)}")
        finally:
            self.check_complete.emit()

    def _is_newer_version(self, latest: str) -> bool:
        """Compare versions to determine if an update is available."""
        try:
            return pkg_version.parse(latest) > pkg_version.parse(self.current_version)
        except Exception:
            # If version parsing fails, assume no update
            return False


class UpdateChecker(QObject):
    """Manager for checking application updates."""

    update_available = Signal(str, str)  # version, url
    check_complete = Signal()

    def __init__(self, current_version: str, settings: Optional[object] = None) -> None:
        super().__init__()
        self.current_version = current_version
        self.settings = settings
        self._thread: Optional[QThread] = None
        self._worker: Optional[UpdateCheckerWorker] = None

    def should_check_for_updates(self) -> bool:
        """Determine if enough time has passed since the last check."""
        if self.settings is None:
            return True

        settings = self.settings if isinstance(self.settings, QSettings) else QSettings("zxlive", "zxlive")
        last_check_str = get_settings_value("last-update-check", str, "", settings)

        if not last_check_str:
            return True

        try:
            last_check = datetime.fromisoformat(last_check_str)
            time_since_check = datetime.now() - last_check
            return time_since_check > timedelta(days=CHECK_INTERVAL_DAYS)
        except Exception:
            return True

    def check_for_updates_async(self) -> None:
        """Check for updates in a background thread."""
        if self._thread is not None and self._thread.isRunning():
            # Already checking
            return

        self._thread = QThread()
        self._worker = UpdateCheckerWorker(self.current_version)
        self._worker.moveToThread(self._thread)

        # Connect signals before starting thread to avoid race conditions
        self._thread.started.connect(self._worker.check_for_updates)
        self._worker.update_available.connect(self._on_update_available)
        self._worker.check_complete.connect(self._on_check_complete)
        self._worker.error_occurred.connect(self._on_error)

        # Also connect thread finished signal to ensure cleanup
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker.deleteLater)

        # Start the thread
        self._thread.start()

    def _on_update_available(self, version: str, url: str) -> None:
        """Handle update available signal."""
        self.update_available.emit(version, url)

    def _on_check_complete(self) -> None:
        """Handle check complete signal."""
        # Update the last check time
        if self.settings is not None:

            settings = self.settings if isinstance(self.settings, QSettings) else QSettings("zxlive", "zxlive")
            set_settings_value("last-update-check", datetime.now().isoformat(), str, settings)

        # Clean up thread
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

        # Emit our own check_complete signal
        self.check_complete.emit()

    def _on_error(self, error_message: str) -> None:
        """Handle error signal."""
        # Silently ignore errors - we don't want to bother the user if the check fails
        pass
