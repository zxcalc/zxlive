from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from packaging import version as pkg_version
from PySide6.QtCore import QObject, QSettings, QUrl, Signal
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                               QNetworkRequest)

from .common import get_settings_value, set_settings_value

GITHUB_API_URL = "https://api.github.com/repos/zxcalc/zxlive/releases/latest"
CHECK_INTERVAL_DAYS = 1


class UpdateChecker(QObject):
    """Simple update checker using QNetworkAccessManager."""

    update_available = Signal(str, str)  # version, url
    check_complete = Signal()

    def __init__(
            self, current_version: str,
            settings: Optional[QSettings] = None) -> None:
        super().__init__()
        self.current_version = current_version
        self.settings = settings or QSettings("zxlive", "zxlive")
        self.network = QNetworkAccessManager(self)

    def should_check_for_updates(self) -> bool:
        """Check if enough time has passed since the last update check."""
        last_check_str = get_settings_value(
            "last-update-check", str, "", self.settings)
        if not last_check_str:
            return True
        try:
            last_check = datetime.fromisoformat(last_check_str)
            return (datetime.now() - last_check >
                    timedelta(days=CHECK_INTERVAL_DAYS))
        except Exception:
            return True

    def check_for_updates_async(self) -> None:
        """Check for updates asynchronously using network manager."""
        request = QNetworkRequest()
        request.setUrl(QUrl(GITHUB_API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github.v3+json")

        reply = self.network.get(request)
        reply.finished.connect(lambda: self._handle_reply(reply))

    def _handle_reply(self, reply: QNetworkReply) -> None:
        """Handle the network reply."""
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                response_text = reply.readAll().toStdString()
                data = json.loads(response_text)
                latest_version = data.get('tag_name', '').lstrip('v')
                release_url = data.get('html_url', '')
                if latest_version and self._is_newer_version(latest_version):
                    self.update_available.emit(latest_version, release_url)
            set_settings_value(
                "last-update-check", datetime.now().isoformat(),
                str, self.settings)
        except Exception:
            pass  # Silently ignore errors
        finally:
            reply.deleteLater()
            self.check_complete.emit()

    def _is_newer_version(self, latest: str) -> bool:
        """Compare versions to determine if an update is available."""
        try:
            return (pkg_version.parse(latest) >
                    pkg_version.parse(self.current_version))
        except Exception:
            return False
