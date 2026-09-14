"""
一键归档包对话框（批次6-2）。
选源路径 → 选输出目录 → 生成 zip 归档 + 校验值 + 清单。
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.archive_service import ArchiveService
from utils.display_utils import format_size
from utils.logger import logger


class ArchiveWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, source_paths, output_dir, package_name):
        super().__init__()
        self.source_paths = source_paths
        self.output_dir = output_dir
        self.package_name = package_name

    def run(self):
        try:
            svc = ArchiveService()
            result = svc.create_package(
                self.source_paths, self.output_dir, self.package_name,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.done.emit({'success': False, 'error': str(exc)})


class ArchiveDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("一键归档包")
        self.setMinimumSize(560, 480)
        self.svc = ArchiveService()
        self._worker = None
        self._init_ui()
        self._refresh_history()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 源路径
        layout.addWidget(QLabel("源路径（文件或文件夹）:"))
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.source_list.setFixedHeight(100)
        layout.addWidget(self.source_list)

        src_btn_layout = QHBoxLayout()
        add_file_btn = QPushButton("＋ 添加文件")
        add_file_btn.clicked.connect(self._add_files)
        src_btn_layout.addWidget(add_file_btn)
        add_dir_btn = QPushButton("＋ 添加文件夹")
        add_dir_btn.clicked.connect(self._add_dir)
        src_btn_layout.addWidget(add_dir_btn)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_selected)
        src_btn_layout.addWidget(remove_btn)
        src_btn_layout.addStretch()
        layout.addLayout(src_btn_layout)

        # 输出目录
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("输出目录:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择归档包保存位置")
        out_layout.addWidget(self.output_edit, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)

        # 包名
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("归档包名:"))
        self.name_edit = QLineEdit()
        from datetime import datetime
        self.name_edit.setPlaceholderText(f"默认 archive_YYYYMMDD_HHMMSS.zip")
        name_layout.addWidget(self.name_edit, 1)
        layout.addLayout(name_layout)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.create_btn = QPushButton("开始归档")
        self.create_btn.setObjectName("primaryBtn")
        self.create_btn.clicked.connect(self._start_archive)
        btn_layout.addWidget(self.create_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # 历史记录
        layout.addWidget(QLabel("最近归档:"))
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["名称", "大小", "文件数", "状态", "创建时间"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.history_table.verticalHeader().setDefaultSectionSize(28)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table, 1)

        hist_btn_layout = QHBoxLayout()
        open_loc_btn = QPushButton("打开所在目录")
        open_loc_btn.clicked.connect(self._open_location)
        hist_btn_layout.addWidget(open_loc_btn)
        delete_btn = QPushButton("删除归档")
        delete_btn.clicked.connect(self._delete_selected)
        hist_btn_layout.addWidget(delete_btn)
        hist_btn_layout.addStretch()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_history)
        hist_btn_layout.addWidget(refresh_btn)
        layout.addLayout(hist_btn_layout)

    # ── 源路径操作 ───────────────────────────────────────────────

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        for f in files:
            self._add_source(f)

    def _add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if d:
            self._add_source(d)

    def _add_source(self, path: str):
        # 去重
        for i in range(self.source_list.count()):
            if self.source_list.item(i).text() == path:
                return
        item = QListWidgetItem(path)
        item.setToolTip(path)
        self.source_list.addItem(item)

    def _remove_selected(self):
        for item in self.source_list.selectedItems():
            self.source_list.takeItem(self.source_list.row(item))

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_edit.setText(d)

    # ── 执行归档 ────────────────────────────────────────────────

    def _start_archive(self):
        sources = [self.source_list.item(i).text()
                   for i in range(self.source_list.count())]
        if not sources:
            QMessageBox.warning(self, "提示", "请先添加源路径")
            return
        output_dir = self.output_edit.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(self, "提示", "请选择有效的输出目录")
            return

        self.create_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("准备中...")

        self._worker = ArchiveWorker(sources, output_dir, self.name_edit.text().strip() or None)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, done, total):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
            self.progress_bar.setFormat(f"{done}/{total}")

    def _on_done(self, result):
        self.progress_bar.setVisible(False)
        self.create_btn.setEnabled(True)
        if result.get('success'):
            QMessageBox.information(
                self, "归档完成",
                f"已创建归档包：\n{result['archive_path']}\n\n"
                f"文件数：{result['item_count']}\n"
                f"总大小：{format_size(result['total_size'])}\n"
                f"校验值：{result.get('checksum', '-')}")
            self._refresh_history()
        else:
            QMessageBox.critical(self, "归档失败", result.get('error', '未知错误'))

    # ── 历史记录 ────────────────────────────────────────────────

    def _refresh_history(self):
        pkgs = self.svc.list_packages()
        self.history_table.setRowCount(len(pkgs))
        for i, p in enumerate(pkgs):
            self.history_table.setItem(i, 0, QTableWidgetItem(p['package_name']))
            self.history_table.setItem(i, 1, QTableWidgetItem(format_size(p.get('total_size', 0))))
            self.history_table.setItem(i, 2, QTableWidgetItem(str(p.get('item_count', 0))))
            self.history_table.setItem(i, 3, QTableWidgetItem(
                {'completed': '已完成', 'creating': '进行中', 'failed': '失败'}.get(
                    p.get('status', ''), p.get('status', '-'))))
            self.history_table.setItem(i, 4, QTableWidgetItem(str(p.get('create_time', ''))))
            self.history_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, p['id'])

    def _open_location(self):
        row = self.history_table.currentRow()
        if row < 0:
            return
        pkg_id = self.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        pkg = self.svc.dao.get_by_id(pkg_id)
        if not pkg or not pkg.get('archive_path'):
            return
        path = pkg['archive_path']
        if os.path.exists(os.path.dirname(path)):
            try:
                # 跨平台打开目录
                if hasattr(os, 'startfile'):
                    os.startfile(os.path.dirname(path))  # noqa: PERF203
                elif os.uname().sysname == 'Darwin':
                    import subprocess
                    subprocess.Popen(['open', os.path.dirname(path)])
                else:
                    import subprocess
                    subprocess.Popen(['xdg-open', os.path.dirname(path)])
            except Exception as e:
                QMessageBox.warning(self, "提示", f"无法打开目录：{e}")

    def _delete_selected(self):
        row = self.history_table.currentRow()
        if row < 0:
            return
        pkg_id = self.history_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "确认删除", "确定删除此归档包（含文件）?")
        if reply == QMessageBox.StandardButton.Yes:
            self.svc.delete_package(pkg_id, delete_file=True)
            self._refresh_history()
