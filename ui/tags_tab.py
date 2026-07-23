"""
标签管理标签页 - 标签云(流式) + 文件列表 + AI 功能
"""
import os
import hashlib
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox,
    QHeaderView, QInputDialog, QScrollArea, QFrame, QMenu, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QAction

from database.db_manager import db
from database.models import FileDAO, TagDAO
from core import TagManager, FileManager
from core.ai_layer import AILayer
from ui.ai_file_actions import show_tag_recommendation_dialog, request_ai_describe_file, _AiRenameWorker
from utils.display_utils import format_size, truncate_path, get_file_icon, get_file_color
from utils.logger import logger
from ui.toast import notify
from ui.empty_state import create_empty_state


class _AiRecWorker(QThread):
    """后台线程：AI 标签推荐（避免卡 UI）"""
    done = pyqtSignal(dict, list, str)  # record, recommendations, source
    error = pyqtSignal(str)

    def __init__(self, ai_layer, record, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.record = record

    def run(self):
        try:
            recs, source = self.ai_layer.recommend_tags(self.record)
            self.done.emit(self.record, recs, source)
        except Exception as e:
            self.error.emit(str(e))


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
        self.file_manager = FileManager()
        self.ai_layer = AILayer()
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
            ("⇄ 合并标签", None, self._merge_tag),
            ("🗑 删除标签", "dangerBtn", self._delete_tag),
            (None, None, None),
            ("🏷 打标签", "successBtn", self._batch_tag),
            ("✂️ 移除标签", None, self._batch_untag),
            (None, None, None),
            ("🤖 智能推荐", None, self._ai_recommend_tags),
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
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._show_context_menu)
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
        self._empty_state = create_empty_state(
            'tags', "重试加载", self.refresh_data, parent=self)
        layout.addWidget(self._empty_state)

    # ── 标签云构建 ──

    def _build_cloud(self):
        self._selected_tag = None
        self._clear_cloud()

        tags = self.tag_dao.get_all_tags()
        palette = _TAG_LIGHT if self._theme == 'light' else _TAG_COLORS

        # 空状态检测
        has_tags = len(tags) > 0
        if has_tags:
            self._empty_state.setVisible(False)
        else:
            self._empty_state.show_empty()

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
            self.tbl.setVisible(False)
            self._empty_state.show_error(f"无法读取文件列表：{e}")

    def _load_by(self, tn: str):
        try:
            self._total_count = self.tag_dao.count_files_by_tag(tn)
            files = self.tag_dao.get_files_by_tag_paginated(
                tn, page=self.current_page, page_size=self.page_size)
            self._fill(files)
        except Exception as e:
            logger.error(f"加载标签文件失败: {e}")
            self.tbl.setVisible(False)
            self._empty_state.show_error(f"无法读取标签文件：{e}")

    def _fill(self, files):
        # 修复：翻页/切换标签时清除上一页的选中状态，避免跨页选中残留
        self.tbl.clearSelection()
        self.current_files = files
        self.tbl.setVisible(bool(files))
        if files:
            self._empty_state.setVisible(False)
        else:
            self._empty_state.show_empty()
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

    def _merge_tag(self):
        if not self.current_tag:
            QMessageBox.information(self, "提示", "请先在标签云中选择要合并的源标签")
            return
        target, ok = QInputDialog.getText(
            self, "合并标签", f"将“{self.current_tag}”合并到标签：")
        if not ok or not target.strip():
            return
        target = target.strip()
        if target == self.current_tag:
            QMessageBox.warning(self, "无法合并", "源标签和目标标签不能相同")
            return
        reply = QMessageBox.question(
            self, "确认合并",
            f"“{self.current_tag}”的文件关联会转移到“{target}”，源标签将被删除。\n确定继续？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.tag_manager.merge_tag(self.current_tag, target)
            self.current_tag = target
            notify(self, f"标签已合并，迁移 {count} 个文件关联", 'success', 3000)
            self.refresh_data()
        except Exception as exc:
            QMessageBox.critical(self, "合并失败", str(exc))

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

    # ── 右键菜单 + AI 功能 ──

    def _show_context_menu(self, pos):
        """文件列表右键菜单"""
        row = self.tbl.rowAt(pos.y())
        if row < 0:
            return
        item = self.tbl.item(row, 0)
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
        copy_path_action.triggered.connect(lambda: QApplication.clipboard().setText(file_path))
        menu.addAction(copy_path_action)

        copy_name_action = QAction("复制文件名", self)
        copy_name_action.triggered.connect(lambda: QApplication.clipboard().setText(record['file_name']))
        menu.addAction(copy_name_action)

        menu.addSeparator()

        # 智能推荐标签
        recommend_tag_action = QAction("智能推荐标签", self)
        recommend_tag_action.triggered.connect(lambda: self._recommend_tags_for_file(file_id))
        menu.addAction(recommend_tag_action)

        # AI 描述文件
        if self.ai_layer.enabled:
            ai_desc_action = QAction("🤖 AI 描述此文件", self)
            ai_desc_action.triggered.connect(lambda: self._ai_describe_file(file_id))
            menu.addAction(ai_desc_action)

            ai_rename_action = QAction("🤖 AI 建议重命名", self)
            ai_rename_action.triggered.connect(lambda: self._ai_suggest_rename(file_id))
            menu.addAction(ai_rename_action)

        menu.addSeparator()

        delete_action = QAction("标记删除", self)
        delete_action.triggered.connect(lambda: self._context_delete(file_id))
        menu.addAction(delete_action)

        menu.exec(self.tbl.viewport().mapToGlobal(pos))

    def _ai_recommend_tags(self):
        """顶部按钮：对选中文件智能推荐标签（后台并发分析，一次性汇总）"""
        ids = self._get_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先在右侧表格中选择文件")
            return

        self._ai_queue = list(ids)
        self._ai_results = []
        self._ai_index = 0
        self._ai_active = 0        # ponytail: 追踪并发 worker 数
        self._ai_cancelled = False  # ponytail: 取消标志

        from PyQt6.QtWidgets import QProgressDialog
        self._progress = QProgressDialog("正在分析文件标签...", "取消", 0, len(ids), self)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)
        self._progress.canceled.connect(self._ai_cancel)
        self._progress.show()

        self._ai_process_next()

    def _ai_cancel(self):
        """用户点击取消——ponytail: 设标志位，正在跑的 worker 回调后自动跳过"""
        self._ai_cancelled = True
        self._ai_queue = []
        self._progress = None
        self.cnt.setText(f"共 {self._total_count} 个文件")
        if self._ai_active == 0:
            self._ai_finish_silent()

    def _ai_finish_silent(self):
        """取消后的静默清理（不弹窗）"""
        if self._progress:
            self._progress.close()
            self._progress = None
        self._ai_results = []

    def _ai_process_next(self):
        """ponytail: 最多 3 个 worker 同时跑，上限由 API 并发能力决定"""
        MAX_CONCURRENT = 3
        while self._ai_active < MAX_CONCURRENT and self._ai_index < len(self._ai_queue):
            if self._ai_cancelled:
                return

            fid = self._ai_queue[self._ai_index]
            self._ai_index += 1
            if self._progress:
                self._progress.setValue(self._ai_index)
                self._progress.setLabelText(f"正在分析... ({self._ai_index}/{len(self._ai_queue)})")

            record = self.file_dao.get_by_id(fid)
            if not record:
                continue

            self._ai_active += 1
            worker = _AiRecWorker(self.ai_layer, record, self)
            worker.done.connect(lambda rec, recs, src, fid=fid: self._on_ai_rec_done(fid, rec, recs, src))
            worker.error.connect(lambda e: self._on_ai_rec_error(e))
            worker.start()

    def _on_ai_rec_done(self, file_id, record, recommendations, source):
        """单个文件推荐完成，缓存结果并尝试补充新 worker"""
        self._ai_active -= 1
        if self._ai_cancelled:
            self._check_all_done()
            return
        if recommendations:
            existing = set(t['tag_name'] for t in self.tag_manager.get_tags_by_file(file_id))
            suggested = [(t, c) for t, c in recommendations if t not in existing]
            if suggested:
                self._ai_results.append((file_id, record, suggested))
        self._ai_process_next()
        self._check_all_done()

    def _on_ai_rec_error(self, err):
        """推荐失败，跳过继续"""
        logger.warning(f"AI 推荐标签失败: {err}")
        self._ai_active -= 1
        if self._ai_cancelled:
            self._check_all_done()
            return
        self._ai_process_next()
        self._check_all_done()

    def _check_all_done(self):
        """队列空 + 无活跃 worker → 收尾"""
        if self._ai_index >= len(self._ai_queue) and self._ai_active == 0:
            self._ai_finish()

    def _ai_finish(self):
        """所有文件分析完成，弹出汇总对话框"""
        if self._progress:
            self._progress.close()
            self._progress = None

        if self._ai_cancelled:
            return  # ponytail: 用户取消了，不弹窗

        if not self._ai_results:
            QMessageBox.information(self, "标签推荐", "选中文件暂无新的推荐标签。")
            self.cnt.setText(f"共 {self._total_count} 个文件")
            return

        self._show_batch_rec_dialog()

    def _show_batch_rec_dialog(self):
        """汇总标签推荐对话框：显示所有文件的建议标签（按频次排序）"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QDialogButtonBox, QScrollArea, QWidget
        from PyQt6.QtCore import Qt
        import hashlib

        # 统计所有推荐标签的频次和最高置信度
        tag_stats = {}  # tag -> {count, max_conf, file_ids}
        for fid, rec, suggested in self._ai_results:
            for tag, conf in suggested:
                if tag not in tag_stats:
                    tag_stats[tag] = {'count': 0, 'max_conf': 0, 'files': []}
                tag_stats[tag]['count'] += 1
                tag_stats[tag]['max_conf'] = max(tag_stats[tag]['max_conf'], conf)
                tag_stats[tag]['files'].append(fid)

        # 按频次降序
        sorted_tags = sorted(tag_stats.items(), key=lambda x: (-x[1]['count'], -x[1]['max_conf']))

        is_light = getattr(self, '_theme', 'dark') == 'light'
        bg = '#eff1f5' if is_light else '#1e1e2e'
        fg = '#4c4f69' if is_light else '#cdd6f4'
        sub = '#7c7f93' if is_light else '#a6adc8'

        dlg = QDialog(self)
        dlg.setWindowTitle(f"智能标签推荐（{len(self._ai_results)} 个文件）")
        dlg.setMinimumWidth(480)
        dlg.setMinimumHeight(400)
        dlg.setModal(True)
        dlg.setStyleSheet(f"QDialog {{ background-color: {bg}; }}")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        # 说明
        total_files = len(self._ai_results)
        info = QLabel(f"从 {total_files} 个文件中共识别出 {len(sorted_tags)} 个推荐标签：")
        info.setStyleSheet(f"font-size: 12px; color: {fg};")
        layout.addWidget(info)

        # 滚动区域容纳标签按钮
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setSpacing(6)

        pal = _TAG_LIGHT if is_light else _TAG_COLORS
        tag_buttons = []
        for tag, stats in sorted_tags:
            idx = int(hashlib.md5(tag.encode()).hexdigest()[:8], 16) % 8
            bg2, fg2 = pal[idx]
            count = stats['count']
            conf = stats['max_conf']
            display = f"{tag}  ({count}个文件, 最高置信度 {conf:.0%})"
            b = QPushButton(display)
            b.setCheckable(True)
            b.setChecked(True)  # 默认全选
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: {bg2}; color: {fg2}; border: none; border-radius: 8px;"
                f" padding: 6px 14px; font-size: 11pt; text-align: left; }}"
                f"QPushButton:checked {{ border: 2px solid {fg2}; }}"
                f"QPushButton:unchecked {{ border: 1px solid {bg2}; background: transparent; color: {fg2}; }}"
            )
            tag_buttons.append((tag, b, stats['files']))
            clayout.addWidget(b)

        clayout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # 按钮区
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            dlg.deleteLater()
            self.cnt.setText(f"共 {self._total_count} 个文件")
            return

        # 收集选中的标签及对应文件
        selected_tags = {}  # tag -> [file_ids]
        for tag, btn, files in tag_buttons:
            if btn.isChecked():
                selected_tags[tag] = files

        dlg.deleteLater()

        if not selected_tags:
            self.cnt.setText(f"共 {self._total_count} 个文件")
            return

        # 批量添加
        try:
            for tag, files in selected_tags.items():
                self.tag_manager.batch_add_tags(files, [tag])
            tag_names = ', '.join(selected_tags.keys())
            notify(self, f"已批量添加标签: {tag_names}", 'success', 4000)
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "标签推荐", f"批量添加失败: {e}")

    def _recommend_tags_for_file(self, file_id):
        """智能推荐标签 —— 委托共享模块"""
        show_tag_recommendation_dialog(
            self, file_id, self.file_dao,
            ai_layer=self.ai_layer, tag_manager=self.tag_manager,
            theme=getattr(self, '_theme', 'dark'),
        )

    def _ai_describe_file(self, file_id):
        """AI 描述单个文件 —— 委托共享模块"""
        request_ai_describe_file(self, file_id, self.file_dao,
                                  ai_layer=self.ai_layer,
                                  on_done=None, on_error=None)

    def _ai_suggest_rename(self, file_id):
        """AI 重命名建议 —— 后台线程"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            return
        worker = _AiRenameWorker(self.ai_layer, record, self)
        worker.done.connect(lambda s: self._on_ai_rename_done(file_id, s))
        worker.error.connect(lambda e: QMessageBox.warning(self, "AI 重命名失败", e))
        worker.start()

    def _on_ai_rename_done(self, file_id, suggestions):
        if not suggestions:
            QMessageBox.information(self, "AI 重命名", "无法生成重命名建议。")
            return
        items = [f"{i}. {s}" for i, s in enumerate(suggestions[:3], 1)]
        chosen, ok = QInputDialog.getItem(self, "🤖 AI 重命名建议",
            "选择一个建议（取消则手动输入）：", items, 0, False)
        if ok and chosen:
            name = chosen.split(". ", 1)[-1]
            new_name, ok2 = QInputDialog.getText(self, "确认重命名", "新文件名：", text=name)
            if ok2 and new_name.strip():
                self._do_rename_file(file_id, new_name.strip())

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
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "重命名失败", f"目标文件已存在: {new_name}")
                return
            os.rename(old_path, new_path)
            self.file_dao.update_name(file_id, new_name, new_path)
            notify(self, f"已重命名为: {new_name}", 'success', 3000)
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "重命名失败", str(e))

    def _safe_open_file(self, file_path, file_id=None):
        BAD = ('', 'False', 'True', 'false', 'true', '0', 'null', 'None')
        if (file_path is None or not isinstance(file_path, str) or file_path.strip() in BAD) and file_id is not None:
            rec = self.file_dao.get_by_id(file_id)
            if rec and rec.get('file_path'):
                file_path = rec['file_path']
        if file_path is None or not isinstance(file_path, str) or file_path.strip() in BAD:
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            return
        file_path = os.path.normpath(file_path)
        if not os.path.exists(file_path):
            notify(self, f"文件不存在: {os.path.basename(file_path)}", 'warning', 4000)
            return
        try:
            os.startfile(file_path)
        except Exception as e:
            notify(self, f"无法打开文件: {e}", 'error', 5000)

    def _safe_open_folder(self, file_path, file_id=None):
        BAD = ('', 'False', 'True', 'false', 'true', '0', 'null', 'None')
        if (file_path is None or not isinstance(file_path, str) or file_path.strip() in BAD) and file_id is not None:
            rec = self.file_dao.get_by_id(file_id)
            if rec and rec.get('file_path'):
                file_path = rec['file_path']
        if file_path is None or not isinstance(file_path, str) or file_path.strip() in BAD:
            notify(self, "无法操作：文件路径无效", 'warning', 4000)
            return
        file_path = os.path.normpath(file_path)
        folder = os.path.dirname(file_path)
        if not folder or not os.path.exists(folder):
            notify(self, "文件所在目录已不存在", 'warning', 4000)
            return
        try:
            os.startfile(folder)
        except Exception as e:
            notify(self, f"无法打开文件夹: {e}", 'error', 5000)

    def _context_delete(self, file_id):
        """标记删除文件"""
        reply = QMessageBox.question(self, "确认删除", "确定标记删除该文件?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.file_manager.delete_file(file_id)
                self.refresh_data()
                notify(self, "文件已标记删除", 'success', 3000)
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))
