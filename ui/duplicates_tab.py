"""
重复文件可视化 - 分组展示、对比、清理
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from core import FileManager
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size, truncate_path, get_file_icon
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class DuplicatesTab(QWidget):
    """重复文件可视化页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.file_mgr = FileManager()
        self.page_size = 50
        self.current_page = 0
        self._total_groups = 0
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
            "以下文件存在重复（相同 SHA256 哈希），可保留一份并删除其余副本来释放空间。"
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
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        splitter.addWidget(self.detail_table)

        splitter.setSizes([300, 200])
        layout.addWidget(splitter, 1)

        # 空状态引导
        self._empty_state = create_empty_state('duplicates', parent=self)
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

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        bottom.addWidget(refresh_btn)

        layout.addLayout(bottom)

    def refresh_data(self):
        try:
            self._load_groups()
        except Exception as e:
            logger.error(f"加载重复文件失败: {e}")

    def _load_groups(self):
        self._total_groups = self.file_dao.count_duplicate_groups()
        total_wasted = self.file_dao.get_duplicate_total_wasted()
        self.stats_label.setText(
            f"共 {self._total_groups} 组重复 · 浪费空间: {format_size(total_wasted)}")

        # 空状态检测
        is_empty = self._total_groups == 0
        self._empty_state.setVisible(is_empty)
        if is_empty:
            self.group_table.setRowCount(0)
            self.detail_table.setRowCount(0)
            self.page_label.setText("第 0 页 / 共 0 页")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        groups = self.file_dao.get_duplicate_groups_paginated(
            page=self.current_page, page_size=self.page_size)

        self.group_table.setRowCount(len(groups))

        for i, g in enumerate(groups):
            # 哈希（截短）
            hash_item = QTableWidgetItem(g['file_hash'][:16] + "...")
            hash_item.setData(Qt.ItemDataRole.UserRole, g['file_hash'])
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
        file_hash = item.data(Qt.ItemDataRole.UserRole)
        self._load_group_details(file_hash)

    def _load_group_details(self, file_hash: str):
        files = self.file_dao.get_duplicate_group_files(file_hash)
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
            del_btn.setFixedHeight(26)
            del_btn.clicked.connect(
                lambda _, fid=f['id'], name=f['file_name']:
                    self._delete_single(fid, name))
            btn_layout.addWidget(del_btn)

            self.detail_table.setCellWidget(i, 4, btn_widget)

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
