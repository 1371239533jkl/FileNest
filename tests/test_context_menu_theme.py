"""右键菜单主题化自检 —— QMenu 样式随明暗主题切换"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication, QMenu  # noqa: E402

from ui.ai_chat_page import _theme_menu_qss  # noqa: E402


def test_menu_qss_varies_by_theme():
    dark, light = _theme_menu_qss(True), _theme_menu_qss(False)
    assert "#1e1e2e" in dark and "#ffffff" not in dark
    assert "#ffffff" in light and "#1e1e2e" not in light


def test_menu_applies_qss_without_crash():
    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    menu.setStyleSheet(_theme_menu_qss(False))
    menu.addAction("测试项")
    assert menu.actions(), "菜单应包含动作"
    menu.setStyleSheet(_theme_menu_qss(True))
