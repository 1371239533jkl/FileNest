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

import os
import re
import html
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTextBrowser, QSizePolicy,
    QListWidget, QListWidgetItem, QSplitter, QComboBox,
    QCheckBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QUrl
from PyQt6.QtGui import QFont, QTextCursor

from core.ai_layer import AILayer
from core.ai_chat import AiConversation, SessionMeta
from core.ai_tools import ToolRegistry
from core.ai_model_config import AIModelConfigManager
from utils.logger import logger

# ── 会话存储目录 ──
_SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sessions"
)


# ══════════════════════════════════════════════════════════════════════════════
# 后台线程
# ══════════════════════════════════════════════════════════════════════════════

class _ChatWorker(QThread):
    """AI 对话后台线程 —— 支持工具调用循环 + 状态通知"""
    chunk = pyqtSignal(str)            # 流式文本增量
    tool_start = pyqtSignal(str)       # 工具调用开始（工具名）
    tool_end = pyqtSignal(str, str, dict)  # 工具调用结束（工具名, 结果摘要, 参数）
    done = pyqtSignal(str)             # 最终结果
    error = pyqtSignal(str)            # 错误信息

    def __init__(self, ai_layer: AILayer, conversation: AiConversation,
                 tool_registry: ToolRegistry, parent=None):
        super().__init__(parent)
        self._layer = ai_layer
        self._conv = conversation
        self._registry = tool_registry

    def run(self):
        try:
            from core.ai_chat import run_tool_loop, MAX_TOOL_LOOP_ROUNDS

            tool_schemas = self._registry.get_tool_schemas() if self._registry else []
            backend = self._layer._backend

            for round_idx in range(MAX_TOOL_LOOP_ROUNDS):
                result = backend.chat(
                    messages=self._conv.get_api_messages(),
                    max_tokens=1024,
                    temperature=0.3,
                    tools=tool_schemas if tool_schemas else None,
                )

                tool_calls = result.tool_calls

                if not tool_calls:
                    # 最终回复
                    self._conv.add_assistant_message(result.content)
                    self.chunk.emit(result.content)
                    self.done.emit(result.content)
                    return

                # 记录工具调用请求
                self._conv.add_assistant_message(
                    content=result.content or "",
                    tool_calls=tool_calls,
                )

                # 执行每个工具
                for tc in tool_calls:
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
                    tool_result = self._registry.execute(tc_name, tc_args)
                    result_summary = tool_result[:200] + ("..." if len(tool_result) > 200 else "")
                    self.tool_end.emit(tc_name, result_summary, tc_args)

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
        self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setFrameShape(QFrame.Shape.NoFrame)
        self._text_browser.document().setDocumentMargin(0)
        self._layout.addWidget(self._text_browser)

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

    def set_text(self, text: str):
        """设置文本内容（支持 Markdown 代码块渲染）"""
        html_text = self._render_markdown(text)
        self._text_browser.setHtml(html_text)
        self._adjust_size()

    def append_text(self, text: str):
        """追加流式文本"""
        current = self._text_browser.toPlainText()
        new_text = current + text
        html_text = self._render_markdown(new_text)
        self._text_browser.setHtml(html_text)
        # 滚动到底部
        cursor = self._text_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text_browser.setTextCursor(cursor)
        self._adjust_size()

    def add_tool_card(self, tool_name: str, result_summary: str,
                      action_text: str = None, action_callback=None):
        """添加工具执行结果卡片，可选附带操作按钮"""
        card = QFrame()
        card.setObjectName("toolCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)

        # 工具名称标题
        icons = {
            "search_files": "📂",
            "search_web": "🌐",
            "read_file": "📄",
            "execute_python": "🐍",
        }
        icon = icons.get(tool_name, "🔧")
        header = QLabel(f"{icon} {tool_name}")
        header.setStyleSheet(
            f"font-weight: bold; font-size: 10pt; color: {'#89b4fa' if self._is_dark else '#8839ef'};"
            f" border: none; background: transparent;"
        )
        card_layout.addWidget(header)

        # 结果摘要
        summary_label = QLabel(result_summary)
        summary_label.setWordWrap(True)
        card_layout.addWidget(summary_label)

        # 可选操作按钮（如 "查看全部 →"）
        action_btn = None
        if action_text and action_callback:
            action_btn = QPushButton(action_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.clicked.connect(action_callback)
            card_layout.addWidget(action_btn)

        tool_bg = "#252538" if self._is_dark else "#dce0e8"
        tool_border = "#45475a" if self._is_dark else "#bcc0cc"
        tool_text = "#a6adc8" if self._is_dark else "#6c6f85"
        accent = "#89b4fa" if self._is_dark else "#8839ef"
        summary_label.setStyleSheet(
            f"font-size: 9pt; color: {tool_text}; border: none; background: transparent;"
        )
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
            f"QFrame#toolCard {{"
            f"  background: {tool_bg}; border: 1px solid {tool_border};"
            f"  border-radius: 8px;"
            f"}}"
        )
        self._layout.addWidget(card)
        self._tool_cards.append((card, header, summary_label))
        self._adjust_size()

    def _render_markdown(self, text: str) -> str:
        """将文本转为 HTML（代码块用 Pygments 高亮，其余用基本 Markdown）"""
        escaped = html.escape(text)

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
                    style="monokai" if self._is_dark else "default",
                    noclasses=True,
                    nowrap=False,
                )
                highlighted = highlight(code, lexer, formatter)
                return (
                    f'<div style="background:#272822;border-radius:8px;padding:12px;'
                    f'margin:8px 0;overflow-x:auto;font-size:9pt;">'
                    f'{highlighted}</div>'
                )
            except Exception:
                return f'<pre style="background:#313244;border-radius:8px;padding:12px;margin:8px 0;font-size:9pt;overflow-x:auto;"><code>{html.escape(code)}</code></pre>'

        result = re.sub(r'```(\w+)?\n(.*?)```', _highlight_code, escaped, flags=re.DOTALL)

        # 处理行内代码 `code`
        result = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#313244;color:#fab387;padding:2px 6px;border-radius:4px;font-size:9pt;">\1</code>',
            result
        )

        # 处理粗体 **text**
        result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)

        # 处理链接 [text](url)
        result = re.sub(
            r'\[(.+?)\]\((https?://[^\s)]+)\)',
            r'<a href="\2" style="color:#89b4fa;">\1</a>',
            result
        )

        # 换行
        result = result.replace("\n", "<br>")

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
        doc.setTextWidth(vp_w)
        doc_height = doc.size().height()
        # 保证至少 20px 高度
        self._text_browser.setFixedHeight(max(int(doc_height + 10), 20))
        # 强制内容框架也更新
        self._content_frame.updateGeometry()
        self._content_frame.setMaximumWidth(700)

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


# ══════════════════════════════════════════════════════════════════════════════
# 主页面
# ══════════════════════════════════════════════════════════════════════════════

class AiChatPage(QWidget):
    """AI 全能助手主页面"""

    go_back = pyqtSignal()
    show_results = pyqtSignal(dict)  # 兼容旧接口
    navigate_to_search = pyqtSignal(dict)  # 跳转到搜索 Tab 并填入参数

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
        self._scroll_area.setObjectName("aiChatScroll")

        self._chat_widget = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setContentsMargins(0, 12, 0, 12)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()

        self._scroll_area.setWidget(self._chat_widget)
        chat_layout.addWidget(self._scroll_area)

        # 欢迎提示
        self._show_welcome()

    def _init_side_panel(self):
        self._side_panel = QWidget()
        self._side_panel.setObjectName("aiChatSidePanel")
        self._side_panel.setFixedWidth(220)
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(12)

        # 工具开关
        tools_header = QLabel("⚡ 能力开关")
        tools_header.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; background: transparent;")
        side_layout.addWidget(tools_header)

        self._tool_checks = {}
        tools_info = [
            ("search_files", "📂 文件搜索", True),
            ("search_web", "🌐 联网搜索", True),
            ("read_file", "📄 读取文件", True),
            ("execute_python", "🐍 代码执行", False),
        ]
        for tool_id, label, default in tools_info:
            cb = QCheckBox(label)
            cb.setObjectName(f"toolCheck_{tool_id}")
            cb.setChecked(default)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.stateChanged.connect(self._on_tool_toggle_changed)
            self._tool_checks[tool_id] = cb
            side_layout.addWidget(cb)

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

        self._session_list = QListWidget()
        self._session_list.setObjectName("aiSessionList")
        self._session_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._session_list.clicked.connect(self._on_session_clicked)
        self._session_list.setMaximumHeight(300)
        side_layout.addWidget(self._session_list)

        side_layout.addStretch()

    def _init_input_bar(self):
        self._input_bar = QFrame()
        self._input_bar.setObjectName("aiChatInputBar")
        input_layout = QHBoxLayout(self._input_bar)
        input_layout.setContentsMargins(16, 10, 16, 10)
        input_layout.setSpacing(10)

        # 输入框（支持多行）
        from PyQt6.QtWidgets import QTextEdit
        self._msg_input = QTextEdit()
        self._msg_input.setObjectName("aiChatMsgInput")
        self._msg_input.setPlaceholderText("输入你的问题，如：帮我找代码中的数据库连接..."
                                            "\n支持 Shift+Enter 换行，Enter 发送")
        self._msg_input.setFixedHeight(56)
        self._msg_input.setAcceptRichText(False)
        self._msg_input.setTabChangesFocus(True)
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

        # 快捷键：Enter 发送, Shift+Enter 换行
        # 使用 keyPressEvent 重载处理

    def keyPressEvent(self, event):
        """全局快捷键处理"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter 换行 - 默认行为
                super().keyPressEvent(event)
            else:
                # Enter 发送（仅当输入框有焦点时）
                if self._msg_input.hasFocus():
                    self._send_message()
                else:
                    super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    # ── 对话管理 ──

    def _new_conversation(self):
        """创建新对话"""
        # 保存当前对话（如有）
        if self._conversation and self._conversation.message_count > 0:
            try:
                self._conversation.save(_SESSIONS_DIR)
            except Exception:
                pass

        from core.ai_prompts import GENERAL_ASSISTANT_SYSTEM_PROMPT
        from datetime import datetime

        self._conversation = AiConversation(
            system_prompt=GENERAL_ASSISTANT_SYSTEM_PROMPT.format(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                working_directory=os.path.abspath("."),
            ),
            model=self.ai_layer.backend_model_name,
            title="新对话",
        )
        self._current_streaming_bubble = None

        # 清空消息区，显示欢迎
        self._clear_chat()
        self._show_welcome()
        self._refresh_sessions()

    def _clear_chat(self):
        """清空对话区"""
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_welcome(self):
        """显示欢迎消息"""
        welcome = _ChatBubble("ai", self._chat_widget)
        welcome._apply_theme(self._is_dark)
        welcome.set_text(
            "你好！我是 **AI 全能助手**。\n\n"
            "我可以帮你：\n"
            "📂 **搜索文件**：找代码、文档、图片，任何类型\n"
            "🌐 **联网搜索**：获取最新信息和技术文档\n"
            "📄 **阅读文件**：分析文件内容，对比代码\n"
            "🐍 **代码执行**：运行简单计算和数据处理\n\n"
            "直接告诉我你需要什么，我会自动选择合适的工具。"
        )
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, welcome)

    def _switch_session(self, session_id: str):
        """切换到指定会话"""
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
            for s in sessions:
                dt = datetime.fromtimestamp(s.updated_at).strftime("%m-%d %H:%M")
                item = QListWidgetItem(f"{s.title}\n  {dt} · {s.message_count} 条消息")
                item.setData(Qt.ItemDataRole.UserRole, s.session_id)
                item.setSizeHint(QSize(0, 48))
                self._session_list.addItem(item)

            # 无历史时隐藏整个对话历史区块
            has_sessions = len(self._session_list) > 0
            self._sessions_sep.setVisible(has_sessions)
            self._sessions_header_label.setVisible(has_sessions)
            self._session_list.setVisible(has_sessions)
        except Exception as e:
            logger.warning(f"刷新会话列表失败: {e}")

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

        # 确保工具注册表已初始化
        if self._tool_registry is None:
            self._tool_registry = self.ai_layer.tool_registry

        # 添加用户消息到对话
        if self._conversation is None:
            self._new_conversation()
        self._conversation.add_user_message(text)

        # 自动生成标题
        if self._conversation.message_count <= 2:
            self._conversation.update_title(
                text[:25] + ("…" if len(text) > 25 else "")
            )

        # 启动后台线程
        self._accumulated_response = ""
        self._worker = _ChatWorker(
            self.ai_layer, self._conversation, self._tool_registry, self
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_end.connect(self._on_tool_end)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop_generation(self):
        """停止当前生成"""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        self._on_done("")

    def _on_chunk(self, text: str):
        """收到流式文本"""
        if self._current_streaming_bubble:
            self._current_streaming_bubble.append_text(text)
            self._scroll_to_bottom()

    def _on_tool_start(self, tool_name: str):
        """工具开始执行 —— 仅在第一次时设置提示文本"""
        if self._current_streaming_bubble:
            current = self._current_streaming_bubble._text_browser.toPlainText()
            if not current.strip() or current.strip() == "🤔 正在思考...":
                icons = {"search_files": "📂", "search_web": "🌐", "read_file": "📄", "execute_python": "🐍"}
                icon = icons.get(tool_name, "🔧")
                self._current_streaming_bubble.set_text(
                    f"{icon} 正在调用工具: **{tool_name}**...\n\n请稍候..."
                )

    def _on_tool_end(self, tool_name: str, result_summary: str, tc_args: dict = None):
        """工具执行完毕 —— 追加卡片，search_files 附带跳转按钮"""
        if self._current_streaming_bubble:
            # 统计文件数量（从摘要中解析）
            action_text = None
            action_callback = None
            if tool_name == "search_files":
                import re
                m = re.search(r'找到 (\d+) 个文件', result_summary)
                if m and tc_args:
                    count = int(m.group(1))
                    action_text = f"📋 查看全部 {count} 个文件 →"
                    # 映射 LLM 参数名 → SearchTab._apply_search_params 参数名
                    mapped = {}
                    if tc_args.get("query"):
                        mapped["name"] = tc_args["query"]
                    for k in ("file_type", "start_date", "end_date", "min_size", "max_size"):
                        if tc_args.get(k) is not None:
                            mapped[k] = tc_args[k]
                    action_callback = lambda _checked=False, p=mapped: self.navigate_to_search.emit(p)

            self._current_streaming_bubble.add_tool_card(
                tool_name, result_summary,
                action_text=action_text, action_callback=action_callback,
            )
        self._scroll_to_bottom()

    def _on_done(self, final_text: str):
        """对话完成"""
        self._worker = None
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._disable_input(False)
        self._msg_input.setFocus()

        # 确保最终文本显示（如果有），否则保留工具卡片不清理
        if self._current_streaming_bubble:
            if final_text and final_text.strip():
                self._current_streaming_bubble.set_text(final_text)
            else:
                # 没有最终文本时也刷新一下布局
                current = self._current_streaming_bubble._text_browser.toPlainText()
                if not current.strip():
                    self._current_streaming_bubble.set_text("完成。")
                self._current_streaming_bubble._adjust_size()

        self._refresh_sessions()

        # 自动保存会话
        if self._conversation and self._conversation.message_count > 0:
            try:
                self._conversation.save(_SESSIONS_DIR)
            except Exception:
                pass

        self._scroll_to_bottom()

    def _on_error(self, err: str):
        """对话出错"""
        if self._current_streaming_bubble:
            self._current_streaming_bubble.set_text(f"❌ 出错了：{err}")
        self._worker = None
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._disable_input(False)
        self._msg_input.setFocus()

    # ── 工具开关 ──

    def _on_tool_toggle_changed(self):
        """工具开关变化时重建注册表"""
        self._rebuild_tool_registry()

    def _rebuild_tool_registry(self):
        """根据开关状态重新构建工具注册表"""
        from core.ai_tools import (
            ToolRegistry, create_search_files_tool, create_search_web_tool,
            create_read_file_tool, create_execute_python_tool,
        )

        registry = ToolRegistry()

        if self._tool_checks.get("search_files", QCheckBox()).isChecked():
            registry.register(create_search_files_tool(db_manager=self.ai_layer.db_manager))
        if self._tool_checks.get("search_web", QCheckBox()).isChecked():
            registry.register(create_search_web_tool())
        if self._tool_checks.get("read_file", QCheckBox()).isChecked():
            registry.register(create_read_file_tool())
        if self._tool_checks.get("execute_python", QCheckBox()).isChecked():
            registry.register(create_execute_python_tool())

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
            logger.info(f"AI 模型切换到: {provider_id}")

    # ── 侧栏事件 ──

    def _on_session_clicked(self, index):
        """点击会话列表项"""
        item = self._session_list.item(index.row())
        if item:
            session_id = item.data(Qt.ItemDataRole.UserRole)
            self._switch_session(session_id)

    # ── 辅助方法 ──

    def _disable_input(self, disabled: bool):
        self._msg_input.setEnabled(not disabled)
        self._model_combo.setEnabled(not disabled)

    def _scroll_to_bottom(self):
        QTimer.singleShot(30, lambda: self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        ))

    # ── 主题 ──

    def _apply_theme(self):
        is_dark = self._is_dark
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        card_bg = "#252538" if is_dark else "#e6e9ef"
        border = "#45475a" if is_dark else "#bcc0cc"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        accent = "#89b4fa" if is_dark else "#8839ef"
        accent2 = "#cba6f7" if is_dark else "#8839ef"

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
                background: {bg}; color: {text}; border: 1px solid {border};
                border-radius: 6px; font-size: 10pt;
            }}
            QListWidget#aiSessionList::item {{
                padding: 6px 8px; border-bottom: 1px solid {border};
            }}
            QListWidget#aiSessionList::item:selected {{
                background: {accent}; color: #1e1e2e;
            }}
            QListWidget#aiSessionList::item:hover {{ background: {card_bg}; }}
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

        # 单独强制设置每个 checkbox 样式（防止全局 QSS 覆盖）
        for cb in self._tool_checks.values():
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {text}; font-size: 10pt; spacing: 8px;
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
            """)

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
