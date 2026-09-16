"""
生命周期策略对话框（批次7 P2-07）。

管理策略（按路径/类型/标签定目标 + 超龄天数 + 动作），
支持「立即检查」预览匹配文件与「执行」预演确认。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QFileDialog, QCheckBox, QComboBox, QSpinBox, QHeaderView,
    QAbstractItemView, QTabWidget, QWidget, QProgressDialog
)
from PyQt6.QtCore import Qt

from core.lifecycle_service import LifecycleService
from utils.display_utils import format_size
from utils.logger import logger

ACTION_LABELS = {'remind': '🔔 提醒', 'archive': '📦 归档', 'trash': '🗑 移入回收区'}
TARGET_LABELS = {'path': '📁 路径前缀', 'type': '🏷 文件类型', 'tag': '# 标签'}


class LifecycleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生命周期策略")
        self.setMinimumSize(760, 560)
        self.service = LifecycleService()
        self._current_id = None
        self._last_check = []  # check_all 结果缓存
        self._init_ui()
        self._refresh_list()

    # ── UI 结构 ───────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_policy_tab(), "策略管理")
        tabs.addTab(self._build_check_tab(), "🔍 检查与执行")
        layout.addWidget(tabs, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_policy_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        layout.addWidget(QLabel("策略列表:"))
        self.policy_table = QTableWidget()
        self.policy_table.setColumnCount(6)
        self.policy_table.setHorizontalHeaderLabels(
            ["名称", "目标", "条件", "动作", "状态", "上次检查"])
        self.policy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.policy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.policy_table.verticalHeader().setDefaultSectionSize(28)
        self.policy_table.verticalHeader().setVisible(False)
        self.policy_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.policy_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.policy_table.cellClicked.connect(self._on_select)
        layout.addWidget(self.policy_table, 2)

        # 表单
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：合同归档 / 临时目录清理")
        name_row.addWidget(self.name_edit, 1)
        self.enabled_cb = QCheckBox("启用")
        self.enabled_cb.setChecked(True)
        name_row.addWidget(self.enabled_cb)
        layout.addLayout(name_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标:"))
        self.target_type_combo = QComboBox()
        for key, label in TARGET_LABELS.items():
            self.target_type_combo.addItem(label, key)
        self.target_type_combo.currentIndexChanged.connect(self._on_target_type_changed)
        target_row.addWidget(self.target_type_combo)
        self.target_value_edit = QLineEdit()
        self.target_value_edit.setPlaceholderText("路径前缀 / 文件类型(document|image|video…) / 标签名")
        target_row.addWidget(self.target_value_edit, 1)
        layout.addLayout(target_row)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("超过:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 3650)
        self.days_spin.setValue(30)
        self.days_spin.setSuffix(" 天未修改")
        action_row.addWidget(self.days_spin)
        action_row.addWidget(QLabel("动作:"))
        self.action_combo = QComboBox()
        for key, label in ACTION_LABELS.items():
            self.action_combo.addItem(label, key)
        self.action_combo.currentIndexChanged.connect(self._on_action_changed)
        action_row.addWidget(self.action_combo)
        self.archive_dir_edit = QLineEdit()
        self.archive_dir_edit.setPlaceholderText("归档输出目录（仅归档动作需要）")
        self.archive_dir_edit.setEnabled(False)
        action_row.addWidget(self.archive_dir_edit, 1)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse_archive_dir)
        action_row.addWidget(browse_btn)
        layout.addLayout(action_row)

        btn_layout = QHBoxLayout()
        new_btn = QPushButton("新建")
        new_btn.clicked.connect(self._new_policy)
        btn_layout.addWidget(new_btn)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save_policy)
        btn_layout.addWidget(save_btn)
        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("dangerBtn")
        delete_btn.clicked.connect(self._delete_policy)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return page

    def _build_check_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        desc = QLabel(
            "点「立即检查」扫描全部启用策略，结果按策略分组展示。\n"
            "勾选后可执行：提醒动作仅展示，归档/回收区动作会先弹预演确认。")
        desc.setStyleSheet("color: #a6adc8;")
        layout.addWidget(desc)

        check_btn = QPushButton("🔍 立即检查")
        check_btn.setObjectName("primaryBtn")
        check_btn.clicked.connect(self._run_check)
        layout.addWidget(check_btn)

        layout.addWidget(QLabel("匹配结果（勾选 = 将执行）:"))
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(5)
        self.result_table.setHorizontalHeaderLabels(
            ["✓", "文件", "策略", "动作", "大小"])
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_table.setColumnWidth(0, 36)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.result_table, 1)

        exec_btn = QPushButton("▶ 执行勾选项")
        exec_btn.setObjectName("primaryBtn")
        exec_btn.clicked.connect(self._execute_checked)
        layout.addWidget(exec_btn)
        return page

    # ── 策略管理 ──────────────────────────────────────────────

    def _browse_archive_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择归档输出目录")
        if d:
            self.archive_dir_edit.setText(d)

    def _on_target_type_changed(self):
        pass  # 占位：placeholder 文案已区分

    def _on_action_changed(self):
        self.archive_dir_edit.setEnabled(
            self.action_combo.currentData() == 'archive')

    def _refresh_list(self):
        rows = self.service.policy_dao.get_all()
        self.policy_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            target = (TARGET_LABELS.get(r['target_type'], '?')
                      + ' ' + (r['target_value'] or ''))
            self.policy_table.setItem(i, 0, QTableWidgetItem(r['name']))
            self.policy_table.setItem(i, 1, QTableWidgetItem(target))
            self.policy_table.setItem(i, 2, QTableWidgetItem(f"> {r['days_threshold']} 天"))
            self.policy_table.setItem(i, 3, QTableWidgetItem(ACTION_LABELS.get(r['action'], r['action'])))
            self.policy_table.setItem(i, 4, QTableWidgetItem('启用' if r['enabled'] else '禁用'))
            self.policy_table.setItem(i, 5, QTableWidgetItem(r.get('last_run_at') or '—'))
            self.policy_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r['id'])

    def _on_select(self, row, _col):
        item = self.policy_table.item(row, 0)
        if not item:
            return
        p = self.service.policy_dao.get_by_id(item.data(Qt.ItemDataRole.UserRole))
        if not p:
            return
        self._current_id = p['id']
        self.name_edit.setText(p['name'])
        self.target_value_edit.setText(p['target_value'] or '')
        self.days_spin.setValue(int(p.get('days_threshold') or 30))
        self.archive_dir_edit.setText(p.get('archive_dir') or '')
        self.enabled_cb.setChecked(bool(p.get('enabled', 1)))
        idx = self.target_type_combo.findData(p.get('target_type', 'path'))
        if idx >= 0:
            self.target_type_combo.setCurrentIndex(idx)
        idx = self.action_combo.findData(p.get('action', 'remind'))
        if idx >= 0:
            self.action_combo.setCurrentIndex(idx)

    def _new_policy(self):
        self._current_id = None
        self.name_edit.clear()
        self.target_value_edit.clear()
        self.archive_dir_edit.clear()
        self.days_spin.setValue(30)
        self.enabled_cb.setChecked(True)
        self.target_type_combo.setCurrentIndex(0)
        self.action_combo.setCurrentIndex(0)
        self.name_edit.setFocus()

    def _save_policy(self):
        name = self.name_edit.text().strip()
        value = self.target_value_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入策略名称")
            return
        if not value:
            QMessageBox.warning(self, "提示", "请填写目标（路径/类型/标签）")
            return
        action = self.action_combo.currentData()
        archive_dir = self.archive_dir_edit.text().strip() or None
        if action == 'archive' and not archive_dir:
            QMessageBox.warning(self, "提示", "归档动作需要选择输出目录")
            return
        kwargs = dict(
            name=name,
            target_type=self.target_type_combo.currentData(),
            target_value=value,
            days_threshold=self.days_spin.value(),
            action=action,
            archive_dir=archive_dir,
            enabled=self.enabled_cb.isChecked(),
        )
        try:
            if self._current_id:
                self.service.policy_dao.update(self._current_id, **kwargs)
            else:
                self._current_id = self.service.policy_dao.create(**kwargs)
            self._refresh_list()
            QMessageBox.information(self, "成功", "策略已保存")
        except Exception as e:
            logger.error('保存生命周期策略失败: %s', e)
            QMessageBox.critical(self, "失败", f"保存失败: {e}")

    def _delete_policy(self):
        if not self._current_id:
            QMessageBox.information(self, "提示", "请先选择要删除的策略")
            return
        reply = QMessageBox.question(self, "确认", "确定删除此策略?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.service.policy_dao.delete(self._current_id)
        self._current_id = None
        self._new_policy()
        self._refresh_list()

    # ── 检查与执行 ────────────────────────────────────────────

    def _run_check(self):
        try:
            self._last_check = self.service.check_all()
        except Exception as e:
            logger.error('生命周期检查失败: %s', e)
            QMessageBox.critical(self, "失败", f"检查失败: {e}")
            return
        rows = []
        for item in self._last_check:
            for rec in item['matches']:
                rows.append((rec, item['policy']))
        self.result_table.setRowCount(len(rows))
        for i, (rec, policy) in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked)
            self.result_table.setItem(i, 0, chk)
            self.result_table.setItem(i, 1, QTableWidgetItem(rec.get('file_path', '')))
            self.result_table.setItem(i, 2, QTableWidgetItem(policy.get('name', '')))
            self.result_table.setItem(i, 3, QTableWidgetItem(ACTION_LABELS.get(policy.get('action'), '?')))
            self.result_table.setItem(i, 4, QTableWidgetItem(format_size(rec.get('file_size') or 0)))
            self.result_table.item(i, 1).setData(Qt.ItemDataRole.UserRole, (policy['id'], rec['id']))
        if not rows:
            QMessageBox.information(self, "检查完成", "没有命中任何策略的文件。")
        self._refresh_list()

    def _execute_checked(self):
        # 按策略分组收集勾选项
        by_policy = {}
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            cell = self.result_table.item(row, 1)
            if not item or not cell or item.checkState() != Qt.CheckState.Checked:
                continue
            data = cell.data(Qt.ItemDataRole.UserRole)
            if not data:
                continue
            policy_id, file_id = data
            by_policy.setdefault(policy_id, {'policy': None, 'matches': []})
            by_policy[policy_id]['matches'].append({'id': file_id})
        if not by_policy:
            QMessageBox.information(self, "提示", "请先勾选要执行的条目")
            return

        # 预演确认（归档/回收区动作）
        lines = []
        total = 0
        for pid, group in by_policy.items():
            policy = self.service.policy_dao.get_by_id(pid)
            if not policy:
                continue
            group['policy'] = policy
            if policy['action'] != 'remind':
                lines.append(f"「{policy['name']}」{ACTION_LABELS[policy['action']]} "
                             f"{len(group['matches'])} 个文件")
                total += len(group['matches'])
        if total and QMessageBox.question(
                self, "执行确认",
                "以下操作将执行（回收区动作可撤销）：\n\n" + "\n".join(lines)
                + "\n\n确定继续？") != QMessageBox.StandardButton.Yes:
            return

        progress = QProgressDialog("执行中...", None, 0, max(total, 1), self)
        progress.setWindowTitle("生命周期执行")
        progress.setMinimumDuration(0)
        done = []
        for pid, group in by_policy.items():
            policy = group['policy']
            if not policy:
                continue
            # 补全文件信息（供归档打包）
            full = [self.service.file_dao.get_by_id(m['id']) or m
                    for m in group['matches']]
            result = self.service.execute(policy, full,
                                          progress_cb=lambda a, b: progress.setValue(min(a + 1, b)))
            done.append((policy['name'], result))
        progress.setValue(progress.maximum())

        ok = [f"{name}: {r['processed']} 成功 / {r['failed']} 失败"
              + (f"，归档: {r['archive_path']}" if r.get('archive_path') else '')
              for name, r in done]
        msg = "\n".join(ok)
        if any(r['errors'] for _, r in done):
            err_lines = [e for _, r in done for e in r['errors'][:5]]
            msg += "\n\n错误:\n" + "\n".join(err_lines)
        QMessageBox.information(self, "执行完成", msg)
        self._run_check()
