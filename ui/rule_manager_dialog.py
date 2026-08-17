"""可视化整理规则管理对话框 —— 增删改、启停、优先级排序、规则测试。

规则数据存 classification_rules 表，执行逻辑复用 FileClassifier（不在此执行，
只提供"测试"能力：按规则对样本文件名模拟分类并展示命中结果）。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QInputDialog,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt

from database.db_manager import db
from database.models import ClassificationRuleDAO
from utils.logger import logger


class RuleManagerDialog(QDialog):
    """分类规则管理对话框"""

    RULE_TYPES = {
        'keyword': '关键词匹配',
        'extension': '扩展名匹配',
        'regex': '正则表达式',
    }

    def __init__(self, parent=None, rule_dao: ClassificationRuleDAO = None):
        super().__init__(parent)
        self.rule_dao = rule_dao or ClassificationRuleDAO(db)
        self.setWindowTitle("整理规则管理")
        self.setMinimumSize(680, 420)
        self._build_ui()
        self._load_rules()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tip = QLabel("规则按优先级从高到低匹配，命中即分类到目标类别。修改后即时保存。")
        tip.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(tip)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["启用", "规则名称", "匹配方式", "匹配内容", "目标类别"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("＋ 新增规则")
        self.add_btn.clicked.connect(self._add_rule)
        btn_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("✎ 编辑")
        self.edit_btn.clicked.connect(self._edit_rule)
        btn_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("🗑 删除")
        self.delete_btn.clicked.connect(self._delete_rule)
        btn_row.addWidget(self.delete_btn)

        self.toggle_btn = QPushButton("启用/停用")
        self.toggle_btn.clicked.connect(self._toggle_rule)
        btn_row.addWidget(self.toggle_btn)

        btn_row.addStretch()

        self.up_btn = QPushButton("↑ 提高优先级")
        self.up_btn.clicked.connect(lambda: self._move_rule(-1))
        btn_row.addWidget(self.up_btn)

        self.down_btn = QPushButton("↓ 降低优先级")
        self.down_btn.clicked.connect(lambda: self._move_rule(1))
        btn_row.addWidget(self.down_btn)

        self.test_btn = QPushButton("🧪 测试规则")
        self.test_btn.clicked.connect(self._test_rule)
        btn_row.addWidget(self.test_btn)

        layout.addLayout(btn_row)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ── 数据加载 ──
    def _load_rules(self):
        rules = self.rule_dao.get_all()  # 已按 priority DESC 排序
        self.table.setRowCount(len(rules))
        self._rules = rules
        for row, rule in enumerate(rules):
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(bool(rule.get('is_enabled')))
            enabled_cb.setEnabled(False)
            cell = QTableWidgetItem()
            self.table.setCellWidget(row, 0, enabled_cb)
            self.table.setItem(row, 1, QTableWidgetItem(rule.get('rule_name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(
                self.RULE_TYPES.get(rule.get('rule_type', ''), rule.get('rule_type', ''))))
            self.table.setItem(row, 3, QTableWidgetItem(rule.get('rule_pattern', '')))
            self.table.setItem(row, 4, QTableWidgetItem(rule.get('target_category', '')))
        if rules:
            self.table.selectRow(0)

    def _selected_rule(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rules):
            return None, None
        return self._rules[row], row

    # ── 增删改 ──
    def _add_rule(self):
        data = self._prompt_rule()
        if not data:
            return
        self.rule_dao.insert(**data)
        self._load_rules()

    def _edit_rule(self):
        rule, row = self._selected_rule()
        if not rule:
            QMessageBox.information(self, "编辑规则", "请先选择一条规则")
            return
        data = self._prompt_rule(rule)
        if not data:
            return
        self.rule_dao.update(rule['id'], **data)
        self._load_rules()
        self.table.selectRow(row)

    def _delete_rule(self):
        rule, _ = self._selected_rule()
        if not rule:
            QMessageBox.information(self, "删除规则", "请先选择一条规则")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除规则「{rule['rule_name']}」吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.rule_dao.delete(rule['id'])
            self._load_rules()

    def _toggle_rule(self):
        rule, row = self._selected_rule()
        if not rule:
            QMessageBox.information(self, "启用/停用", "请先选择一条规则")
            return
        self.rule_dao.toggle_enabled(rule['id'], not bool(rule.get('is_enabled')))
        self._load_rules()
        self.table.selectRow(row)

    def _move_rule(self, direction: int):
        """调整优先级：与相邻规则交换位置。

        ponytail: 原实现交换 priority 值，但多条规则 priority 相同（新建
        默认都是 10）时交换无效，表现为"点了没区别"。改为按表格新顺序
        整列重写唯一 priority（行号越小越高），任何情况下都生效。
        """
        rule, row = self._selected_rule()
        if not rule:
            return
        target = row + direction
        if target < 0 or target >= len(self._rules):
            return
        ordered = list(self._rules)
        ordered[row], ordered[target] = ordered[target], ordered[row]
        n = len(ordered)
        for index, r in enumerate(ordered):
            new_priority = n - index  # 第 0 行最高，保证唯一且与表格顺序一致
            if int(r.get('priority', 0)) != new_priority:
                self.rule_dao.update_priority(r['id'], new_priority)
        self._load_rules()
        self.table.selectRow(target)

    def _prompt_rule(self, rule: dict = None):
        """弹窗收集规则字段。返回 dict 或 None。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑规则" if rule else "新增规则")
        form = QFormLayout(dlg)

        name_edit = QLineEdit(rule.get('rule_name', '') if rule else '')
        type_combo = QComboBox()
        for key, label in self.RULE_TYPES.items():
            type_combo.addItem(label, key)
        if rule:
            idx = type_combo.findData(rule.get('rule_type', ''))
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
        pattern_edit = QLineEdit(rule.get('rule_pattern', '') if rule else '')
        pattern_edit.setPlaceholderText("关键词用 | 分隔，如：报告|会议|方案")
        category_edit = QLineEdit(rule.get('target_category', '') if rule else '')
        priority_spin = QSpinBox()
        priority_spin.setRange(0, 100)
        priority_spin.setValue(int(rule.get('priority', 10)) if rule else 10)

        form.addRow("规则名称:", name_edit)
        form.addRow("匹配方式:", type_combo)
        form.addRow("匹配内容:", pattern_edit)
        form.addRow("目标类别:", category_edit)
        form.addRow("优先级:", priority_spin)

        btns = QHBoxLayout()
        ok = QPushButton("保存")
        cancel = QPushButton("取消")
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)

        def on_ok():
            if not name_edit.text().strip():
                QMessageBox.warning(dlg, "校验", "规则名称不能为空")
                return
            if not pattern_edit.text().strip():
                QMessageBox.warning(dlg, "校验", "匹配内容不能为空")
                return
            dlg.accept()

        ok.clicked.connect(on_ok)
        cancel.clicked.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return {
            'rule_name': name_edit.text().strip(),
            'rule_type': type_combo.currentData(),
            'rule_pattern': pattern_edit.text().strip(),
            'target_category': category_edit.text().strip() or '未分类',
            'priority': priority_spin.value(),
        }

    # ── 测试 ──
    def _test_rule(self):
        rule, _ = self._selected_rule()
        if not rule:
            QMessageBox.information(self, "测试规则", "请先选择一条规则")
            return
        sample, ok = QInputDialog.getText(
            self, "测试规则", "输入文件名（或路径）进行模拟分类:", "规则「%s」" % rule['rule_name'])
        if not ok or not sample.strip():
            return
        from core.file_classifier import FileClassifier
        try:
            classifier = FileClassifier(rule_dao=self.rule_dao)
            category = classifier.classify_file({'file_path': sample.strip(),
                                                 'file_name': sample.strip()})
            hit = self._rule_matches(rule, sample.strip())
            detail = "命中规则" if hit else "未命中该规则"
            QMessageBox.information(
                self, "规则测试结果",
                f"输入: {sample.strip()}\n规则: {rule['rule_name']}\n"
                f"模拟分类结果: {category}\n{detail}")
        except Exception as exc:
            logger.exception("规则测试失败")
            QMessageBox.warning(self, "规则测试失败", str(exc))

    @staticmethod
    def _rule_matches(rule: dict, sample: str) -> bool:
        import re
        rtype = rule.get('rule_type', '')
        pattern = rule.get('rule_pattern', '')
        if not pattern:
            return False
        if rtype == 'keyword':
            return any(kw.strip() and kw.strip() in sample
                       for kw in pattern.split('|'))
        if rtype == 'extension':
            ext = sample.rsplit('.', 1)[-1].lower() if '.' in sample else ''
            return any(ext == e.strip().lower().lstrip('.')
                       for e in pattern.split('|') if e.strip())
        if rtype == 'regex':
            try:
                return re.search(pattern, sample) is not None
            except re.error:
                return False
        return False
