"""
全屏 AI 搜索页面 —— 参考微信搜索交互模式。
独立页面，支持完整的 AI 对话式文件搜索与追问。
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QFrame, QLineEdit, QScrollArea,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from core.ai_layer import AILayer
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size
from utils.logger import logger


# ── 后台线程 ──

class _AiWorker(QThread):
    """通用 AI 后台线程"""
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── 消息气泡组件 ──

class _MessageBubble(QFrame):
    """单条对话气泡"""

    def __init__(self, text: str, role: str = "ai", parent=None):
        super().__init__(parent)
        self.setObjectName(f"msgBubble_{role}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if role == "user":
            label.setObjectName("msgUser")
            label.setStyleSheet(
                "QLabel#msgUser {"
                "  background: #89b4fa; color: #1e1e2e;"
                "  border-radius: 12px; padding: 8px 14px; font-size: 10pt;"
                "}"
            )
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(label)
            row.setContentsMargins(20, 0, 10, 0)
            layout.addLayout(row)
        else:
            label.setObjectName("msgAi")
            label.setStyleSheet(
                "QLabel#msgAi {"
                "  background: #313244; color: #cdd6f4;"
                "  border-radius: 12px; padding: 8px 14px; font-size: 10pt;"
                "}"
            )
            row = QHBoxLayout()
            row.addWidget(label)
            row.addStretch()
            row.setContentsMargins(10, 0, 20, 0)
            layout.addLayout(row)


# ── 主页面 ──

class AiSearchPage(QWidget):
    """全屏 AI 搜索页面"""
    go_back = pyqtSignal()
    # 当用户想查看具体的搜索结果时，发射此信号携带参数
    show_results = pyqtSignal(dict)

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self.ai_layer = AILayer()
        self.file_dao = FileDAO(db)
        self._worker = None
        self._qa_worker = None
        self._current_summary = ""
        self._current_query = ""
        self._last_files = []
        self._last_total = 0
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部导航栏 ──
        top_bar = QWidget()
        top_bar.setFixedHeight(56)
        top_bar.setObjectName("aiTopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 8, 16, 8)

        self.back_btn = QPushButton("← 返回")
        self.back_btn.setObjectName("aiBackBtn")
        self.back_btn.setFixedHeight(32)
        self.back_btn.setFixedWidth(80)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        top_layout.addWidget(self.back_btn)

        title = QLabel("AI 搜索")
        title.setObjectName("aiTitle")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        top_layout.addWidget(title)

        top_layout.addStretch()
        layout.addWidget(top_bar)

        # ── 搜索输入栏 ──
        search_bar = QFrame()
        search_bar.setObjectName("aiSearchBar")
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(16, 10, 16, 10)
        search_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("aiSearchInput")
        self.search_input.setPlaceholderText("描述你想找的文件，如：大于 100MB 的图片、上周的 PDF 文档...")
        self.search_input.setFixedHeight(40)
        self.search_input.returnPressed.connect(self._start_search)
        search_layout.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("🔍 搜索")
        self.search_btn.setObjectName("aiSearchSubmitBtn")
        self.search_btn.setFixedHeight(40)
        self.search_btn.setFixedWidth(90)
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self._start_search)
        search_layout.addWidget(self.search_btn)

        layout.addWidget(search_bar)

        # ── 对话内容区（可滚动） ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setObjectName("aiChatArea")

        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(0, 8, 0, 8)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()

        self.scroll_area.setWidget(self.chat_widget)
        layout.addWidget(self.scroll_area, 1)

        # ── 底部追问输入栏 ──
        bottom_bar = QFrame()
        bottom_bar.setObjectName("aiBottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 10, 16, 10)
        bottom_layout.setSpacing(10)

        self.qa_input = QLineEdit()
        self.qa_input.setObjectName("aiQaInput")
        self.qa_input.setPlaceholderText("追问 AI，如：这些文件中有重复的吗？")
        self.qa_input.setFixedHeight(36)
        self.qa_input.returnPressed.connect(self._ask_followup)
        self.qa_input.setEnabled(False)
        bottom_layout.addWidget(self.qa_input, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("aiSendBtn")
        self.send_btn.setFixedHeight(36)
        self.send_btn.setFixedWidth(70)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._ask_followup)
        self.send_btn.setEnabled(False)
        bottom_layout.addWidget(self.send_btn)

        layout.addWidget(bottom_bar)

    def _apply_theme(self):
        is_dark = self._theme == "dark"
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        card_bg = "#252538" if is_dark else "#dce0e8"
        border = "#45475a" if is_dark else "#bcc0cc"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        accent = "#89b4fa"

        self.setStyleSheet(f"""
            AiSearchPage {{
                background-color: {bg};
            }}
            QWidget#aiTopBar {{
                background-color: {card_bg};
                border-bottom: 1px solid {border};
            }}
            QPushButton#aiBackBtn {{
                background: transparent; color: {accent};
                border: none; font-size: 11pt;
            }}
            QPushButton#aiBackBtn:hover {{ color: #b4d0fb; }}
            QFrame#aiSearchBar {{
                background-color: {card_bg};
                border-bottom: 1px solid {border};
            }}
            QLineEdit#aiSearchInput {{
                background-color: {bg};
                color: {text}; border: 1px solid {border};
                border-radius: 8px; padding: 4px 14px;
                font-size: 12pt;
            }}
            QLineEdit#aiSearchInput:focus {{ border: 1px solid {accent}; }}
            QPushButton#aiSearchSubmitBtn {{
                background: {accent}; color: #1e1e2e;
                border: none; border-radius: 8px;
                font-weight: bold; font-size: 11pt;
            }}
            QPushButton#aiSearchSubmitBtn:hover {{ background: #b4d0fb; }}
            QPushButton#aiSearchSubmitBtn:disabled {{
                background: {border}; color: #6c7086;
            }}
            QFrame#aiBottomBar {{
                background-color: {card_bg};
                border-top: 1px solid {border};
            }}
            QLineEdit#aiQaInput {{
                background-color: {bg};
                color: {text}; border: 1px solid {border};
                border-radius: 8px; padding: 4px 12px;
                font-size: 10pt;
            }}
            QLineEdit#aiQaInput:focus {{ border: 1px solid {accent}; }}
            QPushButton#aiSendBtn {{
                background: {border}; color: {text};
                border: none; border-radius: 8px;
                font-size: 10pt;
            }}
            QPushButton#aiSendBtn:hover {{ background: {accent}; color: #1e1e2e; }}
            QPushButton#aiSendBtn:disabled {{
                background: {border}; color: #6c7086;
            }}
            QScrollArea#aiChatArea {{
                background-color: {bg}; border: none;
            }}
        """)

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    # ── 搜索 ──

    def _start_search(self):
        query = self.search_input.text().strip()
        if not query or not self.ai_layer.enabled:
            return

        self._current_query = query
        self._current_summary = ""
        self._last_files = []
        self._last_total = 0

        # 添加用户消息气泡
        self._add_bubble(query, "user")

        # 添加加载提示
        self._add_bubble("🤖 AI 正在分析搜索结果...", "ai")
        self._scroll_to_bottom()

        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中...")

        self._worker = _AiWorker(
            self._ai_search_and_summarize, query, parent=self
        )
        self._worker.done.connect(self._on_search_done)
        self._worker.error.connect(self._on_search_error)
        self._worker.start()

    def _ai_search_and_summarize(self, query: str):
        """后台：AI 解析 + 执行搜索 + 生成摘要"""
        # 1. AI 解析查询
        params, source = self.ai_layer.search(query)

        # 2. 执行数据库搜索
        clean_params = {k: v for k, v in (params or {}).items()
                        if not k.startswith('_') and v is not None}
        files = self.file_dao.search(**clean_params)
        total = len(files)

        self._last_files = files
        self._last_total = total

        # 3. AI 生成摘要
        summary = self.ai_layer.summarize_results(query, files[:10], total)

        return {
            "params": params,
            "source": source,
            "total": total,
            "files": files,
            "summary": summary or f"找到 {total} 个文件，但 AI 无法生成摘要。",
        }

    def _on_search_done(self, result):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 搜索")

        # 移除 loading 气泡（最后一个）
        if self.chat_layout.count() > 1:
            item = self.chat_layout.itemAt(self.chat_layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()

        total = result.get("total", 0)
        summary = result.get("summary", "")
        files = result.get("files", [])
        params = result.get("params", {})

        self._current_summary = summary
        self._last_files = files
        self._last_total = total

        # 发射信号：将完整结果传给搜索表格
        self.show_results.emit({
            "params": params,
            "files": files,
            "total": total,
        })

        # 构建响应文本：摘要 + 预览 + 提示
        lines = [summary, ""]
        if files:
            lines.append("📂 部分文件预览：")
            for f in files[:6]:
                name = f.get('file_name', '?')
                size = format_size(f.get('file_size', 0))
                lines.append(f"  · {name}  ({size})")
            if total > 6:
                lines.append("")
                lines.append(f"⬆ 点击左上角「← 返回」可在表格中查看全部 {total} 个文件，支持翻页和右键操作")

        full_text = "\n".join(lines)
        self._add_bubble(full_text, "ai")
        self._scroll_to_bottom()

        # 启用追问
        self.qa_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.qa_input.setFocus()

    def _on_search_error(self, err: str):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 搜索")

        # 移除 loading 气泡
        if self.chat_layout.count() > 1:
            item = self.chat_layout.itemAt(self.chat_layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()

        self._add_bubble(f"❌ AI 搜索失败：{err}", "ai")
        self._scroll_to_bottom()
        logger.warning(f"AI 搜索页错误: {err}")

    # ── 追问 ──

    def _ask_followup(self):
        question = self.qa_input.text().strip()
        if not question or not self._current_summary:
            return

        self.qa_input.clear()
        self.qa_input.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")

        self._add_bubble(question, "user")
        self._add_bubble("🤖 AI 正在思考...", "ai")
        self._scroll_to_bottom()

        self._qa_worker = _AiWorker(
            self.ai_layer.answer_question,
            self._current_summary, question, parent=self
        )
        self._qa_worker.done.connect(self._on_qa_done)
        self._qa_worker.error.connect(self._on_qa_error)
        self._qa_worker.start()

    def _on_qa_done(self, answer):
        self.qa_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")

        # 移除 loading 气泡
        if self.chat_layout.count() > 1:
            item = self.chat_layout.itemAt(self.chat_layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()

        self._add_bubble(answer or "无法回答此问题。", "ai")
        self._scroll_to_bottom()
        self.qa_input.setFocus()

    def _on_qa_error(self, err: str):
        self.qa_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")

        if self.chat_layout.count() > 1:
            item = self.chat_layout.itemAt(self.chat_layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()

        self._add_bubble(f"❌ 追问失败：{err}", "ai")
        self._scroll_to_bottom()
        logger.warning(f"AI 追问错误: {err}")

    # ── UI 辅助 ──

    def _add_bubble(self, text: str, role: str = "ai"):
        """在对话区添加一条气泡消息"""
        bubble = _MessageBubble(text, role, self.chat_widget)
        # 插入到 stretch 之前
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)

    def _scroll_to_bottom(self):
        """滚动到底部"""
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _on_back(self):
        """返回主页"""
        self.go_back.emit()

    def focus_search(self):
        """外部调用：聚焦搜索框"""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def refresh_data(self):
        """刷新页面数据"""
        pass
