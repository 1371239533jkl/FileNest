"""批次 5 内容理解对话框：相似图片 / 文件版本关系 / 文件夹画像 / 标签层级。

全部为只读或人工确认式操作，不自动执行删除/移动。
"""
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
    QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QHeaderView,
)

from database.db_manager import db
from database.models import FileDAO, TagDAO, VersionRelationDAO
from utils.display_utils import format_size
from utils.logger import logger


class _FnWorker(QThread):
    """通用后台任务：执行 fn(*args)，完成发 done，异常发 error"""
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn, self._args = fn, args

    def run(self):
        try:
            self.done.emit(self._fn(*self._args))
        except Exception as e:
            logger.error(f"后台任务失败: {e}")
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════
# P1-07 相似图片检测
# ══════════════════════════════════════════════════════════════════════════

class SimilarityDialog(QDialog):
    """感知哈希相似图片：计算哈希 → 按阈值分组展示（不自动删除）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.image_similarity import SimilarityManager
        self.manager = SimilarityManager(db)
        self._hash_worker = None
        self.setWindowTitle("🖼 相似图片检测")
        self.setMinimumSize(720, 520)
        self._init_ui()
        self._load_groups()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel(
            "基于感知哈希（dHash）识别缩放/压缩/轻微编辑后的同一图片。\n"
            "「完全重复」= 字节级相同；「视觉相似」= 内容相近但文件不同。仅展示，不自动删除。")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("相似阈值（汉明距离 ≤）："))
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 16)
        self.threshold.setValue(8)
        self.threshold.setToolTip("越小越严格。0≈感知级相同；8 适合识别缩放/压缩图")
        bar.addWidget(self.threshold)
        self.compute_btn = QPushButton("计算感知哈希")
        self.compute_btn.clicked.connect(self._compute_hashes)
        bar.addWidget(self.compute_btn)
        bar.addStretch()
        self.status = QLabel("")
        self.status.setObjectName("subtitleLabel")
        bar.addWidget(self.status)
        layout.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件", "大小", "路径"])
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_groups(self):
        self.tree.clear()
        try:
            groups = self.manager.get_groups(threshold=self.threshold.value())
        except Exception as e:
            self.status.setText(f"读取失败: {e}")
            return
        stats = self.manager.stats()
        self.status.setText(
            f"图片 {stats['total']} 张 / 已建哈希 {stats['hashed']} 张 · "
            f"{len(groups)} 组")
        for i, g in enumerate(groups, 1):
            files = g['files']
            total = sum(f.get('file_size') or 0 for f in files)
            top = QTreeWidgetItem(
                [f"组 {i} · {g['label']} · {len(files)} 张 · {format_size(total)}",
                 "", ""])
            top.setForeground(0, QColor("#f9e2af" if self._is_dark() else "#df8e1d"))
            for f in files:
                QTreeWidgetItem(top, [
                    f.get('file_name', ''),
                    format_size(f.get('file_size') or 0),
                    f.get('file_path', ''),
                ])
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)

    def _compute_hashes(self):
        if self._hash_worker:
            return
        self.compute_btn.setEnabled(False)
        self.status.setText("正在计算感知哈希...")
        self._hash_worker = _FnWorker(self.manager.compute_hashes)
        self._hash_worker.done.connect(self._on_hash_done)
        self._hash_worker.error.connect(self._on_hash_error)
        self._hash_worker.start()

    def _on_hash_done(self, result):
        self._hash_worker = None
        self.compute_btn.setEnabled(True)
        self.status.setText(
            f"计算完成：成功 {result['computed']}，失败 {result['failed']}")
        self._load_groups()

    def _on_hash_error(self, msg):
        self._hash_worker = None
        self.compute_btn.setEnabled(True)
        self.status.setText(f"计算失败: {msg}")

    def _is_dark(self):
        return self.palette().color(self.backgroundRole()).lightness() < 128


# ══════════════════════════════════════════════════════════════════════════
# P1-08 文件版本关系
# ══════════════════════════════════════════════════════════════════════════

class VersionRelationsDialog(QDialog):
    """版本族候选：扫描推荐 → 人工确认/解除（不改变真实文件路径）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dao = VersionRelationDAO(db)
        self._worker = None
        self.setWindowTitle("🔗 文件版本关系")
        self.setMinimumSize(760, 480)
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel(
            "按「同目录 + 同类型 + 去版本标记后同名 + 修改时间先后」识别版本族候选。\n"
            "候选需人工确认后才视为版本关系；确认/解除只影响关系记录，不改动文件。")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        bar = QHBoxLayout()
        self.scan_btn = QPushButton("扫描候选")
        self.scan_btn.clicked.connect(self._scan)
        bar.addWidget(self.scan_btn)
        bar.addWidget(QLabel("状态："))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["pending", "confirmed", "dismissed"])
        self.status_filter.currentTextChanged.connect(lambda _t: self._load())
        bar.addWidget(self.status_filter)
        bar.addStretch()
        self.status = QLabel("")
        self.status.setObjectName("subtitleLabel")
        bar.addWidget(self.status)
        layout.addLayout(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["较早版本", "较新版本", "置信度", "", ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load(self):
        rows = self.dao.get_by_status(self.status_filter.currentText())
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r.get('name_a') or ''))
            self.table.setItem(i, 1, QTableWidgetItem(r.get('name_b') or ''))
            self.table.setItem(
                i, 2, QTableWidgetItem(f"{(r.get('confidence') or 0):.0%}"))
            if r.get('status') == 'pending':
                self.table.setCellWidget(i, 3, self._action_btn(
                    r['id'], "✅ 确认", 'confirmed'))
                self.table.setCellWidget(i, 4, self._action_btn(
                    r['id'], "🚫 解除", 'dismissed'))
            else:
                self.table.setItem(i, 3, QTableWidgetItem(r.get('status') or ''))
                self.table.setItem(i, 4, QTableWidgetItem(''))
        self.status.setText(f"{len(rows)} 条记录")

    def _action_btn(self, rel_id, text, status):
        btn = QPushButton(text)
        btn.clicked.connect(lambda _c=False, i=rel_id, s=status: self._set_status(i, s))
        return btn

    def _set_status(self, rel_id, status):
        self.dao.set_status(rel_id, status)
        self._load()

    def _scan(self):
        if self._worker:
            return
        from core.version_relations import detect_version_candidates
        self.scan_btn.setEnabled(False)
        self.status.setText("正在扫描...")
        self._worker = _FnWorker(detect_version_candidates)
        self._worker.done.connect(self._on_scan_done)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_done(self, added):
        self._worker = None
        self.scan_btn.setEnabled(True)
        self.status.setText(f"扫描完成：新增候选 {added} 条")
        self.status_filter.setCurrentText('pending')
        self._load()

    def _on_scan_error(self, msg):
        self._worker = None
        self.scan_btn.setEnabled(True)
        self.status.setText(f"扫描失败: {msg}")


# ══════════════════════════════════════════════════════════════════════════
# P1-09 文件夹画像
# ══════════════════════════════════════════════════════════════════════════

class FolderProfileDialog(QDialog):
    """目录画像：规则统计（始终展示）+ AI 解读（可选）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        from core.ai_layer import AILayer
        self.ai_layer = AILayer()
        self._worker = None
        self.setWindowTitle("📂 目录画像")
        self.setMinimumSize(640, 520)
        self._init_ui()
        self._refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("目录："))
        self.dir_combo = QComboBox()
        self.dir_combo.setEditable(True)
        for row in self.file_dao.get_top_directories(limit=20):
            self.dir_combo.addItem(row['dir_path'])
        bar.addWidget(self.dir_combo, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh)
        bar.addWidget(refresh)
        layout.addLayout(bar)

        self.stats_text = QLabel("")
        self.stats_text.setWordWrap(True)
        self.stats_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.stats_text)

        ai_bar = QHBoxLayout()
        self.ai_btn = QPushButton("🤖 AI 解读")
        self.ai_btn.clicked.connect(self._ai_describe)
        ai_bar.addWidget(self.ai_btn)
        ai_bar.addStretch()
        layout.addLayout(ai_bar)

        self.ai_text = QLabel("")
        self.ai_text.setWordWrap(True)
        self.ai_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.ai_text, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _refresh(self):
        dir_path = self.dir_combo.currentText().strip()
        if not dir_path:
            self.stats_text.setText("请选择或输入目录路径")
            return
        p = self.file_dao.get_directory_profile(dir_path)
        dist = "、".join(
            f"{d['file_type']} {d['count']} 个（{format_size(d['total_size'])}）"
            for d in p['type_distribution'][:6]) or "无文件"
        self.stats_text.setText(
            f"📁 {p['dir_path']}\n"
            f"文件 {p['file_count']} 个 · 共 {format_size(p['total_size'])} · "
            f"重复文件 {p['dup_count']} 个\n"
            f"时间范围：{p['oldest'] or '—'} ～ {p['newest'] or '—'}\n"
            f"类型构成：{dist}")

    def _ai_describe(self):
        if self._worker:
            return
        dir_path = self.dir_combo.currentText().strip()
        if not dir_path:
            return
        self.ai_btn.setEnabled(False)
        self.ai_text.setText("正在生成 AI 解读...")
        from datetime import datetime
        profile_text = (
            f"目录: {dir_path}\n数据范围: 该目录直属文件的本地索引统计\n"
            f"统计生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            + self.stats_text.text())
        self._worker = _FnWorker(self.ai_layer.describe_directory,
                                 dir_path, profile_text)
        self._worker.done.connect(self._on_ai_done)
        self._worker.error.connect(self._on_ai_error)
        self._worker.start()

    def _on_ai_done(self, text):
        self._worker = None
        self.ai_btn.setEnabled(True)
        self.ai_text.setText(text or "AI 不可用，以上规则统计仍然有效。")

    def _on_ai_error(self, msg):
        self._worker = None
        self.ai_btn.setEnabled(True)
        self.ai_text.setText(f"AI 解读失败: {msg}")


# ══════════════════════════════════════════════════════════════════════════
# P1-10 标签层级与别名
# ══════════════════════════════════════════════════════════════════════════

class TagHierarchyDialog(QDialog):
    """标签层级管理：父子（防循环）/ 自定义颜色 / 别名登记"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dao = TagDAO(db)
        self.setWindowTitle("🗂 标签层级管理")
        self.setMinimumSize(520, 460)
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel(
            "选中标签后操作：设置父标签（防循环）、取消层级、自定义颜色（标签云生效）、"
            "登记别名（打标签时自动归一为规范名）。合并标签请回到标签页。")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["标签", "别名"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tree, 1)

        bar = QHBoxLayout()
        for text, fn in [
            ("设置父标签", self._set_parent),
            ("取消层级", self._clear_parent),
            ("🎨 设置颜色", self._set_color),
            ("➕ 添加别名", self._add_alias),
            ("➖ 删除别名", self._del_alias),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            bar.addWidget(btn)
        bar.addStretch()
        layout.addLayout(bar)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _selected_tag(self):
        item = self.tree.currentItem()
        return item.text(0) if item else None

    def _load(self):
        self.tree.clear()

        def fill(parent_item, nodes):
            for n in nodes:
                item = QTreeWidgetItem([n['tag_name'],
                                        "、".join(self.dao.get_aliases(n['tag_name']))])
                if n.get('color'):
                    item.setForeground(0, QColor(n['color']))
                fill(item, n.get('children', []))
                (parent_item or self.tree).addTopLevelItem(item)

        fill(None, self.dao.get_tag_tree())
        self.tree.expandAll()

    def _set_parent(self):
        child = self._selected_tag()
        if not child:
            return
        names = [r['tag_name'] for r in self.dao.get_tag_tree_flat()]
        names = [n for n in names if n != child]
        parent, ok = QInputDialog.getItem(
            self, "设置父标签", f"为「{child}」选择父标签：", names, 0, False)
        if not ok:
            return
        if not self.dao.set_parent(child, parent):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "失败",
                                "无法设置该父子关系（会形成循环层级）")
        self._load()

    def _clear_parent(self):
        tag = self._selected_tag()
        if tag:
            self.dao.set_parent(tag, None)
            self._load()

    def _set_color(self):
        tag = self._selected_tag()
        if not tag:
            return
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(parent=self, title=f"「{tag}」颜色")
        if color.isValid():
            self.dao.set_color(tag, color.name())
            self._load()

    def _add_alias(self):
        canonical = self._selected_tag()
        if not canonical:
            return
        alias, ok = QInputDialog.getText(
            self, "添加别名", f"为「{canonical}」添加别名：")
        if ok and alias.strip():
            self.dao.add_alias(alias.strip(), canonical)
            self._load()

    def _del_alias(self):
        tag = self._selected_tag()
        if not tag:
            return
        aliases = self.dao.get_aliases(tag)
        if not aliases:
            return
        alias, ok = QInputDialog.getItem(
            self, "删除别名", f"删除「{tag}」的别名：", aliases, 0, False)
        if ok:
            self.dao.delete_alias(alias)
            self._load()
