"""
工作区配置对话框（批次6-3）。

轻量实现：工作区是"根目录 + 名称 + 权限配置"的映射，
用于按目录隔离规则/标签/AI 权限。当前版本先提供增删改查 + 基础配置，
深度隔离（规则过滤/标签过滤/AI 权限校验）后续按需接入。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QFileDialog, QCheckBox, QComboBox, QTextEdit, QHeaderView,
    QAbstractItemView
)
from PyQt6.QtCore import Qt

from database.models import WorkspaceDAO
from utils.logger import logger


class WorkspaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工作区配置")
        self.setMinimumSize(640, 480)
        self.dao = WorkspaceDAO()
        self._current_id = None
        self._init_ui()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 列表
        layout.addWidget(QLabel("工作区列表:"))
        self.ws_table = QTableWidget()
        self.ws_table.setColumnCount(4)
        self.ws_table.setHorizontalHeaderLabels(["名称", "根目录", "状态", "AI 权限"])
        self.ws_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ws_table.verticalHeader().setDefaultSectionSize(28)
        self.ws_table.verticalHeader().setVisible(False)
        self.ws_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ws_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ws_table.cellClicked.connect(self._on_select)
        layout.addWidget(self.ws_table, 1)

        # 表单
        form_layout = QVBoxLayout()

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("名称:"))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit, 1)
        form_layout.addLayout(name_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("根目录:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择或输入工作区根目录")
        path_row.addWidget(self.path_edit, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        form_layout.addLayout(path_row)

        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel("描述:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setFixedHeight(60)
        desc_row.addWidget(self.desc_edit, 1)
        form_layout.addLayout(desc_row)

        opt_row = QHBoxLayout()
        self.active_cb = QCheckBox("启用")
        self.active_cb.setChecked(True)
        opt_row.addWidget(self.active_cb)

        opt_row.addWidget(QLabel("规则范围:"))
        self.rule_combo = QComboBox()
        self.rule_combo.addItem("全部规则", "all")
        self.rule_combo.addItem("仅工作区专用规则", "workspace_only")
        opt_row.addWidget(self.rule_combo)

        opt_row.addWidget(QLabel("标签范围:"))
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("全部标签", "all")
        self.tag_combo.addItem("仅工作区专用标签", "workspace_only")
        opt_row.addWidget(self.tag_combo)

        self.ai_cb = QCheckBox("允许 AI 访问")
        self.ai_cb.setChecked(True)
        opt_row.addWidget(self.ai_cb)
        opt_row.addStretch()
        form_layout.addLayout(opt_row)

        layout.addLayout(form_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        new_btn = QPushButton("新建")
        new_btn.clicked.connect(self._new_workspace)
        btn_layout.addWidget(new_btn)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save_workspace)
        btn_layout.addWidget(save_btn)
        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("dangerBtn")
        delete_btn.clicked.connect(self._delete_workspace)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _browse_path(self):
        d = QFileDialog.getExistingDirectory(self, "选择工作区根目录")
        if d:
            self.path_edit.setText(d)

    def _refresh_list(self):
        rows = self.dao.get_all()
        self.ws_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.ws_table.setItem(i, 0, QTableWidgetItem(r['name']))
            self.ws_table.setItem(i, 1, QTableWidgetItem(r['root_path']))
            self.ws_table.setItem(i, 2, QTableWidgetItem('启用' if r['is_active'] else '禁用'))
            self.ws_table.setItem(i, 3, QTableWidgetItem('允许' if r['ai_allowed'] else '禁止'))
            self.ws_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r['id'])

    def _on_select(self, row, _col):
        item = self.ws_table.item(row, 0)
        if not item:
            return
        ws_id = item.data(Qt.ItemDataRole.UserRole)
        ws = self.dao.get_by_id(ws_id)
        if not ws:
            return
        self._current_id = ws_id
        self.name_edit.setText(ws['name'])
        self.path_edit.setText(ws['root_path'])
        self.desc_edit.setPlainText(ws.get('description', '') or '')
        self.active_cb.setChecked(bool(ws.get('is_active', 1)))
        self.ai_cb.setChecked(bool(ws.get('ai_allowed', 1)))
        # 设置下拉
        idx = self.rule_combo.findData(ws.get('rule_scope', 'all'))
        if idx >= 0:
            self.rule_combo.setCurrentIndex(idx)
        idx = self.tag_combo.findData(ws.get('tag_scope', 'all'))
        if idx >= 0:
            self.tag_combo.setCurrentIndex(idx)

    def _new_workspace(self):
        self._current_id = None
        self.name_edit.clear()
        self.path_edit.clear()
        self.desc_edit.clear()
        self.active_cb.setChecked(True)
        self.ai_cb.setChecked(True)
        self.rule_combo.setCurrentIndex(0)
        self.tag_combo.setCurrentIndex(0)
        self.name_edit.setFocus()

    def _save_workspace(self):
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入工作区名称")
            return
        if not path:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return
        try:
            if self._current_id:
                self.dao.update(
                    self._current_id,
                    name=name, root_path=path,
                    description=self.desc_edit.toPlainText(),
                    is_active=1 if self.active_cb.isChecked() else 0,
                    rule_scope=self.rule_combo.currentData(),
                    tag_scope=self.tag_combo.currentData(),
                    ai_allowed=1 if self.ai_cb.isChecked() else 0,
                )
            else:
                self._current_id = self.dao.create(
                    name=name, root_path=path,
                    description=self.desc_edit.toPlainText(),
                    rule_scope=self.rule_combo.currentData(),
                    tag_scope=self.tag_combo.currentData(),
                    ai_allowed=self.ai_cb.isChecked(),
                )
            self._refresh_list()
            QMessageBox.information(self, "成功", "工作区已保存")
        except Exception as e:
            logger.error('保存工作区失败: %s', e)
            QMessageBox.critical(self, "失败", f"保存失败: {e}")

    def _delete_workspace(self):
        if not self._current_id:
            QMessageBox.information(self, "提示", "请先选择要删除的工作区")
            return
        reply = QMessageBox.question(self, "确认", "确定删除此工作区?\n（仅删除配置，不影响真实文件）")
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.dao.delete(self._current_id)
            self._current_id = None
            self._new_workspace()
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "失败", f"删除失败: {e}")
