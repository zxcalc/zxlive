import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from PySide6.QtCore import QSettings

from zxlive.update_checker import UpdateChecker


def test_version_comparison() -> None:
    """Test that version comparison works correctly."""
    checker = UpdateChecker("0.3.1")

    # Newer versions
    assert checker._is_newer_version("0.3.2")
    assert checker._is_newer_version("0.4.0")
    assert checker._is_newer_version("1.0.0")

    # Same version
    assert not checker._is_newer_version("0.3.1")

    # Older versions
    assert not checker._is_newer_version("0.3.0")
    assert not checker._is_newer_version("0.2.9")


def test_should_check_for_updates_no_previous_check() -> None:
    """Test that update check is needed when there's no previous check."""
    settings = QSettings("zxlive-test", "zxlive-test")
    settings.clear()  # Clear any existing settings

    checker = UpdateChecker("0.3.1", settings)
    assert checker.should_check_for_updates()

    settings.clear()


def test_should_check_for_updates_recent_check() -> None:
    """Test that update check is not needed when recently checked."""
    settings = QSettings("zxlive-test", "zxlive-test")
    settings.clear()

    # Set last check to now
    from zxlive.common import set_settings_value
    set_settings_value("last-update-check", datetime.now().isoformat(), str, settings)

    checker = UpdateChecker("0.3.1", settings)
    assert not checker.should_check_for_updates()

    settings.clear()


def test_should_check_for_updates_old_check() -> None:
    """Test that update check is needed when last check was long ago."""
    settings = QSettings("zxlive-test", "zxlive-test")
    settings.clear()

    # Set last check to 2 days ago
    from zxlive.common import set_settings_value
    old_time = datetime.now() - timedelta(days=2)
    set_settings_value("last-update-check", old_time.isoformat(), str, settings)

    checker = UpdateChecker("0.3.1", settings)
    assert checker.should_check_for_updates()

    settings.clear()


def test_update_checker_initialization() -> None:
    """Test that UpdateChecker initializes correctly."""
    checker = UpdateChecker("0.3.1")
    assert checker.current_version == "0.3.1"
    assert checker.settings is not None
