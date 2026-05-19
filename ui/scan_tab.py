"""
扫描管理标签页
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem,
    QCheckBox, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import os
from core import FileScanWorker
from database.db_manager import db
from database.models import FileDAO, MetadataDAO, ScanDirectoryDAO
from utils.display_utils import truncate_path
from utils.logger import logger
from ui.toast import notify


class PostProcessWorker(QThread):
    """扫描后处理：元数据提取 + 分类（独立DB连接）"""
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, do_metadata: bool, do_classify: bool, parent=None):
        super().__init__(parent)
        self.do_metadata = do_metadata
        self.do_classify = do_classify

    def run(self):
        import pymysql
        from pymysql.cursors import DictCursor
        from config import MYSQL_CONFIG
        from datetime import datetime
        from core.metadata_extractor import extract_metadata

        conn = pymysql.connect(**MYSQL_CONFIG)
        try:
            with conn.cursor(DictCursor) as cur:
                cur.execute("SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC")
                files = cur.fetchall()

            total = len(files)
            count = 0
            classify_batch = []

            # 分类器（内置规则，不再需要数据库查询规则）
            classifier = None
            if self.do_classify:
                from core import FileClassifier
                classifier = FileClassifier()

            for f in files:
                try:
                    # 元数据提取
                    if self.do_metadata:
                        metadata = extract_metadata(f['file_path'], f['file_type'])
                        if metadata:
                            cols = ['file_id'] + list(metadata.keys())
                            placeholders = ', '.join(['%s'] * len(cols))
                            update_parts = ', '.join(f'`{k}`=VALUES(`{k}`)' for k in metadata)
                            sql = (f"INSERT INTO file_metadata (`{'`, `'.join(cols)}`) "
                                   f"VALUES ({placeholders}) "
                                   f"ON DUPLICATE KEY UPDATE {update_parts}")
                            with conn.cursor() as cur:
                                cur.execute(sql, (f['id'],) + tuple(metadata.values()))

                    # 分类
                    if self.do_classify:
                        file_id = f['id']
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM file_classifications WHERE file_id = %s", (file_id,))
                        cls_results = classifier._classify_file_in_memory(f)
                        if cls_results:
                            now = datetime.now()
                            for cls_type, cls_value, confidence in cls_results:
                                classify_batch.append((file_id, cls_type, cls_value, now, confidence))
                            if len(classify_batch) >= 100:
                                with conn.cursor() as cur:
                                    cur.executemany(
                                        "INSERT INTO file_classifications "
                                        "(file_id, classification_type, classification_value, "
                                        "classification_time, confidence_score) "
                                        "VALUES (%s, %s, %s, %s, %s)", classify_batch)
                                    conn.commit()
                                classify_batch.clear()

                except Exception:
                    pass
                count += 1
                if count % 100 == 0:
                    self.progress.emit(count)

            # 最后一次 flush 分类
            if classify_batch:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO file_classifications "
                        "(file_id, classification_type, classification_value, "
                        "classification_time, confidence_score) "
                        "VALUES (%s, %s, %s, %s, %s)", classify_batch)
                    conn.commit()

            self.progress.emit(total)
            logger.info(f"后处理完成: {total} 个文件")
            self.finished.emit()
        except Exception as e:
            logger.error(f"后处理出错: {e}")
            self.error.emit(str(e))
        finally:
            conn.close()


class ScanTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan_worker = None
        self.file_dao = FileDAO(db)
        self.metadata_dao = MetadataDAO(db)
        self.scan_dao = ScanDirectoryDAO(db)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 目录选择区
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)

        self.dir_label = QLabel("选择扫描目录:")
        dir_layout.addWidget(self.dir_label)

        self.path_label = QLabel("未选择目录")
        self.path_label.setStyleSheet("color: #a6adc8; padding: 8px; background-color: #313244; border-radius: 6px;")
        self.path_label.setMinimumWidth(400)
        dir_layout.addWidget(self.path_label, 1)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)

        layout.addLayout(dir_layout)

        # 扫描选项
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(20)

        self.recursive_cb = QCheckBox("递归扫描子目录")
        self.recursive_cb.setChecked(True)
        opts_layout.addWidget(self.recursive_cb)

        self.hash_cb = QCheckBox("计算文件哈希(用于去重)")
        self.hash_cb.setChecked(True)
        opts_layout.addWidget(self.hash_cb)

        self.classify_cb = QCheckBox("扫描后自动分类")
        self.classify_cb.setChecked(True)
        opts_layout.addWidget(self.classify_cb)

        self.metadata_cb = QCheckBox("提取文件元数据")
        self.metadata_cb.setChecked(True)
        opts_layout.addWidget(self.metadata_cb)

        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setObjectName("primaryBtn")
        self.scan_btn.setMinimumWidth(150)
        self.scan_btn.clicked.connect(self._start_scan)
        btn_layout.addWidget(self.scan_btn)

        self.cancel_btn = QPushButton("取消扫描")
        self.cancel_btn.setObjectName("dangerBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("subtitleLabel")
        btn_layout.addWidget(self.stats_label)

        layout.addLayout(btn_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("subtitleLabel")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # 已配置扫描目录列表
        dir_title = QLabel("已配置扫描目录")
        dir_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #cba6f7; margin-top: 10px;")
        layout.addWidget(dir_title)

        self.dir_table = QTableWidget()
        self.dir_table.setColumnCount(5)
        self.dir_table.setHorizontalHeaderLabels(["目录路径", "递归", "文件数", "最后扫描", "操作"])
        self.dir_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dir_table.setColumnWidth(4, 65)
        self.dir_table.verticalHeader().setDefaultSectionSize(36)
        self.dir_table.verticalHeader().setVisible(False)
        self.dir_table.setAlternatingRowColors(True)
        self.dir_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.dir_table)

        self.refresh_data()

    def _browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择扫描目录")
        if dir_path:
            self.path_label.setText(dir_path)

    def _start_scan(self):
        dir_path = self.path_label.text()
        if dir_path == "未选择目录" or not os.path.isdir(dir_path):
            QMessageBox.warning(self, "提示", "请先选择一个有效的目录")
            return

        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)

        self.scan_worker = FileScanWorker(
            dir_path,
            recursive=self.recursive_cb.isChecked(),
            compute_hash=self.hash_cb.isChecked()
        )
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _cancel_scan(self):
        if self.scan_worker:
            self.scan_worker.cancel()
            self.scan_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.stats_label.setText("扫描已取消")

    def _on_progress(self, current, total, path):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        display_path = truncate_path(path, 80)
        self.progress_label.setText(f"正在扫描 ({current}/{total}): {display_path}")

    def _on_scan_finished(self, new_count, total):
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.stats_label.setText(f"扫描完成: 新文件 {new_count} 个, 共 {total} 个")
        notify(self, f"扫描完成: 新增 {new_count} 个文件, 共 {total} 个", 'success', 4000)

        do_meta = self.metadata_cb.isChecked()
        do_cls = self.classify_cb.isChecked()
        if do_meta or do_cls:
            self.progress_label.setVisible(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setText("正在后处理...")

            self.post_worker = PostProcessWorker(do_meta, do_cls)
            self.post_worker.progress.connect(self._on_post_progress)
            self.post_worker.finished.connect(self._on_post_finished)
            self.post_worker.error.connect(self._on_post_error)
            self.post_worker.start()
        else:
            self.progress_label.setVisible(False)
            self.refresh_data()

    def _on_post_progress(self, count):
        self.progress_label.setText(f"正在后处理 ({count} 个文件)...")

    def _on_post_finished(self):
        self.stats_label.setText("后处理完成")
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.refresh_data()
        notify(self, "后处理完成", 'success', 3000)

    def _on_post_error(self, msg):
        self.progress_label.setText(f"后处理失败: {msg}")
        self.progress_bar.setVisible(False)
        self.stats_label.setText("后处理失败")
        notify(self, f"后处理失败: {msg}", 'error', 5000)

        self.refresh_data()

    def _on_scan_error(self, error):
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        QMessageBox.critical(self, "扫描错误", f"扫描过程中发生错误:\n{error}")

    def refresh_data(self):
        """刷新扫描目录列表"""
        try:
            dirs = self.scan_dao.get_all()
            self.dir_table.setRowCount(len(dirs))
            for i, d in enumerate(dirs):
                self.dir_table.setItem(i, 0, QTableWidgetItem("📁 " + d['directory_path']))
                self.dir_table.setItem(i, 1, QTableWidgetItem("是" if d['scan_recursive'] else "否"))
                self.dir_table.setItem(i, 2, QTableWidgetItem(str(d.get('file_count', 0))))
                scan_time = d.get('last_scan_time')
                self.dir_table.setItem(i, 3, QTableWidgetItem(
                    str(scan_time) if scan_time else "未扫描"))

                del_btn = QPushButton("删除")
                del_btn.setFixedSize(56, 24)
                del_btn.setStyleSheet(
                    "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
                    "border: none; border-radius: 4px; font-size: 11px; padding: 0 2px; }"
                    "QPushButton:hover { background-color: #eba0ac; }")
                del_btn.clicked.connect(lambda _, did=d['id']: self._delete_directory(did))
                self.dir_table.setCellWidget(i, 4, del_btn)

            # 更新统计
            stats = self.file_dao.get_type_stats()
            total = sum(s['count'] for s in stats) if stats else 0
            self.stats_label.setText(f"数据库中共 {total} 个文件")
        except Exception as e:
            logger.error(f"刷新数据失败: {e}")

    def _delete_directory(self, dir_id):
        reply = QMessageBox.question(self, "确认", "确定要删除该扫描目录配置吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.scan_dao.delete(dir_id)
            self.refresh_data()
            notify(self, "扫描目录已删除", 'success', 3000)
