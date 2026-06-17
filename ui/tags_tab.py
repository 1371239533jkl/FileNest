"""
标签管理标签页 - 标签云(流式) + 文件列表
"""
import hashlib
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox,
    QHeaderView, QInputDialog, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from database.db_manager import db
from database.models import FileDAO, TagDAO
from core import TagManager
from utils.display_utils import format_size, truncate_path, get_file_icon, get_file_color
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


_TAG_COLORS = [
    ('#cba6f7', '#1e1e2e'), ('#89b4fa', '#1e1e2e'),
    ('#a6e3a1', '#1e1e2e'), ('#f9e2af', '#1e1e2e'),
    ('#fab387', '#1e1e2e'), ('#94e2d5', '#1e1e2e'),
    ('#f38ba8', '#1e1e2e'), ('#bac2de', '#1e1e2e'),
]
_TAG_LIGHT = [
    ('#cba6f7', '#ffffff'), ('#89b4fa', '#ffffff'),
    ('#a6e3a1', '#1e1e2e'), ('#f9e2af', '#1e1e2e'),
    ('#fab387', '#1e1e2e'), ('#94e2d5', '#1e1e2e'),
    ('#f38ba8', '#ffffff'), ('#bac2de', '#1e1e2e'),
]


def _ci(name: str) -> int:
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 8


class TagsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self.tag_dao = TagDAO(db)
        self.tag_manager = TagManager()
        self.current_files = []
        self.current_tag = None
        self.page_size = 100
        self.current_page = 0
        self._total_count = 0
        self._theme = 'dark'
        self._init_ui()
        self._build_cloud()
        self._load_all()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶部操作栏
        top = QHBoxLayout()
        for text, obj, fn in [
            ("➕ 新建标签", "primaryBtn", self._create_tag),
            ("🗑 删除标签", "dangerBtn", self._delete_tag),
            (None, None, None),
            ("🏷 打标签", "successBtn", self._batch_tag),
            ("✂️ 移除标签", None, self._batch_untag),
        ]:
            if text is None:
                top.addSpacing(8)
            else:
                b = QPushButton(text)
                if obj: b.setObjectName(obj)
                b.clicked.connect(fn)
                b.setFixedHeight(30)
                top.addWidget(b)
        top.addStretch()
        self.cnt = QLabel("")
        self.cnt.setObjectName("subtitleLabel")
        top.addWidget(self.cnt)
        layout.addLayout(top)

        # 分割
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.setHandleWidth(1)

        # ── 左侧：标签云（QScrollArea + QVBoxLayout，全宽按钮） ──
        left = QWidget()
        left.setMinimumWidth(160)
        left.setMaximumWidth(300)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(2)
        tl = QLabel("标签云")
        tl.setStyleSheet("font-weight: bold; color: #cba6f7; padding: 2px 4px; font-size: 13px;")
        lv.addWidget(tl)

        # 标签按钮容器（垂直排列，每个标签占一整行）
        self.cloud_scroll = QScrollArea()
        self.cloud_scroll.setWidgetResizable(True)
        self.cloud_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cloud_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cloud_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        self.cloud_container = QWidget()
        self.cloud_container.setStyleSheet("background: transparent;")
        self.cloud_layout = QVBoxLayout(self.cloud_container)
        self.cloud_layout.setContentsMargins(4, 4, 4, 4)
        self.cloud_layout.setSpacing(4)
        self.cloud_layout.addStretch()
        self.cloud_scroll.setWidget(self.cloud_container)

        lv.addWidget(self.cloud_scroll, 1)

        sp.addWidget(left)

        # ── 右侧 ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(5)
        self.tbl.setHorizontalHeaderLabels(["文件名", "路径", "类型", "大小", "标签"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.tbl.setSortingEnabled(True)
        rv.addWidget(self.tbl)

        # ── 分页控件 ──
        pag_layout = QHBoxLayout()
        pag_layout.setContentsMargins(0, 8, 0, 8)
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self._prev_page)
        self.prev_btn.setFixedHeight(30)
        self.prev_btn.setFixedWidth(80)
        pag_layout.addWidget(self.prev_btn)

        pag_layout.addStretch()
        self.page_label = QLabel("第 1 页 / 共 1 页")
        self.page_label.setObjectName("subtitleLabel")
        pag_layout.addWidget(self.page_label)
        pag_layout.addStretch()

        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self._next_page)
        self.next_btn.setFixedHeight(30)
        self.next_btn.setFixedWidth(80)
        pag_layout.addWidget(self.next_btn)
        rv.addLayout(pag_layout)

        sp.addWidget(right)
        sp.setSizes([180, 820])
        layout.addWidget(sp, 1)

        # 空状态引导
        self._empty_state = create_empty_state('tags', parent=self)
        layout.addWidget(self._empty_state)

    # ── 标签云构建 ──

    def _build_cloud(self):
        self._selected_tag = None
        self._clear_cloud()

        tags = self.tag_dao.get_all_tags()
        palette = _TAG_LIGHT if self._theme == 'light' else _TAG_COLORS

        # 空状态检测
        has_tags = len(tags) > 0
        self._empty_state.setVisible(not has_tags)

        # 全部文件 —— 使用调色板配色，与普通标签风格统一
        all_bg, all_fg = ('#585b70', '#cdd6f4') if self._theme == 'light' else ('#45475a', '#cdd6f4')
        all_btn = self._make_btn(" 全部文件 ", all_bg, all_fg)
        all_btn.clicked.connect(lambda: self._on_tag_click(None))
        self.cloud_layout.addWidget(all_btn)

        for t in tags:
            nm = t['tag_name']
            bg, fg = palette[_ci(nm)]

            btn = self._make_btn(f" {nm} ", bg, fg)
            btn.clicked.connect(lambda checked, n=nm: self._on_tag_click(n))
            self.cloud_layout.addWidget(btn)

        self.cloud_layout.addStretch()  # 底部弹簧，标签按钮从顶部开始

    def _make_btn(self, text: str, bg: str, fg: str, pt: int = 13) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(pt + 18)
        btn.setMinimumHeight(32)
        radius = max(8, pt + 2)
        # 显式覆盖全局 QPushButton 的 border / hover / pressed，防止样式穿透
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {bg};"
            f"  color: {fg};"
            f"  border: none;"
            f"  border-radius: {radius}px;"
            f"  text-align: left;"
            f"  padding: 4px 12px;"
            f"  font-size: {pt}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: {bg}; }}"
            f"QPushButton:pressed {{ background-color: {bg}; }}"
        )
        return btn

    def _clear_cloud(self):
        while self.cloud_layout.count():
            it = self.cloud_layout.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()

    def _on_tag_click(self, tag_name):
        self.current_tag = tag_name
        self.current_page = 0
        if tag_name is None:
            self._load_all()
        else:
            self._load_by(tag_name)

    def apply_theme(self, tn: str):
        self._theme = tn
        self._build_cloud()

    def refresh_data(self):
        self.current_page = 0
        self._build_cloud()
        if self.current_tag:
            self._load_by(self.current_tag)
        else:
            self._load_all()

    # ── 文件加载 ──

    def _load_all(self):
        try:
            self._total_count = self.file_dao.count_active()
            files = self.file_dao.get_all_active_paginated(
                page=self.current_page, page_size=self.page_size)
            self._fill(files)
        except Exception as e:
            logger.error(f"加载文件失败: {e}")

    def _load_by(self, tn: str):
        try:
            self._total_count = self.tag_dao.count_files_by_tag(tn)
            files = self.tag_dao.get_files_by_tag_paginated(
                tn, page=self.current_page, page_size=self.page_size)
            self._fill(files)
        except Exception as e:
            logger.error(f"加载标签文件失败: {e}")

    def _fill(self, files):
        # 修复：翻页/切换标签时清除上一页的选中状态，避免跨页选中残留
        self.tbl.clearSelection()
        self.current_files = files
        total_pages = max(1, (self._total_count + self.page_size - 1) // self.page_size)
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
            # 页码越界时重新加载
            if self.current_tag is None:
                self._load_all()
            else:
                self._load_by(self.current_tag)
            return

        self.tbl.setRowCount(len(files))
        self.cnt.setText(f"共 {self._total_count} 个文件")
        from config import FILE_TYPE_NAMES
        fids = [f['id'] for f in files]
        tmap = self.tag_dao.get_all_tags_by_file(fids) if fids else {}
        for i, f in enumerate(files):
            ft = f.get('file_type', 'other')
            it = QTableWidgetItem(get_file_icon(ft) + f['file_name'])
            it.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.tbl.setItem(i, 0, it)
            self.tbl.setItem(i, 1, QTableWidgetItem(truncate_path(f['file_path'], 60)))
            type_item = QTableWidgetItem(FILE_TYPE_NAMES.get(ft, ft))
            type_item.setForeground(QBrush(QColor(get_file_color(ft))))
            self.tbl.setItem(i, 2, type_item)
            self.tbl.setItem(i, 3, QTableWidgetItem(format_size(f['file_size'])))
            txt = ", ".join(tmap.get(f['id'], []))
            self.tbl.setItem(i, 4, QTableWidgetItem(txt or "-"))

        # 更新分页状态
        self.page_label.setText(
            f"第 {self.current_page + 1} 页 / 共 {total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

    # ── 翻页 ──

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            if self.current_tag is None:
                self._load_all()
            else:
                self._load_by(self.current_tag)

    def _next_page(self):
        total_pages = max(1, (self._total_count + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            if self.current_tag is None:
                self._load_all()
            else:
                self._load_by(self.current_tag)

    # ── 操作 ──

    def _get_ids(self):
        ids = []
        for r in self.tbl.selectionModel().selectedRows():
            it = self.tbl.item(r.row(), 0)
            if it:
                v = it.data(Qt.ItemDataRole.UserRole)
                if v:
                    ids.append(v)
        return ids

    def _create_tag(self):
        name, ok = QInputDialog.getText(self, "新建标签", "输入标签名:")
        if ok and name.strip():
            n = name.strip()
            if self.tag_manager.create_tag(n):
                notify(self, f"标签 '{n}' 已创建", 'success', 3000)
                self.refresh_data()
            else:
                notify(self, "创建失败（可能已存在）", 'warning', 3000)

    def _delete_tag(self):
        if not self.current_tag:
            QMessageBox.information(self, "提示", "请先在标签云中点击要删除的标签")
            return
        if QMessageBox.question(self, "确认删除",
                f"确定删除标签 '{self.current_tag}'？\n将从所有文件中移除。") == QMessageBox.StandardButton.Yes:
            self.tag_manager.delete_tag(self.current_tag)
            notify(self, "标签已删除", 'success', 3000)
            self.current_tag = None
            self.refresh_data()

    def _batch_tag(self):
        ids = self._get_ids()
        if not ids:
            QMessageBox.information(self, "提示",
                "请先在右侧选文件，或使用「新建标签」直接创建。")
            return
        inp, ok = QInputDialog.getText(self, "打标签", "标签名（多个用逗号分隔）:")
        if ok and inp.strip():
            ns = [x.strip() for x in inp.split(",") if x.strip()]
            self.tag_manager.batch_add_tags(ids, ns)
            notify(self, f"已给 {len(ids)} 个文件打标签", 'success', 3000)
            self.refresh_data()

    def _batch_untag(self):
        ids = self._get_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择文件")
            return
        inp, ok = QInputDialog.getText(self, "移除标签", "输入标签名:")
        if ok and inp.strip():
            rm = sum(1 for fid in ids if self.tag_manager.remove_tag(fid, inp.strip()))
            notify(self, f"已从 {rm} 个文件移除标签", 'success', 3000)
            self.refresh_data()
