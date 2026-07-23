"""Shared task-center dialog for background work started by the UI."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

from core.task_manager import TaskManager


class TaskCenterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('任务中心')
        self.resize(680, 360)
        self.manager = TaskManager.instance()
        layout = QVBoxLayout(self)

        title = QLabel('后台任务')
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['任务', '状态', '进度', '详情'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.cancel_btn = QPushButton('取消选中任务')
        self.cancel_btn.clicked.connect(self._cancel_selected)
        buttons.addWidget(self.cancel_btn)
        buttons.addStretch()
        clear_btn = QPushButton('清除已结束')
        clear_btn.clicked.connect(self.manager.clear_finished)
        buttons.addWidget(clear_btn)
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self.manager.task_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        tasks = self.manager.tasks()
        self.table.setRowCount(len(tasks))
        labels = {'running': '进行中', 'completed': '已完成',
                  'failed': '失败', 'cancelled': '已取消'}
        for row, task in enumerate(tasks):
            values = (task.title, labels.get(task.status, task.status),
                      f'{task.progress}%' if task.progress is not None else '—',
                      task.error or task.detail)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1 and task.status == 'failed':
                    item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, task.task_id)
        self.cancel_btn.setEnabled(any(task.status == 'running' for task in tasks))

    def _cancel_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        task_id = self.table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        self.manager.cancel(task_id)
