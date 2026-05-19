"""
分类管理标签页 - 左侧分类树 + 右侧文件列表
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QComboBox, QMessageBox, QHeaderView, QInputDialog, QFileDialog,
    QMenu, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtGui import QAction

import os
from config import FILE_TYPE_NAMES
from core import FileClassifier, FileManager
from database.db_manager import db
from database.models import FileDAO, ClassificationDAO
from utils.display_utils import format_size, truncate_path, get_file_icon, get_file_color
from utils.logger import logger
from ui.toast import notify


class ReclassifyWorker(QThread):
    """后台重新分类工作线程（独立DB连接，不抢主线程的连接）"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, classifier, parent=None):
        super().__init__(parent)
        self.classifier = classifier

    def run(self):
        """独立连接，批量处理，完成后关闭"""
        import pymysql
        from pymysql.cursors import DictCursor
        from config import MYSQL_CONFIG
        from datetime import datetime

        # 创建独立连接
        conn = pymysql.connect(**MYSQL_CONFIG)
        try:
            # 1. 读取全部活动文件
            with conn.cursor(DictCursor) as cur:
                cur.execute("SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC")
                files = cur.fetchall()

            total = len(files)
            classified = 0
            batch = []

            for i, record in enumerate(files):
                file_id = record['id']
                try:
                    # 清除旧分类（独立连接内执行）
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM file_classifications WHERE file_id = %s", (file_id,))

                    # 内存分类，不操作数据库
                    cls_results = self.classifier._classify_file_in_memory(record)
                    if cls_results:
                        classified += 1

                    # 缓存批量插入
                    now = datetime.now()
                    for cls_type, cls_value, confidence in cls_results:
                        batch.append((file_id, cls_type, cls_value, now, confidence))

                    # 每 100 条 flush
                    if len(batch) >= 100:
                        with conn.cursor() as cur:
                            cur.executemany(
                                "INSERT INTO file_classifications "
                                "(file_id, classification_type, classification_value, "
                                "classification_time, confidence_score) "
                                "VALUES (%s, %s, %s, %s, %s)", batch)
                            conn.commit()
                        batch.clear()

                except Exception as e:
                    logger.warning(f"分类失败 {record.get('file_name')}: {e}")

                if i % 50 == 0:
                    self.progress.emit(i + 1, total)

            # 最后一次 flush
            if batch:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO file_classifications "
                        "(file_id, classification_type, classification_value, "
                        "classification_time, confidence_score) "
                        "VALUES (%s, %s, %s, %s, %s)", batch)
                    conn.commit()

            self.progress.emit(total, total)
            logger.info(f"分类完成: {classified}/{total}")
            self.finished.emit(classified)
        except Exception as e:
            logger.error(f"分类出错: {e}")
            self.error.emit(str(e))
        finally:
            conn.close()


class ClassifyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.cls_dao = ClassificationDAO(db)
        self.classifier = FileClassifier()
        self.file_manager = FileManager()
        self.current_files = []
        self.page_size = 100
        self.current_page = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 顶部操作栏
        top_layout = QHBoxLayout()

        reclassify_btn = QPushButton("重新分类所有文件")
        reclassify_btn.setObjectName("primaryBtn")
        reclassify_btn.clicked.connect(self._reclassify_all)
        top_layout.addWidget(reclassify_btn)

        top_layout.addStretch()

        self.file_count_label = QLabel("")
        self.file_count_label.setObjectName("subtitleLabel")
        top_layout.addWidget(self.file_count_label)

        layout.addLayout(top_layout)

        # 分割器: 左树 + 右列表
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧分类树
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tree_title = QLabel("分类导航")
        tree_title.setStyleSheet("font-weight: bold; color: #cba6f7; padding: 4px;")
        left_layout.addWidget(tree_title)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_tree_click)
        left_layout.addWidget(self.tree)

        splitter.addWidget(left_widget)

        # 右侧文件列表
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 批量操作
        batch_layout = QHBoxLayout()

        rename_btn = QPushButton("批量重命名")
        rename_btn.clicked.connect(self._batch_rename)
        batch_layout.addWidget(rename_btn)

        move_btn = QPushButton("批量移动")
        move_btn.clicked.connect(self._batch_move)
        batch_layout.addWidget(move_btn)

        batch_layout.addStretch()

        self.selected_label = QLabel("")
        self.selected_label.setObjectName("subtitleLabel")
        batch_layout.addWidget(self.selected_label)

        right_layout.addLayout(batch_layout)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels(["文件名", "路径", "类型", "大小", "修改时间", "分类"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.file_table.setSortingEnabled(True)
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self._show_context_menu)
        self.file_table.itemSelectionChanged.connect(self._on_selection_changed)
        right_layout.addWidget(self.file_table)

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

        right_layout.addLayout(page_layout)

        # 分类进度条（默认隐藏）
        self.reclassify_progress = QProgressBar()
        self.reclassify_progress.setVisible(False)
        right_layout.addWidget(self.reclassify_progress)

        self.reclassify_label = QLabel("")
        self.reclassify_label.setObjectName("subtitleLabel")
        self.reclassify_label.setVisible(False)
        right_layout.addWidget(self.reclassify_label)

        splitter.addWidget(right_widget)
        splitter.setSizes([200, 800])

        layout.addWidget(splitter, 1)

    def refresh_data(self):
        self._build_tree()
        self._load_all_files()

    def _build_tree(self):
        self.tree.clear()
        try:
            tree_data = self.classifier.get_classification_tree()
        except Exception:
            tree_data = {}

        # 全部文件
        all_item = QTreeWidgetItem(self.tree, ["全部文件"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, ('all', None))

        for category, items in tree_data.items():
            parent = QTreeWidgetItem(self.tree, [category])
            parent.setExpanded(True)
            for value, count in items:
                child = QTreeWidgetItem(parent, [f"{value} ({count})"])
                child.setData(0, Qt.ItemDataRole.UserRole, (category, value))

        self.tree.expandAll()

    def _on_tree_click(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.current_page = 0
        category, value = data
        if category == 'all':
            self._load_all_files()
        else:
            self._load_files_by_classification(category, value)

    def _load_all_files(self):
        try:
            files = self.file_dao.get_all_active()
            self._populate_table(files)
        except Exception as e:
            logger.error(f"加载文件失败: {e}")

    def _load_files_by_classification(self, cls_type, cls_value):
        try:
            type_map = {'按类型': 'by_type', '按日期': 'by_date', '按关键词': 'by_keyword'}
            db_type = type_map.get(cls_type, cls_type)
            sql = """SELECT f.* FROM files f
                     JOIN file_classifications c ON f.id = c.file_id
                     WHERE c.classification_type = %s AND c.classification_value = %s
                     AND f.status = 'active'"""
            files = db.execute_query(sql, (db_type, cls_value))
            self._populate_table(files)
        except Exception as e:
            logger.error(f"加载分类文件失败: {e}")

    def _populate_table(self, files):
        self.current_files = files
        total = len(files)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        # 修正当前页范围
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1

        start = self.current_page * self.page_size
        end = min(start + self.page_size, total)
        page_files = files[start:end]

        self.file_table.setRowCount(len(page_files))
        self.file_count_label.setText(f"共 {total} 个文件")

        for i, f in enumerate(page_files):
            item = QTableWidgetItem(get_file_icon(f['file_type']) + f['file_name'])
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.file_table.setItem(i, 0, item)
            path = f['file_path']
            display_path = truncate_path(path, 60)
            self.file_table.setItem(i, 1, QTableWidgetItem(display_path))

            type_name = FILE_TYPE_NAMES.get(f['file_type'], f['file_type'])
            type_item = QTableWidgetItem(type_name)
            type_item.setForeground(QBrush(QColor(get_file_color(f['file_type']))))
            self.file_table.setItem(i, 2, type_item)

            size_str = format_size(f['file_size'])
            self.file_table.setItem(i, 3, QTableWidgetItem(size_str))

            mtime = f.get('modify_time', '')
            self.file_table.setItem(i, 4, QTableWidgetItem(str(mtime) if mtime else ""))

            # 获取分类
            try:
                cls_records = self.cls_dao.get_by_file_id(f['id'])
                cls_text = ", ".join(c['classification_value'] for c in cls_records) if cls_records else "-"
            except Exception:
                cls_text = "-"
            self.file_table.setItem(i, 5, QTableWidgetItem(cls_text))

        # 更新分页状态
        total_pages = max(1, (len(self.current_files) + self.page_size - 1) // self.page_size)
        self.page_label.setText(f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_page_btn.setEnabled(self.current_page > 0)
        self.next_page_btn.setEnabled(self.current_page < total_pages - 1)

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._populate_table(self.current_files)

    def _next_page(self):
        total_pages = max(1, (len(self.current_files) + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._populate_table(self.current_files)

    def _on_selection_changed(self):
        count = len(self.file_table.selectionModel().selectedRows())
        self.selected_label.setText(f"已选 {count} 个文件" if count > 0 else "")

    def _show_context_menu(self, pos):
        """文件列表右键菜单"""
        row = self.file_table.rowAt(pos.y())
        if row < 0:
            return
        item = self.file_table.item(row, 0)
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
        permanent_delete_action.setObjectName("dangerBtn")
        permanent_delete_action.triggered.connect(
            lambda: self._context_permanent_delete(file_id))
        menu.addAction(permanent_delete_action)

        menu.exec(self.file_table.viewport().mapToGlobal(pos))

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
            "此操作将从硬盘上彻底删除文件，不可恢复！\n"
            "（操作历史中的撤销不可用于永久删除）",
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

    def _get_selected_ids(self):
        """从表格选中行读取文件ID（基于单元格数据，不受排序影响）"""
        ids = []
        for idx in self.file_table.selectionModel().selectedRows():
            item = self.file_table.item(idx.row(), 0)
            if item:
                fid = item.data(Qt.ItemDataRole.UserRole)
                if fid is not None:
                    ids.append(fid)
        return ids

    def _batch_rename(self):
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要重命名的文件")
            return
        reply = QMessageBox.question(
            self, "确认批量重命名",
            f"将对 {len(ids)} 个文件执行重命名\n格式: 日期_类型_原名\n确定继续?")
        if reply == QMessageBox.StandardButton.Yes:
            batch_id, results = self.file_manager.batch_rename(ids)
            msg = f"批量重命名完成: 成功 {results['success']}, 失败 {results['failed']}"
            notify(self, msg, 'success' if results['failed'] == 0 else 'warning', 4000)
            self.refresh_data()

    def _batch_move(self):
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要移动的文件")
            return
        target = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if not target:
            return
        success = 0
        failed = 0
        for fid in ids:
            try:
                self.file_manager.move_file(fid, target)
                success += 1
            except Exception as e:
                failed += 1
                logger.warning(f"移动失败 ID={fid}: {e}")
        QMessageBox.information(
            self, "移动完成",
            f"成功: {success}\n失败: {failed}")
        self.refresh_data()

    def _reclassify_all(self):
        reply = QMessageBox.question(self, "确认", "重新分类所有文件? 这将清除现有分类结果。")
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 禁用按钮，显示进度
        self.reclassify_progress.setVisible(True)
        self.reclassify_label.setVisible(True)
        self.reclassify_progress.setValue(0)
        self.reclassify_label.setText("正在重新分类...")

        self.worker = ReclassifyWorker(self.classifier)
        self.worker.progress.connect(self._on_reclassify_progress)
        self.worker.finished.connect(self._on_reclassify_finished)
        self.worker.error.connect(self._on_reclassify_error)
        self.worker.start()

    def _on_reclassify_progress(self, current, total):
        self.reclassify_progress.setMaximum(total)
        self.reclassify_progress.setValue(current)
        self.reclassify_label.setText(f"正在分类 ({current}/{total})...")

    def _on_reclassify_finished(self, count):
        self.reclassify_progress.setVisible(False)
        self.reclassify_label.setVisible(False)
        notify(self, f"分类完成: 已分类 {count} 个文件", 'success', 4000)
        self.refresh_data()

    def _on_reclassify_error(self, msg):
        self.reclassify_progress.setVisible(False)
        self.reclassify_label.setVisible(False)
        notify(self, f"分类失败: {msg}", 'error', 5000)
