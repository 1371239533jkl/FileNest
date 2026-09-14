"""
操作历史标签页 - 历史记录与还原
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox,
    QHeaderView, QDateEdit, QFileDialog, QLineEdit
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QBrush

import csv

from core import OperationHistoryManager
from database.models import TimelineDAO
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
    'created': '  新建文件',
    'modified': '  修改文件',
    'moved': '  移动文件',
}

OPERATION_ICONS = {
    'scan': '📂',
    'rename': '✏️',
    'move': '📦',
    'delete': '🗑️',
    'classify': '🏷️',
    'dedup': '🔀',
    'restore': '♻️',
    'created': '✨',
    'modified': '✏️',
    'moved': '➡️',
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
        self.timeline_dao = TimelineDAO()
        self._view_mode = 'operations'  # operations | all | external
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 视图切换
        view_layout = QHBoxLayout()
        view_layout.addWidget(QLabel("视图:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem("操作历史", "operations")
        self.view_combo.addItem("全部时间线", "all")
        self.view_combo.addItem("仅外部变化", "external")
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        view_layout.addWidget(self.view_combo)
        view_layout.addStretch(1)
        layout.addLayout(view_layout)

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

        filter_layout.addWidget(QLabel("目录:"))
        self.path_filter = QLineEdit()
        self.path_filter.setPlaceholderText("按目录前缀筛选，留空为全部")
        self.path_filter.setFixedWidth(200)
        self.path_filter.returnPressed.connect(self._on_filter_changed)
        filter_layout.addWidget(self.path_filter)

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
        self._empty_state = create_empty_state(
            'history', "重试加载", self.refresh_data, parent=self)
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

    def _on_view_changed(self):
        self._view_mode = self.view_combo.currentData() or 'operations'
        self._load_history()

    def _load_history(self):
        try:
            op_type = self.type_combo.currentData()
            start = self.start_date.date().toString("yyyy-MM-dd 00:00:00")
            end = self.end_date.date().toString("yyyy-MM-dd 23:59:59")
            path_prefix = self.path_filter.text().strip() or None

            if self._view_mode == 'operations':
                records = self.history_mgr.search_operations(
                    op_type=op_type, start_date=start, end_date=end)
                # 加 event_source 标记以统一处理
                for r in records:
                    r['event_source'] = 'operation'
            else:
                records = self.timeline_dao.get_combined(
                    mode=self._view_mode, op_type=op_type,
                    start_date=start, end_date=end,
                    path_prefix=path_prefix, limit=200)

            self._populate_table(records)
        except Exception as e:
            logger.error(f"加载时间线失败: {e}")
            self.history_table.setVisible(False)
            self._empty_state.show_error(f"无法读取：{e}")

    def _populate_table(self, records):
        self.history_table.setRowCount(len(records))
        self.count_label.setText(f"共 {len(records)} 条记录")

        # 空状态检测
        if records:
            self._empty_state.setVisible(False)
        else:
            self._empty_state.show_empty()
        self.history_table.setVisible(len(records) > 0)
        batch_counts = {}
        for record in records:
            batch_id = record.get('batch_id')
            if batch_id:
                batch_counts[batch_id] = batch_counts.get(batch_id, 0) + 1

        for i, r in enumerate(records):
            is_external = r.get('event_source') == 'external'
            ev_time = r.get('event_time') or r.get('operation_time') or ''
            ev_type = r.get('event_type') or r.get('operation_type') or ''
            ev_status = r.get('status') or r.get('operation_status') or ''

            time_item = QTableWidgetItem(str(ev_time))
            time_item.setData(Qt.ItemDataRole.UserRole, r['id'])
            self.history_table.setItem(i, 0, time_item)

            op_icon = OPERATION_ICONS.get(ev_type, ' ')
            op_name = OPERATION_NAMES.get(ev_type, ev_type)
            if is_external:
                op_name = "［外部］" + op_name
            self.history_table.setItem(i, 1, QTableWidgetItem(op_icon + " " + op_name))
            self.history_table.setItem(i, 2, QTableWidgetItem(
                str(r.get('file_id', ''))))

            old_val = r.get('old_value', '') or ''
            self.history_table.setItem(i, 3, QTableWidgetItem(
                old_val if len(old_val) < 50 else "..." + old_val[-47:]))

            new_val = r.get('new_value', '') or ''
            self.history_table.setItem(i, 4, QTableWidgetItem(
                new_val if len(new_val) < 50 else "..." + new_val[-47:]))

            if is_external:
                status_text = '外部变化'
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(QBrush(QColor('#89b4fa')))
            else:
                status_text = STATUS_NAMES.get(ev_status, ev_status)
                status_item = QTableWidgetItem(status_text)
                if ev_status == 'failed':
                    status_item.setForeground(QBrush(QColor('#f38ba8')))
                elif ev_status == 'completed':
                    status_item.setForeground(QBrush(QColor('#a6e3a1')))
                elif ev_status == 'undone':
                    status_item.setForeground(QBrush(QColor('#f9e2af')))
            if r.get('error_message'):
                status_item.setToolTip(r['error_message'])
            self.history_table.setItem(i, 5, status_item)

            batch_id = r.get('batch_id', '') or ''
            batch_text = f"{batch_id}（{batch_counts[batch_id]} 项）" if batch_id else '-'
            batch_item = QTableWidgetItem(batch_text)
            batch_item.setData(Qt.ItemDataRole.UserRole, batch_id)
            self.history_table.setItem(i, 6, batch_item)

            # 撤销按钮（仅应用内操作且可撤销）
            if not is_external and r.get('undo_available') and ev_status == 'completed':
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
        errors = []
        for row in sorted(rows, reverse=True):
            time_item = self.history_table.item(row, 0)
            try:
                op_id = time_item.data(Qt.ItemDataRole.UserRole) if time_item else None
                if op_id:
                    self.history_mgr.undo_operation(op_id)
                    success += 1
            except Exception as e:
                logger.warning(f"撤销失败: {e}")
                errors.append(str(e))

        message = f"成功撤销 {success} 条操作"
        if errors:
            message += f"\n失败 {len(errors)} 条：\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "批量撤销", message)
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
            batch_id = item.data(Qt.ItemDataRole.UserRole) if item else None
            if batch_id:
                batch_ids.add(batch_id)

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
