"""AI 气泡 Markdown 渲染自检 —— 覆盖标题/列表/表格/引用/分隔线/代码块占位还原"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.ai_chat_page import _ChatBubble  # noqa: E402

MD = """## iPhone 18 Pro 价格

**首发价格**如下：

| 版本 | 价格 | 备注 |
|------|------|------|
| 256GB | ¥9,999 | 预购 |
| 512GB | ¥11,999 | - |

- 要点一
- 要点二 `code`

1. 第一
2. 第二

> 引用内容
---
### 小节
```python
print('hi')  # | not a table | ##
```
"""


@pytest.fixture(scope="module")
def bubble_html():
    app = QApplication.instance() or QApplication([])
    bubble = _ChatBubble("ai")
    return bubble._render_markdown(MD)


def test_table(bubble_html):
    assert "<table" in bubble_html and "<th" in bubble_html
    assert "9,999" in bubble_html


def test_lists(bubble_html):
    assert "<ul" in bubble_html and "<li>要点一</li>" in bubble_html
    assert "<ol" in bubble_html and "<li>第一</li>" in bubble_html


def test_heading(bubble_html):
    assert "font-weight:700" in bubble_html
    assert "iPhone 18 Pro 价格" in bubble_html


def test_blockquote_and_hr(bubble_html):
    assert "border-left" in bubble_html
    assert "border-top" in bubble_html


def test_inline_code_and_code_block(bubble_html):
    assert "<code style=" in bubble_html
    # 代码块内容不被块级解析污染（| 与 ## 原样保留在 pre 中）
    assert "not a table" in bubble_html
    assert "background:#272822" in bubble_html


def test_theme_switch_rerenders_html():
    """切主题后气泡 HTML 必须重渲染（代码块等颜色烘焙在 HTML 里）"""
    app = QApplication.instance() or QApplication([])
    b = _ChatBubble("ai")
    b._apply_theme(True)
    b.set_text("代码：\n```python\nx = 1\n```")
    assert "#272822" in b._text_browser.toHtml()  # 暗色代码块底
    b._apply_theme(False)
    h = b._text_browser.toHtml()
    assert "#272822" not in h, "切浅色后仍残留暗色代码块"
    assert "#eff1f5" in h, "切浅色后未使用浅色代码块底"


def test_no_placeholder_leak(bubble_html):
    assert "\x00" not in bubble_html


def test_br_in_table_cell_restored():
    app = QApplication.instance() or QApplication([])
    b = _ChatBubble("ai")
    h = b._render_markdown("| 项 | 说明 |\n|---|---|\n| 极低：<br>• 一套 | 高 |")
    # 模型写的 <br> 应还原为真换行，而不是显示字面量
    assert "&lt;br" not in h
    assert "<br>" in h


def test_blank_lines_around_blocks_collapsed():
    app = QApplication.instance() or QApplication([])
    b = _ChatBubble("ai")
    h = b._render_markdown("第一段\n\n\n\n- 项目一\n- 项目二\n\n\n尾段\n")
    # 块级元素前后不应残留空行 <br>
    assert "<br><ul" not in h
    assert "</ul><br>" not in h
    # 连续空行折叠：不允许三个及以上连续 <br>
    assert "<br><br><br>" not in h
    # 末尾空行不产生尾部 <br>
    assert not h.endswith("<br></div>")
