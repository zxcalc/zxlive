"""Pytest fixtures and hooks shared across the test suite.

QSettings is redirected at conftest import time (so zxlive's import-time
writes are sandboxed) and again per-test by an autouse fixture (so tests
that build fresh QSettings don't leak state to each other). Module-level
QSettings instances created during import keep using the session-scoped
path for their whole lifetime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from PySide6.QtCore import QSettings


def _probe_default_path(fmt: QSettings.Format) -> str:
    """Probe Qt's default UserScope base path for ``fmt`` via a throwaway QSettings.

    Accepts the ``<base>/<org>/<app>.ext`` and ``<base>/<app>.ext`` layouts;
    raises on anything else rather than silently restoring a wrong path.
    """
    probe_org = "zxlive-conftest-probe-org"
    probe_app = "zxlive-conftest-probe-app"
    probe = QSettings(fmt, QSettings.Scope.UserScope, probe_org, probe_app)
    probe_path = Path(probe.fileName())

    if probe_path.stem == probe_app:
        if probe_path.parent.name == probe_org:
            return str(probe_path.parent.parent)
        return str(probe_path.parent)

    raise RuntimeError(
        f"Unable to derive QSettings base path for {fmt!r} from "
        f"{probe.fileName()!r}"
    )


# PySide6's ``QSettings(org, app)`` ignores ``setDefaultFormat`` and uses
# ``NativeFormat``, so redirect both formats to cover either choice.
_ORIGINAL_FORMAT = QSettings.defaultFormat()
_ORIGINAL_NATIVE_PATH = _probe_default_path(QSettings.Format.NativeFormat)
_ORIGINAL_INI_PATH = _probe_default_path(QSettings.Format.IniFormat)

_QSETTINGS_TMPDIR = tempfile.TemporaryDirectory(prefix="zxlive-test-qsettings-")


def _set_qsettings_paths(path: str) -> None:
    """Point both QSettings formats at ``path`` for UserScope."""
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                      path)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      path)


QSettings.setDefaultFormat(QSettings.Format.IniFormat)
_set_qsettings_paths(_QSETTINGS_TMPDIR.name)


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path: Path) -> Iterator[None]:
    """Redirect new QSettings instances to a per-test subdirectory."""
    _set_qsettings_paths(str(tmp_path))
    try:
        yield
    finally:
        _set_qsettings_paths(_QSETTINGS_TMPDIR.name)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restore the original QSettings state and remove the temp directory."""
    QSettings.setDefaultFormat(_ORIGINAL_FORMAT)
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                      _ORIGINAL_NATIVE_PATH)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      _ORIGINAL_INI_PATH)
    _QSETTINGS_TMPDIR.cleanup()
