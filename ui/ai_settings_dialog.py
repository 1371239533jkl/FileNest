"""
AI 模型设置对话框 —— 添加/管理自定义 AI 提供商。

支持: 选择内置模板 → 填 API Key → 选择模型 → 设为激活。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QListWidget, QStackedWidget, QGroupBox,
    QMessageBox, QSpinBox, QDoubleSpinBox, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.ai_model_config import AIModelConfigManager, AIModelProvider, BUILTIN_PROVIDERS
from utils.logger import logger


class AiSettingsDialog(QDialog):
    """AI 模型管理对话框"""

    config_changed = pyqtSignal()  # 配置变更信号，通知父窗口重载后端

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self._config = AIModelConfigManager()
        self.setWindowTitle("🤖 AI 模型配置")
        self.setMinimumSize(600, 450)
        self._init_ui()
        self._apply_theme()
        self._refresh_list()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 左侧：提供商列表 ──
        left = QVBoxLayout()
        left.setSpacing(8)

        title = QLabel("已配置的 AI 提供商")
        title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #89b4fa;")
        left.addWidget(title)

        self.provider_list = QListWidget()
        self.provider_list.setFixedWidth(180)
        self.provider_list.currentRowChanged.connect(self._on_provider_selected)
        left.addWidget(self.provider_list, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._show_add_menu)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("删除")
        del_btn.setFixedHeight(32)
        del_btn.clicked.connect(self._delete_provider)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)

        layout.addLayout(left)

        # ── 右侧：编辑面板 ──
        right = QVBoxLayout()
        right.setSpacing(10)

        self.edit_title = QLabel("选择一个提供商进行编辑")
        self.edit_title.setStyleSheet("font-size: 13pt; font-weight: bold;")
        right.addWidget(self.edit_title)

        # 基本信息
        info_group = QGroupBox("提供商信息")
        form = QFormLayout(info_group)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如: 我的 DeepSeek")
        form.addRow("名称:", self.name_input)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("API 地址:", self.base_url_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-xxxxxxxx")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key:", self.api_key_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("deepseek-chat")
        form.addRow("模型名:", self.model_input)

        self.models_input = QLineEdit()
        self.models_input.setPlaceholderText("model1,model2,model3（逗号分隔）")
        form.addRow("可用模型列表:", self.models_input)

        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(20)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("超时:", self.timeout_spin)

        right.addWidget(info_group)

        # 激活状态
        status_group = QGroupBox("状态")
        status_layout = QHBoxLayout(status_group)

        self.active_label = QLabel("⚪ 未激活")
        self.active_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        status_layout.addWidget(self.active_label)
        status_layout.addStretch()

        self.activate_btn = QPushButton("设为当前使用")
        self.activate_btn.setObjectName("primaryBtn")
        self.activate_btn.clicked.connect(self._activate_current)
        status_layout.addWidget(self.activate_btn)
        right.addWidget(status_group)

        # 保存按钮
        save_row = QHBoxLayout()
        save_row.addStretch()

        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setFixedHeight(36)
        self.save_btn.clicked.connect(self._save_current)
        save_row.addWidget(self.save_btn)

        test_btn = QPushButton("🔌 测试连接")
        test_btn.setFixedHeight(36)
        test_btn.clicked.connect(self._test_connection)
        save_row.addWidget(test_btn)

        right.addLayout(save_row)

        # 提示
        hint = QLabel(
            "支持所有兼容 OpenAI API 协议的服务商：\n"
            "DeepSeek、通义千问、Moonshot、智谱GLM、OpenAI 等\n"
            "只需填写正确的 API 地址和 Key 即可使用"
        )
        hint.setStyleSheet("font-size: 10pt;")
        right.addWidget(hint)

        layout.addLayout(right, 1)

    def _apply_theme(self):
        is_dark = self._theme == "dark"
        bg = "#1e1e2e" if is_dark else "#eff1f5"
        surface = "#313244" if is_dark else "#e6e9ef"
        text = "#cdd6f4" if is_dark else "#4c4f69"
        subtle = "#a6adc8" if is_dark else "#7c7f93"

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; }}
            QLabel {{ color: {text}; background: transparent; }}
            QGroupBox {{
                color: {text}; border: 1px solid {surface};
                border-radius: 8px; margin-top: 12px; padding-top: 16px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px; padding: 0 6px;
            }}
            QLineEdit {{
                background-color: {surface}; color: {text};
                border: 1px solid {surface}; border-radius: 6px;
                padding: 6px 10px; font-size: 11pt;
            }}
            QLineEdit:focus {{ border: 1px solid #89b4fa; }}
            QDoubleSpinBox {{
                background-color: {surface}; color: {text};
                border: 1px solid {surface}; border-radius: 6px;
                padding: 6px;
            }}
            QListWidget {{
                background-color: {surface}; color: {text};
                border: 1px solid {surface}; border-radius: 8px;
                font-size: 11pt;
            }}
            QListWidget::item:selected {{
                background-color: #89b4fa; color: #1e1e2e;
                border-radius: 4px;
            }}
            QListWidget::item {{ padding: 6px 10px; }}
        """)

    def _refresh_list(self):
        """刷新提供商列表"""
        self.provider_list.clear()
        providers = self._config.list_providers()
        active_id = self._config.active_provider_id

        for p in providers:
            marker = " ✅" if p.provider_id == active_id else ""
            self.provider_list.addItem(f"{p.name}{marker}")

        if providers:
            self.provider_list.setCurrentRow(0)
        else:
            self._clear_edit_form()

    def _on_provider_selected(self, row: int):
        if row < 0:
            self._clear_edit_form()
            return

        providers = self._config.list_providers()
        if row >= len(providers):
            return

        p = providers[row]
        self._fill_edit_form(p)

    def _fill_edit_form(self, p: AIModelProvider):
        """填充编辑表单"""
        self._current_edit_id = p.provider_id
        self.name_input.setText(p.name)
        self.base_url_input.setText(p.base_url)
        self.api_key_input.setText(p.api_key)
        self.model_input.setText(p.model)
        self.models_input.setText(p.models)
        self.timeout_spin.setValue(p.timeout)

        is_active = p.provider_id == self._config.active_provider_id
        self.active_label.setText("🟢 已激活" if is_active else "⚪ 未激活")
        self.activate_btn.setEnabled(not is_active)

        self.edit_title.setText(f"编辑: {p.name}")

    def _clear_edit_form(self):
        """清空编辑表单"""
        self._current_edit_id = None
        self.name_input.clear()
        self.base_url_input.clear()
        self.api_key_input.clear()
        self.model_input.clear()
        self.models_input.clear()
        self.timeout_spin.setValue(20)
        self.active_label.setText("⚪ 未激活")
        self.activate_btn.setEnabled(False)
        self.edit_title.setText("选择一个提供商进行编辑")

    def _show_add_menu(self):
        """显示添加菜单：内置模板 或 自定义"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)

        # 内置模板
        template_menu = menu.addMenu("从模板添加")
        for pid, info in BUILTIN_PROVIDERS.items():
            action = QAction(f"{info['name']}", self)
            action.triggered.connect(lambda checked, p=pid: self._add_from_template(p))
            template_menu.addAction(action)

        menu.addSeparator()

        custom_action = QAction("自定义（空白）", self)
        custom_action.triggered.connect(self._add_custom)
        menu.addAction(custom_action)

        btn = self.sender()
        if btn:
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _add_from_template(self, provider_id: str):
        """从内置模板添加"""
        p = self._config.add_builtin_template(provider_id)
        if not p:
            QMessageBox.warning(self, "错误", f"不支持的模板: {provider_id}")
            return

        self._refresh_list()
        # 选中新添加的
        providers = self._config.list_providers()
        for i, prov in enumerate(providers):
            if prov.provider_id == provider_id:
                self.provider_list.setCurrentRow(i)
                break

    def _add_custom(self):
        """添加自定义空白提供商"""
        from PyQt6.QtWidgets import QInputDialog

        pid, ok = QInputDialog.getText(
            self, "添加自定义提供商",
            "请输入唯一标识（英文）:",
            text="custom"
        )
        if not ok or not pid:
            return

        pid = pid.strip().lower().replace(" ", "_")
        if not pid:
            return

        # 检查重复
        if self._config.get_provider(pid):
            QMessageBox.warning(self, "重复", f"标识 '{pid}' 已存在")
            return

        provider = AIModelProvider(
            provider_id=pid,
            name=pid.title(),
            base_url="https://api.example.com/v1",
            api_key="",
            model="",
            timeout=20,
        )
        self._config.add_provider(provider)
        self._refresh_list()

    def _delete_provider(self):
        """删除当前选中的提供商"""
        row = self.provider_list.currentRow()
        if row < 0:
            return

        providers = self._config.list_providers()
        if row >= len(providers):
            return

        p = providers[row]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除提供商 '{p.name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._config.delete_provider(p.provider_id)
            self._refresh_list()
            self.config_changed.emit()

    def _save_current(self):
        """保存当前编辑的提供商"""
        if not self._current_edit_id:
            QMessageBox.warning(self, "提示", "请先选择一个提供商")
            return

        name = self.name_input.text().strip()
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not name or not base_url:
            QMessageBox.warning(self, "提示", "名称和 API 地址不能为空")
            return

        provider = AIModelProvider(
            provider_id=self._current_edit_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=self.model_input.text().strip(),
            models=self.models_input.text().strip(),
            timeout=self.timeout_spin.value(),
        )
        self._config.add_provider(provider)
        self._refresh_list()
        self.config_changed.emit()

        from ui.toast import notify
        notify(self, f"已保存: {name}", 'success', 3000)

    def _activate_current(self):
        """激活当前提供商"""
        if not self._current_edit_id:
            return

        self._config.set_active(self._current_edit_id)
        self._refresh_list()
        self.config_changed.emit()

        providers = self._config.list_providers()
        for i, p in enumerate(providers):
            if p.provider_id == self._current_edit_id:
                self.provider_list.setCurrentRow(i)
                break

    def _test_connection(self):
        """测试当前配置的连接"""
        if not self._current_edit_id:
            QMessageBox.warning(self, "提示", "请先选择或保存一个提供商")
            return

        api_key = self.api_key_input.text().strip()
        base_url = self.base_url_input.text().strip()
        model = self.model_input.text().strip()

        if not api_key or not base_url:
            QMessageBox.warning(self, "提示", "请填写 API Key 和 API 地址")
            return

        self.test_btn = self.sender()
        if self.test_btn:
            self.test_btn.setEnabled(False)
            self.test_btn.setText("测试中...")

        try:
            from core.ai_backends import OpenAICompatibleBackend
            backend = OpenAICompatibleBackend(
                api_key=api_key,
                base_url=base_url,
                model=model or "default",
                timeout=10,
            )
            result = backend.chat(
                [{"role": "user", "content": "回复 OK"}],
                max_tokens=10,
                temperature=0,
            )
            QMessageBox.information(
                self, "测试成功",
                f"连接成功！\n\n模型: {result.model}\n延迟: {result.latency_ms}ms\nToken: {result.tokens_in}+{result.tokens_out}"
            )
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"连接失败:\n{str(e)[:300]}")
        finally:
            if self.test_btn:
                self.test_btn.setEnabled(True)
                self.test_btn.setText("🔌 测试连接")
