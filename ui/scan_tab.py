"""
扫描管理标签页
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem,
    QCheckBox, QMessageBox, QHeaderView, QApplication, QFrame, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings

import os
from core import FileScanWorker
from core.batch_classifier import BatchClassifyWorker
from core.file_watcher import WatcherManager
from core.rule_engine import CleanupAdvisor
from core.content_indexer import ContentIndexer
from database.db_manager import db
from database.models import FileDAO, MetadataDAO, ScanDirectoryDAO, TagDAO, ClassificationDAO
from utils.display_utils import truncate_path, format_size
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state
from ui.task_center import TaskCenterDialog
from core.task_manager import TaskManager
from core.index_health import IndexHealthService


class CleanupAnalysisWorker(QThread):
    """Run database-heavy cleanup analysis outside the GUI thread."""
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            report = CleanupAdvisor(
                file_dao=FileDAO(db),
                tag_dao=TagDAO(db),
                cls_dao=ClassificationDAO(db),
            ).analyze()
            self.done.emit(report)
        except Exception as exc:
            logger.exception("清理建议分析失败")
            self.error.emit(str(exc))


class ContentIndexWorker(QThread):
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, directory: str, parent=None):
        super().__init__(parent)
        self.directory = directory

    def run(self):
        try:
            records = FileDAO(db).get_by_directory(self.directory)
            self.done.emit(ContentIndexer().index_records(records))
        except Exception as exc:
            self.error.emit(str(exc))


class ScanTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan_worker = None
        self.post_worker = None
        self.cleanup_worker = None
        self.content_index_worker = None
        self._pending_content_index = False
        # ponytail: 清理建议缓存——指纹(数据状态)未变时复用上次结果，避免重复消耗 token
        self._settings = QSettings("FileNest", "FileNest")
        self._cleanup_fingerprint = ""
        self.file_dao = FileDAO(db)
        self.metadata_dao = MetadataDAO(db)
        self.scan_dao = ScanDirectoryDAO(db)
        self._watcher_mgr = WatcherManager.get_instance()
        self._theme = 'dark'
        self._scan_issues = []
        self._last_scan_report = {}
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
        self.path_label.setObjectName("scanPathLabel")
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

        self.content_index_cb = QCheckBox("建立正文索引")
        self.content_index_cb.setToolTip("索引文本、PDF 和 DOCX 正文，仅保存在本机")
        opts_layout.addWidget(self.content_index_cb)

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

        self.cleanup_btn = QPushButton("清理中心")
        self.cleanup_btn.setToolTip("聚合重复、临时、空、长期未用与超大文件建议，一键安全移入回收区")
        self.cleanup_btn.clicked.connect(self._show_cleanup_report)
        btn_layout.addWidget(self.cleanup_btn)

        self.task_center_btn = QPushButton('任务中心')
        self.task_center_btn.setToolTip('查看后台扫描、索引和分析任务的状态')
        self.task_center_btn.clicked.connect(self._show_task_center)
        btn_layout.addWidget(self.task_center_btn)

        self.health_btn = QPushButton('索引检查')
        self.health_btn.setToolTip('检查不存在的索引路径和孤立正文索引，可在确认后安全修复')
        self.health_btn.clicked.connect(self._check_index_health)
        btn_layout.addWidget(self.health_btn)

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
        self.eta_label.setObjectName("scanEtaLabel")
        self.eta_label.setVisible(False)
        layout.addWidget(self.eta_label)

        self.scan_summary = QFrame()
        self.scan_summary.setObjectName("scanSummaryPanel")
        summary_layout = QVBoxLayout(self.scan_summary)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        summary_header = QHBoxLayout()
        self.summary_title = QLabel("本次扫描结果")
        self.summary_title.setObjectName("scanDirectoryTitle")
        summary_header.addWidget(self.summary_title)
        summary_header.addStretch()
        self.summary_close_btn = QPushButton("×")
        self.summary_close_btn.setFixedSize(28, 28)
        self.summary_close_btn.setToolTip("关闭本次扫描结果")
        self.summary_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.summary_close_btn.clicked.connect(self._dismiss_scan_summary)
        summary_header.addWidget(self.summary_close_btn)
        summary_layout.addLayout(summary_header)
        self.summary_values = QLabel("")
        self.summary_values.setObjectName("subtitleLabel")
        self.summary_values.setWordWrap(True)
        summary_layout.addWidget(self.summary_values)
        self.issue_details = QTextEdit()
        self.issue_details.setReadOnly(True)
        self.issue_details.setFixedHeight(88)
        self.issue_details.setPlaceholderText("本次扫描没有发现问题")
        summary_layout.addWidget(self.issue_details)
        self.issue_details.setVisible(False)
        self.scan_summary.setMaximumHeight(110)
        self.scan_summary.setVisible(False)
        layout.addWidget(self.scan_summary)

        # 已配置扫描目录列表
        self.dir_title = QLabel("已配置扫描目录")
        self.dir_title.setObjectName("scanDirectoryTitle")
        layout.addWidget(self.dir_title)

        self.dir_table = QTableWidget()
        self.dir_table.setColumnCount(5)
        self.dir_table.setHorizontalHeaderLabels(["目录路径", "递归", "文件数", "最后扫描", "操作"])
        self.dir_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dir_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.dir_table.setColumnWidth(4, 88)
        self.dir_table.verticalHeader().setDefaultSectionSize(41)
        self.dir_table.verticalHeader().setVisible(False)
        self.dir_table.setAlternatingRowColors(True)
        self.dir_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.dir_table)

        # 空状态引导
        self._empty_state = create_empty_state(
            'scan', "重试加载", self.refresh_data, parent=self)
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
        self._scan_issues = []
        self._last_scan_report = {}
        self.scan_summary.setVisible(False)
        self.issue_details.setVisible(False)
        self.issue_details.clear()

        self.scan_worker = FileScanWorker(
            dir_path,
            recursive=self.recursive_cb.isChecked(),
            compute_hash=self.hash_cb.isChecked()
        )
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.progress_eta.connect(self._on_eta)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.cancelled.connect(self._on_scan_cancelled)
        self.scan_worker.issue.connect(self._on_scan_issue)
        self.scan_worker.report.connect(self._on_scan_report)
        TaskManager.instance().register('目录扫描', self.scan_worker)
        self.scan_worker.start()

        self.eta_label.setVisible(True)

    def _cancel_scan(self):
        if self.scan_worker:
            self.scan_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.stats_label.setText("正在取消扫描...")
            self.eta_label.setVisible(False)

    def _on_scan_cancelled(self):
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.stats_label.setText("扫描已取消")
        self.scan_worker = None

    def _show_cleanup_report(self):
        """打开安全清理中心（单例复用 + 数据指纹缓存，无需每次重新分析）。"""
        from ui.cleanup_center_dialog import CleanupCenterDialog
        dlg = CleanupCenterDialog.open_center(self)
        dlg.ensure_fresh()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _show_task_center(self):
        TaskCenterDialog(self).exec()

    def _check_index_health(self):
        try:
            service = IndexHealthService()
            report = service.inspect()
        except Exception as exc:
            logger.exception('索引健康检查失败')
            QMessageBox.critical(self, '索引检查', f'检查失败: {exc}')
            return

        missing = report['missing_records']
        orphan = report['orphan_content_count']
        message = (f"已检查 {report['active_files']} 条活跃索引记录。\n"
                   f"不存在的路径：{len(missing)} 条\n"
                   f"孤立正文索引：{orphan} 条")
        if not missing and not orphan:
            QMessageBox.information(self, '索引检查', message + '\n\n索引状态正常。')
            return
        answer = QMessageBox.question(
            self, '索引检查', message +
            '\n\n是否修复？不存在的路径只会标记为已删除，正文孤立索引会被移除。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = service.repair(report)
            self.refresh_data()
            notify(self, f"已修复：标记缺失 {result['marked_deleted']} 条，清理孤立正文索引 {result['orphan_content_removed']} 条", 'success', 4000)
        except Exception as exc:
            logger.exception('索引修复失败')
            QMessageBox.critical(self, '索引修复', f'修复失败: {exc}')

    def _on_cleanup_ready(self, report):
        self._finish_cleanup_analysis()
        if not report or not report.get('categories'):
            text = "未发现需要清理的文件，磁盘状况良好！"
            QMessageBox.information(self, "清理建议", text)
            if self._cleanup_fingerprint:
                self._settings.setValue("ai/cleanup_fingerprint", self._cleanup_fingerprint)
                self._settings.setValue("ai/cleanup_text", text)
            return
        lines = [
            f"共 {report['total_active_files']} 个活跃文件，占用 {format_size(report['total_size'])}",
            f"预计可释放约 {format_size(report['total_potential_savings'])} 空间\n",
        ]
        icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'info': '🔵'}
        for category in report['categories']:
            lines.extend((
                f"{icons.get(category.get('severity', 'info'), '🔵')} {category.get('category', '未知')}",
                f"   {category.get('description', '')}",
                f"   建议: {category.get('action', '')}\n",
            ))
        # ponytail: 原本 ai_advice 生成后从未展示，纯浪费 token；现附在报告末尾
        ai_advice = report.get('ai_advice')
        if ai_advice:
            lines.extend(("🤖 AI 建议:", f"   {ai_advice}", ""))
        text = "\n".join(lines)
        QMessageBox.information(self, "磁盘清理建议报告", text)
        # ponytail: 仅当 AI 建议成功生成时才缓存；否则不缓存，下次重试，
        # 避免"没额度时无 AI 建议的报告"被缓存后额度恢复也无法刷新。
        if self._cleanup_fingerprint and ai_advice:
            self._settings.setValue("ai/cleanup_fingerprint", self._cleanup_fingerprint)
            self._settings.setValue("ai/cleanup_text", text)

    def _on_cleanup_error(self, error):
        self._finish_cleanup_analysis()
        QMessageBox.critical(self, "清理建议", f"分析失败: {error}")

    def _finish_cleanup_analysis(self):
        self.cleanup_btn.setEnabled(True)
        self.cleanup_btn.setText("清理建议")
        self.cleanup_worker = None

    def _on_progress(self, current, total, path):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        display_path = truncate_path(path, 80)
        self.progress_label.setText(f"正在扫描 ({current}/{total}): {display_path}")

    def _on_eta(self, eta_str):
        """显示扫描 ETA"""
        self.eta_label.setText(f"⏱ 预计剩余: {eta_str}")

    def _on_scan_issue(self, path: str, reason: str):
        self._scan_issues.append((path, reason))
        if len(self._scan_issues) <= 100:
            self.issue_details.append(f"{truncate_path(path, 70)}\n  {reason}")

    def _on_scan_report(self, report: dict):
        self._last_scan_report = dict(report or {})
        issues = len(self._scan_issues)
        self.summary_values.setText(
            f"发现 {report.get('total', 0)} 个 · 新增 {report.get('new', 0)} 个 · "
            f"更新 {report.get('updated', 0)} 个 · 未变化/跳过 {report.get('skipped', 0)} 个 · "
            f"问题 {issues} 个")
        has_issues = issues > 0
        self.issue_details.setVisible(has_issues)
        self.scan_summary.setMaximumHeight(210 if has_issues else 110)
        if issues > 100:
            self.issue_details.append(f"还有 {issues - 100} 条问题未显示，请查看应用日志。")
        self.scan_summary.setVisible(True)

    def _dismiss_scan_summary(self):
        """Hide the transient result panel without affecting saved scan data."""
        self.scan_summary.setVisible(False)

    def _on_scan_finished(self, new_count, total):
        self.scan_worker = None
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.stats_label.setText(f"扫描完成: 新文件 {new_count} 个, 共 {total} 个")
        self.eta_label.setVisible(False)
        notify(self, f"扫描完成: 新增 {new_count} 个文件, 共 {total} 个", 'success', 4000)

        do_meta = self.metadata_cb.isChecked()
        do_cls = self.classify_cb.isChecked()
        self._pending_content_index = self.content_index_cb.isChecked()
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
            TaskManager.instance().register('扫描后处理', self.post_worker)
            self.post_worker.start()
        else:
            self._start_content_index_or_finish()

    def _on_post_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在后处理 ({current}/{total})...")

    def _on_post_finished(self):
        self.stats_label.setText("后处理完成")
        self._start_content_index_or_finish()

    def _start_content_index_or_finish(self):
        if not self._pending_content_index:
            self._finish_scan_pipeline()
            return
        directory = self.path_label.text()
        self.progress_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText("正在建立正文索引...")
        self.content_index_worker = ContentIndexWorker(directory, self)
        self.content_index_worker.done.connect(self._on_content_index_done)
        self.content_index_worker.error.connect(self._on_content_index_error)
        TaskManager.instance().register('正文索引', self.content_index_worker)
        self.content_index_worker.start()

    def _on_content_index_done(self, result):
        self._pending_content_index = False
        self.content_index_worker = None
        self.summary_values.setText(self.summary_values.text() +
            f"\n正文索引：已索引 {result['indexed']} 个，跳过 {result['skipped']} 个，失败 {result['failed']} 个")
        self._finish_scan_pipeline()

    def _on_content_index_error(self, error):
        self._pending_content_index = False
        self.content_index_worker = None
        self._on_scan_issue(self.path_label.text(), f"正文索引失败: {error}")
        self._finish_scan_pipeline()

    def _finish_scan_pipeline(self):
        self.progress_bar.setRange(0, 100)
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.refresh_data()
        notify(self, "扫描后处理完成", 'success', 3000)
        self._start_watching()

    def _on_post_error(self, msg):
        self.progress_label.setText(f"后处理失败: {msg}")
        self.progress_bar.setVisible(False)
        self.stats_label.setText("后处理失败")
        notify(self, f"后处理失败: {msg}", 'error', 5000)

        self.refresh_data()

    def _on_scan_error(self, error):
        self.scan_worker = None
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.eta_label.setVisible(False)
        self._on_scan_issue(self.path_label.text(), error)
        self.summary_values.setText(f"扫描失败 · 已记录 {len(self._scan_issues)} 个问题")
        self.scan_summary.setVisible(True)
        QMessageBox.critical(self, "扫描错误", f"扫描过程中发生错误:\n{error}")

    def refresh_data(self):
        """刷新扫描目录列表"""
        try:
            dirs = self.scan_dao.get_all()
            self.dir_table.setRowCount(len(dirs))
            for i, d in enumerate(dirs):
                self.dir_table.setRowHeight(i, 41)
                self.dir_table.setItem(i, 0, QTableWidgetItem("📁 " + d['directory_path']))
                self.dir_table.setItem(i, 1, QTableWidgetItem("是" if d['scan_recursive'] else "否"))
                self.dir_table.setItem(i, 2, QTableWidgetItem(str(d.get('file_count', 0))))
                scan_time = d.get('last_scan_time')
                self.dir_table.setItem(i, 3, QTableWidgetItem(
                    str(scan_time) if scan_time else "未扫描"))

                action_cell = QWidget()
                action_layout = QHBoxLayout(action_cell)
                action_layout.setContentsMargins(0, 0, 0, 0)
                action_layout.setSpacing(0)
                action_layout.addStretch()
                del_btn = QPushButton("删除")
                del_btn.setFixedSize(56, 24)
                del_btn.setObjectName("scanDeleteBtn")
                del_btn.clicked.connect(lambda _, did=d['id']: self._delete_directory(did))
                action_layout.addWidget(del_btn)
                action_layout.addStretch()
                self.dir_table.setCellWidget(i, 4, action_cell)

            # 更新统计
            stats = self.file_dao.get_type_stats()
            total = sum(s['count'] for s in stats) if stats else 0
            self.stats_label.setText(f"数据库中共 {total} 个文件")
        except Exception as e:
            logger.error(f"刷新数据失败: {e}")
            self.dir_table.setVisible(False)
            self._empty_state.show_error(f"无法读取扫描目录：{e}")
            return

        # 空状态检测
        if self.dir_table.rowCount() == 0:
            self.dir_table.setVisible(False)
            self._empty_state.show_empty()
        else:
            self.dir_table.setVisible(True)
            self._empty_state.setVisible(False)
        
        # 注意：不在这里启动文件监控，应该在扫描完成后启动
        # self._start_watching()  # 已移除

    def _delete_directory(self, dir_id):
        reply = QMessageBox.question(self, "确认", "确定要删除该扫描目录配置吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.scan_dao.delete(dir_id)
            self.refresh_data()
            notify(self, "扫描目录已删除", 'success', 3000)

    def _start_watching(self):
        """启动文件变化监控 + 自动增量落库"""
        try:
            dirs = self.scan_dao.get_all()
            dir_paths = [d['directory_path'] for d in dirs if os.path.isdir(d['directory_path'])]
            if dir_paths:
                self._watcher_mgr.enable(
                    dir_paths,
                    scan_callback=self._on_auto_scan_triggered,
                    auto_apply=True,
                    apply_done_callback=self._on_auto_apply_done
                )
        except Exception as e:
            logger.debug(f"启动文件监控失败: {e}")

    def _on_auto_apply_done(self, stats: dict):
        """增量落库完成后：提示结果并刷新数据"""
        try:
            applied = stats.get('applied', 0)
            failed = stats.get('failed', 0)
            if applied > 0:
                self.refresh_data()
            if failed > 0:
                notify(self, f"增量索引完成：成功 {applied}，失败 {failed}，可手动重扫修复",
                       'warning', 5000)
            elif applied > 0:
                notify(self, f"增量索引已自动更新 {applied} 个文件", 'success', 3000)
        except Exception as e:
            logger.warning(f"增量落库完成回调失败: {e}")

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
                f"检测到文件变化，如需同步请手动点击“开始扫描”",
                'info', 
                5000
            )
            logger.info(f"检测到文件变化，已提示用户: {dir_path}")
        except Exception as e:
            logger.warning(f"自动扫描提示失败: {e}")

    def apply_theme(self, theme_name: str):
        self._theme = theme_name
        dark = theme_name == 'dark'
        surface = '#1a1a2e' if dark else '#ffffff'
        border = '#2a2a3e' if dark else '#e2e8f0'
        text = '#e8e8ef' if dark else '#0f172a'
        muted = '#a0a0b0' if dark else '#64748b'
        self.scan_summary.setStyleSheet(
            f"QFrame#scanSummaryPanel {{ background-color: {surface}; "
            f"border: 1px solid {border}; border-radius: 6px; }}")
        self.summary_values.setStyleSheet(
            f"color: {muted}; background: transparent; border: none;")
        self.issue_details.setStyleSheet(
            f"background-color: {surface}; color: {text}; border: 1px solid {border};")
