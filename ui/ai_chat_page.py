"""
AI 全能助手页面 —— 多轮对话 + 工具调用 + 流式交互。

支持：
- 多轮对话与上下文记忆（AiConversation）
- 工具自动调用循环（文件搜索/联网搜索/代码执行/文件读取）
- 代码块语法高亮（Pygments）
- 工具执行结果卡片
- 会话历史管理

替代原有的 ui/ai_search_page.py（仅文件搜索）。
"""

import json
import os
import re
import html
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTextBrowser,
    QListWidget, QListWidgetItem, QSplitter, QComboBox,
    QCheckBox, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPainter, QPen, QColor

from core.ai_layer import AILayer
from core.ai_chat import AiConversation
from core.ai_tools import ToolRegistry
from core.ai_model_config import AIModelConfigManager
from core.ai_prompts import GENERAL_ASSISTANT_SYSTEM_PROMPT
from utils.logger import logger

# ── P2-1: 错误信息用户友好映射 ──
def _friendly_error(err: str) -> str:
    """将技术错误映射为用户可操作的提示"""
    err_lower = err.lower()
    if "403" in err_lower or ("insufficient" in err_lower and "balance" in err_lower):
        return "账户余额不足，请前往 API 平台充值（如 SiliconFlow 或 DeepSeek）"
    if "401" in err_lower:
        return "API Key 无效或未配置，请在左侧「AI 设置」中检查并填写正确的 Key"
    if "402" in err_lower:
        return "账户余额不足（402），请充值后重试"
    if "timeout" in err_lower or "timed out" in err_lower:
        return "请求超时，请检查网络连接或稍后重试"
    if "connection" in err_lower or "connect" in err_lower or "refused" in err_lower:
        return "无法连接到 API 服务器，请检查网络或 API 地址是否正确"
    if "429" in err_lower:
        return "请求过于频繁（429），请稍等片刻后重试"
    if "500" in err_lower or "502" in err_lower or "503" in err_lower:
        return "API 服务器出现故障，请稍后重试"
    if "rate" in err_lower and "limit" in err_lower:
        return "超过 API 调用频率限制，请稍等后重试"
    return f"❌ {err}"  # 兜底：保留原文

# ── 会话存储目录 ──
_SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sessions"
)


# ══════════════════════════════════════════════════════════════════════════════
# 后台线程
# ══════════════════════════════════════════════════════════════════════════════

class _ChatWorker(QThread):
    """AI 对话后台线程 —— 支持工具调用循环 + 流式输出 + 优雅取消"""
    chunk = pyqtSignal(str)            # 流式文本增量
    tool_start = pyqtSignal(str)       # 工具调用开始（工具名）
    tool_end = pyqtSignal(str, str, dict, str)  # P3: 工具调用结束（工具名, 结果摘要, 参数, 完整结果）
    tool_error = pyqtSignal(str, str, dict)  # P3-5: 工具执行异常（工具名, 错误信息, 参数）
    done = pyqtSignal(str)             # 最终结果
    error = pyqtSignal(str)            # 错误信息

    def __init__(self, ai_layer: AILayer, conversation: AiConversation,
                 tool_registry: ToolRegistry, parent=None):
        super().__init__(parent)
        self._layer = ai_layer
        self._conv = conversation
        self._registry = tool_registry
        self._cancelled = False  # P1-2: 优雅取消标志

    def cancel(self):
        """请求取消当前任务 —— 替代 terminate()"""
        self._cancelled = True

    def run(self):
        try:
            from core.ai_chat import MAX_TOOL_LOOP_ROUNDS

            tool_schemas = self._registry.get_tool_schemas() if self._registry else []
            backend = self._layer._backend

            for round_idx in range(MAX_TOOL_LOOP_ROUNDS):
                if self._cancelled:
                    break

                # P1-1: 真正的流式输出 —— 逐 chunk 向 UI 推送增量文本
                accumulated_content = ""
                tool_calls = None

                for stream_chunk in backend.chat_stream(
                    messages=self._conv.get_api_messages(),
                    max_tokens=1024,
                    temperature=0.3,
                    tools=tool_schemas if tool_schemas else None,
                ):
                    if self._cancelled:
                        break
                    if stream_chunk.content_delta:
                        accumulated_content += stream_chunk.content_delta
                        self.chunk.emit(stream_chunk.content_delta)
                    if stream_chunk.is_done:
                        tool_calls = stream_chunk.tool_calls

                if self._cancelled:
                    break

                if not tool_calls:
                    # 最终回复（已逐字流式发送）
                    self._conv.add_assistant_message(accumulated_content)
                    self.done.emit(accumulated_content)
                    return

                # 记录工具调用请求
                self._conv.add_assistant_message(
                    content=accumulated_content or "",
                    tool_calls=tool_calls,
                )

                # 执行每个工具
                for tc in tool_calls:
                    if self._cancelled:
                        break
                    tc_id = tc.get("id", f"call_{round_idx}")
                    tc_func = tc.get("function", {})
                    tc_name = tc_func.get("name", "")
                    tc_args_str = tc_func.get("arguments", "{}")

                    import json
                    try:
                        tc_args = json.loads(tc_args_str) if isinstance(tc_args_str, str) else tc_args_str
                    except json.JSONDecodeError:
                        tc_args = {}

                    self.tool_start.emit(tc_name)
                    # P3-5: 独立异常捕获，单个工具失败不中断整轮对话
                    try:
                        tool_result = self._registry.execute(tc_name, tc_args)
                        result_summary = tool_result[:200] + ("..." if len(tool_result) > 200 else "")
                        self.tool_end.emit(tc_name, result_summary, tc_args, tool_result)
                    except Exception as tool_e:
                        tool_result = f"[工具执行出错] {tool_e}"
                        self.tool_error.emit(tc_name, str(tool_e), tc_args)

                    self._conv.add_tool_result(tc_id, tc_name, tool_result)

            else:
                # 达到最大轮数
                logger.warning(f"工具调用达到最大轮数 {MAX_TOOL_LOOP_ROUNDS}")
                msg = "我已执行了多轮工具调用。如需更深入的分析，请告诉我具体需求。"
                self._conv.add_assistant_message(msg)
                self.chunk.emit(msg)
                self.done.emit(msg)

        except Exception as e:
            logger.error(f"AI 对话失败: {e}")
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 聊天气泡组件
# ══════════════════════════════════════════════════════════════════════════════

class _ChatBubble(QFrame):
    """单条对话气泡 —— 支持文本 + 代码块 + 工具卡片"""

    def __init__(self, role: str = "ai", parent=None):
        super().__init__(parent)
        self._role = role
        self._is_dark = True
        self._init_ui()

    def _init_ui(self):
        self.setObjectName(f"chatBubble_{self._role}")
        self._tool_cards = []  # 跟踪工具卡片用于主题刷新
        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 6, 20, 6)

        self._content_frame = QFrame()
        self._content_frame.setObjectName(f"bubbleContent_{self._role}")
        self._layout = QVBoxLayout(self._content_frame)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(6)

        self._text_browser = QTextBrowser()
        self._text_browser.setObjectName(f"bubbleText_{self._role}")
        self._text_browser.setOpenExternalLinks(True)
        # P1-02 引用溯源：cite://N 锚点由气泡自己处理（http 外链仍由 Qt 打开浏览器）
        self._text_browser.anchorClicked.connect(self._on_anchor_clicked)
        self._citations: list[dict] = []   # P1-02: 本条回答的引用来源
        self._citation_opener = None       # P1-02: 点击来源的回调
        self._cite_chips: list = []        # P1-02: 主题热刷新跟踪
        self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setFrameShape(QFrame.Shape.NoFrame)
        self._text_browser.document().setDocumentMargin(0)
        self._layout.addWidget(self._text_browser)

        # [MODULE-A] 流式渲染跟踪：QTimer 合帧刷新（~16fps），与 chunk 到达频率解耦
        self._accumulated_raw = ""     # 累积原始文本
        self._streaming = False        # 流式进行中（控制打字光标）
        self._stream_timer = QTimer(self)
        self._stream_timer.setSingleShot(True)
        self._stream_timer.setInterval(60)
        self._stream_timer.timeout.connect(self._flush_stream)

        # [MODULE-B] 右键菜单：复制全部文本
        self._text_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text_browser.customContextMenuRequested.connect(self._on_text_context_menu)

        outer_layout = QHBoxLayout()
        if self._role == "user":
            outer.addStretch()
            outer_layout.addWidget(self._content_frame)
            outer.addLayout(outer_layout)
        else:
            outer_layout.addWidget(self._content_frame)
            outer.addStretch()
            outer.addLayout(outer_layout)

        self._apply_theme(True)

    def set_text(self, text: str, streaming: bool = False):
        """设置文本内容（支持 Markdown 渲染）—— streaming=True 时带打字光标"""
        self._accumulated_raw = text
        self._streaming = streaming
        self._stream_timer.stop()
        self._flush_stream()

    def append_text(self, text: str):
        """[MODULE-A] 流式追加 —— 只累积，由 QTimer 合帧后统一渲染

        刷新频率固定 ~16fps，与 token 到达速率解耦：高频 chunk 不卡顿，
        慢速流式也不会长时间无更新（旧实现按 20 字符跳变，观感差）。
        """
        self._accumulated_raw += text
        self._streaming = True
        if not self._stream_timer.isActive():
            self._stream_timer.start()

    def _flush_stream(self):
        """合帧渲染当前累积文本（QTimer 回调）"""
        raw = self._accumulated_raw
        # 代码块未闭合 → 补闭合符渐进渲染，避免长代码期间画面冻结
        if raw.count('```') % 2 != 0:
            raw += '\n```'
        html = self._render_markdown(raw)
        if self._streaming:
            accent = "#89b4fa" if self._is_dark else "#1e66f5"
            caret = f'<span style="color:{accent};font-weight:700;">▌</span>'
            if html.endswith('</div>'):
                html = html[:-6] + caret + '</div>'
        self._text_browser.setHtml(html)
        self._adjust_size()

    def _on_text_context_menu(self, pos):
        """[MODULE-B] 右键菜单：复制全部文本"""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(_theme_menu_qss(self._is_dark))
        copy_all = menu.addAction("📋 复制全部文本")
        action = menu.exec(self._text_browser.mapToGlobal(pos))
        if action == copy_all:
            QApplication.clipboard().setText(self._text_browser.toPlainText())

    def add_retry_button(self, callback):
        """P1-3: 在气泡底部添加'重试'按钮"""
        btn = QPushButton("🔄 重试")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        accent = "#89b4fa" if self._is_dark else "#8839ef"
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {accent};"
            f"  border: 1px solid {accent}; border-radius: 6px;"
            f"  padding: 4px 12px; font-size: 9pt;"
            f"}}"
            f"QPushButton:hover {{ background: {accent}; color: #1e1e2e; }}"
        )
        btn.clicked.connect(callback)
        self._layout.addWidget(btn)
        self._retry_btn = btn

    def add_regenerate_button(self, callback):
        """P3-3: 在气泡底部添加'重新生成'按钮"""
        btn = QPushButton("🔄 重新生成")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        accent = "#a6e3a1" if self._is_dark else "#40a02b"
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {accent};"
            f"  border: 1px solid {accent}; border-radius: 6px;"
            f"  padding: 4px 12px; font-size: 9pt;"
            f"}}"
            f"QPushButton:hover {{ background: {accent}; color: #1e1e2e; }}"
        )
        btn.clicked.connect(callback)
        self._layout.addWidget(btn)

    def set_citations(self, citations: list, opener):
        """P1-02 引用溯源：在气泡底部渲染"📎 来源"chip 行

        citations: [{"file_id": int|None, "file_name": str,
                     "file_path": str, "snippet": str|None}, ...]
        opener: 点击 chip 时的回调，接收 cite dict。
        """
        from PyQt6.QtWidgets import QHBoxLayout

        self._citations = list(citations or [])
        self._citation_opener = opener
        if not self._citations:
            return

        row = QFrame()
        row.setObjectName("citeRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(6)

        title = QLabel("📎 来源")
        title.setStyleSheet("border: none; background: transparent;")
        h.addWidget(title)
        self._cite_title = title

        for cite in self._citations:
            name = cite.get("file_name") or os.path.basename(
                cite.get("file_path", "")) or "未知文件"
            if len(name) > 22:
                name = name[:21] + "…"
            chip = QPushButton(f"📄 {name}")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            tip = cite.get("file_path", "")
            snip = cite.get("snippet")
            if snip:
                tip += f"\n\n摘录: {snip[:120]}"
            tip += "\n\n点击打开该文件"
            chip.setToolTip(tip)
            chip.clicked.connect(
                lambda _checked=False, c=cite: self._citation_opener and self._citation_opener(c)
            )
            h.addWidget(chip)
            self._cite_chips.append((chip, title))

        h.addStretch()
        self._layout.addWidget(row)
        self._style_citation_chips()
        self._adjust_size()

    def _style_citation_chips(self):
        """P1-02: 引用 chip / 标题主题样式（切主题热刷新）"""
        is_dark = self._is_dark
        chip_border = "#45475a" if is_dark else "#bcc0cc"
        chip_text = "#a6adc8" if is_dark else "#6c6f85"
        accent = "#89b4fa" if is_dark else "#8839ef"
        for chip, title in self._cite_chips:
            chip.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent; color: {chip_text};"
                f"  border: 1px solid {chip_border}; border-radius: 10px;"
                f"  padding: 3px 10px; font-size: 9pt;"
                f"}}"
                f"QPushButton:hover {{"
                f"  color: {accent}; border-color: {accent};"
                f"}}"
            )
            title.setStyleSheet(
                f"font-size: 9pt; color: {chip_text};"
                f" border: none; background: transparent;"
            )

    def show_no_evidence_hint(self):
        """P1-02 无证据兜底：正文引用了 [来源 N] 但工具层未收集到任何文件证据"""
        hint = QLabel(
            "⚠️ 本回答中的 [来源] 编号未匹配到可追溯的文件证据，相关结论请人工核实"
        )
        hint.setWordWrap(True)
        is_dark = self._is_dark
        hint.setStyleSheet(
            f"font-size: 9pt; color: {'#f9e2af' if is_dark else '#df8e1d'};"
            " border: none; background: transparent;"
        )
        self._layout.addWidget(hint)
        self._adjust_size()

    def _on_anchor_clicked(self, url):
        """P1-02: 点击正文中的 [来源 N] 锚点 → 打开对应来源文件"""
        if self._citation_opener is None or not self._citations:
            return
        s = url.toString()
        if not s.startswith("cite://"):
            return
        try:
            idx = int(s[len("cite://"):]) - 1
        except ValueError:
            return
        if 0 <= idx < len(self._citations):
            self._citation_opener(self._citations[idx])

    def add_tool_card(self, tool_name: str, result_summary: str,
                      action_text: str = None, action_callback=None,
                      full_result: str = None, is_error: bool = False):
        """添加工具执行结果卡片 —— P3-1: 支持完整内容查看, P3-5: 错误卡片样式"""
        card = QFrame()
        card.setObjectName("toolCardError" if is_error else "toolCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)

        # 工具名称标题
        icons = {
            "search_files": "📂",
            "search_content": "📝",
            "search_web": "🌐",
            "read_file": "📄",
        }
        icon = icons.get(tool_name, "🔧")
        status = " ⚠️" if is_error else ""
        header_color = "#f38ba8" if is_error else ("#89b4fa" if self._is_dark else "#8839ef")
        header = QLabel(f"{icon} {tool_name}{status}")
        header.setStyleSheet(
            f"font-weight: bold; font-size: 10pt; color: {header_color};"
            f" border: none; background: transparent;"
        )
        card_layout.addWidget(header)

        # 结果摘要
        summary_label = QLabel(result_summary)
        summary_label.setWordWrap(True)
        card_layout.addWidget(summary_label)

        # P3-1: 完整内容查看按钮（有额外内容时显示）
        detail_btn = None
        if full_result and len(full_result) > 200:
            detail_btn = QPushButton("📋 查看完整内容")
            detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            detail_btn.clicked.connect(
                lambda _checked=False, r=full_result, n=tool_name:
                self._show_full_result(r, n)
            )
            card_layout.addWidget(detail_btn)

        # 可选操作按钮（如 "查看全部 →"）
        action_btn = None
        if action_text and action_callback:
            action_btn = QPushButton(action_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.clicked.connect(action_callback)
            card_layout.addWidget(action_btn)

        tool_bg = "#3d1e2e" if is_error else ("#252538" if self._is_dark else "#dce0e8")
        tool_border = "#f38ba8" if is_error else ("#45475a" if self._is_dark else "#bcc0cc")
        tool_text = "#f38ba8" if is_error else ("#a6adc8" if self._is_dark else "#6c6f85")
        accent = "#89b4fa" if self._is_dark else "#8839ef"
        summary_label.setStyleSheet(
            f"font-size: 9pt; color: {tool_text}; border: none; background: transparent;"
        )
        btn_style = (
            f"QPushButton {{"
            f"  background: transparent; color: {tool_text if detail_btn else accent};"
            f"  border: 1px solid {tool_text if detail_btn else accent}; border-radius: 6px;"
            f"  padding: 4px 12px; font-size: 9pt;"
            f"}}"
            f"QPushButton:hover {{ background: {tool_text if detail_btn else accent}; color: #1e1e2e; }}"
        )
        if detail_btn:
            detail_btn.setStyleSheet(btn_style)
        if action_btn:
            action_btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent; color: {accent};"
                f"  border: 1px solid {accent}; border-radius: 6px;"
                f"  padding: 4px 12px; font-size: 9pt;"
                f"}}"
                f"QPushButton:hover {{ background: {accent}; color: #1e1e2e; }}"
            )
        card.setStyleSheet(
            f"QFrame#toolCard{'Error' if is_error else ''} {{"
            f"  background: {tool_bg}; border: 1px solid {tool_border};"
            f"  border-radius: 8px;"
            f"}}"
        )
        self._layout.addWidget(card)
        self._tool_cards.append((card, header, summary_label))
        # P3-5: 错误卡片也追加热刷新支持
        if is_error:
            self._tool_cards[-1] = (card, header, summary_label)
        self._adjust_size()

    def _show_full_result(self, full_result: str, tool_name: str):
        """P3-1: 在对话框中显示工具执行完整结果"""
        from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout as QVBL
        dlg = QDialog(self)
        dlg.setWindowTitle(f"完整结果 - {tool_name}")
        dlg.resize(540, 380)
        layout = QVBL(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(full_result)
        text_edit.setStyleSheet(
            "background: #1e1e2e; color: #cdd6f4; border-radius: 6px;"
            "padding: 8px; font-size: 10pt; font-family: monospace;"
        ) if self._is_dark else text_edit.setStyleSheet(
            "background: #f5f5f9; color: #4c4f69; border: 1px solid #ccd0da;"
            "border-radius: 6px; padding: 8px; font-size: 10pt; font-family: monospace;"
        )
        layout.addWidget(text_edit)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.close)
        close_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e;"
            "border-radius: 6px; padding: 6px 20px; }"
            "QPushButton:hover { background: #cba6f7; }"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _render_markdown(self, text: str) -> str:
        """将文本转为 HTML（代码块用 Pygments 高亮，其余用基本 Markdown）—— P2-3: 浅色主题适配"""
        escaped = html.escape(text)

        # P2-3: 根据主题选代码块背景和 Pygments 样式
        code_bg = "#272822" if self._is_dark else "#eff1f5"
        code_border = "#45475a" if self._is_dark else "#ccd0da"
        code_text = "#fab387" if self._is_dark else "#fe640b"
        inline_bg = "#313244" if self._is_dark else "#e6e9ef"
        inline_fg = "#fab387" if self._is_dark else "#d20f39"
        tool_text = "#a6adc8" if self._is_dark else "#6c6f85"
        pygments_style = "monokai" if self._is_dark else "default"

        # 处理代码块 ```lang\ncode\n```
        def _highlight_code(match):
            lang = match.group(1) or "text"
            code = match.group(2)
            try:
                from pygments import highlight
                from pygments.lexers import get_lexer_by_name, TextLexer
                from pygments.formatters import HtmlFormatter
                try:
                    lexer = get_lexer_by_name(lang, stripall=True)
                except Exception:
                    lexer = TextLexer()
                formatter = HtmlFormatter(
                    style=pygments_style,
                    noclasses=True,
                    nowrap=False,
                )
                highlighted = highlight(code, lexer, formatter)
                lang_display = lang.upper()
                return (
                    f'<div style="background:{code_bg};border:1px solid {code_border};'
                    f'border-radius:8px;padding:10px 12px 8px 12px;margin:8px 0;overflow-x:auto;font-size:9pt;">'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;margin-bottom:6px;font-size:8pt;'
                    f'color:{tool_text};opacity:0.7;">'
                    f'<span style="font-family:monospace;">{lang_display}</span>'
                    f'<span>📋 右键复制</span></div>'
                    f'{highlighted}</div>'
                )
            except Exception:
                lang_display = lang.upper() if lang else "TEXT"
                return (
                    f'<div style="background:{code_bg};border:1px solid {code_border};'
                    f'border-radius:8px;padding:10px 12px 8px 12px;margin:8px 0;font-size:9pt;overflow-x:auto;">'
                    f'<div style="font-size:8pt;color:{tool_text};opacity:0.7;margin-bottom:6px;'
                    f'font-family:monospace;">{lang_display}</div>'
                    f'<pre style="margin:0;"><code>{html.escape(code)}</code></pre></div>'
                )

        # 代码块先暂存为占位符，避免块级解析误伤代码内容
        stash: list[str] = []

        def _stash_code(match):
            stash.append(_highlight_code(match))
            return f"\x00CB{len(stash) - 1}\x00"

        result = re.sub(r'```(\w+)?\n(.*?)```', _stash_code, escaped, flags=re.DOTALL)

        # 处理行内代码 `code`
        result = re.sub(
            r'`([^`]+)`',
            rf'<code style="background:{inline_bg};color:{inline_fg};padding:2px 6px;border-radius:4px;font-size:9pt;">\1</code>',
            result
        )

        # 处理粗体 **text**
        result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)

        # 处理链接 [text](url)
        link_color = "#89b4fa" if self._is_dark else "#1e66f5"
        result = re.sub(
            r'\[(.+?)\]\((https?://[^\s)]+)\)',
            rf'<a href="\2" style="color:{link_color};">\1</a>',
            result
        )

        # P1-02 引用溯源：正文中的 [来源 N] → 可点击锚点（cite://N → 对应来源文件）
        result = re.sub(
            r'\[(?:来源|Source)\s*(\d+)\]',
            rf'<a href="cite://\1" style="color:{link_color};text-decoration:none;">[\1]</a>',
            result
        )

        # 块级元素（标题/列表/表格/分隔线/引用）—— 对齐主流 AI 渲染
        accent = link_color

        def _td(cells, is_head=False):
            tag = "th" if is_head else "td"
            bg = f"background:{inline_bg};" if is_head else ""
            weight = "font-weight:700;" if is_head else ""
            return "".join(
                f'<{tag} style="{bg}{weight}padding:5px 10px;">{c}</{tag}>'
                for c in cells
            )

        lines = result.split("\n")
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            s = lines[i].strip()

            # 表格：| a | b | + 分隔行 |---|---|
            if s.startswith("|") and s.endswith("|") and i + 1 < n \
                    and re.match(r'^\|[\s:\-|]+\|$', lines[i + 1].strip()):
                header = [c.strip() for c in s.strip("|").split("|")]
                rows = []
                j = i + 2
                while j < n and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                    rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                    j += 1
                body = f'<tr>{_td(header, True)}</tr>' + "".join(f'<tr>{_td(r)}</tr>' for r in rows)
                out.append(
                    f'<table border="1" cellspacing="0" cellpadding="0" '
                    f'style="border-collapse:collapse;margin:6px 0;font-size:9.5pt;">{body}</table>'
                )
                i = j
                continue

            # 标题 # ~ ######
            m = re.match(r'^(#{1,6})\s+(.+)$', s)
            if m:
                size = {1: "14pt", 2: "13pt", 3: "12pt"}.get(len(m.group(1)), "11pt")
                out.append(
                    f'<div style="font-size:{size};font-weight:700;color:{accent};margin-top:6px;">{m.group(2)}</div>'
                )
                i += 1
                continue

            # 分隔线 ---
            if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
                out.append(f'<div style="border-top:1px solid {code_border};margin:8px 0;font-size:1px;">&nbsp;</div>')
                i += 1
                continue

            # 无序列表（连续行合并）
            if re.match(r'^[-*]\s+', s):
                items = []
                while i < n and re.match(r'^[-*]\s+', lines[i].strip()):
                    txt = re.sub(r'^[-*]\s+', '', lines[i].strip())
                    items.append(f'<li>{txt}</li>')
                    i += 1
                out.append(f'<ul style="margin-top:2px;margin-bottom:2px;">{"".join(items)}</ul>')
                continue

            # 有序列表（连续行合并）
            if re.match(r'^\d+\.\s+', s):
                items = []
                while i < n and re.match(r'^\d+\.\s+', lines[i].strip()):
                    txt = re.sub(r'^\d+\.\s+', '', lines[i].strip())
                    items.append(f'<li>{txt}</li>')
                    i += 1
                out.append(f'<ol style="margin-top:2px;margin-bottom:2px;">{"".join(items)}</ol>')
                continue

            # 引用 >
            if s.startswith("&gt;"):
                quote = []
                while i < n and lines[i].strip().startswith("&gt;"):
                    quote.append(re.sub(r'^&gt;\s?', '', lines[i].strip()))
                    i += 1
                out.append(
                    f'<div style="border-left:3px solid {accent};padding:2px 0 2px 10px;'
                    f'color:{tool_text};margin:6px 0;">{"<br>".join(quote)}</div>'
                )
                continue

            out.append(lines[i])
            i += 1

        # 空行治理 + 拼接：块级元素（自带外边距）与相邻内容之间不插 <br>，
        # 与块级相邻的空行丢弃，连续空行折叠为一个段落间隔
        def _is_block(item):
            return item.startswith(("<ul", "<ol", "<table", "<div", "\x00CB"))

        parts: list[str] = []
        for idx, item in enumerate(out):
            if item.strip() == "":
                nxt = next((x for x in out[idx + 1:] if x.strip() != ""), None)
                if not parts or _is_block(parts[-1]) or nxt is None or _is_block(nxt):
                    continue  # 开头/结尾/块级相邻的空行
                if parts[-1] == "":
                    continue  # 连续空行折叠
                parts.append("")
                continue
            if parts:
                if _is_block(parts[-1]) or _is_block(item):
                    parts.append(item)
                else:
                    parts.extend(("<br>", item))
            else:
                parts.append(item)
        result = "".join(parts)

        # 模型在表格/列表单元格内用 <br> 换行（Markdown 表格不支持真实换行符），
        # 转义后会显示为字面量，这里还原为真换行（代码块已 stash，不受影响）
        result = re.sub(r'&lt;br\s*/?&gt;', '<br>', result)

        # 还原代码块
        result = re.sub(r'\x00CB(\d+)\x00', lambda m: stash[int(m.group(1))], result)

        return f'<div style="font-size:10pt;line-height:1.6;">{result}</div>'

    def _adjust_size(self):
        """自适应高度 —— 使用实际可用宽度"""
        doc = self._text_browser.document()
        # 优先用 viewport 宽度，其次用父容器宽度，保底 400
        vp_w = self._text_browser.viewport().width()
        if vp_w <= 0 and self._content_frame.parent():
            vp_w = self._content_frame.parent().width() - 80
        if vp_w <= 0:
            vp_w = 400
        # 气泡框架最大 700（含内边距）：按更宽容器测量会低估行数 → 末行被裁剪
        vp_w = min(vp_w, 660)
        doc.setTextWidth(vp_w)
        doc_height = doc.size().height()
        # 保证至少 20px 高度
        self._text_browser.setFixedHeight(max(int(doc_height + 12), 20))
        # 强制内容框架也更新
        self._content_frame.updateGeometry()
        self._content_frame.setMaximumWidth(700)
        # 布局稳定后再量一次（首条消息时 viewport 宽度可能尚未就绪）
        QTimer.singleShot(0, self._adjust_size_after_layout)

    def _adjust_size_after_layout(self):
        """布局后的二次校准：viewport 宽度变化时重测高度"""
        doc = self._text_browser.document()
        vp_w = self._text_browser.viewport().width()
        if vp_w <= 0:
            return
        vp_w = min(vp_w, 660)
        if doc.textWidth() != vp_w:
            doc.setTextWidth(vp_w)
        real_h = int(doc.size().height() + 12)
        if abs(self._text_browser.height() - real_h) > 4:
            self._text_browser.setFixedHeight(max(real_h, 20))

    def _apply_theme(self, is_dark: bool):
        self._is_dark = is_dark
        if self._role == "user":
            self._content_frame.setStyleSheet(
                "QFrame#bubbleContent_user {"
                "  background: #89b4fa; border-radius: 14px;"
                "}"
            )
            self._text_browser.setStyleSheet(
                "QTextBrowser#bubbleText_user {"
                "  background: transparent; color: #1e1e2e; border: none; font-size: 13px;"
                "}"
            )
        else:
            # AI 气泡跟随主题
            bg_color = "#313244" if is_dark else "#e6e9ef"
            text_color = "#cdd6f4" if is_dark else "#4c4f69"
            self._content_frame.setStyleSheet(
                f"QFrame#bubbleContent_ai {{"
                f"  background: {bg_color}; border-radius: 14px;"
                f"}}"
            )
            self._text_browser.setStyleSheet(
                f"QTextBrowser#bubbleText_ai {{"
                f"  background: transparent; color: {text_color}; border: none; font-size: 13px;"
                f"}}"
            )

        # 刷新工具卡片样式
        tool_bg = "#252538" if is_dark else "#dce0e8"
        tool_border = "#45475a" if is_dark else "#bcc0cc"
        tool_text = "#a6adc8" if is_dark else "#6c6f85"
        accent = "#89b4fa" if is_dark else "#8839ef"
        for card, header, summary in self._tool_cards:
            header.setStyleSheet(
                f"font-weight: bold; font-size: 10pt; color: {accent};"
                f" border: none; background: transparent;"
            )
            summary.setStyleSheet(
                f"font-size: 9pt; color: {tool_text}; border: none; background: transparent;"
            )
            card.setStyleSheet(
                f"QFrame#toolCard {{"
                f"  background: {tool_bg}; border: 1px solid {tool_border};"
                f"  border-radius: 8px;"
                f"}}"
            )

        # P1-02: 刷新引用 chip 样式
        if self._cite_chips:
            self._style_citation_chips()

        # 主题切换后重渲染 Markdown HTML —— 代码块/表格/标题等颜色是渲染时
        # 烘焙进 HTML 的，只改 QSS 会导致切主题后残留旧主题配色
        if getattr(self, "_accumulated_raw", ""):
            self._flush_stream()


class _SemanticWorker(QThread):
    """🧠 语义检索后台线程：查询向量库，返回与问题语义最相关的文件"""

    done = pyqtSignal(list)   # [{file_name, file_path, score}, ...]
    error = pyqtSignal(str)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        try:
            from PyQt6.QtCore import QSettings
            from core.ai_layer import AILayer
            from core.embedding_service import EmbeddingService
            from database.db_manager import db

            # 向量模型独立配置（对话模型不支持 /embeddings）
            model = (QSettings("smart-file-manager", "ai")
                     .value("embed_model", "", str) or "").strip() or None
            svc = EmbeddingService(AILayer(), embed_model=model)
            if svc.count_embedded() == 0:
                self.done.emit([])
                return
            results = svc.search(self._query, top_k=8)
            if not results:
                self.done.emit([])
                return
            ids = [fid for fid, _ in results]
            scores = {fid: s for fid, s in results}
            placeholders = ",".join("?" * len(ids))
            rows = db.execute_query(
                f"SELECT id, file_name, file_path FROM files "
                f"WHERE id IN ({placeholders}) AND status = 'active'",
                ids,
            ) or []
            files = [
                {
                    "file_id": r["id"],
                    "file_name": r["file_name"],
                    "file_path": r["file_path"],
                    "score": scores.get(r["id"], 0.0),
                }
                for r in rows
            ]
            files.sort(key=lambda f: f["score"], reverse=True)
            self.done.emit(files)
        except Exception as e:
            logger.error(f"语义检索线程失败: {e}")
            self.error.emit(str(e))


def _theme_menu_qss(is_dark: bool) -> str:
    """右键弹出菜单的主题化样式（QMenu 弹窗不继承页面 QSS，需单独设置）"""
    bg = "#1e1e2e" if is_dark else "#ffffff"
    fg = "#cdd6f4" if is_dark else "#4c4f69"
    border = "#45475a" if is_dark else "#bcc0cc"
    hl = "rgba(137, 180, 250, 0.18)" if is_dark else "rgba(136, 57, 239, 0.12)"
    return (
        f"QMenu {{ background: {bg}; color: {fg}; border: 1px solid {border};"
        f" border-radius: 8px; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 18px; border-radius: 6px; margin: 1px 2px; }}"
        f"QMenu::item:selected {{ background: {hl}; }}"
        f"QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}"
    )


class _ContextRing(QWidget):
    """主流 AI 风格的上下文用量圆环（替代进度条）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._pct = 0
        self._color = QColor("#a6e3a1")
        self._track = QColor("#45475a")

    def set_usage(self, pct: int, color: str, track: str):
        self._pct = max(0, min(pct, 100))
        self._color = QColor(color)
        self._track = QColor(track)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = QPen(self._track, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        if self._pct > 0:
            pen.setColor(self._color)
            p.setPen(pen)
            # Qt 角度单位为 1/16 度：90*16 从顶部起，负跨度为顺时针
            p.drawArc(rect, 90 * 16, int(-3.6 * 16 * self._pct))


# ══════════════════════════════════════════════════════════════════════════════
# 主页面
# ══════════════════════════════════════════════════════════════════════════════

class AiChatPage(QWidget):
    """AI 全能助手主页面"""

    go_back = pyqtSignal()
    show_results = pyqtSignal(dict)  # 兼容旧接口
    navigate_to_search = pyqtSignal(dict)  # 跳转到搜索 Tab 并填入参数
    # P1-02 引用溯源：请求主窗口打开某个来源文件 (file_path, file_id|None)
    open_file_request = pyqtSignal(str, object)

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self._is_dark = theme == "dark"

        # 初始化核心层
        self.ai_layer = AILayer()
        self._model_cfg = AIModelConfigManager()
        self._tool_registry: Optional[ToolRegistry] = None

        # 对话状态
        self._conversation: Optional[AiConversation] = None
        self._worker: Optional[_ChatWorker] = None
        self._current_streaming_bubble: Optional[_ChatBubble] = None
        self._streaming_content_accumulated = False  # P1-1: 跟踪当前轮是否已收到过文本
        self._all_sessions = []  # P2-2: 缓存全部会话用于搜索过滤
        self._current_citations: list[dict] = []  # P1-02: 本轮回答的引用来源
        self._pending_semantic_sources: list[dict] = []  # P1-02: 待注入的语义检索来源

        self._init_ui()
        self._refresh_sessions()
        self._new_conversation()

    # ── UI 构建 ──

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部栏 ──
        self._init_top_bar()
        layout.addWidget(self._top_bar)

        # ── 主内容区（对话 + 侧面板） ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # 对话区
        self._init_chat_area()
        splitter.addWidget(self._chat_container)

        # 侧面板
        self._init_side_panel()
        splitter.addWidget(self._side_panel)

        splitter.setSizes([700, 220])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        layout.addWidget(splitter, 1)

        # ── 输入栏 ──
        self._init_input_bar()
        layout.addWidget(self._input_bar)

        self._apply_theme()

    def _init_top_bar(self):
        self._top_bar = QWidget()
        self._top_bar.setFixedHeight(56)
        self._top_bar.setObjectName("aiChatTopBar")
        top_layout = QHBoxLayout(self._top_bar)
        top_layout.setContentsMargins(12, 8, 16, 8)
        top_layout.setSpacing(12)

        self._back_btn = QPushButton("← 返回")
        self._back_btn.setObjectName("aiChatBackBtn")
        self._back_btn.setFixedHeight(32)
        self._back_btn.setFixedWidth(80)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(lambda: self.go_back.emit())
        top_layout.addWidget(self._back_btn)

        title = QLabel("🤖 AI 全能助手")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; background: transparent; border: none;")
        top_layout.addWidget(title)

        top_layout.addStretch()

        # 新建对话按钮
        self._new_chat_btn = QPushButton("➕ 新对话")
        self._new_chat_btn.setObjectName("aiChatNewBtn")
        self._new_chat_btn.setFixedHeight(32)
        self._new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_chat_btn.clicked.connect(self._new_conversation)
        top_layout.addWidget(self._new_chat_btn)

        # 模型选择器
        self._model_combo = QComboBox()
        self._model_combo.setFixedHeight(32)
        self._model_combo.setFixedWidth(200)
        self._model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_model_list()
        top_layout.addWidget(self._model_combo)

    def _init_chat_area(self):
        self._chat_container = QWidget()
        self._chat_container.setObjectName("aiChatContainer")
        chat_layout = QVBoxLayout(self._chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._follow_bottom = True  # 用户向上回看时暂停自动滚底
        self._scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll_moved)
        self._scroll_area.setObjectName("aiChatScroll")

        self._chat_widget = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setContentsMargins(0, 12, 0, 12)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()

        self._scroll_area.setWidget(self._chat_widget)
        chat_layout.addWidget(self._scroll_area)

        # [MODULE-B] 上下文圆环已集成到输入栏 chip 行（见 _init_input_bar）

        # P2-4: 请求超时进度提示标签
        self._progress_label = QLabel()
        self._progress_label.setObjectName("aiProgressLabel")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet(
            "font-size: 10pt; color: #a6adc8; background: transparent; padding: 4px;"
        )
        chat_layout.addWidget(self._progress_label)

        # P2-4: 进度更新计时器
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._update_progress)
        self._progress_seconds = 0

        # 欢迎提示
        self._show_welcome()

    def _init_side_panel(self):
        self._side_panel = QWidget()
        self._side_panel.setObjectName("aiChatSidePanel")
        self._side_panel.setFixedWidth(220)
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(12)

        # 能力开关已集成到输入栏（工具胶囊 chips，见 _init_input_bar）

        side_layout.addSpacing(8)

        # 分隔线（有历史时显示）
        self._sessions_sep = QFrame()
        self._sessions_sep.setObjectName("aiSideSep")
        self._sessions_sep.setFrameShape(QFrame.Shape.HLine)
        side_layout.addWidget(self._sessions_sep)

        # 会话历史标题（有历史时显示）
        self._sessions_header_label = QLabel("💬 对话历史")
        self._sessions_header_label.setStyleSheet(
            "font-weight: bold; font-size: 11pt; border: none; background: transparent;")
        side_layout.addWidget(self._sessions_header_label)

        # P2-2: 搜索过滤输入框
        from PyQt6.QtWidgets import QLineEdit
        self._session_search = QLineEdit()
        self._session_search.setObjectName("aiSessionSearch")
        self._session_search.setPlaceholderText("🔍 搜索会话…")
        self._session_search.setClearButtonEnabled(True)
        self._session_search.textChanged.connect(self._filter_sessions)
        side_layout.addWidget(self._session_search)

        self._session_list = QListWidget()
        self._session_list.setObjectName("aiSessionList")
        self._session_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._session_list.clicked.connect(self._on_session_clicked)
        self._session_list.doubleClicked.connect(self._on_session_double_clicked)  # C1
        self._session_list.setMaximumHeight(300)
        # P2-2: 右键菜单（删除会话）
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._on_session_context_menu)
        side_layout.addWidget(self._session_list)

        side_layout.addStretch()

    # 输入栏工具胶囊（能力开关集成到输入框上方，主流 AI 风格）
    _TOOL_CHIPS = [
        ("search_files", "📂 文件", "文件搜索"),
        ("search_content", "📝 正文", "正文检索（含来源）"),
        ("search_web", "🌐 联网", "联网搜索"),
        ("read_file", "📄 读取", "读取文件"),
        ("semantic", "🧠 语义", "语义搜索：按内容含义检索相关文件注入上下文（需先生成向量索引）"),
    ]

    def _init_input_bar(self):
        self._input_bar = QFrame()
        self._input_bar.setObjectName("aiChatInputBar")
        outer_layout = QVBoxLayout(self._input_bar)
        outer_layout.setContentsMargins(16, 8, 16, 10)
        outer_layout.setSpacing(6)

        # 工具胶囊行：可点选的能力开关（激活=主题色描边，未激活=灰色描边）
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self._tool_checks = {}
        for tool_id, label, tip in self._TOOL_CHIPS:
            chip = QPushButton(label)
            chip.setObjectName(f"toolChip_{tool_id}")
            chip.setCheckable(True)
            # 语义默认关闭：需先生成向量索引才有意义
            chip.setChecked(tool_id != "semantic")
            chip.setFixedHeight(26)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(tip)
            chip.clicked.connect(self._on_tool_toggle_changed)
            self._tool_checks[tool_id] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch()

        # 上下文用量圆环（集成到输入栏，chip 行右端，主流 AI 风格）
        self._ctx_ring = _ContextRing()
        chip_row.addWidget(self._ctx_ring)

        outer_layout.addLayout(chip_row)

        # 输入行
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)

        # 输入框（支持多行；Enter 发送，Shift+Enter 换行）
        from PyQt6.QtWidgets import QTextEdit

        class _EnterTextEdit(QTextEdit):
            """Enter 发送、Shift+Enter 换行的多行输入框"""

            def __init__(self, on_send):
                super().__init__()
                self._on_send = on_send

            def keyPressEvent(self, event):
                if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                        and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._on_send()
                    return
                super().keyPressEvent(event)

        self._msg_input = _EnterTextEdit(self._send_message)
        self._msg_input.setObjectName("aiChatMsgInput")
        self._msg_input.setPlaceholderText("输入你的问题，如：帮我找代码中的数据库连接..."
                                            "\n支持 Shift+Enter 换行，Enter 发送")
        self._msg_input.setAcceptRichText(False)
        self._msg_input.setTabChangesFocus(True)
        self._msg_input.textChanged.connect(self._auto_resize_input)  # [D2]
        self._auto_resize_input()  # 初始即锁定高度，避免 QTextEdit 默认撑大
        input_layout.addWidget(self._msg_input, 1)

        # 发送按钮
        self._send_btn = QPushButton("发送 ▶")
        self._send_btn.setObjectName("aiChatSendBtn")
        self._send_btn.setFixedHeight(56)
        self._send_btn.setFixedWidth(90)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        # 停止按钮（流式输出时显示）
        self._stop_btn = QPushButton("停止 ■")
        self._stop_btn.setObjectName("aiChatStopBtn")
        self._stop_btn.setFixedHeight(56)
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self._stop_generation)
        self._stop_btn.setVisible(False)
        input_layout.addWidget(self._stop_btn)

        outer_layout.addLayout(input_layout)

    def keyPressEvent(self, event):
        """全局快捷键处理 —— [MODULE-B] 扩展快捷键"""
        # Ctrl+/ 快捷键面板
        if event.key() == Qt.Key.Key_Slash and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._show_shortcuts_panel()
            return
        # Ctrl+N 新建对话
        if event.key() == Qt.Key.Key_N and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._new_conversation()
            return
        # Ctrl+L 清空当前对话
        if event.key() == Qt.Key.Key_L and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._new_conversation()
            return
        # Ctrl+Shift+C 复制最后一条 AI 回复
        if (event.key() == Qt.Key.Key_C
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if self._conversation:
                msgs = self._conversation.get_messages()
                for m in reversed(msgs):
                    if m.role == "assistant" and m.content:
                        from PyQt6.QtWidgets import QApplication
                        QApplication.clipboard().setText(m.content)
                        break
            return
        # Escape 停止生成
        if event.key() == Qt.Key.Key_Escape and self._worker:
            self._stop_generation()
            return
        # Enter 发送 / Shift+Enter 换行
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                if self._msg_input.hasFocus():
                    self._send_message()
                else:
                    super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _show_shortcuts_panel(self):
        """[MODULE-B] 快捷键面板"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout as QVBL, QHBoxLayout as QHBL
        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键")
        dlg.setFixedSize(360, 280)
        layout = QVBL(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("⌨️ 快捷键")
        title.setStyleSheet(
            "font-size: 14pt; font-weight: bold; background: transparent;"
            + (" color: #cdd6f4;" if self._is_dark else " color: #4c4f69;")
        )
        layout.addWidget(title)

        shortcuts = [
            ("Enter", "发送消息"),
            ("Shift + Enter", "换行"),
            ("Ctrl + N", "新建对话"),
            ("Ctrl + /", "显示此面板"),
            ("Escape", "停止生成"),
            ("Ctrl + Shift + C", "复制最后一条 AI 回复"),
            ("Ctrl + L", "清空当前对话"),
        ]
        for key, desc in shortcuts:
            row = QHBL()
            row.setSpacing(12)
            key_label = QLabel(key)
            key_label.setStyleSheet(
                "background: #313244; color: #89b4fa; border-radius: 4px;"
                "padding: 2px 8px; font-size: 10pt; font-family: monospace;"
                "border: none;"
            ) if self._is_dark else key_label.setStyleSheet(
                "background: #e6e9ef; color: #1e66f5; border-radius: 4px;"
                "padding: 2px 8px; font-size: 10pt; font-family: monospace;"
                "border: none;"
            )
            row.addWidget(key_label)
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(
                "font-size: 10pt; background: transparent; border: none;"
                + (" color: #cdd6f4;" if self._is_dark else " color: #4c4f69;")
            )
            row.addWidget(desc_label)
            row.addStretch()
            layout.addLayout(row)

        layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dlg.close)
        close_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e;"
            "border-radius: 6px; padding: 6px 20px; font-size: 10pt; }"
            "QPushButton:hover { background: #cba6f7; }"
        )
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    # ── 对话管理 ──

    def _new_conversation(self):
        """创建新对话"""
        # 保存当前对话（如有）
        if self._conversation and self._conversation.message_count > 0:
            try:
                self._conversation.save(_SESSIONS_DIR)
            except Exception:
                pass

        self._conversation = AiConversation(
            system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT.format(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                working_directory=os.path.abspath("."),
            ),
            model=self.ai_layer.backend_model_name,
            title="新对话",
            max_context_size=self._get_model_max_context(),
        )
        self._current_streaming_bubble = None
        self._streaming_content_accumulated = False

        # 清空消息区，显示欢迎
        self._clear_chat()
        self._show_welcome()
        self._update_context_indicator()  # [MODULE-B]
        self._refresh_sessions()

    def _clear_chat(self):
        """清空对话区"""
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_welcome(self):
        """显示欢迎消息 + P3-2: 可点击建议提示"""
        welcome = _ChatBubble("ai", self._chat_widget)
        welcome._apply_theme(self._is_dark)
        welcome.set_text(
            "你好！我是 **AI 全能助手**。\n\n"
            "我可以帮你：\n"
            "📂 搜索文件 · 🌐 联网搜索 · 📄 阅读文件 · 🐍 代码执行\n\n"
            "直接告诉我你需要什么，或点击下方建议快速开始："
        )

        # P3-2: 可点击建议按钮
        suggestions = [
            ("🔍 帮我找最近一周修改过的 Python 文件", "帮我找最近一周修改过的 Python 文件"),
            ("🧹 分析一下哪些文件可以清理", "分析一下哪些文件可以清理，给我清理建议"),
            ("🌐 搜索 Python 3.13 新特性", "搜索 Python 3.13 新特性"),
            ("📊 统计各类型文件占用空间", "帮我统计各类型文件分别占用多少空间"),
        ]
        accent = "#89b4fa" if self._is_dark else "#8839ef"
        btn_bg = "#313244" if self._is_dark else "#e6e9ef"
        btn_hover = "#45475a" if self._is_dark else "#dce0e8"
        for label, query in suggestions:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {btn_bg}; color: {accent};"
                f"  border: 1px solid {btn_hover}; border-radius: 8px;"
                f"  padding: 6px 12px; font-size: 9pt; text-align: left;"
                f"}}"
                f"QPushButton:hover {{ background: {btn_hover}; }}"
            )
            btn.clicked.connect(lambda _checked=False, q=query: self._trigger_suggestion(q))
            welcome._layout.addWidget(btn)

        self._chat_layout.insertWidget(self._chat_layout.count() - 1, welcome)

    def _trigger_suggestion(self, query: str):
        """P3-2: 点击建议直接发送"""
        self._msg_input.setPlainText(query)
        self._send_message()

    def _switch_session(self, session_id: str):
        """切换到指定会话 + P3-4: 同步重建工具注册表"""
        filepath = os.path.join(_SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(filepath):
            return

        # 保存当前会话
        if self._conversation and self._conversation.message_count > 0:
            try:
                self._conversation.save(_SESSIONS_DIR)
            except Exception:
                pass

        try:
            self._conversation = AiConversation.load(filepath)
            # 切换会话时按当前模型更新上下文窗口大小
            self._conversation.max_context_size = self._get_model_max_context()
            self._rebuild_tool_registry()  # P3-4: 切换会话时重建工具注册表
            self._current_streaming_bubble = None

            # 重建对话 UI（应用当前主题）
            self._clear_chat()
            bubbles = []
            for msg in self._conversation.get_messages():
                if msg.role == "system":
                    continue
                if msg.role == "user":
                    bubble = _ChatBubble("user", self._chat_widget)
                    bubble._apply_theme(self._is_dark)
                    bubble.set_text(msg.content or "")
                    self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
                    bubbles.append(bubble)
                elif msg.role == "assistant":
                    # 跳过空内容的消息（工具调用请求只有 tool_calls，无文本）
                    if not msg.content:
                        continue
                    bubble = _ChatBubble("ai", self._chat_widget)
                    bubble._apply_theme(self._is_dark)
                    bubble.set_text(msg.content)
                    self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
                    bubbles.append(bubble)
                elif msg.role == "tool":
                    pass

            # 强制完成布局后再调整一次大小
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            for b in bubbles:
                b._adjust_size()

            self._scroll_to_bottom()
            self._update_context_indicator()  # [MODULE-B]
            logger.info(f"切换到会话: {session_id}")

        except Exception as e:
            logger.error(f"加载会话失败: {e}")

    def _refresh_model_list(self):
        """刷新模型选择列表"""
        self._model_combo.clear()
        providers = self._model_cfg.list_providers()
        active_id = self._model_cfg.active_provider_id
        active = self._model_cfg.get_active()

        for p in providers:
            label = f"{p.name}: {p.model}" if p.model else f"{p.name}"
            self._model_combo.addItem(label, p.provider_id)

        # 选中当前激活的
        for i in range(self._model_combo.count()):
            if self._model_combo.itemData(i) == active_id:
                self._model_combo.setCurrentIndex(i)
                break

        self._model_combo.currentIndexChanged.connect(self._on_model_changed)

    def _refresh_sessions(self):
        """刷新会话列表"""
        self._session_list.clear()
        try:
            sessions = AiConversation.list_sessions(_SESSIONS_DIR)
            self._all_sessions = sessions  # P2-2: 缓存全部会话用于搜索过滤
            # 应用当前搜索关键词
            keyword = self._session_search.text().strip().lower() if hasattr(self, '_session_search') else ""
            for s in sessions:
                if keyword and keyword not in s.title.lower():
                    continue
                dt = datetime.fromtimestamp(s.updated_at).strftime("%m-%d %H:%M")
                item = QListWidgetItem(f"{s.title}\n  {dt} · {s.message_count} 条消息")
                item.setData(Qt.ItemDataRole.UserRole, s.session_id)
                item.setSizeHint(QSize(0, 48))
                self._session_list.addItem(item)

            # 无历史时隐藏整个对话历史区块
            has_sessions = len(self._session_list) > 0
            self._sessions_sep.setVisible(has_sessions)
            self._sessions_header_label.setVisible(has_sessions)
            self._session_search.setVisible(has_sessions)
            self._session_list.setVisible(has_sessions)
        except Exception as e:
            logger.warning(f"刷新会话列表失败: {e}")

    # ── P2-2: 会话搜索过滤 + 右键删除 ──

    def _filter_sessions(self, keyword: str):
        """根据搜索关键词过滤会话列表"""
        if not hasattr(self, '_all_sessions'):
            return
        self._session_list.clear()
        keyword_lower = keyword.strip().lower()
        for s in self._all_sessions:
            if keyword_lower and keyword_lower not in s.title.lower():
                continue
            dt = datetime.fromtimestamp(s.updated_at).strftime("%m-%d %H:%M")
            item = QListWidgetItem(f"{s.title}\n  {dt} · {s.message_count} 条消息")
            item.setData(Qt.ItemDataRole.UserRole, s.session_id)
            item.setSizeHint(QSize(0, 48))
            self._session_list.addItem(item)

    def _on_session_context_menu(self, pos):
        """会话列表右键菜单"""
        item = self._session_list.itemAt(pos)
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        session_title = item.text().split('\n')[0] if item.text() else "此会话"

        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(_theme_menu_qss(self._is_dark))
        export_action = menu.addAction(f"📥 导出「{session_title}」为 Markdown")
        menu.addSeparator()
        delete_action = menu.addAction(f"🗑 删除「{session_title}」")
        action = menu.exec(self._session_list.mapToGlobal(pos))
        if action == export_action:
            self._export_conversation(session_id)
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "删除会话", f"确定删除「{session_title}」吗？\n此操作不可撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._delete_session(session_id)

    def _delete_session(self, session_id: str):
        """删除指定会话及文件"""
        filepath = os.path.join(_SESSIONS_DIR, f"{session_id}.json")
        is_current = self._conversation and self._conversation.meta.session_id == session_id
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            # 如果删除的是当前会话，直接清空（不用 _new_conversation()，避免它 save() 把刚删的文件写回来）
            if is_current:
                self._conversation = AiConversation(
                    system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT.format(
                        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        working_directory=os.path.abspath("."),
                    ),
                    model=self.ai_layer.backend_model_name,
                    title="新对话",
                    max_context_size=self._get_model_max_context(),
                )
                self._current_streaming_bubble = None
                self._streaming_content_accumulated = False
                self._clear_chat()
                self._show_welcome()
            self._refresh_sessions()
            logger.info(f"已删除会话: {session_id}")
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            QMessageBox.warning(self, "删除失败", f"无法删除会话: {e}")

    def _export_conversation(self, session_id: str = None):
        """[C2] 导出会话为 Markdown"""
        if session_id and session_id != (self._conversation.meta.session_id if self._conversation else None):
            filepath = os.path.join(_SESSIONS_DIR, f"{session_id}.json")
            if not os.path.exists(filepath):
                return
            conv = AiConversation.load(filepath)
            conv.max_context_size = self._get_model_max_context()
        elif self._conversation:
            conv = self._conversation
        else:
            return

        title = conv.meta.title
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出对话", f"{title}.md", "Markdown (*.md)"
        )
        if not save_path:
            return

        lines = [f"# {title}", "", f"*模型: {conv.meta.model}*",
                 f"*时间: {datetime.fromtimestamp(conv.meta.updated_at).strftime('%Y-%m-%d %H:%M:%S')}*",
                 "", "---", ""]
        for msg in conv.get_messages():
            if msg.role == "system":
                continue
            if msg.role == "user":
                lines.append(f"**👤 你:** {msg.content or ''}")
            elif msg.role == "assistant":
                lines.append(f"**🤖 AI:** {msg.content or ''}")
            elif msg.role == "tool":
                lines.append(f"> 🔧 工具 `{msg.name or ''}` 返回结果")
            lines.append("")

        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"会话已导出: {save_path}")

    # ── 发送消息 ──

    def _send_message(self):
        """发送用户消息"""
        text = self._msg_input.toPlainText().strip()
        if not text:
            return

        if not self.ai_layer.enabled:
            QMessageBox.warning(self, "AI 未启用", "请先在设置中配置 AI 模型。")
            return

        # 清空输入
        self._msg_input.clear()

        # 添加用户气泡（应用当前主题）
        user_bubble = _ChatBubble("user", self._chat_widget)
        user_bubble._apply_theme(self._is_dark)
        user_bubble.set_text(text)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, user_bubble)

        # 添加 AI 加载气泡（应用当前主题）
        self._current_streaming_bubble = _ChatBubble("ai", self._chat_widget)
        self._current_streaming_bubble._apply_theme(self._is_dark)
        self._current_streaming_bubble.set_text("🤔 正在思考...")
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, self._current_streaming_bubble)
        self._scroll_to_bottom()

        # 更新 UI 状态
        self._send_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._disable_input(True)

        # 🧠 语义模式：先在后台检索语义相关文件，检索完再带着上下文开始对话
        semantic_chip = self._tool_checks.get("semantic")
        self._pending_user_text = text
        if semantic_chip and semantic_chip.isChecked():
            self._current_streaming_bubble.set_text("🧠 正在检索语义相关文件...")
            self._semantic_worker = _SemanticWorker(text)
            self._semantic_worker.done.connect(self._on_semantic_done)
            self._semantic_worker.error.connect(self._on_semantic_error)
            self._semantic_worker.start()
            return

        self._begin_chat()

    def _on_semantic_done(self, files):
        """语义检索完成：相关文件注入上下文，正式启动对话"""
        self._pending_semantic_sources = []
        if files:
            self._current_streaming_bubble.set_text(
                f"🧠 找到 {len(files)} 个语义相关文件，正在思考..."
            )
            # P1-02: 编号与引用 chip 一一对应（注入 registry 后 search_content 接续编号）
            cite_lines = [
                f"- [来源 {i}] {f['file_name']}（{f['file_path']}，相似度 {f['score']:.2f}）"
                for i, f in enumerate(files, 1)
            ]
            note = (
                "\n\n[语义检索结果] 以下是与用户问题语义最相关的本地文件，"
                "回答时请在对应结论后标注 [来源 N]（N 为下方来源编号）；"
                "需要内容细节请用 read_file 工具读取：\n"
                + "\n".join(cite_lines)
            )
            self._pending_semantic_sources = [
                {
                    "file_id": f.get("file_id"),
                    "file_name": f.get("file_name", ""),
                    "file_path": f.get("file_path", ""),
                    "snippet": None,
                }
                for f in files
            ]
        else:
            note = (
                "\n\n[语义检索结果] 未检索到语义相关文件"
                "（可能尚未在 AI 设置中生成向量索引）。"
            )
        self._begin_chat(note)

    def _on_semantic_error(self, msg):
        """语义检索失败：忽略上下文直接对话，不中断用户"""
        logger.warning(f"语义检索失败，跳过注入: {msg}")
        self._begin_chat("")

    def _begin_chat(self, semantic_note: str = ""):
        """启动 AI 对话（原 _send_message 后半段，semantic_note 为注入的检索上下文）"""
        # 确保工具注册表已初始化
        if self._tool_registry is None:
            self._tool_registry = self.ai_layer.tool_registry

        # P1-02: 新一轮提问前清空来源收集，防止跨问题串引用
        self._current_citations = []
        self._pending_semantic_sources = getattr(self, "_pending_semantic_sources", [])
        try:
            self._tool_registry.clear_sources()
        except AttributeError:
            pass
        # P1-02: 注入语义检索命中的来源（在工具调用前，保证 [来源 N] 编号对齐）
        if self._pending_semantic_sources:
            try:
                self._tool_registry.add_sources(self._pending_semantic_sources)
            except AttributeError:
                pass

        # 添加用户消息到对话（检索上下文只注入模型输入，用户气泡保持原文）
        if self._conversation is None:
            self._new_conversation()
        self._conversation.add_user_message(self._pending_user_text + semantic_note)
        self._update_context_indicator()  # [MODULE-B]

        # 自动生成标题
        if self._conversation.message_count <= 2:
            title_src = self._pending_user_text
            self._conversation.update_title(
                title_src[:25] + ("…" if len(title_src) > 25 else "")
            )

        # 启动后台线程
        self._streaming_content_accumulated = False
        self._accumulated_response = ""
        self._start_progress()  # P2-4: 启动超时进度提示
        self._worker = _ChatWorker(
            self.ai_layer, self._conversation, self._tool_registry, self
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_end.connect(self._on_tool_end)
        self._worker.tool_error.connect(self._on_tool_error)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop_generation(self):
        """停止当前生成 —— P1-2: 使用取消标志替代 terminate()"""
        self._stop_progress()  # P2-4
        # 语义检索阶段停止：断开信号避免迟到回调启动对话
        sw = getattr(self, "_semantic_worker", None)
        if sw and sw.isRunning():
            try:
                sw.done.disconnect()
                sw.error.disconnect()
            except TypeError:
                pass
            sw.wait(10000)
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            # 等待 worker 优雅退出（最多等连接超时时间）
            self._worker.wait(30000)
        self._on_done("")

    def _on_chunk(self, text: str):
        """收到流式文本 —— 合帧渲染 + P2-4: 进度提示"""
        if self._current_streaming_bubble:
            # 每轮工具循环后的第一个文本块替换占位文字，后续追加
            if not self._streaming_content_accumulated:
                self._current_streaming_bubble.set_text(text, streaming=True)
                self._streaming_content_accumulated = True
            else:
                self._current_streaming_bubble.append_text(text)
            self._progress_seconds = 0  # P2-4: 收到数据则重置计时
            self._smart_scroll()

    # ── P2-4: 超时进度提示 ──

    def _start_progress(self):
        """开始显示进度计时"""
        self._progress_seconds = 0
        self._progress_label.setVisible(True)
        self._progress_label.setText("⏳ 等待响应...")
        self._progress_timer.start(1000)

    def _update_progress(self):
        """每秒更新进度提示"""
        self._progress_seconds += 1
        if self._progress_seconds >= 10:
            self._progress_label.setText(
                f"⏳ 响应较慢... 已等待 {self._progress_seconds}s，请耐心等待"
            )
        elif self._progress_seconds >= 5:
            self._progress_label.setText(f"⏳ 等待中... ({self._progress_seconds}s)")
        else:
            self._progress_label.setText(f"⏳ 等待响应... ({self._progress_seconds}s)")

    def _stop_progress(self):
        """停止进度计时"""
        self._progress_timer.stop()
        # 5s 以内完成的不需要闪一下
        if self._progress_seconds >= 3:
            self._progress_label.setText(
                f"✓ 完成 (耗时 {self._progress_seconds}s)"
            )
            QTimer.singleShot(2000, lambda: self._progress_label.setVisible(False))
        else:
            self._progress_label.setVisible(False)

    def _on_tool_start(self, tool_name: str):
        """工具开始执行 —— 仅在第一次时设置提示文本"""
        if self._current_streaming_bubble:
            current = self._current_streaming_bubble._text_browser.toPlainText()
            if not current.strip() or current.strip() == "🤔 正在思考...":
                icons = {"search_files": "📂", "search_content": "📝",
                         "search_web": "🌐", "read_file": "📄"}
                icon = icons.get(tool_name, "🔧")
                self._current_streaming_bubble.set_text(
                    f"{icon} 正在调用工具: **{tool_name}**...\n\n请稍候..."
                )

    def _on_tool_end(self, tool_name: str, result_summary: str, tc_args: dict = None, full_result: str = ""):
        """工具执行完毕 —— 追加卡片，search_files/read_file/search_web 附带完整内容查看"""
        # P1-1: 工具执行后重置流式标记，下一轮首块文本会替换占位文字
        self._streaming_content_accumulated = False
        # P1-02: 同步收集本轮工具命中的文件证据（回答完成后渲染引用 chip）
        if self._tool_registry is not None:
            try:
                self._current_citations = self._tool_registry.get_sources()
            except AttributeError:
                pass
        if self._current_streaming_bubble:
            # 统计文件数量（从摘要中解析）
            action_text = None
            action_callback = None
            if tool_name == "search_files":
                m = re.search(r'找到 (\d+) 个文件', result_summary)
                if m and tc_args:
                    count = int(m.group(1))
                    action_text = f"📋 查看全部 {count} 个文件 →"
                    mapped = {}
                    if tc_args.get("query"):
                        mapped["name"] = tc_args["query"]
                    for k in ("file_type", "start_date", "end_date", "min_size", "max_size"):
                        if tc_args.get(k) is not None:
                            mapped[k] = tc_args[k]
                    action_callback = lambda _checked=False, p=mapped: self.navigate_to_search.emit(p)

            # P3-1: 传递完整结果供查看
            self._current_streaming_bubble.add_tool_card(
                tool_name, result_summary,
                action_text=action_text, action_callback=action_callback,
                full_result=full_result,
            )
        self._scroll_to_bottom()

    def _on_tool_error(self, tool_name: str, err_msg: str, tc_args: dict = None):
        """P3-5: 工具执行异常 —— 红色错误卡片，不中断对话"""
        self._streaming_content_accumulated = False
        if self._current_streaming_bubble:
            self._current_streaming_bubble.add_tool_card(
                tool_name, f"执行失败: {err_msg}",
                full_result=f"工具 {tool_name} 执行时发生错误:\n\n{err_msg}\n\n参数: {tc_args}",
                is_error=True,
            )
        self._scroll_to_bottom()

    def _on_done(self, final_text: str):
        """对话完成 + P3-3: 添加重新生成按钮"""
        self._worker = None
        self._streaming_content_accumulated = False
        self._stop_progress()  # P2-4: 停止进度提示
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._disable_input(False)
        self._msg_input.setFocus()

        # 确保最终文本显示（如果有），否则保留工具卡片不清理
        if self._current_streaming_bubble:
            if final_text and final_text.strip():
                self._current_streaming_bubble.set_text(final_text)
            else:
                current = self._current_streaming_bubble._text_browser.toPlainText()
                if not current.strip():
                    self._current_streaming_bubble.set_text("完成。")
                self._current_streaming_bubble._adjust_size()
            # P3-3: 成功完成时添加重新生成按钮
            self._current_streaming_bubble.add_regenerate_button(self._regenerate_last)
            # P1-02 引用溯源: 回答完成后渲染"📎 来源"chip 行（正文 [来源 N] 锚点同源）
            if self._tool_registry is not None:
                try:
                    self._current_citations = self._tool_registry.get_sources()
                except AttributeError:
                    pass
            if self._current_citations:
                self._current_streaming_bubble.set_citations(
                    self._current_citations, self._open_citation
                )
            elif re.search(r'\[来源\s*\d+\]', final_text or ''):
                # P1-02 无证据兜底: 正文标了 [来源 N] 但没有可追溯证据 → 提示人工核实
                self._current_streaming_bubble.show_no_evidence_hint()

    def _open_citation(self, cite: dict):
        """P1-02: 点击引用（chip 或正文锚点）→ 请求主窗口打开来源文件"""
        path = cite.get("file_path", "")
        if path:
            self.open_file_request.emit(path, cite.get("file_id"))

        self._update_context_indicator()  # [MODULE-B]
        self._refresh_sessions()

        # 自动保存会话
        if self._conversation and self._conversation.message_count > 0:
            try:
                self._conversation.save(_SESSIONS_DIR)
            except Exception:
                pass

        self._scroll_to_bottom()

    def _on_error(self, err: str):
        """对话出错 —— P1-3: 添加重试入口 + P2: 用户友好提示"""
        self._stop_progress()  # P2-4
        friendly = _friendly_error(err)
        if self._current_streaming_bubble:
            self._current_streaming_bubble.set_text(friendly)
            self._current_streaming_bubble.add_retry_button(self._retry_last_message)
        self._worker = None
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._disable_input(False)
        self._msg_input.setFocus()

    def _retry_last_message(self):
        """P1-3: 重试最后一次失败的请求 —— 用户消息已在对话中，只需移除错误气泡并重发"""
        if self._current_streaming_bubble:
            self._chat_layout.removeWidget(self._current_streaming_bubble)
            self._current_streaming_bubble.deleteLater()
            self._current_streaming_bubble = None

        self._restart_worker()

    def _regenerate_last(self):
        """P3-3: 重新生成最后一次回答 —— 移除 AI 回答，从对话中移除最后一条 assistant 消息，重新发送"""
        if self._current_streaming_bubble:
            self._chat_layout.removeWidget(self._current_streaming_bubble)
            self._current_streaming_bubble.deleteLater()
            self._current_streaming_bubble = None

        # 从对话中移除最后一条 assistant 消息
        if self._conversation:
            msgs = self._conversation.get_messages()
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].role == "assistant":
                    self._conversation._messages.pop(i)
                    break

        self._restart_worker()

    def _restart_worker(self):
        """统一起动/重启 worker"""
        # P1-02: 重试/重新生成也是新一轮，清空来源收集
        self._current_citations = []
        if self._tool_registry is not None:
            try:
                self._tool_registry.clear_sources()
            except AttributeError:
                pass

        # 创建新流式气泡
        self._current_streaming_bubble = _ChatBubble("ai", self._chat_widget)
        self._current_streaming_bubble._apply_theme(self._is_dark)
        self._current_streaming_bubble.set_text("🤔 正在思考...")
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, self._current_streaming_bubble)
        self._scroll_to_bottom()

        # 重置流式状态
        self._streaming_content_accumulated = False
        self._send_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._disable_input(True)

        # 确保工具注册表已初始化
        if self._tool_registry is None:
            self._rebuild_tool_registry()

        # 启动 worker
        self._start_progress()
        self._worker = _ChatWorker(
            self.ai_layer, self._conversation, self._tool_registry, self
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_end.connect(self._on_tool_end)
        self._worker.tool_error.connect(self._on_tool_error)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    # ── 工具开关 ──

    def _on_tool_toggle_changed(self):
        """工具胶囊点击：刷新样式并重建注册表"""
        self._refresh_tool_chips()
        self._rebuild_tool_registry()

    def _rebuild_tool_registry(self):
        """根据开关状态重新构建工具注册表"""
        from core.ai_tools import (
            ToolRegistry, create_search_files_tool, create_search_web_tool,
            create_read_file_tool, create_search_content_tool,
        )

        registry = ToolRegistry()

        if self._tool_checks.get("search_files", QCheckBox()).isChecked():
            registry.register(create_search_files_tool(db_manager=self.ai_layer.db_manager))
        if self._tool_checks.get("search_content", QCheckBox()).isChecked():
            registry.register(create_search_content_tool(db_manager=self.ai_layer.db_manager))
        if self._tool_checks.get("search_web", QCheckBox()).isChecked():
            registry.register(create_search_web_tool())
        if self._tool_checks.get("read_file", QCheckBox()).isChecked():
            registry.register(create_read_file_tool(db_manager=self.ai_layer.db_manager))

        self._tool_registry = registry

    # ── 模型切换 ──

    def _on_model_changed(self, index: int):
        """模型选择变化"""
        if index < 0:
            return
        provider_id = self._model_combo.itemData(index)
        if provider_id:
            self._model_cfg.set_active(provider_id)
            self.ai_layer.reload_backend()
            # 更新当前会话的上下文窗口大小
            if self._conversation:
                self._conversation.max_context_size = self._get_model_max_context()
                self._update_context_indicator()
            logger.info(f"AI 模型切换到: {provider_id}")

    # ── 侧栏事件 ──

    def _on_session_clicked(self, index):
        """点击会话列表项"""
        item = self._session_list.item(index.row())
        if item:
            session_id = item.data(Qt.ItemDataRole.UserRole)
            self._switch_session(session_id)

    def _on_session_double_clicked(self, index):
        """[C1] 双击会话标题 → 内联重命名"""
        item = self._session_list.item(index.row())
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        old_title = item.text().split('\n')[0] if item.text() else "新对话"

        from PyQt6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(
            self, "重命名会话", "新标题:", text=old_title
        )
        if ok and new_title.strip() and new_title.strip() != old_title:
            filepath = os.path.join(_SESSIONS_DIR, f"{session_id}.json")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["meta"]["title"] = new_title.strip()
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                if self._conversation and self._conversation.meta.session_id == session_id:
                    self._conversation.meta.title = new_title.strip()
                self._refresh_sessions()
            except Exception as e:
                QMessageBox.warning(self, "重命名失败", str(e))

    # ── 辅助方法 ──

    def _disable_input(self, disabled: bool):
        self._msg_input.setEnabled(not disabled)
        self._model_combo.setEnabled(not disabled)

    def _auto_resize_input(self):
        """[D2] 输入框随内容自动扩展高度"""
        doc_h = self._msg_input.document().size().height()
        new_h = min(max(int(doc_h + 10), 56), 150)
        if self._msg_input.height() != new_h:
            self._msg_input.setFixedHeight(new_h)

    def _get_model_max_context(self) -> int:
        """[MODULE-B] 从当前模型名获取上下文窗口大小"""
        return AIModelConfigManager.get_model_context_limit(
            self.ai_layer.backend_model_name
        )

    def _update_context_indicator(self):
        """[MODULE-B] 更新上下文使用率指示器（圆环，悬浮显示具体用量）"""
        track = "#45475a" if self._is_dark else "#bcc0cc"
        if not self._conversation:
            self._ctx_ring.set_usage(0, "#a6e3a1", track)
            tip = "上下文占用 --"
        else:
            try:
                size = self._conversation.estimate_context_size()
                max_size = self._conversation.max_context_size
                pct = min(int(size / max_size * 100), 100)
                tip = f"上下文占用 {pct}%（{size//1000}k / {max_size//1000}k）"
                if pct > 80:
                    color = "#f38ba8"
                elif pct > 50:
                    color = "#f9e2af"
                else:
                    color = "#a6e3a1"
                self._ctx_ring.set_usage(pct, color, track)
            except Exception:
                tip = "上下文占用 --"
        self._ctx_ring.setToolTip(tip)

    def _scroll_to_bottom(self):
        QTimer.singleShot(30, lambda: self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        ))

    def _on_scroll_moved(self, value: int):
        """用户滚动时更新跟随意图：滚离底部暂停跟随，滚回底部恢复"""
        sb = self._scroll_area.verticalScrollBar()
        self._follow_bottom = value >= sb.maximum() - 60

    def _smart_scroll(self):
        """流式期间仅在用户本就位于底部时跟随滚动，不打断向上回看"""
        if getattr(self, "_follow_bottom", True):
            self._scroll_to_bottom()

    # ── 主题 ──

    def _apply_theme(self):
        is_dark = self._is_dark
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        card_bg = "#252538" if is_dark else "#e6e9ef"
        border = "#45475a" if is_dark else "#bcc0cc"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        accent = "#89b4fa" if is_dark else "#8839ef"
        accent2 = "#cba6f7" if is_dark else "#8839ef"
        # 会话列表胶囊条目的选中/悬浮淡色底（主流 AI 风格）
        sel_tint = "rgba(137, 180, 250, 0.18)" if is_dark else "rgba(136, 57, 239, 0.12)"
        hover_tint = "rgba(137, 180, 250, 0.10)" if is_dark else "rgba(136, 57, 239, 0.06)"

        self.setStyleSheet(f"""
            AiChatPage {{
                background-color: {bg};
            }}
            QWidget#aiChatTopBar {{
                background-color: {card_bg};
                border-bottom: 1px solid {border};
            }}
            QPushButton#aiChatBackBtn {{
                background: transparent; color: {accent};
                border: none; font-size: 11pt;
            }}
            QPushButton#aiChatBackBtn:hover {{ color: {accent2}; }}
            QPushButton#aiChatNewBtn {{
                background: {border}; color: {text};
                border: none; border-radius: 6px; padding: 4px 12px; font-size: 10pt;
            }}
            QPushButton#aiChatNewBtn:hover {{ background: {accent}; color: #1e1e2e; }}
            QComboBox {{
                background: {bg}; color: {text};
                border: 1px solid {border}; border-radius: 6px; padding: 4px 10px;
            }}
            QWidget#aiChatSidePanel {{
                background-color: {card_bg};
                border-left: 1px solid {border};
            }}
            QFrame#aiSideSep {{
                background: {border}; max-height: 1px;
            }}
            QCheckBox {{
                color: {text}; font-size: 10pt; spacing: 6px;
                background: transparent; border: none;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 2px solid {border}; border-radius: 3px;
                background-color: {bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent}; border-color: {accent};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {bg}; border-color: {border};
            }}
            QListWidget#aiSessionList {{
                background: transparent; color: {text}; border: none;
                font-size: 10pt; outline: none;
            }}
            QListWidget#aiSessionList::item {{
                background: transparent; border: none; border-radius: 10px;
                margin: 1px 6px; padding: 7px 10px;
            }}
            QListWidget#aiSessionList QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 4px 2px; border: none;
            }}
            QListWidget#aiSessionList QScrollBar::handle:vertical {{
                background: {border}; border-radius: 3px; min-height: 30px;
            }}
            QListWidget#aiSessionList QScrollBar::handle:vertical:hover {{
                background: {text};
            }}
            QListWidget#aiSessionList QScrollBar::add-line:vertical,
            QListWidget#aiSessionList QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QListWidget#aiSessionList::item:selected {{
                background: {sel_tint}; color: {text};
            }}
            QListWidget#aiSessionList::item:hover {{ background: {hover_tint}; }}
            QLineEdit#aiSessionSearch {{
                background: {bg}; color: {text};
                border: 1px solid {border}; border-radius: 6px;
                padding: 4px 10px; font-size: 10pt;
            }}
            QLineEdit#aiSessionSearch:focus {{ border: 1px solid {accent}; }}
            QFrame#aiChatInputBar {{
                background-color: {card_bg};
                border-top: 1px solid {border};
            }}
            QTextEdit#aiChatMsgInput {{
                background-color: {bg}; color: {text};
                border: 1px solid {border}; border-radius: 8px;
                padding: 8px 14px; font-size: 11pt;
            }}
            QTextEdit#aiChatMsgInput:focus {{ border: 1px solid {accent}; }}
            QPushButton#aiChatSendBtn {{
                background: {accent}; color: #1e1e2e;
                border: none; border-radius: 8px;
                font-weight: bold; font-size: 12pt;
            }}
            QPushButton#aiChatSendBtn:hover {{ background: {accent2}; }}
            QPushButton#aiChatSendBtn:disabled {{ background: {border}; color: #6c7086; }}
            QPushButton#aiChatStopBtn {{
                background: #f38ba8; color: #1e1e2e;
                border: none; border-radius: 8px;
                font-weight: bold; font-size: 10pt;
            }}
            QPushButton#aiChatStopBtn:hover {{ background: #eba0ac; }}
            QScrollArea#aiChatScroll {{
                background-color: {bg}; border: none;
            }}
        """)

        # 上下文指示器跟随主题（圆环轨道色）
        if getattr(self, "_ctx_ring", None):
            self._update_context_indicator()

        # 工具胶囊 chips 样式（激活=主题色描边+淡底，未激活=灰色描边）
        if getattr(self, "_tool_checks", None):
            self._refresh_tool_chips()

    def _refresh_tool_chips(self):
        """按选中状态刷新工具胶囊样式（主题切换 / 点击后调用）"""
        is_dark = self._is_dark
        accent = "#89b4fa" if is_dark else "#8839ef"
        border = "#45475a" if is_dark else "#bcc0cc"
        muted = "#a6adc8" if is_dark else "#6c6f85"
        sel_tint = "rgba(137, 180, 250, 0.18)" if is_dark else "rgba(136, 57, 239, 0.12)"
        for chip in self._tool_checks.values():
            if chip.isChecked():
                chip.setStyleSheet(
                    f"QPushButton {{ background: {sel_tint}; color: {accent};"
                    f" border: 1px solid {accent}; border-radius: 13px;"
                    f" padding: 2px 12px; font-size: 9pt; }}"
                )
            else:
                chip.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {muted};"
                    f" border: 1px solid {border}; border-radius: 13px;"
                    f" padding: 2px 12px; font-size: 9pt; }}"
                    f"QPushButton:hover {{ border-color: {accent}; }}"
                )

    def apply_theme(self, theme_name: str):
        self._theme = theme_name
        self._is_dark = theme_name == "dark"
        self._apply_theme()
        # 更新已有聊天气泡的主题
        self._refresh_bubbles_theme()

    def _refresh_bubbles_theme(self):
        """遍历已存在的聊天气泡，重新应用主题"""
        for i in range(self._chat_layout.count()):
            item = self._chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _ChatBubble):
                item.widget()._apply_theme(self._is_dark)
                # 重新渲染文本以更新代码块样式
                text = item.widget()._text_browser.toPlainText()
                if text:
                    item.widget().set_text(text)

    def set_theme(self, theme: str):
        self.apply_theme(theme)

    # ── 公开接口 ──

    def focus_search(self):
        self._msg_input.setFocus()

    def refresh_data(self):
        self._refresh_model_list()
        self._refresh_sessions()
        if self._conversation is None:
            self._new_conversation()
