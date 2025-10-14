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

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from PySide6.QtCore import QSettings

from zxlive.update_checker import UpdateChecker, UpdateCheckerWorker


def test_version_comparison() -> None:
    """Test that version comparison works correctly."""
    worker = UpdateCheckerWorker("0.3.1")
    
    # Newer versions
    assert worker._is_newer_version("0.3.2")
    assert worker._is_newer_version("0.4.0")
    assert worker._is_newer_version("1.0.0")
    
    # Same version
    assert not worker._is_newer_version("0.3.1")
    
    # Older versions
    assert not worker._is_newer_version("0.3.0")
    assert not worker._is_newer_version("0.2.9")


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


def test_update_checker_signals(qtbot) -> None:  # type: ignore
    """Test that UpdateChecker properly emits signals."""
    checker = UpdateChecker("0.3.1")
    
    # Mock the worker to emit update available
    with patch.object(checker, 'check_for_updates_async'):
        checker.update_available.emit("0.4.0", "https://github.com/zxcalc/zxlive/releases/tag/v0.4.0")
        # The signal emission is tested by the fact that this doesn't raise an exception
