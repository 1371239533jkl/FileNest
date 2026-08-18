"""安全清理中心对话框 —— 聚合各类清理建议、原因说明、排除目录、误报反馈。

数据源：core.cleanup_center.CleanupCenter
安全保证：执行清理一律移入回收区（可撤销），不物理删除。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QInputDialog,
    QCheckBox, QTabWidget, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from database.db_manager import db
from database.models import FileDAO, TagDAO, ClassificationDAO
from core.cleanup_center import CleanupCenter
from utils.display_utils import format_size, truncate_path
from utils.logger import logger
from ui.toast import notify

CATEGORY_NAMES = {
    'duplicates': '重复文件',
    'temp': '临时/缓存',
    'empty': '空文件',
    'old': '长期未用',
    'large': '超大文件',
}

CATEGORY_ICONS = {
    'duplicates': '🔁', 'temp': '🗑️', 'empty': '📄',
    'old': '🕰️', 'large': '💾',
}


class _CleanupAnalysisWorker(QThread):
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def cancel(self):
        self.requestInterruption()

    def run(self):
        try:
            center = CleanupCenter(
                file_dao=FileDAO(db), tag_dao=TagDAO(db),
                cls_dao=ClassificationDAO(db))
            if self.isInterruptionRequested():
                return
            self.done.emit(center.analyze())
        except Exception as exc:
            logger.exception("清理中心分析失败")
            self.error.emit(str(exc))


class CleanupCenterDialog(QDialog):
    """安全清理中心对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧹 安全清理中心")
        self.setMinimumSize(820, 560)
        self._center = CleanupCenter(
            file_dao=FileDAO(db), tag_dao=TagDAO(db),
            cls_dao=ClassificationDAO(db))
        self._items = []
        self._worker = None
        self._build_ui()
        self._reload()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tip = QLabel(
            "聚合重复、临时、空、长期未用与超大文件建议。所有清理默认移入回收区（可撤销）。")
        tip.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(tip)

        # 分类 Tab
        self.tabs = QTabWidget()
        self.cat_tables = {}
        for key, name in CATEGORY_NAMES.items():
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(
                ["文件名", "路径", "大小", "原因", "操作"])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
            table.setAlternatingRowColors(True)
            table.setColumnWidth(4, 110)
            self.cat_tables[key] = table
            self.tabs.addTab(table, f"{CATEGORY_ICONS[key]} {name}")
        layout.addWidget(self.tabs, 1)

        # 底部操作
        bottom = QHBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("subtitleLabel")
        bottom.addWidget(self.summary_label)
        bottom.addStretch()

        self.select_all_btn = QPushButton("全选当前页")
        self.select_all_btn.clicked.connect(self._select_all_current)
        bottom.addWidget(self.select_all_btn)

        self.cleanup_btn = QPushButton("🗑 移入回收区")
        self.cleanup_btn.setObjectName("dangerBtn")
        self.cleanup_btn.setToolTip("将所选文件移入回收区（可撤销）")
        self.cleanup_btn.clicked.connect(self._execute_cleanup)
        bottom.addWidget(self.cleanup_btn)

        self.exclude_btn = QPushButton("⛔ 排除目录")
        self.exclude_btn.setToolTip("将选中文件的所在目录加入排除，之后不再建议")
        self.exclude_btn.clicked.connect(self._exclude_selected)
        bottom.addWidget(self.exclude_btn)

        self.fp_btn = QPushButton("🙅 误报反馈")
        self.fp_btn.setToolTip("将选中文件标记为误报，之后不再建议")
        self.fp_btn.clicked.connect(self._mark_false_positive)
        bottom.addWidget(self.fp_btn)

        self.exclusions_btn = QPushButton("排除管理")
        self.exclusions_btn.clicked.connect(self._manage_exclusions)
        bottom.addWidget(self.exclusions_btn)

        layout.addLayout(bottom)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ── 数据加载 ──────────────────────────────────────────────

    def _reload(self):
        self.cleanup_btn.setEnabled(False)
        self._stop_worker()
        self._worker = _CleanupAnalysisWorker(self)
        self._worker.done.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop_worker(self):
        """请求中断并等待分析线程结束，避免 QThread 销毁时仍在运行。"""
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            worker.cancel()
            if worker.isRunning():
                worker.wait(10000)
        except RuntimeError:
            pass  # 线程对象已被 C++ 侧销毁

    def _on_loaded(self, result: dict):
        self._items = result.get('all', [])
        total_size = sum(item['file_size'] for item in self._items)
        self.summary_label.setText(
            f"共 {len(self._items)} 项建议 · 占用 {format_size(total_size)} · "
            f"（重复 {len(result.get('duplicates', []))} / "
            f"临时 {len(result.get('temp', []))} / "
            f"空 {len(result.get('empty', []))} / "
            f"未用 {len(result.get('old', []))} / "
            f"超大 {len(result.get('large', []))}）")
        self.cleanup_btn.setEnabled(True)
        self._worker = None
        for key in self.cat_tables:
            self._populate_table(self.cat_tables[key], result.get(key, []))

    def _on_error(self, error: str):
        self.cleanup_btn.setEnabled(True)
        self._worker = None
        QMessageBox.warning(self, "清理分析失败", error)

    def closeEvent(self, event):
        """关闭对话框前等待后台线程结束，防止 QThread 销毁崩溃。"""
        self._stop_worker()
        super().closeEvent(event)

    def _populate_table(self, table: QTableWidget, items: list):
        table.setRowCount(len(items))
        for i, item in enumerate(items):
            table.setItem(i, 0, QTableWidgetItem(item.get('file_name', '')))
            table.setItem(i, 1, QTableWidgetItem(
                truncate_path(item.get('file_path', ''), 60)))
            table.setItem(i, 2, QTableWidgetItem(format_size(item.get('file_size', 0))))
            table.setItem(i, 3, QTableWidgetItem(item.get('reason', '')))
            btn = QPushButton("移入回收区")
            btn.setFixedSize(96, 26)
            btn.clicked.connect(
                lambda _checked=False, fid=item['file_id']: self._cleanup_one(fid))
            table.setCellWidget(i, 4, btn)

    def _selected_items(self) -> list:
        """返回当前激活 Tab 中选中的建议项。"""
        key = list(self.cat_tables.keys())[self.tabs.currentIndex()]
        table = self.cat_tables[key]
        selected_names = set()
        for index in table.selectionModel().selectedRows():
            selected_names.add(table.item(index.row(), 0).text())
        return [item for item in self._items
                if item['category'] == key and item.get('file_name') in selected_names]

    # ── 操作 ──────────────────────────────────────────────────

    def _select_all_current(self):
        key = list(self.cat_tables.keys())[self.tabs.currentIndex()]
        table = self.cat_tables[key]
        table.selectAll()

    def _cleanup_one(self, file_id: int):
        items = [item for item in self._items if item['file_id'] == file_id]
        if not items:
            return
        self._execute(items)

    def _execute_cleanup(self):
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, "移入回收区", "请先选择要清理的文件（或在行内直接点按钮）")
            return
        self._execute(items)

    def _execute(self, items: list):
        reply = QMessageBox.question(
            self, "确认清理",
            f"将 {len(items)} 个文件移入回收区（可撤销），"
            f"预计释放 {format_size(sum(i['file_size'] for i in items))}。\n\n确定继续？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        outcome = self._center.execute_cleanup(items)
        notify(self, f"已移入回收区 {outcome['moved']} 个，失败 {outcome['failed']} 个",
               'success' if outcome['failed'] == 0 else 'warning', 4000)
        self._reload()

    def _exclude_selected(self):
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, "排除目录", "请先选择文件")
            return
        paths = {item['file_path'].rsplit('/', 1)[0] for item in items}
        for directory in sorted(paths):
            self._center.add_exclusion(directory, '用户在清理中心手动排除')
        notify(self, f"已排除 {len(paths)} 个目录，之后不再建议", 'success', 3000)
        self._reload()

    def _mark_false_positive(self):
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, "误报反馈", "请先选择文件")
            return
        reason, ok = QInputDialog.getText(
            self, "误报反馈", "说明原因（可选）:")
        if not ok:
            return
        for item in items:
            self._center.mark_false_positive(item['file_path'], reason.strip())
        notify(self, f"已将 {len(items)} 个文件标记为误报", 'success', 3000)
        self._reload()

    def _manage_exclusions(self):
        rows = self._center.list_exclusions()
        if not rows:
            QMessageBox.information(self, "排除管理", "暂无排除目录")
            return
        names = "\n".join(f"- {r['path_pattern']}" for r in rows)
        reply = QMessageBox.question(
            self, "排除管理",
            f"当前排除的目录：\n{names}\n\n是否清空全部排除？")
        if reply == QMessageBox.StandardButton.Yes:
            for r in rows:
                self._center.remove_exclusion(r['path_pattern'])
            notify(self, "已清空全部排除", 'success', 3000)
            self._reload()
