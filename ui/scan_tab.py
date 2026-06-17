"""
扫描管理标签页
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem,
    QCheckBox, QMessageBox, QHeaderView, QApplication
)
from PyQt6.QtCore import Qt

import os
from core import FileScanWorker
from core.batch_classifier import BatchClassifyWorker
from core.file_watcher import WatcherManager
from core.rule_engine import CleanupAdvisor
from database.db_manager import db
from database.models import FileDAO, MetadataDAO, ScanDirectoryDAO, TagDAO, ClassificationDAO
from utils.display_utils import truncate_path, format_size
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class ScanTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan_worker = None
        self.file_dao = FileDAO(db)
        self.metadata_dao = MetadataDAO(db)
        self.scan_dao = ScanDirectoryDAO(db)
        self._watcher_mgr = WatcherManager.get_instance()
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

        self.cleanup_btn = QPushButton("清理建议")
        self.cleanup_btn.setToolTip("分析重复文件、长期未修改文件、临时文件等，生成磁盘清理建议")
        self.cleanup_btn.clicked.connect(self._show_cleanup_report)
        btn_layout.addWidget(self.cleanup_btn)

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

        self.eta_label = QLabel("")
        self.eta_label.setObjectName("subtitleLabel")
        self.eta_label.setStyleSheet("color: #89b4fa;")
        self.eta_label.setVisible(False)
        layout.addWidget(self.eta_label)

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

        # 空状态引导
        self._empty_state = create_empty_state('scan', parent=self)
        layout.addWidget(self._empty_state)

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
        self.scan_worker.progress_eta.connect(self._on_eta)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

        self.eta_label.setVisible(True)

    def _cancel_scan(self):
        if self.scan_worker:
            self.scan_worker.cancel()
            self.scan_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.stats_label.setText("扫描已取消")
            self.eta_label.setVisible(False)

    def _show_cleanup_report(self):
        """分析数据库中的文件并展示清理建议报告"""
        try:
            self.cleanup_btn.setEnabled(False)
            self.cleanup_btn.setText("分析中...")

            QApplication.processEvents()

            advisor = CleanupAdvisor(
                file_dao=self.file_dao,
                tag_dao=TagDAO(db),
                cls_dao=ClassificationDAO(db),
            )
            report = advisor.analyze()

            if not report or not report['categories']:
                QMessageBox.information(self, "清理建议", "未发现需要清理的文件，磁盘状况良好！")
                return

            # 构建报告
            total_active = report['total_active_files']
            total_size = format_size(report['total_size'])
            total_savings = format_size(report['total_potential_savings'])

            lines = [
                f"共 {total_active} 个活跃文件，占用 {total_size}",
                f"预计可释放约 {total_savings} 空间\n",
            ]

            severity_icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'info': '🔵'}
            for cat in report['categories']:
                icon = severity_icons.get(cat.get('severity', 'info'), '🔵')
                category = cat.get('category', '未知')
                desc = cat.get('description', '')
                action = cat.get('action', '')
                lines.append(f"{icon} {category}")
                lines.append(f"   {desc}")
                lines.append(f"   建议: {action}\n")

            QMessageBox.information(
                self, "磁盘清理建议报告",
                "\n".join(lines))

        except Exception as e:
            logger.error(f"清理建议分析失败: {e}")
            QMessageBox.critical(self, "清理建议", f"分析失败: {e}")
        finally:
            self.cleanup_btn.setEnabled(True)
            self.cleanup_btn.setText("清理建议")

    def _on_progress(self, current, total, path):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        display_path = truncate_path(path, 80)
        self.progress_label.setText(f"正在扫描 ({current}/{total}): {display_path}")

    def _on_eta(self, eta_str):
        """显示扫描 ETA"""
        self.eta_label.setText(f"⏱ 预计剩余: {eta_str}")

    def _on_scan_finished(self, new_count, total):
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.stats_label.setText(f"扫描完成: 新文件 {new_count} 个, 共 {total} 个")
        self.eta_label.setVisible(False)
        notify(self, f"扫描完成: 新增 {new_count} 个文件, 共 {total} 个", 'success', 4000)

        do_meta = self.metadata_cb.isChecked()
        do_cls = self.classify_cb.isChecked()
        if do_meta or do_cls:
            self.progress_label.setVisible(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setText("正在后处理...")

            # 构建分类器（仅在需要分类时传入）
            classifier = None
            if do_cls:
                from core import FileClassifier
                classifier = FileClassifier()

            self.post_worker = BatchClassifyWorker(
                classifier=classifier, do_metadata=do_meta)
            self.post_worker.progress.connect(self._on_post_progress)
            self.post_worker.finished.connect(self._on_post_finished)
            self.post_worker.error.connect(self._on_post_error)
            self.post_worker.start()
        else:
            self.progress_label.setVisible(False)
            self.refresh_data()
            # 扫描完成后启动文件监控
            self._start_watching()

    def _on_post_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在后处理 ({current}/{total})...")

    def _on_post_finished(self):
        self.stats_label.setText("后处理完成")
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.refresh_data()
        notify(self, "后处理完成", 'success', 3000)
        # 后处理完成后启动文件监控
        self._start_watching()

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
        self.eta_label.setVisible(False)
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

        # 空状态检测
        self._empty_state.setVisible(self.dir_table.rowCount() == 0)
        
        # 注意：不在这里启动文件监控，应该在扫描完成后启动
        # self._start_watching()  # 已移除

    def _delete_directory(self, dir_id):
        reply = QMessageBox.question(self, "确认", "确定要删除该扫描目录配置吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.scan_dao.delete(dir_id)
            self.refresh_data()
            notify(self, "扫描目录已删除", 'success', 3000)

    def _start_watching(self):
        """启动文件变化监控"""
        try:
            dirs = self.scan_dao.get_all()
            dir_paths = [d['directory_path'] for d in dirs if os.path.isdir(d['directory_path'])]
            if dir_paths:
                self._watcher_mgr.enable(
                    dir_paths,
                    scan_callback=self._on_auto_scan_triggered
                )
        except Exception as e:
            logger.debug(f"启动文件监控失败: {e}")

    def _on_auto_scan_triggered(self):
        """文件变化触发的自动扫描提示"""
        try:
            dirs = self.scan_dao.get_all()
            if not dirs:
                return
            # 只提示，不自动扫描
            dir_path = dirs[-1]['directory_path']
            if not os.path.isdir(dir_path):
                return
            # 给用户一个选择，而不是直接扫描
            notify(
                self, 
                f"检测到新文件，如需扫描请手动点击“开始扫描”",
                'info', 
                5000
            )
            logger.info(f"检测到文件变化，已提示用户: {dir_path}")
        except Exception as e:
            logger.warning(f"自动扫描提示失败: {e}")
