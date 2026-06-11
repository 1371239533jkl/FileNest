"""
操作历史标签页 - 历史记录与还原
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox,
    QHeaderView, QDateEdit, QFileDialog
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QBrush

import csv

from core import OperationHistoryManager
from utils.logger import logger
from ui.empty_state import create_empty_state


OPERATION_NAMES = {
    'scan': '  扫描',
    'rename': '  重命名',
    'move': '  移动',
    'delete': '  删除',
    'classify': '  分类',
    'dedup': '  去重',
    'restore': '  还原',
}

OPERATION_ICONS = {
    'scan': '📂',
    'rename': '✏️',
    'move': '📦',
    'delete': '🗑️',
    'classify': '🏷️',
    'dedup': '🔀',
    'restore': '♻️',
}

STATUS_NAMES = {
    'completed': '已完成',
    'failed': '失败',
    'undone': '已撤销',
}


class HistoryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_mgr = OperationHistoryManager()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 筛选工具栏
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("操作类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部", None)
        for key, name in OPERATION_NAMES.items():
            self.type_combo.addItem(name, key)
        self.type_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_combo)

        filter_layout.addWidget(QLabel("从:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-30))
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.start_date)

        filter_layout.addWidget(QLabel("至:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.end_date)

        filter_btn = QPushButton("筛选")
        filter_btn.setObjectName("primaryBtn")
        filter_btn.clicked.connect(self._on_filter_changed)
        filter_layout.addWidget(filter_btn)

        filter_layout.addStretch()

        self.count_label = QLabel("")
        self.count_label.setObjectName("subtitleLabel")
        filter_layout.addWidget(self.count_label)

        layout.addLayout(filter_layout)

        # 操作历史表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels(
            ["时间", "操作", "文件ID", "旧值", "新值", "状态", "批次", "操作"])
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.history_table.setColumnWidth(7, 65)
        self.history_table.verticalHeader().setDefaultSectionSize(36)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.history_table, 1)

        # 空状态引导
        self._empty_state = create_empty_state('history', parent=self)
        layout.addWidget(self._empty_state)

        # 底部操作
        bottom_layout = QHBoxLayout()

        undo_selected_btn = QPushButton("撤销选中操作")
        undo_selected_btn.setObjectName("dangerBtn")
        undo_selected_btn.clicked.connect(self._undo_selected)
        bottom_layout.addWidget(undo_selected_btn)

        undo_batch_btn = QPushButton("撤销选中批次")
        undo_batch_btn.clicked.connect(self._undo_batch)
        bottom_layout.addWidget(undo_batch_btn)

        export_btn = QPushButton("导出 CSV")
        export_btn.clicked.connect(self._export_csv)
        bottom_layout.addWidget(export_btn)

        bottom_layout.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        bottom_layout.addWidget(refresh_btn)

        layout.addLayout(bottom_layout)

    def refresh_data(self):
        self._load_history()

    def _on_filter_changed(self):
        self._load_history()

    def _load_history(self):
        try:
            op_type = self.type_combo.currentData()
            start = self.start_date.date().toString("yyyy-MM-dd 00:00:00")
            end = self.end_date.date().toString("yyyy-MM-dd 23:59:59")

            records = self.history_mgr.search_operations(
                op_type=op_type, start_date=start, end_date=end)
            self._populate_table(records)
        except Exception as e:
            logger.error(f"加载操作历史失败: {e}")

    def _populate_table(self, records):
        self.history_table.setRowCount(len(records))
        self.count_label.setText(f"共 {len(records)} 条记录")

        # 空状态检测
        self._empty_state.setVisible(len(records) == 0)
        self.history_table.setVisible(len(records) > 0)

        for i, r in enumerate(records):
            self.history_table.setItem(i, 0, QTableWidgetItem(
                str(r['operation_time']) if r['operation_time'] else ""))
            op_icon = OPERATION_ICONS.get(r['operation_type'], ' ')
            self.history_table.setItem(i, 1, QTableWidgetItem(
                op_icon + " " + OPERATION_NAMES.get(r['operation_type'], r['operation_type'])))
            self.history_table.setItem(i, 2, QTableWidgetItem(
                str(r.get('file_id', ''))))

            old_val = r.get('old_value', '') or ''
            self.history_table.setItem(i, 3, QTableWidgetItem(
                old_val if len(old_val) < 50 else "..." + old_val[-47:]))

            new_val = r.get('new_value', '') or ''
            self.history_table.setItem(i, 4, QTableWidgetItem(
                new_val if len(new_val) < 50 else "..." + new_val[-47:]))

            status = STATUS_NAMES.get(r['operation_status'], r['operation_status'])
            status_item = QTableWidgetItem(status)
            if r['operation_status'] == 'failed':
                status_item.setForeground(QBrush(QColor('#f38ba8')))
            elif r['operation_status'] == 'completed':
                status_item.setForeground(QBrush(QColor('#a6e3a1')))
            elif r['operation_status'] == 'undone':
                status_item.setForeground(QBrush(QColor('#f9e2af')))
            self.history_table.setItem(i, 5, status_item)

            self.history_table.setItem(i, 6, QTableWidgetItem(
                r.get('batch_id', '') or '-'))

            # 撤销按钮
            if r.get('undo_available') and r['operation_status'] == 'completed':
                undo_btn = QPushButton("撤销")
                undo_btn.setFixedSize(56, 24)
                undo_btn.setStyleSheet(
                    "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
                    "border: none; border-radius: 4px; font-size: 11px; padding: 0 2px; }"
                    "QPushButton:hover { background-color: #eba0ac; }")
                undo_btn.clicked.connect(lambda _, oid=r['id']: self._undo_single(oid))
                self.history_table.setCellWidget(i, 7, undo_btn)
            else:
                self.history_table.setItem(i, 7, QTableWidgetItem("-"))

    def _undo_single(self, op_id):
        reply = QMessageBox.question(self, "确认撤销", f"确定要撤销操作 ID={op_id}?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.history_mgr.undo_operation(op_id)
                QMessageBox.information(self, "成功", "操作已撤销")
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(self, "撤销失败", str(e))

    def _undo_selected(self):
        rows = set(idx.row() for idx in self.history_table.selectionModel().selectedRows())
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要撤销的操作")
            return

        reply = QMessageBox.question(self, "确认", f"确定要撤销选中的 {len(rows)} 条操作?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = 0
        for row in sorted(rows, reverse=True):
            op_id_item = self.history_table.item(row, 2)
            time_item = self.history_table.item(row, 0)
            # 通过历史记录查找
            try:
                # 获取操作id - 重新查询
                records = self.history_mgr.search_operations()
                if row < len(records):
                    self.history_mgr.undo_operation(records[row]['id'])
                    success += 1
            except Exception as e:
                logger.warning(f"撤销失败: {e}")

        QMessageBox.information(self, "批量撤销", f"成功撤销 {success} 条操作")
        self.refresh_data()

    def _undo_batch(self):
        rows = set(idx.row() for idx in self.history_table.selectionModel().selectedRows())
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要撤销的批次记录")
            return

        # 收集批次ID
        batch_ids = set()
        for row in rows:
            item = self.history_table.item(row, 6)
            if item and item.text() and item.text() != '-':
                batch_ids.add(item.text())

        if not batch_ids:
            QMessageBox.information(self, "提示", "选中的记录没有关联的批次")
            return

        reply = QMessageBox.question(
            self, "确认", f"确定要撤销 {len(batch_ids)} 个批次?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        total_success = 0
        for bid in batch_ids:
            try:
                result = self.history_mgr.undo_batch(bid)
                total_success += result['success']
            except Exception as e:
                logger.warning(f"批次撤销失败 {bid}: {e}")

        QMessageBox.information(self, "批量撤销", f"成功撤销 {total_success} 条操作")
        self.refresh_data()

    def _export_csv(self):
        """导出当前筛选的操作历史为 CSV 文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出操作历史", "operation_history.csv",
            "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            op_type = self.type_combo.currentData()
            start = self.start_date.date().toString("yyyy-MM-dd 00:00:00")
            end = self.end_date.date().toString("yyyy-MM-dd 23:59:59")
            records = self.history_mgr.search_operations(
                op_type=op_type, start_date=start, end_date=end)

            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'id', 'operation_time', 'operation_type', 'file_id',
                    'old_value', 'new_value', 'operation_status', 'batch_id'])
                writer.writeheader()
                for r in records:
                    writer.writerow({k: r.get(k, '') for k in writer.fieldnames})

            QMessageBox.information(self, "导出成功", f"已导出 {len(records)} 条记录到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
