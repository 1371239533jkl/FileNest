"""AI 气泡流式渲染自检 —— 合帧刷新/打字光标/未闭合代码块渐进渲染/最终态清理"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.ai_chat_page import _ChatBubble  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _plain(bubble):
    return bubble._text_browser.toPlainText()


def test_append_coalesces_until_timer(app, qtbot=None):
    b = _ChatBubble("ai")
    b.append_text("第一段")
    b.append_text("第二段")
    # 定时器未触发前不渲染（合帧）
    assert "第一段" not in _plain(b)
    b._flush_stream()  # 模拟 60ms 定时器到期
    assert "第一段第二段" in _plain(b)


def test_caret_during_streaming_only(app):
    b = _ChatBubble("ai")
    b.set_text("部分回答", streaming=True)
    assert "▌" in _plain(b)
    b.append_text("后续内容")
    b._flush_stream()
    assert "▌" in _plain(b)
    # 最终态（done 后 set_text 无 streaming）光标消失
    b.set_text("完整回答")
    assert "▌" not in _plain(b)


def test_open_code_block_renders_progressively(app):
    b = _ChatBubble("ai")
    b.set_text("看代码：\n```python\nx = 1 + 2", streaming=True)
    # 未闭合的代码块也应立即渲染出来，而不是冻结
    assert "x = 1 + 2" in _plain(b)
    b.append_text("\ny = x * 2\n```")
    b._flush_stream()
    assert "y = x * 2" in _plain(b)


def test_timer_stopped_after_final_set(app):
    b = _ChatBubble("ai")
    b.append_text("x")
    assert b._stream_timer.isActive()
    b.set_text("最终")
    assert not b._stream_timer.isActive()
