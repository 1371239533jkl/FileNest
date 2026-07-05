"""
共享 AI 文件操作 —— classify_tab / tags_tab 复用。
Ponytail 原则：提取一处，两边调用，零重复代码。
"""
import hashlib

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QMessageBox, QFrame, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.ai_layer import AILayer
from core.tag_manager import TagManager
from database.models import FileDAO
from ui.toast import notify
from utils.logger import logger


# ── 标签配色（与 classify_tab / tags_tab 一致） ──
_TAG_COLORS = [
    ('#cba6f7', '#1e1e2e'), ('#89b4fa', '#1e1e2e'),
    ('#a6e3a1', '#1e1e2e'), ('#f9e2af', '#1e1e2e'),
    ('#fab387', '#1e1e2e'), ('#94e2d5', '#1e1e2e'),
    ('#f38ba8', '#1e1e2e'), ('#bac2de', '#1e1e2e'),
]
_TAG_LIGHT = [
    ('#cba6f7', '#ffffff'), ('#89b4fa', '#ffffff'),
    ('#a6e3a1', '#1e1e2e'), ('#f9e2af', '#1e1e2e'),
    ('#fab387', '#1e1e2e'), ('#94e2d5', '#1e1e2e'),
    ('#f38ba8', '#ffffff'), ('#bac2de', '#1e1e2e'),
]


def _tag_color_index(name: str) -> int:
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 8


def _make_tag_btn(text: str, bg: str, fg: str, pt: int = 13, bold: bool = False,
                  checkable: bool = True, checked: bool = False) -> QPushButton:
    """创建标签云风格按钮"""
    btn = QPushButton(text)
    btn.setCheckable(checkable)
    if checkable:
        btn.setChecked(checked)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(pt + 18)
    btn.setMinimumHeight(32)
    radius = max(8, pt + 2)
    bold_css = 'font-weight: bold;' if bold else ''
    hover_qss = (
        f"QPushButton:hover {{ background-color: {bg}; }}"
        f"QPushButton:pressed {{ background-color: {bg}; }}"
    )
    check_qss = (
        f"QPushButton:checked {{ background: {bg}; color: {fg}; border: 2px solid {fg}; }}"
        f"QPushButton:unchecked {{ background: transparent; color: {fg}; border: 1px solid {bg}; }}"
    ) if checkable else ''
    btn.setStyleSheet(
        f"QPushButton {{"
        f"  background-color: {bg};"
        f"  color: {fg};"
        f"  border: none;"
        f"  border-radius: {radius}px;"
        f"  text-align: left;"
        f"  padding: 4px 12px;"
        f"  font-size: {pt}pt;"
        f"  {bold_css}"
        f"}}"
        f"{hover_qss}"
        f"{check_qss}"
    )
    return btn


# ── 后台线程：AI 标签推荐（ai_file_actions 用，与 tags_tab._AiRecWorker 相同） ──
class _AiRecWorker(QThread):
    """后台线程：AI 标签推荐"""
    done = pyqtSignal(dict, list, str)  # record, recommendations, source
    error = pyqtSignal(str)

    def __init__(self, ai_layer, record, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.record = record

    def run(self):
        try:
            recs, source = self.ai_layer.recommend_tags(self.record)
            self.done.emit(self.record, recs, source)
        except Exception as e:
            self.error.emit(str(e))


class _TagRecDialog(QDialog):
    """异步标签推荐对话框——先显示加载状态，后台分析完成后填充内容。
    ponytail: open() 代替 exec()，window-modal 但不阻塞事件循环，worker 信号正常到达。
    """

    def __init__(self, parent, record, existing_tags, ai, tm, is_light):
        super().__init__(parent)
        self._record = record
        self._existing = existing_tags
        self._ai = ai
        self._tm = tm
        self._is_light = is_light
        self._tag_buttons = []

        self._init_loading()
        self._start_worker()

    def _colors(self):
        if self._is_light:
            return '#eff1f5', '#4c4f69', '#7c7f93', '#ccd0da'
        return '#1e1e2e', '#cdd6f4', '#a6adc8', '#45475a'

    def _init_loading(self):
        bg, fg, _, _ = self._colors()
        self.setWindowTitle("智能推荐标签")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background-color: {bg}; }}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(12)
        label = QLabel(f"正在为 '{self._record['file_name']}' 分析推荐标签...")
        label.setWordWrap(True)
        label.setStyleSheet(f"font-size: 13px; color: {fg};")
        self._layout.addWidget(label)

    def _start_worker(self):
        worker = _AiRecWorker(self._ai, self._record, self)
        worker.done.connect(self._on_done)
        worker.error.connect(self._on_error)
        worker.start()

    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_done(self, record, recommendations, source):
        self._record = record
        if not recommendations:
            self.close()
            QMessageBox.information(self.parent(), "标签推荐",
                                    f"未找到适合'{record['file_name']}'的推荐标签。")
            return

        suggested = [(tag, conf) for tag, conf in recommendations if tag not in self._existing]
        if not suggested:
            self.close()
            QMessageBox.information(self.parent(), "标签推荐",
                                    f"'{record['file_name']}'已有标签覆盖了所有推荐。")
            return

        source_label = "AI" if source == "ai" else "本地规则"
        self.setWindowTitle(f"智能推荐标签 ({source_label})")

        self._clear_layout()
        bg, fg, sub, sep_c = self._colors()

        info = QLabel(f"为'{record['file_name']}'推荐以下标签（点击切换选中/取消）：")
        info.setWordWrap(True)
        info.setStyleSheet(f"font-size: 12px; color: {fg}; margin-bottom: 4px;")
        self._layout.addWidget(info)

        if self._existing:
            palette = _TAG_LIGHT if self._is_light else _TAG_COLORS
            row = QHBoxLayout()
            row.setSpacing(6)
            el = QLabel("已有:")
            el.setStyleSheet(f"color: {sub}; font-size: 11pt;")
            row.addWidget(el)
            for et in sorted(self._existing):
                idx = _tag_color_index(et)
                bg_t, fg_t = palette[idx]
                row.addWidget(_make_tag_btn(f"  {et}  ", bg_t, fg_t, pt=13, checkable=False))
            row.addStretch()
            self._layout.addLayout(row)

        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet(f"color: {sep_c};")
        self._layout.addWidget(sep_line)

        palette = _TAG_LIGHT if self._is_light else _TAG_COLORS
        for tag, conf in suggested:
            idx = _tag_color_index(tag)
            bg_t, fg_t = palette[idx]
            display = f"{tag}  ({conf:.0%})"
            btn = _make_tag_btn(display, bg_t, fg_t, pt=13, checkable=True)
            self._tag_buttons.append((tag, btn, conf))
            self._layout.addWidget(btn)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._apply)
        btn_box.rejected.connect(self.reject)
        self._layout.addWidget(btn_box)

    def _on_error(self, err):
        self.close()
        QMessageBox.warning(self.parent(), "标签推荐失败", str(err))

    def _apply(self):
        selected = [tag for tag, btn, _ in self._tag_buttons if btn.isChecked()]
        if not selected:
            self.accept()
            return
        try:
            self._tm.batch_add_tags([self._record['id']], selected)
            notify(self.parent(), f"已添加标签: {', '.join(selected)}", 'success', 3500)
            logger.info(f"标签推荐: file_id={self._record['id']} 添加了标签 {selected}")
        except Exception as e:
            logger.error(f"添加标签失败: {e}")
            QMessageBox.critical(self.parent(), "标签推荐", f"添加标签失败: {e}")
        self.accept()


def show_tag_recommendation_dialog(parent, file_id, file_dao, ai_layer=None,
                                    tag_manager=None, theme='dark'):
    """智能推荐标签对话框——异步版：后台分析，不阻塞 UI"""
    record = file_dao.get_by_id(file_id)
    if not record:
        notify(parent, "文件记录不存在", 'warning', 3000)
        return

    ai = ai_layer or AILayer()
    tm = tag_manager or TagManager()
    existing_tags = set(t['tag_name'] for t in tm.get_tags_by_file(file_id))
    is_light = theme == 'light'

    dlg = _TagRecDialog(parent, record, existing_tags, ai, tm, is_light)
    dlg.open()  # window-modal 但不阻塞事件循环，worker 信号可正常到达


# ── AI 描述文件（后台线程，classify_tab / tags_tab / search_tab 共用） ──

class _AiDescWorker(QThread):
    """后台线程：AI 描述文件"""
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, ai_layer, record, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.record = record

    def run(self):
        try:
            result = self.ai_layer.describe_file(self.record) or "无法生成描述"
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


def request_ai_describe_file(parent, file_id, file_dao, ai_layer=None,
                              on_done=None, on_error=None):
    """发起 AI 文件描述请求（后台线程）
    
    Args:
        on_done: callable(text) - 描述完成回调
        on_error: callable(err) - 错误回调
    """
    record = file_dao.get_by_id(file_id)
    if not record:
        return

    ai = ai_layer or AILayer()
    worker = _AiDescWorker(ai, record, parent)
    if on_done:
        worker.done.connect(on_done)
    else:
        worker.done.connect(lambda t: QMessageBox.information(parent, "🤖 AI 文件描述", t))
    if on_error:
        worker.error.connect(on_error)
    else:
        worker.error.connect(lambda e: QMessageBox.warning(parent, "AI 描述失败", e))
    worker.start()
    return worker


# ── AI 重命名建议（后台线程，分类/search/标签共用） ──

class _AiRenameWorker(QThread):
    """后台线程：AI 重命名建议"""
    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, ai_layer, record, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.record = record

    def run(self):
        try:
            from utils.display_utils import format_size
            suggestions = self.ai_layer.suggest_rename(
                file_name=self.record.get('file_name', ''),
                file_path=self.record.get('file_path', ''),
                file_type=self.record.get('file_type', 'unknown'),
                file_size=format_size(self.record.get('file_size', 0)),
                modify_time=str(self.record.get('modify_time', '')),
            )
            self.done.emit(suggestions or [])
        except Exception as e:
            self.error.emit(str(e))
