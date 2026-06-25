"""
Command Palette —— 自然语言驱动文件批量操作。

Ctrl+Shift+P 呼出，用户输入自然语言指令，
AI 解析后执行对应的文件操作（移动/复制/删除/分类等）。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from datetime import datetime

import os
import shutil
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size
from utils.logger import logger
from ui.toast import notify


class _CmdWorker(QThread):
    """后台 AI 解析线程"""
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, ai_layer, command, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.command = command

    def run(self):
        try:
            if not self.ai_layer or not getattr(self.ai_layer, '_backend', None):
                self.error.emit("AI 后端未配置")
                return

            msgs = [
                {"role": "system",
                 "content": """你是文件操作助手。解析用户的自然语言指令为结构化操作。

支持的操作:
- move: 移动文件到目标目录
- copy: 复制文件
- delete: 删除文件（危险操作需确认）
- classify: 按规则分类文件

条件筛选支持:
- name: 文件名关键词
- file_type: 文件类型 (image/document/video/audio/archive/other)
- min_size: 最小文件大小 (bytes)
- max_size: 最大文件大小 (bytes)
- path_contains: 路径包含的关键词

输出 JSON 格式:
{
  "action": "move|copy|delete|classify",
  "target_dir": "目标目录路径",
  "filters": {"name": "...", "file_type": "...", "min_size": null, "max_size": null, "path_contains": "..."},
  "explanation": "操作说明"
}"""},
                {"role": "user",
                 "content": f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n用户指令: {self.command}"}
            ]
            result = self.ai_layer._backend.chat(msgs, max_tokens=400, temperature=0.1)
            if not result or not getattr(result, 'content', None):
                self.error.emit("AI 返回为空")
                return

            from core.ai_response import ResponseParser
            parsed = ResponseParser.parse_search(result.content)
            self.done.emit(parsed or {})
        except Exception as e:
            self.error.emit(str(e))


class CommandPalette(QDialog):
    """Command Palette 弹窗 —— 自然语言文件操作"""

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self.file_dao = FileDAO(db)
        self._worker = None
        self._parsed = None
        self._init_ui()
        self._apply_theme()

        # Esc 关闭
        QShortcut(QKeySequence("Escape"), self, self.close)

    def _init_ui(self):
        self.setWindowTitle("命令面板")
        self.setFixedSize(560, 420)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("🤖 自然语言命令")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("输入你想执行的操作，如：把下载文件夹里大于 100MB 的视频移到 D:/视频/大文件")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 9pt;")
        layout.addWidget(hint)

        # 输入框
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("描述你想做什么...")
        self.input_box.setFixedHeight(38)
        self.input_box.returnPressed.connect(self._execute)
        layout.addWidget(self.input_box)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.parse_btn = QPushButton("🔍 解析")
        self.parse_btn.setFixedHeight(34)
        self.parse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.parse_btn.clicked.connect(self._parse_command)
        btn_row.addWidget(self.parse_btn)

        self.exec_btn = QPushButton("▶ 执行")
        self.exec_btn.setFixedHeight(34)
        self.exec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exec_btn.clicked.connect(self._execute)
        self.exec_btn.setEnabled(False)
        btn_row.addWidget(self.exec_btn)

        btn_row.addStretch()

        close_btn = QPushButton("取消")
        close_btn.setFixedHeight(34)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        # 预览区域
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(180)
        self.preview.setPlaceholderText("解析结果和匹配文件将显示在这里...")
        layout.addWidget(self.preview)

    def _apply_theme(self):
        is_dark = self._theme == "dark"
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        card_bg = "#252538" if is_dark else "#dce0e8"
        border = "#45475a" if is_dark else "#bcc0cc"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        accent = "#89b4fa"

        self.setStyleSheet(f"""
            CommandPalette {{
                background-color: {bg}; border: 2px solid {border};
                border-radius: 12px;
            }}
            QLineEdit {{
                background-color: {card_bg}; color: {text};
                border: 1px solid {border}; border-radius: 8px;
                padding: 4px 14px; font-size: 11pt;
            }}
            QLineEdit:focus {{ border: 1px solid {accent}; }}
            QTextEdit {{
                background-color: {card_bg}; color: {text};
                border: 1px solid {border}; border-radius: 8px;
                font-size: 10pt; padding: 8px;
            }}
            QPushButton {{
                background: {border}; color: {text};
                border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 10pt;
            }}
            QPushButton:hover {{ background: {accent}; color: #1e1e2e; }}
            QPushButton:disabled {{ background: {border}; color: #6c7086; }}
            QLabel {{ color: {text}; }}
        """)

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    def _parse_command(self):
        """解析自然语言命令"""
        cmd = self.input_box.text().strip()
        if not cmd:
            return

        from core.ai_layer import AILayer
        ai = AILayer()
        if not ai.enabled:
            self.preview.setPlainText("AI 未启用，请在设置中配置 AI 模型")
            return

        self.parse_btn.setEnabled(False)
        self.parse_btn.setText("解析中...")
        self.preview.setPlainText("🤖 AI 正在解析命令...")

        self._worker = _CmdWorker(ai, cmd, self)
        self._worker.done.connect(self._on_parsed)
        self._worker.error.connect(self._on_parse_error)
        self._worker.start()

    def _on_parsed(self, parsed: dict):
        self._worker = None
        self.parse_btn.setEnabled(True)
        self.parse_btn.setText("🔍 解析")
        self._parsed = parsed

        action = parsed.get('action', '未知')
        target = parsed.get('target_dir', '未指定')
        explanation = parsed.get('explanation', '')
        filters = parsed.get('filters', {})

        # 执行文件搜索
        clean_filters = {k: v for k, v in filters.items() if v is not None and v != ''}
        files = self.file_dao.search(**clean_filters) if clean_filters else []
        total = len(files)

        lines = [
            f"📋 操作: {action}",
            f"📁 目标: {target}",
            f"💡 说明: {explanation}",
            f"📊 匹配文件: {total} 个",
            "",
        ]
        if files:
            total_size = sum(f.get('file_size', 0) for f in files)
            lines.append(f"总大小: {format_size(total_size)}")
            lines.append("预览 (前10个):")
            for f in files[:10]:
                lines.append(
                    f"  · {f.get('file_name','?')} "
                    f"({format_size(f.get('file_size',0))})"
                )

        self.preview.setPlainText("\n".join(lines))
        self.exec_btn.setEnabled(total > 0 and action != '未知')

    def _on_parse_error(self, err: str):
        self._worker = None
        self.parse_btn.setEnabled(True)
        self.parse_btn.setText("🔍 解析")
        self.preview.setPlainText(f"❌ 解析失败: {err}")
        logger.warning(f"命令解析失败: {err}")

    def _execute(self):
        """执行已解析的操作"""
        if not self._parsed:
            self._parse_command()
            return

        parsed = self._parsed
        action = parsed.get('action', '')
        target = parsed.get('target_dir', '')
        filters = parsed.get('filters', {})

        clean_filters = {k: v for k, v in filters.items() if v is not None and v != ''}
        files = self.file_dao.search(**clean_filters) if clean_filters else []

        if not files:
            self.preview.setPlainText("没有匹配的文件")
            return

        if action == 'delete':
            # 危险操作需要二次确认
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.warning(
                self, "⚠️ 确认删除",
                f"即将删除 {len(files)} 个文件，此操作不可撤销！\n\n确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            success = 0
            for f in files:
                old_path = f.get('file_path', '')
                if not old_path or not os.path.exists(old_path):
                    continue

                if action in ('move', 'copy'):
                    if not target:
                        continue
                    os.makedirs(target, exist_ok=True)
                    new_path = os.path.join(target, os.path.basename(old_path))
                    # 避免覆盖
                    if os.path.exists(new_path):
                        base, ext = os.path.splitext(new_path)
                        new_path = f"{base}_dup{ext}"
                    if action == 'move':
                        shutil.move(old_path, new_path)
                    else:
                        shutil.copy2(old_path, new_path)
                elif action == 'delete':
                    os.remove(old_path)

                success += 1

            notify(self.parent(), f"已完成: {success}/{len(files)} 个文件", 'success', 4000)
            self.close()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "操作失败", str(e))
            logger.error(f"批量操作失败: {e}")

    def focus_input(self):
        """外部调用：聚焦输入框"""
        self.input_box.setFocus()
        self.input_box.selectAll()
