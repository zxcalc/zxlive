"""Test tab styling improvements.

This module tests the custom tab styling features added to ZXLive:
- CustomTabBar class implementation
- Close button visibility behavior (hidden by default, shown on hover)
- Mouse tracking functionality for hover detection
"""

import pytest
from PySide6.QtWidgets import QTabBar
from pytestqt.qtbot import QtBot

from zxlive.mainwindow import MainWindow, CustomTabBar


def test_custom_tab_bar_type(qtbot: QtBot) -> None:
    """Test that MainWindow uses CustomTabBar."""
    mw = MainWindow()
    mw.open_demo_graph()
    qtbot.addWidget(mw)
    
    # Verify custom tab bar is being used
    tab_bar = mw.tab_widget.tabBar()
    assert isinstance(tab_bar, CustomTabBar)
    assert hasattr(tab_bar, 'hovered_tab')


def test_close_buttons_hidden_by_default(qtbot: QtBot) -> None:
    """Test that close buttons are hidden by default."""
    mw = MainWindow()
    mw.open_demo_graph()
    mw.new_graph()
    qtbot.addWidget(mw)
    
    tab_bar = mw.tab_widget.tabBar()
    assert isinstance(tab_bar, CustomTabBar)
    
    # All close buttons should be hidden initially
    for i in range(tab_bar.count()):
        button = tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
        if button:
            assert not button.isVisible(), f"Tab {i} close button should be hidden by default"


def test_tab_bar_mouse_tracking(qtbot: QtBot) -> None:
    """Test that tab bar has mouse tracking enabled."""
    mw = MainWindow()
    mw.open_demo_graph()
    qtbot.addWidget(mw)
    
    tab_bar = mw.tab_widget.tabBar()
    assert isinstance(tab_bar, CustomTabBar)
    assert tab_bar.hasMouseTracking(), "Tab bar should have mouse tracking enabled"
