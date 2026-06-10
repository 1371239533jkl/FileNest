"""
回收区管理标签页 - 浏览、恢复、永久删除已删除文件
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt

from core import FileManager
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size, truncate_path
from utils.logger import logger
from ui.toast import notify


class RecycleBinTab(QWidget):
    """回收区管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.file_mgr = FileManager()
        self.page_size = 100
        self.current_page = 0
        self._total_count = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── 顶部说明 ──
        info_layout = QHBoxLayout()

        title_label = QLabel("♻️ 回收区")
        title_label.setStyleSheet("font-weight: bold; color: #f9e2af;")
        info_layout.addWidget(title_label)

        info_layout.addStretch()

        self.count_label = QLabel("")
        self.count_label.setObjectName("subtitleLabel")
        info_layout.addWidget(self.count_label)

        self.size_label = QLabel("")
        self.size_label.setObjectName("subtitleLabel")
        info_layout.addWidget(self.size_label)

        layout.addLayout(info_layout)

        hint = QLabel(
            "已删除的文件存放在应用回收区（.trash/），可从此处恢复或永久清除。"
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 文件表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["文件名", "原路径", "大小", "删除时间", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 180)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.table, 1)

        # ── 分页 ──
        page_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self._prev_page)
        page_layout.addWidget(self.prev_btn)

        page_layout.addStretch()
        self.page_label = QLabel("第 1 页 / 共 1 页")
        page_layout.addWidget(self.page_label)
        page_layout.addStretch()

        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self._next_page)
        page_layout.addWidget(self.next_btn)

        layout.addLayout(page_layout)

        # ── 底部操作 ──
        bottom_layout = QHBoxLayout()

        restore_btn = QPushButton("恢复选中文件")
        restore_btn.setObjectName("primaryBtn")
        restore_btn.clicked.connect(self._restore_selected)
        bottom_layout.addWidget(restore_btn)

        purge_btn = QPushButton("永久删除选中")
        purge_btn.setObjectName("dangerBtn")
        purge_btn.clicked.connect(self._purge_selected)
        bottom_layout.addWidget(purge_btn)

        empty_btn = QPushButton("清空回收区")
        empty_btn.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
            "border: none; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background-color: #eba0ac; }")
        empty_btn.clicked.connect(self._empty_recycle_bin)
        bottom_layout.addWidget(empty_btn)

        bottom_layout.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        bottom_layout.addWidget(refresh_btn)

        layout.addLayout(bottom_layout)

    # ── 数据加载 ──

    def refresh_data(self):
        self._load_page()

    def _load_page(self):
        try:
            self._total_count = self.file_dao.count_deleted()
            files = self.file_dao.get_deleted_files(
                page=self.current_page, page_size=self.page_size)
            self._populate_table(files)
        except Exception as e:
            logger.error(f"加载回收区数据失败: {e}")

    def _populate_table(self, files):
        total_pages = max(
            1, (self._total_count + self.page_size - 1) // self.page_size)
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1

        self.table.setRowCount(len(files))
        self.count_label.setText(f"共 {self._total_count} 个文件")

        total_size = sum(f.get('file_size', 0) for f in files)
        self.size_label.setText(f"本页占用: {format_size(total_size)}")

        for i, f in enumerate(files):
            file_id = f['id']

            # 文件名
            name_item = QTableWidgetItem("🗑️ " + f['file_name'])
            name_item.setData(Qt.ItemDataRole.UserRole, file_id)
            self.table.setItem(i, 0, name_item)

            # 原路径
            path = f.get('file_path', '')
            self.table.setItem(i, 1, QTableWidgetItem(truncate_path(path, 70)))

            # 大小
            self.table.setItem(i, 2, QTableWidgetItem(
                format_size(f.get('file_size', 0))))

            # 删除时间（取 scan_time 作为最近状态变更时间）
            scan_time = f.get('scan_time', '')
            self.table.setItem(i, 3, QTableWidgetItem(
                str(scan_time) if scan_time else "-"))

            # 操作按钮容器
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(6)

            restore_btn = QPushButton("恢复")
            restore_btn.setFixedSize(80, 30)
            restore_btn.setStyleSheet(
                "QPushButton { background-color: #a6e3a1; color: #1e1e2e; "
                "border: none; border-radius: 4px; font-size: 12px; "
                "padding: 4px 8px; min-height: 0px; }"
                "QPushButton:hover { background-color: #94e2d5; }")
            restore_btn.clicked.connect(
                lambda _, fid=file_id: self._restore_single(fid))
            btn_layout.addWidget(restore_btn)

            purge_btn = QPushButton("永久删除")
            purge_btn.setFixedSize(80, 30)
            purge_btn.setStyleSheet(
                "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
                "border: none; border-radius: 4px; font-size: 12px; "
                "padding: 4px 8px; min-height: 0px; }"
                "QPushButton:hover { background-color: #eba0ac; }")
            purge_btn.clicked.connect(
                lambda _, fid=file_id, name=f['file_name']:
                    self._purge_single(fid, name))
            btn_layout.addWidget(purge_btn)

            self.table.setCellWidget(i, 4, btn_widget)

        # 分页状态
        self.page_label.setText(
            f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

    # ── 翻页 ──

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._load_page()

    def _next_page(self):
        total_pages = max(
            1, (self._total_count + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._load_page()

    # ── 单文件操作 ──

    def _restore_single(self, file_id: int):
        try:
            self.file_mgr.restore_file(file_id)
            notify(self, "文件已恢复到原路径", 'success', 3000)
            self.refresh_data()
        except FileNotFoundError as e:
            QMessageBox.warning(self, "恢复失败", str(e))
        except FileExistsError as e:
            QMessageBox.warning(
                self, "恢复失败", f"原路径已被占用:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def _purge_single(self, file_id: int, file_name: str):
        reply = QMessageBox.question(
            self, "确认永久删除",
            f"确定要永久删除以下文件？\n\n{file_name}\n\n"
            "此操作将清除回收区副本，无法恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.file_mgr.purge_file(file_id)
            notify(self, f"已永久删除: {file_name}", 'success', 3000)
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    # ── 批量操作 ──

    def _get_selected_ids(self) -> list:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if item:
                fid = item.data(Qt.ItemDataRole.UserRole)
                if fid is not None:
                    ids.append(fid)
        return ids

    def _restore_selected(self):
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要恢复的文件")
            return
        reply = QMessageBox.question(
            self, "确认恢复",
            f"确定要恢复选中的 {len(ids)} 个文件到原路径？")
        if reply != QMessageBox.StandardButton.Yes:
            return

        success, failed = 0, 0
        errors = []
        for fid in ids:
            try:
                self.file_mgr.restore_file(fid)
                success += 1
            except Exception as e:
                failed += 1
                errors.append(str(e))

        msg = f"恢复完成: 成功 {success} 个"
        if failed:
            msg += f", 失败 {failed} 个"
        notify(self, msg, 'success' if failed == 0 else 'warning', 4000)
        if errors:
            logger.warning(f"批量恢复错误: {errors[:3]}")
        self.refresh_data()

    def _purge_selected(self):
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要永久删除的文件")
            return
        reply = QMessageBox.warning(
            self, "⚠️ 永久删除",
            f"确定要永久删除选中的 {len(ids)} 个文件？\n\n"
            "此操作将清除回收区副本，无法恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        success, failed = 0, 0
        for fid in ids:
            try:
                self.file_mgr.purge_file(fid)
                success += 1
            except Exception as e:
                failed += 1
                logger.warning(f"永久删除失败 ID={fid}: {e}")

        notify(self,
               f"永久删除完成: 成功 {success}, 失败 {failed}",
               'success' if failed == 0 else 'warning', 4000)
        self.refresh_data()

    def _empty_recycle_bin(self):
        """清空回收区：永久删除所有已删除文件的回收区副本"""
        count = self._total_count
        if count == 0:
            QMessageBox.information(self, "提示", "回收区已经是空的")
            return

        reply = QMessageBox.warning(
            self, "⚠️ 清空回收区",
            f"确定要清空回收区？\n\n"
            f"将永久删除 {count} 个文件的回收区副本，此操作不可恢复！\n"
            "（数据库记录会保留，但磁盘文件将被清除）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 先收集所有已删除文件的 ID，再逐个清除
        all_ids = []
        page = 0
        while True:
            files = self.file_dao.get_deleted_files(page=page, page_size=200)
            if not files:
                break
            for f in files:
                all_ids.append(f['id'])
            page += 1
            if len(files) < 200:
                break

        success, failed = 0, 0
        for fid in all_ids:
            try:
                self.file_mgr.purge_file(fid)
                success += 1
            except Exception as e:
                failed += 1
                logger.warning(f"清空回收区: ID={fid} 失败: {e}")

        notify(self,
               f"清空完成: 成功 {success}, 失败 {failed}",
               'success' if failed == 0 else 'warning', 4000)
        self.current_page = 0
        self.refresh_data()

