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
from PyQt6.QtCore import Qt, pyqtSignal, QSettings

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
        self.setMinimumSize(640, 560)
        self._ollama_models = []
        self._embed_worker = None
        self._init_ui()
        self._apply_theme()
        self._refresh_list()
        self._check_ollama()
        self._refresh_embed_status()

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

        # ── 右侧：标签页 ──
        from PyQt6.QtWidgets import QTabWidget, QScrollArea, QWidget

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        # 标签1：提供商设置
        # ponytail: 内容总高超过对话框时 Qt 会把控件压到重叠，用滚动区域兜底
        provider_tab = QWidget()
        provider_outer = QVBoxLayout(provider_tab)
        provider_outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        provider_content = QWidget()
        provider_content.setStyleSheet("background: transparent;")
        right = QVBoxLayout(provider_content)
        right.setSpacing(10)
        right.setContentsMargins(8, 8, 8, 8)

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

        # 本地 Ollama 状态
        ollama_group = QGroupBox("本地 Ollama")
        ollama_layout = QVBoxLayout(ollama_group)

        self.ollama_status = QLabel("检测中...")
        self.ollama_status.setStyleSheet("font-size: 10pt;")
        ollama_layout.addWidget(self.ollama_status)

        ollama_btn_row = QHBoxLayout()
        self.refresh_ollama_btn = QPushButton("🔄 检测本地模型")
        self.refresh_ollama_btn.setFixedHeight(28)
        self.refresh_ollama_btn.clicked.connect(self._check_ollama)
        ollama_btn_row.addWidget(self.refresh_ollama_btn)

        self.add_ollama_btn = QPushButton("➕ 添加为提供商")
        self.add_ollama_btn.setFixedHeight(28)
        self.add_ollama_btn.clicked.connect(self._add_ollama_as_provider)
        self.add_ollama_btn.setEnabled(False)
        ollama_btn_row.addWidget(self.add_ollama_btn)
        ollama_btn_row.addStretch()
        ollama_layout.addLayout(ollama_btn_row)

        right.addWidget(ollama_group)

        # 向量索引管理
        embed_group = QGroupBox("🧠 语义搜索索引")
        embed_layout = QVBoxLayout(embed_group)

        self.embed_status = QLabel("加载中...")
        self.embed_status.setStyleSheet("font-size: 10pt;")
        embed_layout.addWidget(self.embed_status)

        # 向量模型与对话模型是两回事：对话模型（如 qwen-plus）不支持 /embeddings
        embed_model_row = QHBoxLayout()
        embed_model_row.addWidget(QLabel("向量模型:"))
        self.embed_model_input = QLineEdit(
            QSettings("smart-file-manager", "ai").value("embed_model", "", str)
        )
        self.embed_model_input.setPlaceholderText(
            "如 text-embedding-v4 / nomic-embed-text，留空用当前对话模型"
        )
        embed_model_row.addWidget(self.embed_model_input, 1)
        embed_layout.addLayout(embed_model_row)

        embed_btn_row = QHBoxLayout()
        self.build_embed_btn = QPushButton("⚡ 为所有文件生成索引")
        self.build_embed_btn.setFixedHeight(28)
        self.build_embed_btn.clicked.connect(self._build_embeddings)
        embed_btn_row.addWidget(self.build_embed_btn)

        self.clear_embed_btn = QPushButton("🗑 清空索引")
        self.clear_embed_btn.setFixedHeight(28)
        self.clear_embed_btn.clicked.connect(self._clear_embeddings)
        embed_btn_row.addWidget(self.clear_embed_btn)
        embed_btn_row.addStretch()
        embed_layout.addLayout(embed_btn_row)

        right.addWidget(embed_group)

        # 提示
        hint = QLabel(
            "支持所有兼容 OpenAI API 协议的服务商：\n"
            "DeepSeek、通义千问、Moonshot、智谱GLM、OpenAI 等\n"
            "本地 Ollama 无需 API Key，自动发现零配置使用"
        )
        hint.setStyleSheet("font-size: 10pt;")
        right.addWidget(hint)
        right.addStretch()
        scroll.setWidget(provider_content)
        provider_outer.addWidget(scroll)

        self.tab_widget.addTab(provider_tab, "🔑 提供商")

        # 标签2：隐私控制
        privacy_tab = QWidget()
        privacy_layout = QVBoxLayout(privacy_tab)
        privacy_layout.setSpacing(10)
        privacy_layout.setContentsMargins(8, 8, 8, 8)
        self._build_privacy_tab(privacy_layout)
        self.tab_widget.addTab(privacy_tab, "🔒 隐私控制")

        layout.addWidget(self.tab_widget, 1)

    # ── 隐私控制标签页 ──

    def _build_privacy_tab(self, layout: QVBoxLayout):
        """构建隐私控制标签页。"""
        from core.ai_privacy import AIPrivacy
        from core.ai_layer import AILayer
        from core.ollama_backend import OllamaBackend

        privacy = AIPrivacy()
        ai = AILayer()

        # 数据去向卡片
        dest_group = QGroupBox("📡 数据去向")
        dest_layout = QVBoxLayout(dest_group)

        backend_info = ai.get_backend_info()
        is_local = backend_info.get('name') == '本地 Ollama'
        dest = privacy.get_data_destination(
            'local' if is_local else 'cloud',
            backend_info.get('model', '')
        )

        dest_title = QLabel(dest['title'])
        dest_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        dest_layout.addWidget(dest_title)

        dest_desc = QLabel(dest['description'])
        dest_desc.setStyleSheet("font-size: 10pt;")
        dest_layout.addWidget(dest_desc)

        details_text = "\n".join(f"  • {d}" for d in dest['details'])
        dest_details = QLabel(details_text)
        dest_details.setStyleSheet("font-size: 9pt;")
        dest_layout.addWidget(dest_details)

        layout.addWidget(dest_group)

        # 禁止目录
        dir_group = QGroupBox("🚫 禁止 AI 访问的目录")
        dir_layout = QVBoxLayout(dir_group)

        dir_hint = QLabel("以下目录中的文件不会被 AI 读取或分析：")
        dir_hint.setStyleSheet("font-size: 10pt;")
        dir_layout.addWidget(dir_hint)

        self.forbidden_dir_list = QListWidget()
        self.forbidden_dir_list.setFixedHeight(100)
        for d in privacy.get_forbidden_dirs():
            self.forbidden_dir_list.addItem(d)
        dir_layout.addWidget(self.forbidden_dir_list)

        dir_btn_row = QHBoxLayout()
        add_dir_btn = QPushButton("➕ 添加目录")
        add_dir_btn.setFixedHeight(28)
        add_dir_btn.clicked.connect(self._add_forbidden_dir)
        dir_btn_row.addWidget(add_dir_btn)

        remove_dir_btn = QPushButton("➖ 移除选中")
        remove_dir_btn.setFixedHeight(28)
        remove_dir_btn.clicked.connect(self._remove_forbidden_dir)
        dir_btn_row.addWidget(remove_dir_btn)
        dir_btn_row.addStretch()
        dir_layout.addLayout(dir_btn_row)

        layout.addWidget(dir_group)

        # 调用统计
        stats_group = QGroupBox("📊 AI 使用统计（最近 7 天）")
        stats_layout = QVBoxLayout(stats_group)

        stats = privacy.get_stats(days=7)
        stats_text = (
            f"总调用次数: {stats['total_calls']} 次  |  "
            f"成功: {stats['success_calls']} 次  |  "
            f"总 Token: {stats['total_tokens']:,}  |  "
            f"涉及文件: {stats['total_files']} 个"
        )
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("font-size: 10pt;")
        stats_layout.addWidget(stats_label)

        # 按类型统计
        if stats['by_type']:
            type_text = "按类型: " + ", ".join(
                f"{t['call_type']} {t['cnt']}次" for t in stats['by_type'][:5]
            )
            type_label = QLabel(type_text)
            type_label.setStyleSheet("font-size: 9pt;")
            stats_layout.addWidget(type_label)

        log_btn_row = QHBoxLayout()
        view_log_btn = QPushButton("📋 查看调用记录")
        view_log_btn.setFixedHeight(28)
        view_log_btn.clicked.connect(self._view_ai_logs)
        log_btn_row.addWidget(view_log_btn)

        clear_log_btn = QPushButton("🗑 清空日志")
        clear_log_btn.setFixedHeight(28)
        clear_log_btn.clicked.connect(self._clear_ai_logs)
        log_btn_row.addWidget(clear_log_btn)
        log_btn_row.addStretch()
        stats_layout.addLayout(log_btn_row)

        layout.addWidget(stats_group)

        layout.addStretch()

    def _add_forbidden_dir(self):
        """添加禁止目录。"""
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择禁止 AI 访问的目录")
        if path:
            from core.ai_privacy import AIPrivacy
            privacy = AIPrivacy()
            if privacy.add_forbidden_dir(path):
                self.forbidden_dir_list.addItem(path)
                from ui.toast import notify
                notify(self, "已添加禁止目录", 'success', 2000)
            else:
                from ui.toast import notify
                notify(self, "目录已存在", 'warning', 2000)

    def _remove_forbidden_dir(self):
        """移除选中的禁止目录。"""
        item = self.forbidden_dir_list.currentItem()
        if not item:
            return
        path = item.text()
        from core.ai_privacy import AIPrivacy
        privacy = AIPrivacy()
        if privacy.remove_forbidden_dir(path):
            self.forbidden_dir_list.takeItem(self.forbidden_dir_list.currentRow())
            from ui.toast import notify
            notify(self, "已移除禁止目录", 'success', 2000)

    def _view_ai_logs(self):
        """查看 AI 调用记录。"""
        from core.ai_privacy import AIPrivacy
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        import time
        from datetime import datetime

        privacy = AIPrivacy()
        logs = privacy.get_logs(limit=100)

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 AI 调用记录（最近 100 条）")
        dlg.setMinimumSize(600, 400)
        dlg_layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)

        lines = []
        for log in logs:
            ts = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            status = "✅" if log['success'] else "❌"
            line = (
                f"[{ts}] {status} {log['call_type']} - "
                f"{log['model']} - {log['total_tokens']} tokens - "
                f"{log['latency_ms']}ms - {log['file_count']}个文件"
            )
            if not log['success'] and log.get('error_msg'):
                line += f"\n  错误: {log['error_msg']}"
            if log.get('file_paths'):
                paths = log['file_paths'].split('\n')[:3]
                line += f"\n  文件: {', '.join(paths)}"
            lines.append(line)

        text.setPlainText("\n\n".join(lines) if lines else "暂无调用记录")
        dlg_layout.addWidget(text)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        btn_box.accepted.connect(dlg.accept)
        dlg_layout.addWidget(btn_box)

        dlg.exec()

    def _clear_ai_logs(self):
        """清空 AI 调用日志。"""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有 AI 调用日志吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from core.ai_privacy import AIPrivacy
            AIPrivacy().clear_logs()
            from ui.toast import notify
            notify(self, "已清空调用日志", 'success', 2000)

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

    def _check_ollama(self):
        """检测本地 Ollama 服务和已安装模型。"""
        from core.ollama_backend import OllamaBackend

        self.refresh_ollama_btn.setEnabled(False)
        self.refresh_ollama_btn.setText("检测中...")

        try:
            ok, info = OllamaBackend.is_available()
            if ok:
                models = OllamaBackend.list_local_models()
                model_names = [m.get("name", "") for m in models]
                self._ollama_models = model_names
                if model_names:
                    self.ollama_status.setText(
                        f"🟢 {info}\n已安装模型: {', '.join(model_names[:5])}"
                        + ("..." if len(model_names) > 5 else "")
                    )
                    self.add_ollama_btn.setEnabled(True)
                else:
                    self.ollama_status.setText(f"🟡 Ollama 运行中，但未安装任何模型")
                    self.add_ollama_btn.setEnabled(False)
            else:
                self.ollama_status.setText(f"🔴 Ollama 不可用: {info}")
                self.add_ollama_btn.setEnabled(False)
                self._ollama_models = []
        except Exception as e:
            self.ollama_status.setText(f"🔴 检测失败: {str(e)[:80]}")
            self.add_ollama_btn.setEnabled(False)
        finally:
            self.refresh_ollama_btn.setEnabled(True)
            self.refresh_ollama_btn.setText("🔄 检测本地模型")

    def _add_ollama_as_provider(self):
        """将本地 Ollama 添加为提供商。"""
        if not getattr(self, '_ollama_models', None):
            return

        # 检查是否已存在
        if self._config.get_provider("ollama"):
            QMessageBox.information(self, "提示", "Ollama 提供商已存在")
            return

        models_str = ",".join(self._ollama_models)
        default_model = self._ollama_models[0]
        # 优先选 instruct/chat 模型
        for m in self._ollama_models:
            if "instruct" in m.lower() or "chat" in m.lower():
                default_model = m
                break

        provider = AIModelProvider(
            provider_id="ollama",
            name="Ollama (本地)",
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # 占位符，Ollama 不需要
            model=default_model,
            models=models_str,
            timeout=120,
        )
        self._config.add_provider(provider)
        self._refresh_list()
        self.config_changed.emit()

        # 选中新添加的
        providers = self._config.list_providers()
        for i, p in enumerate(providers):
            if p.provider_id == "ollama":
                self.provider_list.setCurrentRow(i)
                break

        from ui.toast import notify
        notify(self, "已添加本地 Ollama 提供商", 'success', 3000)

    # ── 向量索引 ──

    def _get_embedding_service(self):
        """获取 EmbeddingService 实例（懒加载，读取当前向量模型输入）。"""
        from core.embedding_service import EmbeddingService
        from core.ai_layer import AILayer
        model = self.embed_model_input.text().strip() or None
        return EmbeddingService(AILayer(), embed_model=model)

    def _refresh_embed_status(self):
        """刷新向量索引状态显示。"""
        try:
            svc = self._get_embedding_service()
            count = svc.count_embedded()
            total = 0
            try:
                from database.db_manager import db
                row = db.execute_one(
                    "SELECT COUNT(*) as c FROM files WHERE status = 'active'"
                )
                total = row['c'] if row else 0
            except Exception:
                pass

            if total > 0:
                pct = count / total * 100
                self.embed_status.setText(
                    f"📊 已索引 {count} / {total} 个文件 ({pct:.1f}%)"
                )
            else:
                self.embed_status.setText(f"📊 已索引 {count} 个文件")

            self.build_embed_btn.setEnabled(svc.is_available())
            self.clear_embed_btn.setEnabled(count > 0)
        except Exception as e:
            self.embed_status.setText(f"❌ 状态获取失败: {str(e)[:60]}")

    def _build_embeddings(self):
        """为所有未索引的文件生成 embedding。"""
        from PyQt6.QtCore import QThread, pyqtSignal
        from database.db_manager import db
        from core import file_reader

        svc = self._get_embedding_service()
        if not svc.is_available():
            QMessageBox.warning(self, "提示", "AI 后端不可用，无法生成向量索引")
            return

        # 持久化向量模型，下次打开自动填入
        QSettings("smart-file-manager", "ai").setValue(
            "embed_model", self.embed_model_input.text().strip()
        )

        # 获取未索引的文件
        try:
            rows = db.execute_query("""
                SELECT f.id, f.file_path, f.file_name, f.file_extension, f.file_size
                FROM files f
                LEFT JOIN file_embeddings e ON f.id = e.file_id
                WHERE f.status = 'active' AND e.file_id IS NULL
                ORDER BY f.file_size ASC
                LIMIT 500
            """)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查询文件失败: {e}")
            return

        if not rows:
            QMessageBox.information(self, "完成", "所有文件都已生成向量索引")
            return

        reply = QMessageBox.question(
            self, "确认",
            f"将为 {len(rows)} 个文件生成向量索引，可能需要几分钟。\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.build_embed_btn.setEnabled(False)
        self.build_embed_btn.setText("生成中...")

        # 后台线程生成
        class _EmbedWorker(QThread):
            progress = pyqtSignal(int, int)  # done, total
            finished_ok = pyqtSignal(int)
            error = pyqtSignal(str)

            def __init__(self, svc, rows):
                super().__init__()
                self._svc = svc
                self._rows = rows

            def run(self):
                success = 0
                total = len(self._rows)
                batch = []
                for i, row in enumerate(self._rows):
                    try:
                        # 提取文本内容（文件名+扩展名+前几KB内容）
                        from core import file_reader
                        content = file_reader.read_file_content(
                            row['file_path'], max_chars=1500
                        ) or ""
                        text = f"{row['file_name']}\n{content}" if content else row['file_name']
                        if text:
                            batch.append((row['id'], text[:2000]))

                        # 每 10 个一批
                        if len(batch) >= 10 or i == total - 1:
                            if batch:
                                n = self._svc.batch_upsert(batch)
                                success += n
                                batch = []
                    except Exception:
                        pass
                    self.progress.emit(i + 1, total)

                self.finished_ok.emit(success)

        self._embed_worker = _EmbedWorker(svc, rows)
        self._embed_worker.progress.connect(
            lambda done, total: self.build_embed_btn.setText(
                f"生成中... {done}/{total}"
            )
        )
        self._embed_worker.finished_ok.connect(self._on_embed_done)
        self._embed_worker.error.connect(
            lambda e: (
                self.build_embed_btn.setEnabled(True),
                self.build_embed_btn.setText("⚡ 为所有文件生成索引"),
                QMessageBox.critical(self, "错误", f"生成失败: {e}"),
            )
        )
        self._embed_worker.start()

    def _on_embed_done(self, count: int):
        self.build_embed_btn.setEnabled(True)
        self.build_embed_btn.setText("⚡ 为所有文件生成索引")
        self._refresh_embed_status()
        if count == 0:
            QMessageBox.warning(
                self, "失败",
                "没有生成任何向量索引。\n"
                "常见原因：当前对话模型不支持 /embeddings 接口（如 qwen-plus、deepseek-chat）。\n"
                "请在上方填写专门的向量模型，如 text-embedding-v4（通义）、"
                "nomic-embed-text（Ollama）。\n详情见 logs/app.log。"
            )
            return
        QMessageBox.information(self, "完成", f"成功生成 {count} 个文件的向量索引")

    def _clear_embeddings(self):
        """清空所有向量索引。"""
        reply = QMessageBox.question(
            self, "确认",
            "确定要清空所有向量索引吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            svc = self._get_embedding_service()
            svc.clear_all()
            self._refresh_embed_status()
            from ui.toast import notify
            notify(self, "已清空向量索引", 'success', 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"清空失败: {e}")

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
