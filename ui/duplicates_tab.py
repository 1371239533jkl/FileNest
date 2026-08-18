"""
重复文件可视化 - 分组展示、对比、清理
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush

from core import FileManager
from core.dedup_manager import DedupManager
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size, truncate_path, get_file_icon
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class _MultistageDedupWorker(QThread):
    """后台多阶段重复检测线程"""
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, detector, parent=None):
        super().__init__(parent)
        self._detector = detector

    def cancel(self):
        self.requestInterruption()

    def run(self):
        try:
            stats = self._detector.run(cancel_check=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                return  # 页面已关闭：静默退出，不触发 done
            self.done.emit(stats)
        except Exception as exc:
            logger.exception("多阶段重复检测失败")
            self.error.emit(str(exc))


class DuplicatesTab(QWidget):
    """重复文件可视化页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.file_mgr = FileManager()
        self.dedup_mgr = DedupManager()
        self.page_size = 50
        self.current_page = 0
        self._total_groups = 0
        self._ai_worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 顶部统计
        header = QHBoxLayout()
        title = QLabel("🔁 重复文件")
        title.setStyleSheet("font-weight: bold; color: #f9e2af;")
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("subtitleLabel")
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        hint = QLabel(
            "以下为多阶段检测确认的重复文件（大小→快速哈希→完整哈希三级校验）。\n"
            "数据来自「多阶段重新检测」，未运行检测时列表为空。可保留一份并删除其余副本来释放空间。"
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 分割器：上方分组列表 + 下方组内文件
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上方：重复组列表
        self.group_table = QTableWidget()
        self.group_table.setColumnCount(4)
        self.group_table.setHorizontalHeaderLabels(
            ["哈希值", "副本数", "单文件大小", "浪费空间"])
        self.group_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.group_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self.group_table.setAlternatingRowColors(True)
        self.group_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.group_table.itemSelectionChanged.connect(self._on_group_selected)
        splitter.addWidget(self.group_table)

        # 下方：组内文件详情
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(5)
        self.detail_table.setHorizontalHeaderLabels(
            ["文件名", "路径", "大小", "修改时间", "操作"])
        self.detail_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.detail_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.detail_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed)
        self.detail_table.setColumnWidth(4, 126)
        self.detail_table.verticalHeader().setDefaultSectionSize(36)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        splitter.addWidget(self.detail_table)

        splitter.setSizes([300, 200])
        layout.addWidget(splitter, 1)

        # 空状态引导
        self._empty_state = create_empty_state(
            'duplicates', "重试加载", self.refresh_data, parent=self)
        layout.addWidget(self._empty_state)

        # 分页 + 操作
        bottom = QHBoxLayout()

        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self._prev_page)
        bottom.addWidget(self.prev_btn)

        bottom.addStretch()
        self.page_label = QLabel("第 1 页 / 共 1 页")
        bottom.addWidget(self.page_label)
        bottom.addStretch()

        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self._next_page)
        bottom.addWidget(self.next_btn)

        bottom.addSpacing(20)

        self.ai_select_btn = QPushButton("🤖 AI 智能选择")
        self.ai_select_btn.setObjectName("aiSelectBtn")
        self.ai_select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_select_btn.setToolTip("AI 分析当前重复组，建议保留哪个文件")
        self.ai_select_btn.clicked.connect(self._on_ai_select)
        self.ai_select_btn.setStyleSheet(
            "QPushButton#aiSelectBtn {"
            "  background: #89b4fa; color: #1e1e2e; border: none;"
            "  border-radius: 6px; padding: 6px 14px; font-weight: bold; font-size: 10pt;"
            "}"
            "QPushButton#aiSelectBtn:hover { background: #b4d0fb; }"
        )
        bottom.addWidget(self.ai_select_btn)

        self.keep_newest_btn = QPushButton("保留最新副本")
        self.keep_newest_btn.setToolTip("按修改时间保留最新文件，其余副本移入回收区")
        self.keep_newest_btn.clicked.connect(self._keep_newest_in_group)
        bottom.addWidget(self.keep_newest_btn)

        self.multistage_btn = QPushButton("🔎 多阶段重新检测")
        self.multistage_btn.setToolTip(
            "按 大小→快速哈希→完整哈希 三级确认重复；中断后可续算")
        self.multistage_btn.clicked.connect(self._run_multistage_dedup)
        bottom.addWidget(self.multistage_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        bottom.addWidget(refresh_btn)

        layout.addLayout(bottom)

    def _run_multistage_dedup(self):
        """后台执行多阶段重复检测，完成后刷新列表。"""
        if getattr(self, '_dedup_worker', None) and self._dedup_worker.isRunning():
            notify(self, "多阶段检测正在进行中，请稍候", 'info', 3000)
            return
        self.multistage_btn.setEnabled(False)
        self.multistage_btn.setText("正在检测...")
        from core.multistage_dedup import MultistageDedupDetector
        self._dedup_worker = _MultistageDedupWorker(
            MultistageDedupDetector(self.file_dao), self)
        self._dedup_worker.done.connect(self._on_multistage_done)
        self._dedup_worker.error.connect(self._on_multistage_error)
        self._dedup_worker.start()

    def _stop_dedup_worker(self):
        """请求中断并等待后台检测线程结束，避免 QThread 销毁时仍在运行。"""
        worker = getattr(self, '_dedup_worker', None)
        if worker is None:
            return
        try:
            worker.cancel()
            if worker.isRunning():
                worker.wait(10000)
        except RuntimeError:
            pass  # 线程对象已被 C++ 侧销毁
        finally:
            self._dedup_worker = None

    def _on_multistage_done(self, stats: dict):
        self.multistage_btn.setEnabled(True)
        self.multistage_btn.setText("🔎 多阶段重新检测")
        self._dedup_worker = None
        notify(
            self,
            f"多阶段检测完成：重复组 {stats.get('dup_groups', 0)}，"
            f"重复文件 {stats.get('dup_files', 0)} 个",
            'success', 4000)
        self.refresh_data()

    def _on_multistage_error(self, error: str):
        self.multistage_btn.setEnabled(True)
        self.multistage_btn.setText("🔎 多阶段重新检测")
        self._dedup_worker = None
        QMessageBox.warning(self, "多阶段检测失败", error)

    def _on_ai_select(self):
        """点击 AI 智能选择按钮"""
        rows = self.group_table.selectionModel().selectedRows()
        if not rows:
            notify(self, "请先在重复组列表中选中一组", 'info', 3000)
            return
        row = rows[0].row()
        item = self.group_table.item(row, 0)
        if not item:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        files = self.file_dao.get_duplicate_group_files_by_flag(group_id)
        if not files:
            return
        self._ai_smart_select(group_id, files)

    def _keep_newest_in_group(self):
        rows = self.group_table.selectionModel().selectedRows()
        if not rows:
            notify(self, "请先选择一个重复文件组", 'info', 3000)
            return
        item = self.group_table.item(rows[0].row(), 0)
        if not item:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        files = self.file_dao.get_duplicate_group_files_by_flag(group_id)
        keep_id, remove_ids = self.dedup_mgr.suggest_keep(files, 'keep_newest')
        keep = next((file for file in files if file['id'] == keep_id), None)
        if not keep or not remove_ids:
            return
        reply = QMessageBox.question(
            self, "确认清理重复文件",
            f"将保留最新副本：\n{keep['file_name']}\n\n"
            f"其余 {len(remove_ids)} 个副本将移入回收区，预计释放 "
            f"{format_size(sum(file.get('file_size', 0) for file in files if file['id'] in remove_ids))}。\n\n确定继续？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        _batch_id, removed = self.dedup_mgr.remove_duplicates(0, keep_id, remove_ids)
        notify(self, f"重复文件清理完成：保留 1 个，移入回收区 {removed} 个", 'success', 4000)
        self.refresh_data()

    def refresh_data(self):
        try:
            self._load_groups()
        except Exception as e:
            logger.error(f"加载重复文件失败: {e}")
            self.group_table.setVisible(False)
            self.detail_table.setVisible(False)
            self._empty_state.show_error(f"无法分析重复文件：{e}")

    def closeEvent(self, event):
        """页面销毁前等待后台检测线程结束，防止 QThread 销毁崩溃。"""
        self._stop_dedup_worker()
        super().closeEvent(event)

    def _load_groups(self):
        self._total_groups = self.file_dao.count_duplicate_groups_by_flag()
        total_wasted = self.file_dao.get_duplicate_total_wasted_by_flag()
        self.stats_label.setText(
            f"共 {self._total_groups} 组重复 · 浪费空间: {format_size(total_wasted)}")

        # 空状态检测
        is_empty = self._total_groups == 0
        if is_empty:
            self._empty_state.show_empty()
        else:
            self._empty_state.setVisible(False)
            self.group_table.setVisible(True)
            self.detail_table.setVisible(True)
        if is_empty:
            self.group_table.setVisible(False)
            self.detail_table.setVisible(False)
            self.group_table.setRowCount(0)
            self.detail_table.setRowCount(0)
            self.page_label.setText("第 0 页 / 共 0 页")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        groups = self.file_dao.get_duplicate_groups_paginated_by_flag(
            page=self.current_page, page_size=self.page_size)

        self.group_table.setRowCount(len(groups))

        for i, g in enumerate(groups):
            # 哈希（截短；组内代表哈希，可能为空则显示组号）
            hash_text = (g.get('file_hash') or '')[:16] + "..." if g.get('file_hash') else f"组 {g.get('group_id')}"
            hash_item = QTableWidgetItem(hash_text)
            hash_item.setData(Qt.ItemDataRole.UserRole, g.get('group_id'))
            self.group_table.setItem(i, 0, hash_item)

            self.group_table.setItem(i, 1, QTableWidgetItem(
                str(g['file_count'])))
            self.group_table.setItem(i, 2, QTableWidgetItem(
                format_size(g['single_size'])))

            wasted_item = QTableWidgetItem(format_size(g['wasted_size']))
            wasted_item.setForeground(QBrush(QColor('#f38ba8')))
            self.group_table.setItem(i, 3, wasted_item)

        # 分页
        total_pages = max(
            1, (self._total_groups + self.page_size - 1) // self.page_size)
        self.page_label.setText(
            f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

        # 清空详情
        self.detail_table.setRowCount(0)

    def _on_group_selected(self):
        rows = self.group_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        item = self.group_table.item(row, 0)
        if not item:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_group_details(group_id)

    def _load_group_details(self, group_id: int):
        files = self.file_dao.get_duplicate_group_files_by_flag(group_id)
        self.detail_table.setRowCount(len(files))

        for i, f in enumerate(files):
            item = QTableWidgetItem(get_file_icon(f['file_type']) + f['file_name'])
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.detail_table.setItem(i, 0, item)

            path = f.get('file_path', '')
            self.detail_table.setItem(i, 1, QTableWidgetItem(
                truncate_path(path, 60)))

            self.detail_table.setItem(i, 2, QTableWidgetItem(
                format_size(f.get('file_size', 0))))

            mtime = f.get('modify_time', '')
            self.detail_table.setItem(i, 3, QTableWidgetItem(
                str(mtime) if mtime else "-"))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            del_btn = QPushButton("删除此副本")
            del_btn.setStyleSheet(
                "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
                "border: none; border-radius: 4px; font-size: 11px; "
                "padding: 3px 8px; min-height: 0px; }"
                "QPushButton:hover { background-color: #eba0ac; }")
            del_btn.setFixedWidth(110)
            del_btn.setFixedHeight(26)
            del_btn.clicked.connect(
                lambda _, fid=f['id'], name=f['file_name']:
                    self._delete_single(fid, name))
            btn_layout.addWidget(del_btn)
            btn_layout.setAlignment(del_btn, Qt.AlignmentFlag.AlignCenter)

            self.detail_table.setCellWidget(i, 4, btn_widget)

    def _ai_smart_select(self, file_hash: str, files: list):
        """AI 智能裁决：分析重复文件组，建议保留哪个"""
        from core.ai_layer import AILayer
        ai = AILayer()
        if not ai.enabled:
            notify(self, "AI 未启用，请在设置中配置 AI 模型", 'info', 3000)
            return

        # 构建文件描述
        lines = [f"重复文件组（共 {len(files)} 个）:"]
        for i, f in enumerate(files, 1):
            lines.append(
                f"{i}. {f['file_name']} | 路径: {f.get('file_path','')} | "
                f"大小: {format_size(f.get('file_size',0))} | "
                f"修改时间: {f.get('modify_time','')}"
            )

        self.stats_label.setText("🤖 AI 正在分析重复文件...")

        class _SmartWorker(QThread):
            done = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, ai_layer, desc, parent=None):
                super().__init__(parent)
                self.ai_layer = ai_layer
                self.desc = desc

            def run(self):
                try:
                    backend = getattr(self.ai_layer, '_backend', None)
                    if not backend:
                        self.error.emit("AI 后端未配置")
                        return
                    msgs = [
                        {"role": "system",
                         "content": "你是文件去重专家。分析重复文件组，建议保留哪个副本。考虑：文件名更规范、路径更合理、修改时间更新。输出一行建议。"},
                        {"role": "user",
                         "content": f"请建议保留哪个文件（输出序号和理由）:\n{self.desc}"}
                    ]
                    result = backend.chat(msgs, max_tokens=200, temperature=0.2)
                    if result and hasattr(result, 'content'):
                        self.done.emit(str(result.content))
                    else:
                        self.error.emit("AI 返回为空")
                except Exception as e:
                    self.error.emit(str(e))

        desc_text = "\n".join(lines)
        self._ai_worker = _SmartWorker(ai, desc_text, self)
        self._ai_worker.done.connect(
            lambda t: self._on_smart_done(t, files))
        self._ai_worker.error.connect(self._on_smart_error)
        self._ai_worker.start()

    def _on_smart_done(self, text: str, files: list):
        self._ai_worker = None
        self.stats_label.setText(
            f"🤖 AI 建议: {text[:200]}")
        QMessageBox.information(
            self, "🤖 AI 智能裁决", text)

    def _on_smart_error(self, err: str):
        self._ai_worker = None
        self.stats_label.setText(f"AI 裁决失败: {err}")
        logger.warning(f"AI 重复裁决失败: {err}")

    def _delete_single(self, file_id: int, file_name: str):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要将此副本移入回收区？\n\n{file_name}\n\n"
            "保留的文件不受影响。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.file_mgr.delete_file(file_id)
            notify(self, f"已移入回收区: {file_name}", 'success', 3000)
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._load_groups()

    def _next_page(self):
        total_pages = max(
            1, (self._total_groups + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._load_groups()
