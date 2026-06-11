"""
文件搜索标签页 - 多条件搜索
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QSpinBox, QDateEdit, QGroupBox, QHeaderView, QMessageBox,
    QCheckBox, QMenu, QApplication, QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QAction, QColor, QBrush

import os
import csv
from config import FILE_TYPE_NAMES
from core import FileManager
from database.db_manager import db
from database.models import FileDAO
from utils.display_utils import format_size, truncate_path, get_file_icon, get_file_color
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class SearchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.file_manager = FileManager()
        self.page_size = 100
        self.current_page = 0
        self.total_count = 0
        self._search_params = {}  # 存储搜索条件，翻页时复用
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 搜索条件区
        search_group = QGroupBox("搜索条件")
        search_layout = QVBoxLayout(search_group)

        # 第一行: 文件名搜索
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("文件名:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入文件名关键词...")
        self.name_input.returnPressed.connect(self._do_search)
        row1.addWidget(self.name_input)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("primaryBtn")
        self.search_btn.clicked.connect(self._do_search)
        row1.addWidget(self.search_btn)

        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self._reset_search)
        row1.addWidget(self.reset_btn)

        search_layout.addLayout(row1)

        # 第二行: 高级条件
        row2 = QHBoxLayout()
        row2.setSpacing(20)

        row2.addWidget(QLabel("类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部", None)
        for key, name in FILE_TYPE_NAMES.items():
            self.type_combo.addItem(name, key)
        row2.addWidget(self.type_combo)

        row2.addWidget(QLabel("最小大小(KB):"))
        self.min_size = QSpinBox()
        self.min_size.setRange(0, 999999999)
        self.min_size.setValue(0)
        row2.addWidget(self.min_size)

        row2.addWidget(QLabel("最大大小(MB):"))
        self.max_size = QSpinBox()
        self.max_size.setRange(0, 999999)
        self.max_size.setValue(0)
        self.max_size.setSpecialValueText("不限")
        row2.addWidget(self.max_size)

        row2.addWidget(QLabel("重复文件:"))
        self.dup_combo = QComboBox()
        self.dup_combo.addItem("全部", None)
        self.dup_combo.addItem("仅重复", 1)
        self.dup_combo.addItem("非重复", 0)
        row2.addWidget(self.dup_combo)

        search_layout.addLayout(row2)

        # 第三行: 日期范围
        row3 = QHBoxLayout()
        row3.setSpacing(20)

        row3.addWidget(QLabel("修改时间从:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-90))
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setEnabled(False)
        row3.addWidget(self.start_date)

        row3.addWidget(QLabel("至:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setEnabled(False)
        row3.addWidget(self.end_date)

        self.use_date_cb = QCheckBox("启用日期筛选")
        self.use_date_cb.toggled.connect(self._on_date_filter_toggled)
        row3.addWidget(self.use_date_cb)

        row3.addStretch()
        search_layout.addLayout(row3)

        layout.addWidget(search_group)

        # 结果统计
        stats_layout = QHBoxLayout()
        self.result_label = QLabel("请输入搜索条件")
        self.result_label.setObjectName("subtitleLabel")
        stats_layout.addWidget(self.result_label)
        stats_layout.addStretch()

        self.total_size_label = QLabel("")
        self.total_size_label.setObjectName("subtitleLabel")
        stats_layout.addWidget(self.total_size_label)

        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.clicked.connect(self._export_csv)
        self.export_btn.setVisible(False)
        stats_layout.addWidget(self.export_btn)

        layout.addLayout(stats_layout)

        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(7)
        self.result_table.setHorizontalHeaderLabels(
            ["文件名", "路径", "类型", "大小", "修改时间", "哈希", "重复"])
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setSortingEnabled(True)
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.result_table, 1)

        # 空状态引导
        self._empty_state = create_empty_state('search', parent=self)
        layout.addWidget(self._empty_state)

        # 分页控件
        page_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.clicked.connect(self._prev_page)
        self.prev_page_btn.setEnabled(False)
        page_layout.addWidget(self.prev_page_btn)

        page_layout.addStretch()
        self.page_label = QLabel("第 1 页 / 共 1 页")
        page_layout.addWidget(self.page_label)
        page_layout.addStretch()

        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.clicked.connect(self._next_page)
        self.next_page_btn.setEnabled(False)
        page_layout.addWidget(self.next_page_btn)

        layout.addLayout(page_layout)

    def _on_date_filter_toggled(self, checked: bool):
        """日期筛选开关：勾选后日期输入才可编辑"""
        self.start_date.setEnabled(checked)
        self.end_date.setEnabled(checked)

    def _do_search(self):
        self._search_params = {
            'name': self.name_input.text().strip() or None,
            'file_type': self.type_combo.currentData(),
            'min_size': self.min_size.value() * 1024 if self.min_size.value() > 0 else None,
            'max_size': self.max_size.value() * 1024 * 1024 if self.max_size.value() > 0 else None,
            'start_date': self.start_date.date().toString("yyyy-MM-dd 00:00:00") if self.use_date_cb.isChecked() else None,
            'end_date': self.end_date.date().toString("yyyy-MM-dd 23:59:59") if self.use_date_cb.isChecked() else None,
            'is_duplicate': self.dup_combo.currentData(),
        }
        self.current_page = 0
        self._load_page()

    def _load_page(self):
        """服务端分页：每次只查询当前页数据"""
        if not self._search_params:
            return
        try:
            # 查总数（只在第一页时查询，缓存结果）
            if self.current_page == 0 or self.total_count == 0:
                self.total_count = self.file_dao.search_count(**self._search_params)

            # 查当前页数据
            page_files = self.file_dao.search_paginated(
                page=self.current_page, page_size=self.page_size, **self._search_params)
            self._populate_results(page_files)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            QMessageBox.critical(self, "搜索错误", str(e))

    def _populate_results(self, files):
        total = self.total_count
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        # 空状态检测
        self._empty_state.setVisible(total == 0)
        self.result_table.setVisible(total > 0)

        # 修正当前页范围
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1

        self.result_table.setRowCount(len(files))
        total_size = 0

        for i, f in enumerate(files):
            item = QTableWidgetItem(get_file_icon(f['file_type']) + f['file_name'])
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.result_table.setItem(i, 0, item)

            path = f['file_path']
            display_path = truncate_path(path, 60)
            self.result_table.setItem(i, 1, QTableWidgetItem(display_path))

            type_name = FILE_TYPE_NAMES.get(f['file_type'], f['file_type'])
            type_item = QTableWidgetItem(type_name)
            type_item.setForeground(QBrush(QColor(get_file_color(f['file_type']))))
            self.result_table.setItem(i, 2, type_item)

            size = f['file_size']
            total_size += size
            size_str = format_size(size)
            self.result_table.setItem(i, 3, QTableWidgetItem(size_str))

            mtime = f.get('modify_time', '')
            self.result_table.setItem(i, 4, QTableWidgetItem(str(mtime) if mtime else ""))

            file_hash = f.get('file_hash', '') or ''
            self.result_table.setItem(i, 5, QTableWidgetItem(file_hash[:16] + "..." if file_hash else "-"))

            is_dup = "是" if f.get('is_duplicate') else "否"
            self.result_table.setItem(i, 6, QTableWidgetItem(is_dup))

        self.result_label.setText(f"找到 {total} 个文件")
        self.total_size_label.setText(f"当前页: {format_size(total_size)}")

        # 更新分页状态
        self.page_label.setText(f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_page_btn.setEnabled(self.current_page > 0)
        self.next_page_btn.setEnabled(self.current_page < total_pages - 1)
        self.export_btn.setVisible(total > 0)

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._load_page()

    def _next_page(self):
        total_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._load_page()

    def _reset_search(self):
        self.name_input.clear()
        self.type_combo.setCurrentIndex(0)
        self.min_size.setValue(0)
        self.max_size.setValue(0)
        self.dup_combo.setCurrentIndex(0)
        self.use_date_cb.setChecked(False)
        self.current_page = 0
        self.total_count = 0
        self._search_params = {}
        self.result_table.setRowCount(0)
        self.result_label.setText("请输入搜索条件")
        self.total_size_label.setText("")
        self.page_label.setText("第 0 页 / 共 0 页")
        self.prev_page_btn.setEnabled(False)
        self.next_page_btn.setEnabled(False)
        self.export_btn.setVisible(False)

    def _show_context_menu(self, pos):
        """搜索列表右键菜单"""
        row = self.result_table.rowAt(pos.y())
        if row < 0:
            return
        item = self.result_table.item(row, 0)
        if not item:
            return
        file_id = item.data(Qt.ItemDataRole.UserRole)
        if file_id is None:
            return
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return

        menu = QMenu(self)
        open_action = QAction("打开文件", self)
        open_action.triggered.connect(lambda fp=record['file_path']: self._safe_open_file(fp))
        menu.addAction(open_action)

        open_folder_action = QAction("打开所在文件夹", self)
        open_folder_action.triggered.connect(
            lambda fp=record['file_path']: self._safe_open_folder(fp))
        menu.addAction(open_folder_action)

        menu.addSeparator()

        copy_path_action = QAction("复制路径", self)
        copy_path_action.triggered.connect(
            lambda: QApplication.clipboard().setText(record['file_path']))
        menu.addAction(copy_path_action)

        copy_name_action = QAction("复制文件名", self)
        copy_name_action.triggered.connect(
            lambda: QApplication.clipboard().setText(record['file_name']))
        menu.addAction(copy_name_action)

        menu.addSeparator()

        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(lambda: self._context_rename(file_id))
        menu.addAction(rename_action)

        menu.addSeparator()

        delete_action = QAction("标记删除", self)
        delete_action.triggered.connect(lambda: self._context_delete(file_id))
        menu.addAction(delete_action)

        permanent_delete_action = QAction("永久删除", self)
        permanent_delete_action.triggered.connect(
            lambda: self._context_permanent_delete(file_id))
        menu.addAction(permanent_delete_action)

        menu.exec(self.result_table.viewport().mapToGlobal(pos))

    def _safe_open_file(self, file_path: str):
        """安全打开文件，文件不存在时给出友好提示"""
        if not file_path or not isinstance(file_path, str):
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            return
        if not os.path.exists(file_path):
            notify(self, f"文件不存在: {os.path.basename(file_path)}", 'warning', 4000)
            logger.warning(f"尝试打开不存在的文件: {file_path}")
            return
        try:
            os.startfile(file_path)
        except Exception as e:
            notify(self, f"无法打开文件: {e}", 'error', 5000)
            logger.error(f"打开文件失败: {file_path}, 错误: {e}")

    def _safe_open_folder(self, file_path: str):
        """安全打开所在文件夹"""
        if not file_path or not isinstance(file_path, str):
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            return
        folder = os.path.dirname(file_path)
        if not folder or not os.path.exists(folder):
            notify(self, "文件所在目录已不存在", 'warning', 4000)
            return
        try:
            os.startfile(folder)
        except Exception as e:
            notify(self, f"无法打开文件夹: {e}", 'error', 5000)

    def _context_rename(self, file_id):
        """右键菜单：重命名单个文件（需二次确认）"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return
        new_name, ok = QInputDialog.getText(
            self, "重命名", "输入新文件名:",
            text=record['file_name'])
        if not ok or not new_name:
            return
        reply = QMessageBox.question(
            self, "确认重命名",
            f"确定要将\n{record['file_name']}\n重命名为\n{new_name}?\n\n"
            "此操作会真的修改硬盘上的文件名！")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.file_manager.rename_file(file_id, new_name=new_name)
                self.refresh_data()
                notify(self, f"已重命名为: {new_name}", 'success', 3000)
            except Exception as e:
                QMessageBox.critical(self, "重命名失败", str(e))

    def _context_delete(self, file_id):
        """右键菜单：标记删除单个文件"""
        reply = QMessageBox.question(
            self, "确认删除", "确定标记删除该文件?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.file_manager.delete_file(file_id)
                self.refresh_data()
                notify(self, "文件已标记删除", 'success', 3000)
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def _context_permanent_delete(self, file_id):
        """右键菜单：永久删除文件（从硬盘清除）"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return
        reply = QMessageBox.question(
            self, "⚠️ 永久删除",
            f"确定要永久删除以下文件?\n\n{record['file_name']}\n\n"
            "此操作将从硬盘上彻底删除文件，不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 二次确认
            reply2 = QMessageBox.question(
                self, "⚠️ 最终确认",
                "此操作无法撤销，确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply2 == QMessageBox.StandardButton.Yes:
                try:
                    self.file_manager.permanent_delete(file_id)
                    self.refresh_data()
                except Exception as e:
                    QMessageBox.critical(self, "删除失败", str(e))

    def refresh_data(self):
        pass

    def focus_search(self):
        """Ctrl+F 聚焦搜索框"""
        self.name_input.setFocus()
        self.name_input.selectAll()

    def delete_selected(self):
        """Delete 快捷键触发：标记删除选中文件"""
        rows = self.result_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要删除的文件")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定标记删除选中的 {len(rows)} 个文件?")
        if reply == QMessageBox.StandardButton.Yes:
            success = 0
            for idx in rows:
                item = self.result_table.item(idx.row(), 0)
                if item:
                    fid = item.data(Qt.ItemDataRole.UserRole)
                    try:
                        self.file_manager.delete_file(fid)
                        success += 1
                    except Exception as e:
                        logger.warning(f"删除失败: {e}")
            notify(self, f"已标记删除 {success} 个文件", 'success', 3000)
            self.refresh_data()

    def rename_selected(self):
        """F2 快捷键触发：重命名当前选中的第一个文件"""
        rows = self.result_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要重命名的文件")
            return
        item = self.result_table.item(rows[0].row(), 0)
        if item:
            fid = item.data(Qt.ItemDataRole.UserRole)
            if fid is not None:
                self._context_rename(fid)

    def _export_csv(self):
        """导出当前搜索结果（全量）为 CSV 文件"""
        if not self._search_params:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出搜索结果", "search_results.csv",
            "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            # 导出全部结果，不分页
            all_files = self.file_dao.search(**self._search_params)
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'file_name', 'file_path', 'file_type', 'file_size',
                    'modify_time', 'file_hash', 'is_duplicate'])
                writer.writeheader()
                for r in all_files:
                    writer.writerow({k: r.get(k, '') for k in writer.fieldnames})
            notify(self, f"已导出 {len(all_files)} 条记录", 'success', 3000)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
