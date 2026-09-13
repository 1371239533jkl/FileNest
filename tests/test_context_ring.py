"""上下文圆环指示器自检 —— set_usage 钳制/绘制不崩溃/主题联动"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.ai_chat_page import _ContextRing  # noqa: E402


def test_ring_usage_clamped_and_paints():
    app = QApplication.instance() or QApplication([])
    ring = _ContextRing()
    ring.set_usage(150, "#f38ba8", "#45475a")  # 超界钳制
    assert ring._pct == 100
    ring.set_usage(-5, "#a6e3a1", "#45475a")
    assert ring._pct == 0
    ring.set_usage(37, "#f9e2af", "#45475a")
    assert ring._pct == 37 and ring._color.name() == "#f9e2af"
    ring.grab()  # 触发 paintEvent，不崩溃即通过


def test_ring_zero_pct_paints_track_only():
    app = QApplication.instance() or QApplication([])
    ring = _ContextRing()
    ring.set_usage(0, "#a6e3a1", "#45475a")
    ring.grab()
