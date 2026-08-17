"""
文件搜索标签页 - 多条件搜索
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QSpinBox, QDateEdit, QGroupBox, QHeaderView, QMessageBox,
    QCheckBox, QMenu, QApplication, QInputDialog, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QAction, QColor, QBrush, QPalette

import os
import csv
import json
from config import FILE_TYPE_NAMES
from core import FileManager
from core.rule_engine import NLSearchParser
from database.db_manager import db
from database.models import FileDAO, FileContentDAO, SavedQueryDAO
from core.content_indexer import ContentIndexer
from utils.display_utils import format_size, truncate_path, get_file_icon, get_file_color
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class ThemedComboBox(QComboBox):
    """Force the Windows combo popup container to use the active QSS surface.

    Qt creates a private popup QFrame outside the combo's normal widget tree.
    On Windows that frame can retain the native white palette even when the
    QAbstractItemView itself is styled.
    """

    def showPopup(self):
        super().showPopup()
        self._style_popup_container()
        # Some platform styles finish creating the popup after showPopup().
        QTimer.singleShot(0, self._style_popup_container)

    def _style_popup_container(self):
        popup = self.view().window()
        if popup is self.window():
            return

        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Base)
        foreground = palette.color(QPalette.ColorRole.Text)
        # The Windows native palette can report a near-white Mid color even
        # for a dark QSS surface, which reintroduces a visible popup rim.
        border = QColor('#2a2a3e' if background.lightness() < 128 else '#cbd5e1')
        popup_palette = popup.palette()
        popup_palette.setColor(QPalette.ColorRole.Window, background)
        popup_palette.setColor(QPalette.ColorRole.Base, background)
        popup_palette.setColor(QPalette.ColorRole.Text, foreground)
        popup.setPalette(popup_palette)
        popup.setAutoFillBackground(True)
        popup.setContentsMargins(0, 0, 0, 0)
        if popup.layout():
            popup.layout().setContentsMargins(0, 0, 0, 0)
        popup.setStyleSheet(
            f"background-color: {background.name()}; color: {foreground.name()}; "
            f"border: 1px solid {border.name()}; margin: 0; padding: 0;")


class ContentIndexWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            self.finished.emit(ContentIndexer().index_active_files())
        except Exception as exc:
            self.error.emit(str(exc))


class SearchTab(QWidget):
    # 信号：用户点击“AI 搜索”按钮
    ai_search_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.content_dao = FileContentDAO(db)
        self.file_manager = FileManager()
        self.nl_parser = NLSearchParser()
        self.page_size = 100
        self.current_page = 0
        self.total_count = 0
        self._search_params = {}  # 存储搜索条件，翻页时复用
        self._current_files = {}
        self._content_results = []
        self._content_mode = False
        self._content_worker = None
        self._settings = QSettings("FileNest", "FileNest")
        self._collection_dao = SavedQueryDAO(db)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── AI 自然语言搜索栏 ──
        ai_row = QHBoxLayout()
        ai_row.setSpacing(10)
        self.nl_input = QLineEdit()
        self.nl_input.setPlaceholderText("用自然语言描述，如：近一年的文档、大于100MB的图片...（本地规则引擎解析）")
        self.nl_input.setFixedHeight(38)
        self.nl_input.returnPressed.connect(self._do_nl_search)
        self.nl_input.setStyleSheet(
            "QLineEdit {"
            "  border: 2px solid #89b4fa; border-radius: 8px; padding: 4px 14px; font-size: 11pt;"
            "}"
        )
        ai_row.addWidget(self.nl_input, 1)

        self.nl_hint_btn = QPushButton("❓ 语法")
        self.nl_hint_btn.setFixedHeight(38)
        self.nl_hint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nl_hint_btn.setToolTip("查看可用的搜索语法示例")
        self.nl_hint_btn.clicked.connect(self._show_nl_syntax_help)
        ai_row.addWidget(self.nl_hint_btn)

        self.nl_search_btn = QPushButton("🔍 解读")
        self.nl_search_btn.setObjectName("aiSearchBtn")
        self.nl_search_btn.setFixedHeight(38)
        self.nl_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nl_search_btn.setToolTip("规则引擎解析自然语言为搜索条件")
        self.nl_search_btn.clicked.connect(self._do_nl_search)
        self.nl_search_btn.setStyleSheet(
            "QPushButton#aiSearchBtn {"
            "  background: #89b4fa; color: #1e1e2e; border: none;"
            "  border-radius: 8px; padding: 8px 20px; font-weight: bold; font-size: 11pt;"
            "}"
            "QPushButton#aiSearchBtn:hover { background: #b4d0fb; }"
        )
        ai_row.addWidget(self.nl_search_btn)

        self.ai_chat_btn = QPushButton("💬 AI 对话")
        self.ai_chat_btn.setFixedHeight(38)
        self.ai_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_chat_btn.setToolTip("打开 AI 对话式搜索，支持联网")
        self.ai_chat_btn.clicked.connect(self.ai_search_clicked.emit)
        self.ai_chat_btn.setStyleSheet(
            "QPushButton {"
            "  background: #cba6f7; color: #1e1e2e; border: none;"
            "  border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 10pt;"
            "}"
            "QPushButton:hover { background: #d4bfff; }"
        )
        ai_row.addWidget(self.ai_chat_btn)
        layout.addLayout(ai_row)

        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("最近搜索:"))
        self.history_combo = ThemedComboBox()
        self.history_combo.setMinimumWidth(260)
        self.history_combo.addItem("选择历史记录...", None)
        self._reload_search_history()
        self.history_combo.activated.connect(self._apply_history)
        history_row.addWidget(self.history_combo)
        clear_history_btn = QPushButton("清除历史")
        clear_history_btn.clicked.connect(self._clear_search_history)
        history_row.addWidget(clear_history_btn)
        history_row.addStretch()
        self.filter_toggle_btn = QPushButton("展开高级筛选")
        self.filter_toggle_btn.setToolTip("显示文件类型、大小、日期和重复文件筛选条件")
        self.filter_toggle_btn.clicked.connect(self._toggle_advanced_filters)
        history_row.addWidget(self.filter_toggle_btn)
        self.content_search_cb = QCheckBox("搜索正文")
        self.content_search_cb.setToolTip("在已建立的本地文档内容索引中搜索")
        history_row.addWidget(self.content_search_cb)
        self.index_content_btn = QPushButton("构建正文索引")
        self.index_content_btn.setToolTip("索引支持读取的文本、PDF 和 DOCX 文件，不会上传内容")
        self.index_content_btn.clicked.connect(self._build_content_index)
        history_row.addWidget(self.index_content_btn)
        layout.addLayout(history_row)

        collection_row = QHBoxLayout()
        collection_row.addWidget(QLabel("智能集合:"))
        self.collection_combo = ThemedComboBox()
        self.collection_combo.addItem("选择已保存的集合...", None)
        self.collection_combo.activated.connect(self._apply_collection)
        collection_row.addWidget(self.collection_combo)
        save_collection_btn = QPushButton("保存当前条件")
        save_collection_btn.clicked.connect(self._save_collection)
        collection_row.addWidget(save_collection_btn)
        delete_collection_btn = QPushButton("删除集合")
        delete_collection_btn.clicked.connect(self._delete_collection)
        collection_row.addWidget(delete_collection_btn)
        collection_row.addStretch()
        layout.addLayout(collection_row)
        self._reload_collections()

        # 搜索条件区
        self.search_group = QGroupBox("高级搜索条件")
        search_layout = QVBoxLayout(self.search_group)

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
        self.type_combo = ThemedComboBox()
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
        self.dup_combo = ThemedComboBox()
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

        layout.addWidget(self.search_group)
        self._set_advanced_filters_expanded(False)

        self.filter_summary = QLabel("当前条件：未设置")
        self.filter_summary.setObjectName("subtitleLabel")
        self.filter_summary.setWordWrap(True)
        layout.addWidget(self.filter_summary)

        # 结果统计
        stats_layout = QHBoxLayout()
        self.result_label = QLabel("请输入搜索条件")
        self.result_label.setObjectName("subtitleLabel")
        stats_layout.addWidget(self.result_label)
        stats_layout.addStretch()

        stats_layout.addWidget(QLabel("排序:"))
        self.sort_combo = ThemedComboBox()
        self.sort_combo.addItem("相关度/默认", -1)
        self.sort_combo.addItem("文件名", 0)
        self.sort_combo.addItem("大小", 3)
        self.sort_combo.addItem("修改时间", 4)
        self.sort_combo.currentIndexChanged.connect(self._sort_current_page)
        stats_layout.addWidget(self.sort_combo)

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
        self.result_table.verticalHeader().setDefaultSectionSize(34)
        self.result_table.verticalHeader().setMinimumSectionSize(30)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setSortingEnabled(True)
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_context_menu)
        self.result_table.itemSelectionChanged.connect(self._update_result_detail)
        layout.addWidget(self.result_table, 1)

        self.result_detail = QLabel("选择一个文件查看路径、大小和修改时间")
        self.result_detail.setObjectName("subtitleLabel")
        self.result_detail.setWordWrap(True)
        self.result_detail.setMinimumHeight(42)
        self.result_detail.setContentsMargins(10, 6, 10, 6)
        layout.addWidget(self.result_detail)

        # 空状态引导
        self._empty_state = create_empty_state(
            'search', "重试搜索", self._load_page, parent=self)
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

    def _toggle_advanced_filters(self):
        self._set_advanced_filters_expanded(not self.search_group.isVisible())

    def _set_advanced_filters_expanded(self, expanded: bool):
        self.search_group.setVisible(expanded)
        self.filter_toggle_btn.setText(
            "收起高级筛选" if expanded else "展开高级筛选")
        self.filter_toggle_btn.setToolTip(
            "收起筛选条件以显示更多结果" if expanded
            else "显示文件类型、大小、日期和重复文件筛选条件")

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
        self.result_label.setStyleSheet("")
        self._remember_search(self.name_input.text().strip() or self.nl_input.text().strip())
        self._update_filter_summary()
        self._set_advanced_filters_expanded(False)
        self.current_page = 0
        if self.content_search_cb.isChecked():
            self._do_content_search()
            return
        self._content_mode = False
        self._load_page()

    def _build_content_index(self):
        if self._content_worker and self._content_worker.isRunning():
            return
        self.index_content_btn.setEnabled(False)
        self.index_content_btn.setText("正在构建...")
        self._content_worker = ContentIndexWorker(self)
        self._content_worker.finished.connect(self._on_content_index_done)
        self._content_worker.error.connect(self._on_content_index_error)
        self._content_worker.start()

    def _on_content_index_done(self, result: dict):
        self.index_content_btn.setEnabled(True)
        self.index_content_btn.setText("构建正文索引")
        self._content_worker = None
        notify(self, f"正文索引完成：已索引 {result['indexed']}，跳过 {result['skipped']}，失败 {result['failed']}", 'success', 5000)

    def _on_content_index_error(self, error: str):
        self.index_content_btn.setEnabled(True)
        self.index_content_btn.setText("构建正文索引")
        self._content_worker = None
        QMessageBox.warning(self, "正文索引失败", error)

    def _do_content_search(self):
        query = self._search_params.get('name') or self.nl_input.text().strip()
        if not query:
            QMessageBox.information(self, "搜索正文", "请输入要在文档正文中查找的关键词")
            return
        records = self.content_dao.search(query, limit=1000)
        def matches(record):
            if self._search_params.get('file_type') and record.get('file_type') != self._search_params['file_type']:
                return False
            if self._search_params.get('min_size') is not None and record.get('file_size', 0) < self._search_params['min_size']:
                return False
            if self._search_params.get('max_size') is not None and record.get('file_size', 0) > self._search_params['max_size']:
                return False
            if self._search_params.get('is_duplicate') is not None and record.get('is_duplicate') != self._search_params['is_duplicate']:
                return False
            modified = str(record.get('modify_time') or '')
            if self._search_params.get('start_date') and modified < self._search_params['start_date']:
                return False
            if self._search_params.get('end_date') and modified > self._search_params['end_date']:
                return False
            return True
        self._content_results = [record for record in records if matches(record)]
        self._content_mode = True
        self.total_count = len(self._content_results)
        self.current_page = 0
        self._load_page()

    def _load_page(self):
        """服务端分页：每次只查询当前页数据"""
        if not self._search_params:
            return

        if self._content_mode:
            start = self.current_page * self.page_size
            self._populate_results(self._content_results[start:start + self.page_size])
            return
        # AI 来源的结果也用正常分页
        self._search_params.pop("_ai_mode", None)
        self._search_params.pop("_ai_files", None)

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
            self.result_table.setVisible(False)
            self._empty_state.show_error(f"搜索请求失败：{e}")

    def _populate_results(self, files):
        total = self.total_count
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        # 空状态检测
        self._empty_state.setVisible(total == 0)
        self.result_table.setVisible(total > 0)

        # 修正当前页范围
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1

        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(len(files))
        self._current_files = {f['id']: f for f in files}
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

        self.result_table.setSortingEnabled(True)
        self._sort_current_page()

        self.result_label.setText(f"共 {total} 个文件")
        self.total_size_label.setText(f"当前页: {format_size(total_size)}")

        # 更新分页状态
        self.page_label.setText(f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_page_btn.setEnabled(self.current_page > 0)
        self.next_page_btn.setEnabled(self.current_page < total_pages - 1)
        self.export_btn.setVisible(total > 0)
        self.result_detail.setText(
            "选择一个文件查看路径、大小和修改时间" if total else "没有可显示的搜索结果")

    def _update_filter_summary(self):
        labels = []
        if self._search_params.get('name'):
            labels.append(f"名称: {self._search_params['name']}")
        if self._search_params.get('file_type'):
            labels.append(f"类型: {FILE_TYPE_NAMES.get(self._search_params['file_type'], self._search_params['file_type'])}")
        if self._search_params.get('min_size'):
            labels.append(f"最小: {format_size(self._search_params['min_size'])}")
        if self._search_params.get('max_size'):
            labels.append(f"最大: {format_size(self._search_params['max_size'])}")
        if self._search_params.get('start_date'):
            labels.append(f"日期: {self._search_params['start_date'][:10]} 至 {self._search_params['end_date'][:10]}")
        dup = self._search_params.get('is_duplicate')
        if dup is not None:
            labels.append("仅重复文件" if dup else "排除重复文件")
        self.filter_summary.setText("当前条件：" + (" · ".join(labels) if labels else "全部文件"))

    def _sort_current_page(self):
        column = self.sort_combo.currentData() if hasattr(self, 'sort_combo') else -1
        if column is not None and column >= 0:
            self.result_table.sortItems(column, Qt.SortOrder.AscendingOrder)

    def _update_result_detail(self):
        rows = self.result_table.selectionModel().selectedRows()
        if len(rows) != 1:
            self.result_detail.setText(
                f"已选择 {len(rows)} 个文件" if rows else "选择一个文件查看路径、大小和修改时间")
            return
        item = self.result_table.item(rows[0].row(), 0)
        record = self._current_files.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        if not record:
            return
        self.result_detail.setText(
            f"{record['file_name']}\n{record['file_path']}  ·  "
            f"{format_size(record.get('file_size', 0))}  ·  修改于 {record.get('modify_time') or '-'}"
            + (f"\n正文命中：{record['content_snippet']}" if record.get('content_snippet') else ""))

    def _history_values(self):
        values = self._settings.value("search/history", [], type=list)
        return [str(value) for value in values if str(value).strip()]

    def _reload_search_history(self):
        if not hasattr(self, 'history_combo'):
            return
        current = self.history_combo.currentText() if self.history_combo.count() else ""
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        self.history_combo.addItem("选择历史记录...", None)
        for value in self._history_values():
            self.history_combo.addItem(value, value)
        self.history_combo.setCurrentText(current)
        self.history_combo.blockSignals(False)

    def _remember_search(self, text: str):
        text = text.strip()
        if not text:
            return
        values = [value for value in self._history_values() if value != text]
        self._settings.setValue("search/history", [text] + values[:9])
        self._reload_search_history()

    def _apply_history(self, index: int):
        value = self.history_combo.itemData(index)
        if value:
            self.name_input.setText(value)
            self._do_search()

    def _clear_search_history(self):
        self._settings.remove("search/history")
        self._reload_search_history()

    def _collections(self):
        return self._collection_dao.get_all()

    def _reload_collections(self):
        if not hasattr(self, 'collection_combo'):
            return
        self.collection_combo.blockSignals(True)
        self.collection_combo.clear()
        self.collection_combo.addItem("选择已保存的集合...", None)
        for collection in self._collections():
            self.collection_combo.addItem(collection.get('name', '未命名集合'), collection)
        self.collection_combo.blockSignals(False)

    def _save_collection(self):
        if not self._search_params:
            QMessageBox.information(self, "保存智能集合", "请先执行一次搜索")
            return
        name, ok = QInputDialog.getText(self, "保存智能集合", "集合名称:")
        if not ok or not name.strip():
            return
        params = {key: value for key, value in self._search_params.items()
                  if not key.startswith('_')}
        self._collection_dao.upsert(name.strip(), params)
        self._reload_collections()
        notify(self, f"已保存智能集合：{name.strip()}", 'success', 3000)

    def _apply_collection(self, index: int):
        collection = self.collection_combo.itemData(index)
        if collection:
            self._apply_search_params(collection.get('params', {}), source="智能集合")

    def _delete_collection(self):
        index = self.collection_combo.currentIndex()
        collection = self.collection_combo.itemData(index)
        if not collection:
            QMessageBox.information(self, "删除智能集合", "请先选择一个集合")
            return
        self._collection_dao.delete(collection.get('name'))
        self._reload_collections()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._load_page()

    def _next_page(self):
        total_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._load_page()

    def _do_nl_search(self):
        """自然语言搜索：使用规则引擎解析为结构化参数"""
        query = self.nl_input.text().strip()
        if not query:
            return

        self.result_label.setText("🔍 正在解析...")
        self.result_label.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")

        params = self.nl_parser.parse_with_explanation(query)
        if params and any(key in params for key in
                          ('name', 'file_type', 'extension', 'min_size',
                           'max_size', 'start_date', 'end_date', 'is_duplicate')):
            self._remember_search(query)
            self._apply_search_params(params, source="规则")
        else:
            self.result_label.setText(
                "无法解析，请尝试更明确的描述或点击「❓ 语法」查看示例。")
            self.result_label.setStyleSheet("color: #f38ba8; font-size: 13px;")

    def _show_nl_syntax_help(self):
        """展示自然语言搜索语法提示"""
        QMessageBox.information(
            self, "搜索语法提示",
            "支持用自然语言组合以下条件（中英文均可）：\n\n"
            + self.nl_parser.syntax_help()
            + "\n\n示例：\n"
            + "· 最近一周大于100MB的图片\n"
            + "· 上周修改的PDF文档\n"
            + "· 重复文件")

    def _apply_search_params(self, params: dict, source: str = ""):
        """将 AI 解析的参数填入搜索条件并执行搜索"""
        # 排除内部字段
        self._search_params = {
            'name': params.get('name'),
            'file_type': params.get('file_type'),
            'min_size': params.get('min_size'),
            'max_size': params.get('max_size'),
            'start_date': params.get('start_date'),
            'end_date': params.get('end_date'),
            'is_duplicate': params.get('is_duplicate'),
        }
        # 同步到 UI 控件
        self.name_input.setText(params.get('name') or '')
        if params.get('file_type'):
            idx = self.type_combo.findData(params['file_type'])
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        if params.get('min_size'):
            self.min_size.setValue(max(0, params['min_size'] // 1024))
        if params.get('max_size'):
            self.max_size.setValue(max(0, params['max_size'] // (1024 * 1024)))
        if params.get('start_date') or params.get('end_date'):
            self.use_date_cb.setChecked(True)
            if params.get('start_date'):
                try:
                    self.start_date.setDate(QDate.fromString(params['start_date'][:10], "yyyy-MM-dd"))
                except Exception:
                    pass
            if params.get('end_date'):
                try:
                    self.end_date.setDate(QDate.fromString(params['end_date'][:10], "yyyy-MM-dd"))
                except Exception:
                    pass

        self.current_page = 0
        self.total_count = 0
        self._update_filter_summary()
        self._set_advanced_filters_expanded(False)
        self._load_page()
        explanation = params.get('explanation', '')
        source_text = f" ({source})" if source else ""
        self.result_label.setText(f"🤖 {explanation or 'AI 解读完成'}{source_text}")
        self.result_label.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 13px;")



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
        self._content_mode = False
        self._content_results = []
        self.content_search_cb.setChecked(False)
        self._current_files = {}
        self.result_table.setRowCount(0)
        self.result_table.setVisible(False)
        self._empty_state.show_empty()
        self.result_label.setText("请输入搜索条件")
        self.result_label.setStyleSheet("")
        self.total_size_label.setText("")
        self.page_label.setText("第 0 页 / 共 0 页")
        self.prev_page_btn.setEnabled(False)
        self.next_page_btn.setEnabled(False)
        self.export_btn.setVisible(False)
        self.filter_summary.setText("当前条件：未设置")
        self.result_detail.setText("选择一个文件查看路径、大小和修改时间")

    def display_ai_results(self, result: dict):
        """接收 AI 搜索结果，通过数据库分页展示到表格"""
        params = result.get("params", {})
        # 从 AI 解析结果提取结构化条件
        clean = {
            'name': params.get('name'),
            'file_type': params.get('file_type'),
            'min_size': params.get('min_size'),
            'max_size': params.get('max_size'),
            'start_date': params.get('start_date'),
            'end_date': params.get('end_date'),
        }
        clean = {k: v for k, v in clean.items() if v is not None}
        self._apply_search_params(clean, source="ai")

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

        file_path = record.get('file_path', '')
        file_path = os.path.normpath(file_path) if isinstance(file_path, str) and file_path else ''

        menu = QMenu(self)

        # 修复：用具名函数 + 显式参数，避免 PyQt6 QAction.triggered(bool) 默认参数陷阱
        def _do_open_file(checked=False, fp=file_path, fid=file_id):
            self._safe_open_file(fp, file_id=fid)

        def _do_open_folder(checked=False, fp=file_path, fid=file_id):
            self._safe_open_folder(fp, file_id=fid)

        open_action = QAction("打开文件", self)
        open_action.triggered.connect(_do_open_file)
        menu.addAction(open_action)

        open_folder_action = QAction("打开所在文件夹", self)
        open_folder_action.triggered.connect(_do_open_folder)
        menu.addAction(open_folder_action)

        menu.addSeparator()

        copy_path_action = QAction("复制路径", self)
        copy_path_action.triggered.connect(
            lambda: QApplication.clipboard().setText(file_path))
        menu.addAction(copy_path_action)

        copy_name_action = QAction("复制文件名", self)
        copy_name_action.triggered.connect(
            lambda: QApplication.clipboard().setText(record['file_name']))
        menu.addAction(copy_name_action)

        menu.addSeparator()

        # ── AI 功能 ──
        from core.ai_layer import AILayer
        ai_check = AILayer()
        if ai_check.enabled:
            ai_desc_action = QAction("🤖 AI 描述此文件", self)
            ai_desc_action.triggered.connect(
                lambda: self._ai_describe_file(file_id))
            menu.addAction(ai_desc_action)

            ai_rename_action = QAction("🤖 AI 建议重命名", self)
            ai_rename_action.triggered.connect(
                lambda: self._ai_suggest_rename(file_id))
            menu.addAction(ai_rename_action)

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

    def _safe_open_file(self, file_path, file_id=None):
        """安全打开文件，文件不存在时给出友好提示

        修复：兼容 file_path 为空/False/非字符串等异常情况，
        优先尝试用 file_id 从数据库反查真实路径。
        """
        # 路径无效判定（兼容空串、False 字符串、None 等异常值）
        BAD_VALUES = ('', 'False', 'True', 'false', 'true', '0', 'null', 'None')
        needs_lookup = (
            file_path is None
            or not isinstance(file_path, str)
            or file_path.strip() in BAD_VALUES
        )

        if needs_lookup and file_id is not None:
            try:
                rec = self.file_dao.get_by_id(file_id)
                if rec and rec.get('file_path'):
                    file_path = rec['file_path']
                    logger.info(f"路径无效已用 file_id={file_id} 反查: {file_path!r}")
            except Exception as e:
                logger.warning(f"反查 file_id={file_id} 失败: {e}")

        # 再次校验
        if (file_path is None
                or not isinstance(file_path, str)
                or file_path.strip() in BAD_VALUES):
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            logger.warning(
                f"文件路径无效: {file_path!r} (type: {type(file_path).__name__})")
            return

        logger.debug(f"尝试打开文件: {file_path}")
        file_path = os.path.normpath(file_path)
        logger.debug(f"标准化后路径: {file_path}")

        if not os.path.exists(file_path):
            notify(self, f"文件不存在: {os.path.basename(file_path)}", 'warning', 4000)
            logger.warning(f"尝试打开不存在的文件: {file_path}")
            return

        try:
            os.startfile(file_path)
            logger.info(f"成功打开文件: {file_path}")
        except Exception as e:
            notify(self, f"无法打开文件: {e}", 'error', 5000)
            logger.error(f"打开文件失败: {file_path}, 错误: {e}")

    def _safe_open_folder(self, file_path, file_id=None):
        """安全打开所在文件夹

        修复：兼容 file_path 为空/False/非字符串等异常情况，
        优先尝试用 file_id 从数据库反查真实路径。
        """
        BAD_VALUES = ('', 'False', 'True', 'false', 'true', '0', 'null', 'None')
        needs_lookup = (
            file_path is None
            or not isinstance(file_path, str)
            or file_path.strip() in BAD_VALUES
        )

        if needs_lookup and file_id is not None:
            try:
                rec = self.file_dao.get_by_id(file_id)
                if rec and rec.get('file_path'):
                    file_path = rec['file_path']
                    logger.info(f"路径无效已用 file_id={file_id} 反查: {file_path!r}")
            except Exception as e:
                logger.warning(f"反查 file_id={file_id} 失败: {e}")

        if (file_path is None
                or not isinstance(file_path, str)
                or file_path.strip() in BAD_VALUES):
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            logger.warning(
                f"文件路径无效: {file_path!r} (type: {type(file_path).__name__})")
            return

        logger.debug(f"尝试打开文件夹: {file_path}")
        file_path = os.path.normpath(file_path)
        folder = os.path.dirname(file_path)
        logger.debug(f"文件夹路径: {folder}")

        if not folder or not os.path.exists(folder):
            notify(self, "文件所在目录已不存在", 'warning', 4000)
            logger.warning(f"文件夹不存在: {folder}")
            return

        try:
            os.startfile(folder)
            logger.info(f"成功打开文件夹: {folder}")
        except Exception as e:
            notify(self, f"无法打开文件夹: {e}", 'error', 5000)
            logger.error(f"打开文件夹失败: {folder}, 错误: {e}")

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

    def _ai_describe_file(self, file_id):
        """AI 描述单个文件 —— 后台线程调用（优先内容级分析）"""
        from core.ai_layer import AILayer
        from core.file_reader import read_file_content
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return

        self.result_label.setText("🤖 AI 正在分析文件...")
        self.result_label.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")

        class _DescWorker(QThread):
            done = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, ai_layer, record, parent=None):
                super().__init__(parent)
                self.ai_layer = ai_layer
                self.record = record

            def run(self):
                try:
                    # 尝试读取文件内容做深度分析
                    file_path = self.record.get('file_path', '')
                    content = read_file_content(file_path) if file_path else None

                    if content:
                        # 内容级分析
                        from config import FILE_TYPE_NAMES as FTN
                        from utils.display_utils import format_size
                        result = self.ai_layer.summarize_file_content(
                            file_name=self.record.get('file_name', ''),
                            file_path=file_path,
                            file_type=FTN.get(self.record.get('file_type', ''), '未知'),
                            file_size=format_size(self.record.get('file_size', 0)),
                            modify_time=str(self.record.get('modify_time', '')),
                            file_content=content,
                        )
                    else:
                        # 降级：仅元数据分析
                        result = self.ai_layer.describe_file(self.record)

                    self.done.emit(result or "无法生成描述")
                except Exception as e:
                    self.error.emit(str(e))

        ai = AILayer()
        self._desc_worker = _DescWorker(ai, record, self)
        self._desc_worker.done.connect(self._on_ai_desc_done)
        self._desc_worker.error.connect(self._on_ai_desc_error)
        self._desc_worker.start()

    def _on_ai_desc_done(self, text: str):
        self._desc_worker = None
        self.result_label.setText(f"🤖 AI 描述: {text}")
        self.result_label.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 12px;")
        QMessageBox.information(self, "🤖 AI 文件描述", text)

    def _on_ai_desc_error(self, err: str):
        self._desc_worker = None
        self.result_label.setText(f"AI 描述失败: {err}")
        self.result_label.setStyleSheet("color: #f38ba8; font-size: 12px;")
        logger.warning(f"AI 描述文件失败: {err}")

    def _ai_suggest_rename(self, file_id):
        """AI 智能重命名建议 —— 后台线程调用"""
        from core.ai_layer import AILayer
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return

        self.result_label.setText("🤖 AI 正在生成重命名建议...")
        self.result_label.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")

        class _RenameWorker(QThread):
            done = pyqtSignal(list)
            error = pyqtSignal(str)

            def __init__(self, ai_layer, record, parent=None):
                super().__init__(parent)
                self.ai_layer = ai_layer
                self.record = record

            def run(self):
                try:
                    from utils.display_utils import format_size
                    suggestions = self.ai_layer.suggest_rename(
                        file_name=self.record.get('file_name', ''),
                        file_path=self.record.get('file_path', ''),
                        file_type=self.record.get('file_type', 'unknown'),
                        file_size=format_size(self.record.get('file_size', 0)),
                        modify_time=str(self.record.get('modify_time', '')),
                    )
                    self.done.emit(suggestions or [])
                except Exception as e:
                    self.error.emit(str(e))

        ai = AILayer()
        self._rename_worker = _RenameWorker(ai, record, self)
        self._rename_worker.done.connect(self._on_ai_rename_done)
        self._rename_worker.error.connect(self._on_ai_rename_error)
        self._rename_worker.start()

    def _on_ai_rename_done(self, suggestions: list):
        self._rename_worker = None
        self.result_label.setText("")
        self.result_label.setStyleSheet("")

        if not suggestions:
            QMessageBox.information(self, "🤖 AI 重命名", "无法生成重命名建议。")
            return

        # 获取 file_id（从 _rename_worker 的 record 中）
        file_id = getattr(self._rename_worker, 'record', {}).get('file_id') if hasattr(self, '_rename_worker') else None

        # 让用户从建议中选择
        items = []
        for i, s in enumerate(suggestions[:3], 1):
            items.append(f"{i}. {s}")
        chosen, ok = QInputDialog.getItem(
            self, "🤖 AI 重命名建议",
            "选择一个建议（取消则手动输入）：",
            items, 0, False
        )
        if ok and chosen:
            name = chosen.split(". ", 1)[-1]
            new_name, ok2 = QInputDialog.getText(
                self, "确认重命名", "新文件名：", text=name
            )
            if ok2 and new_name.strip() and file_id:
                self._do_rename_file(file_id=file_id, new_name=new_name.strip())

    def _on_ai_rename_error(self, err: str):
        self._rename_worker = None
        self.result_label.setText(f"AI 重命名失败: {err}")
        self.result_label.setStyleSheet("color: #f38ba8; font-size: 12px;")
        logger.warning(f"AI 重命名建议失败: {err}")

    def _do_rename_file(self, file_id, new_name):
        """执行重命名"""
        try:
            record = self.file_dao.get_by_id(file_id)
            if not record:
                return
            old_path = record.get('file_path', '')
            if not old_path or not os.path.exists(old_path):
                QMessageBox.warning(self, "重命名失败", "文件不存在")
                return
            dir_path = os.path.dirname(old_path)
            new_path = os.path.join(dir_path, new_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "重命名失败", f"目标文件已存在: {new_name}")
                return
            os.rename(old_path, new_path)
            self.file_dao.update_name(file_id, new_name, new_path)
            notify(self, f"已重命名为: {new_name}", 'success', 3000)
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "重命名失败", str(e))

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



