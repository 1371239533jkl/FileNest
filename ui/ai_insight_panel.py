"""
AI 洞察面板 —— 紧凑摘要卡片（默认单行）+ 可折叠追问面板。

默认极省空间，只在用户需要时展开。
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.ai_layer import AILayer
from utils.logger import logger


class _AiWorker(QThread):
    """后台 AI 线程"""
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.done.emit(result or "")
        except Exception as e:
            self.error.emit(str(e))


class AiInsightPanel(QWidget):
    """紧凑 AI 洞察面板：默认只显示一行摘要 + 追问按钮。"""

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self.ai_layer = AILayer()
        self._worker = None
        self._qa_worker = None
        self._search_summary_text = ""
        self._current_query = ""
        self._qa_expanded = False

        self.setVisible(False)
        self.setMaximumHeight(40)  # 默认单行高度
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        # ── 主行：摘要（单行省略）+ 操作按钮 ──
        main_row = QHBoxLayout()
        main_row.setContentsMargins(10, 4, 10, 4)
        main_row.setSpacing(8)

        self.summary_line = QLabel("")
        self.summary_line.setObjectName("aiInsightLine")
        self.summary_line.setWordWrap(False)
        self.summary_line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.summary_line.mousePressEvent = lambda e: self._toggle_expand()
        main_row.addWidget(self.summary_line, 1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setObjectName("aiInsightCloseBtn")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.clear)
        main_row.addWidget(self.close_btn)

        layout.addLayout(main_row)

        # ── 展开区：完整摘要内容 + 操作按钮 ──
        self.expanded_frame = QFrame()
        self.expanded_frame.setObjectName("aiInsightExpanded")
        self.expanded_frame.setVisible(False)
        exp_layout = QVBoxLayout(self.expanded_frame)
        exp_layout.setContentsMargins(6, 2, 6, 2)
        exp_layout.setSpacing(2)

        self.full_summary = QLabel("")
        self.full_summary.setWordWrap(True)
        self.full_summary.setObjectName("aiInsightFull")
        exp_layout.addWidget(self.full_summary)

        # 按钮行（在文字下方）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.expand_btn2 = QPushButton("收起")
        self.expand_btn2.setFixedHeight(24)
        self.expand_btn2.setFixedWidth(60)
        self.expand_btn2.setObjectName("aiInsightBtn")
        self.expand_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn2.clicked.connect(self._toggle_expand)
        btn_row.addWidget(self.expand_btn2)

        self.qa_toggle_btn2 = QPushButton("💬 追问")
        self.qa_toggle_btn2.setFixedHeight(24)
        self.qa_toggle_btn2.setFixedWidth(70)
        self.qa_toggle_btn2.setObjectName("aiInsightBtn")
        self.qa_toggle_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qa_toggle_btn2.clicked.connect(self._toggle_qa)
        btn_row.addWidget(self.qa_toggle_btn2)

        exp_layout.addLayout(btn_row)
        layout.addWidget(self.expanded_frame)

        # ── 追问面板（默认隐藏） ──
        self.qa_frame = QFrame()
        self.qa_frame.setObjectName("aiQaCard")
        self.qa_frame.setVisible(False)
        qa_layout = QVBoxLayout(self.qa_frame)
        qa_layout.setContentsMargins(10, 4, 10, 6)
        qa_layout.setSpacing(4)

        self.qa_history = QTextEdit()
        self.qa_history.setReadOnly(True)
        self.qa_history.setFixedHeight(80)
        self.qa_history.setObjectName("aiQaHistory")
        self.qa_history.setPlaceholderText("对话历史...")
        qa_layout.addWidget(self.qa_history)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self.qa_input = QLineEdit()
        self.qa_input.setPlaceholderText("追问 AI...")
        self.qa_input.returnPressed.connect(self._ask_question)
        self.qa_input.setObjectName("aiQaInput")
        self.qa_input.setFixedHeight(26)
        input_row.addWidget(self.qa_input, 1)

        self.ask_btn = QPushButton("发送")
        self.ask_btn.setFixedHeight(26)
        self.ask_btn.setMinimumWidth(50)
        self.ask_btn.clicked.connect(self._ask_question)
        input_row.addWidget(self.ask_btn)
        qa_layout.addLayout(input_row)

        layout.addWidget(self.qa_frame)

    def _apply_theme(self):
        is_dark = self._theme == "dark"
        card_bg = "#252538" if is_dark else "#dce0e8"
        border = "#45475a" if is_dark else "#bcc0cc"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        subtle = "#a6adc8" if is_dark else "#7c7f93"
        accent = "#89b4fa"

        self.setStyleSheet(f"""
            AiInsightPanel {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel#aiInsightLine {{
                color: {text}; font-size: 10pt;
                background: transparent;
            }}
            QLabel#aiInsightFull {{
                color: {text}; font-size: 10pt;
                background: transparent; padding: 0;
            }}
            QPushButton#aiInsightBtn {{
                background: {border};
                color: {text}; border: none;
                border-radius: 4px; font-size: 9pt;
                padding: 1px 8px;
            }}
            QPushButton#aiInsightBtn:hover {{ background: {accent}; color: #1e1e2e; }}
            QPushButton#aiInsightCloseBtn {{
                background: transparent; color: {subtle};
                border: none; font-size: 10pt; font-weight: bold;
            }}
            QPushButton#aiInsightCloseBtn:hover {{ color: #f38ba8; }}
            QFrame#aiInsightExpanded {{
                background: transparent; border-top: 1px solid {border};
            }}
            QFrame#aiQaCard {{
                background: transparent; border-top: 1px solid {border};
            }}
            QTextEdit#aiQaHistory {{
                background-color: {card_bg.replace('252538', '1e1e2e').replace('dce0e8', 'ccd0da')};
                color: {text}; border: 1px solid {border}; border-radius: 4px;
                font-size: 9pt; padding: 4px;
            }}
            QLineEdit#aiQaInput {{
                background-color: {card_bg.replace('252538', '1e1e2e').replace('dce0e8', 'ccd0da')};
                color: {text}; border: 1px solid {border}; border-radius: 4px;
                padding: 2px 8px; font-size: 9pt;
            }}
            QLineEdit#aiQaInput:focus {{ border: 1px solid {accent}; }}
        """)

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    # ── 公共接口 ──

    def start_analysis(self, query: str, files: list, total_count: int):
        """触发 AI 分析"""
        if not self.ai_layer.enabled:
            self._show_no_ai()
            return

        self._current_query = query
        self._qa_expanded = False
        self._search_summary_text = ""
        self.qa_frame.setVisible(False)
        self.expanded_frame.setVisible(False)

        self.summary_line.setText("🤖 AI 正在分析搜索结果...")
        self.setMaximumHeight(40)
        self.setVisible(True)

        self._worker = _AiWorker(
            self.ai_layer.summarize_results, query, files, total_count, parent=self
        )
        self._worker.done.connect(self._on_summary_done)
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def _show_no_ai(self):
        self.setVisible(True)
        self.summary_line.setText("🤖 AI 未启用 — 在系统设置 → AI 模型中配置")
        self.qa_frame.setVisible(False)
        self.expanded_frame.setVisible(False)
        self.setMaximumHeight(40)

    def _on_summary_done(self, text: str):
        self._search_summary_text = text
        # 摘要首行作为摘要行
        first_line = text.split("\n")[0][:80] if text else "AI 未返回摘要"
        self.summary_line.setText(f"🤖 {first_line}")
        self.full_summary.setText(text if text else "AI 未返回摘要。")

    def _on_summary_error(self, err: str):
        self.summary_line.setText("🤖 AI 分析失败")
        logger.warning(f"AI 摘要错误: {err}")

    # ── 展开/折叠 ──

    def _toggle_expand(self):
        """展开/折叠摘要全文"""
        expanded = self.expanded_frame.isVisible()
        self.expanded_frame.setVisible(not expanded)
        self.summary_line.setVisible(expanded)  # 展开时隐藏单行，折叠时显示
        self._recalc_height()

    def _toggle_qa(self):
        """展开/折叠追问面板"""
        self._qa_expanded = not self._qa_expanded
        self.qa_frame.setVisible(self._qa_expanded)
        self.qa_toggle_btn2.setText("✕ 关闭" if self._qa_expanded else "💬 追问")
        self._recalc_height()

        if self._qa_expanded:
            self.qa_input.setFocus()

    def _recalc_height(self):
        """根据展开状态重新计算面板高度"""
        if self.expanded_frame.isVisible() or self._qa_expanded:
            self.setMaximumHeight(9999)    # 展开时允许自适应
        else:
            self.setMaximumHeight(40)      # 折叠时仅一行

    # ── 追问 ──

    def _ask_question(self):
        question = self.qa_input.text().strip()
        if not question or not self._search_summary_text:
            return

        self.qa_input.clear()
        self.ask_btn.setEnabled(False)
        self.ask_btn.setText("...")

        current = self.qa_history.toPlainText()
        self.qa_history.setPlainText(
            current + ("" if not current else "\n\n") + f"🙋 {question}"
        )

        self._qa_worker = _AiWorker(
            self.ai_layer.answer_question,
            self._search_summary_text, question, parent=self
        )
        self._qa_worker.done.connect(self._on_qa_done)
        self._qa_worker.error.connect(self._on_qa_error)
        self._qa_worker.start()

    def _on_qa_done(self, answer: str):
        self.ask_btn.setEnabled(True)
        self.ask_btn.setText("发送")
        current = self.qa_history.toPlainText()
        self.qa_history.setPlainText(
            current + f"\n\n🤖 {answer}" if answer else current + "\n\n🤖 无法回答。"
        )

    def _on_qa_error(self, err: str):
        self.ask_btn.setEnabled(True)
        self.ask_btn.setText("发送")
        logger.warning(f"AI 问答错误: {err}")

    def clear(self):
        self.setVisible(False)
        self._search_summary_text = ""
        self._qa_expanded = False
        self.qa_history.clear()
        self.expanded_frame.setVisible(False)
        self.qa_frame.setVisible(False)
        self.setMaximumHeight(40)
