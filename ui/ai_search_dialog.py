"""
AI 智能搜索浮层 —— Spotlight 风格输入框。

只负责 AI 解析，结果交由搜索页展示（不重复造轮子）。
唤起方式: Ctrl+Shift+F 或搜索页蓝色按钮。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.ai_layer import AILayer
from utils.logger import logger


class AiSearchWorker(QThread):
    """后台 AI 解析线程"""
    done = pyqtSignal(dict)       # params
    error = pyqtSignal(str)

    def __init__(self, ai_layer, query, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.query = query

    def run(self):
        try:
            params, source = self.ai_layer.search(self.query)
            # 标记来源 + 查询原文供 UI 展示
            if params is None:
                params = {}
            params['_source'] = source
            params['_query'] = self.query  # 传给搜索页用于 AI 摘要
            self.done.emit(params)
        except Exception as e:
            self.error.emit(str(e))


class AiSearchDialog(QDialog):
    """AI 搜索输入浮层 —— 简洁搜索框 + 解析状态"""

    search_ready = pyqtSignal(dict)  # 解析完成，携带搜索参数

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self.ai_layer = AILayer()
        self._ai_worker = None

        self.setWindowTitle("AI 智能搜索")
        self.setFixedSize(520, 180)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(12)

        # 标题
        title = QLabel("🤖 AI 搜索")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title)

        # 输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "说出你想找什么: 大于100MB的图片 | 上周修改的合同 | 成都的照片...")
        self.search_input.setMinimumHeight(40)
        self.search_input.returnPressed.connect(self._do_search)
        layout.addWidget(self.search_input)

        # 状态 + 按钮行
        row = QHBoxLayout()
        row.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 10pt;")
        self.status_label.setVisible(False)
        row.addWidget(self.status_label, 1)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setFixedHeight(36)
        self.search_btn.setMinimumWidth(70)
        self.search_btn.setObjectName("primaryBtn")
        self.search_btn.clicked.connect(self._do_search)
        row.addWidget(self.search_btn)

        layout.addLayout(row)

        # 提示
        hint = QLabel("Esc 关闭  ·  Enter 搜索  ·  结果跳转到搜索页展示")
        hint.setStyleSheet("font-size: 9pt;")
        layout.addWidget(hint)

    def _apply_theme(self):
        is_dark = self._theme == "dark"
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        surface = "#313244" if is_dark else "#e6e9ef"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        subtle = "#a6adc8" if is_dark else "#7c7f93"

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; }}
            QLabel {{ color: {text}; background: transparent; }}
            QLineEdit {{
                background-color: {surface}; color: {text};
                border: 1px solid {surface}; border-radius: 10px;
                padding: 8px 14px; font-size: 12pt;
            }}
            QLineEdit:focus {{ border: 1px solid #89b4fa; }}
        """)
        hint_color = subtle
        self.findChild(QLabel, "hint")  # won't find; just style via loop below
        # Update hint last
        for lbl in self.findChildren(QLabel):
            if "Esc 关闭" in (lbl.text() or ""):
                lbl.setStyleSheet(f"font-size: 9pt; color: {subtle};")

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        # 禁止重复请求
        if self._ai_worker and self._ai_worker.isRunning():
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("解析中...")
        self.status_label.setText("🤖 AI 正在理解查询...")
        self.status_label.setVisible(True)
        self.status_label.setStyleSheet("color: #89b4fa; font-size: 10pt; font-weight: bold;")
        QApplication.processEvents()

        self._ai_worker = AiSearchWorker(self.ai_layer, query, self)
        self._ai_worker.done.connect(self._on_done)
        self._ai_worker.error.connect(self._on_error)
        self._ai_worker.start()

    def _on_done(self, params: dict):
        self._ai_worker = None
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")
        self.status_label.setVisible(False)

        if not params or not any(v is not None for k, v in params.items()
                                   if not k.startswith('_')):
            self.status_label.setText("未能理解查询，请换种说法")
            self.status_label.setVisible(True)
            self.status_label.setStyleSheet("color: #f9e2af; font-size: 10pt;")
            return

        # 发射信号 → 主窗口跳转到搜索页展示结果
        self.search_ready.emit(params)
        self.hide()

    def _on_error(self, error_msg: str):
        self._ai_worker = None
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")
        self.status_label.setText(f"AI 暂时不可用")
        self.status_label.setVisible(True)
        self.status_label.setStyleSheet("color: #f38ba8; font-size: 10pt;")
        logger.warning(f"AI 搜索错误: {error_msg}")

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.clear()
        self.search_input.setFocus()
        self.status_label.setVisible(False)
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")
        if self.parent():
            pg = self.parent().geometry()
            self.move(pg.center().x() - self.width() // 2,
                      pg.center().y() - self.height() // 2 - 80)

    def closeEvent(self, event):
        self.hide()
        event.ignore()
