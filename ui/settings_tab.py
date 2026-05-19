"""
设置标签页 - 通用、扫描、重命名模板、去重策略
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox,
    QSpinBox, QFormLayout, QGroupBox
)

from config import DEDUP_STRATEGIES, MYSQL_CONFIG
from database.db_manager import db
from database.models import SystemSettingsDAO
from utils.logger import logger
from ui.toast import notify


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_dao = SystemSettingsDAO(db)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 左侧分类列表
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(130)
        self.category_list.addItems(["通用设置", "扫描设置", "重命名模板", "去重策略"])
        self.category_list.currentRowChanged.connect(self._on_category_changed)
        layout.addWidget(self.category_list)

        # 右侧设置面板
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_general_page())
        self.stack.addWidget(self._create_scan_page())
        self.stack.addWidget(self._create_rename_page())
        self.stack.addWidget(self._create_dedup_page())
        layout.addWidget(self.stack, 1)

        self.category_list.setCurrentRow(0)

    def _on_category_changed(self, index):
        self.stack.setCurrentIndex(index)

    def _create_general_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("通用设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7;")
        layout.addWidget(title)

        group = QGroupBox("应用配置")
        form = QFormLayout(group)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        log_hint = QLabel("DEBUG=详细调试  INFO=常规  WARNING=仅警告  ERROR=仅错误")
        log_hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        form.addRow("", log_hint)
        form.addRow("日志级别:", self.log_level_combo)

        layout.addWidget(group)

        # 数据库信息（从配置读取，非硬编码）
        db_group = QGroupBox("数据库信息")
        db_layout = QFormLayout(db_group)
        db_layout.addRow("主机:", QLabel(MYSQL_CONFIG.get('host', 'localhost')))
        db_layout.addRow("端口:", QLabel(str(MYSQL_CONFIG.get('port', 3306))))
        db_layout.addRow("数据库名:", QLabel(MYSQL_CONFIG.get('database', '-')))
        db_layout.addRow("用户名:", QLabel(MYSQL_CONFIG.get('user', 'root')))
        layout.addWidget(db_group)

        # 操作按钮行
        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(lambda: self._save_settings([
            ('log_level', self.log_level_combo.currentText(), 'string', '日志级别'),
        ]))
        btn_row.addWidget(save_btn)
        reset_btn = QPushButton("重置默认", self)
        reset_btn.clicked.connect(lambda: self._reset_general())
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return page

    def _create_scan_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("扫描设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7;")
        layout.addWidget(title)

        group = QGroupBox("默认扫描参数")
        form = QFormLayout(group)

        self.default_recursive = QCheckBox("默认递归扫描子目录")
        self.default_recursive.setChecked(True)
        form.addRow(self.default_recursive)

        self.include_hidden = QCheckBox("包含隐藏文件")
        self.include_hidden.setChecked(False)
        form.addRow(self.include_hidden)

        self.hash_algo_combo = QComboBox()
        self.hash_algo_combo.addItems(["sha256", "md5"])
        form.addRow("去重哈希算法:", self.hash_algo_combo)
        algo_hint = QLabel("sha256更安全（推荐），md5速度更快")
        algo_hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        form.addRow("", algo_hint)

        self.max_hash_size = QSpinBox()
        self.max_hash_size.setRange(1, 10000)
        self.max_hash_size.setValue(500)
        self.max_hash_size.setSuffix(" MB")
        form.addRow("大文件跳过哈希（＞多少MB不计算）:", self.max_hash_size)

        layout.addWidget(group)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(lambda: self._save_settings([
            ('scan_recursive', '1' if self.default_recursive.isChecked() else '0', 'bool'),
            ('include_hidden', '1' if self.include_hidden.isChecked() else '0', 'bool'),
            ('hash_algorithm', self.hash_algo_combo.currentText(), 'string'),
            ('max_hash_size_mb', str(self.max_hash_size.value()), 'int'),
        ]))
        btn_row.addWidget(save_btn)
        reset_btn = QPushButton("重置默认", self)
        reset_btn.clicked.connect(lambda: self._reset_scan())
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return page

    def _create_rename_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("重命名模板设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7;")
        layout.addWidget(title)

        group = QGroupBox("命名模板")
        form = QFormLayout(group)

        self.rename_pattern = QLineEdit()
        self.rename_pattern.setPlaceholderText("例如：{date}_{type}_{original_name}")
        form.addRow("模板格式:", self.rename_pattern)

        # 可用变量（紧跟输入框下方）
        var_hint = QLabel(
            "  可用变量：{date}日期  {time}时间  {type}类型  "
            "{original_name}原名  {ext}扩展名")
        var_hint.setStyleSheet("color: #6c7086; font-size: 11px; padding: 4px 0 0 0;")
        form.addRow("", var_hint)

        layout.addWidget(group)

        # 预览（带样式面板）
        preview_group = QGroupBox("实时预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("20240315_图片_风景照.jpg")
        self.preview_label.setStyleSheet(
            "color: #a6e3a1; font-size: 15px; font-weight: bold; "
            "background: #1e1e2e; border: 1px solid #45475a; "
            "border-radius: 6px; padding: 10px 14px;")
        preview_layout.addWidget(self.preview_label)
        preview_hint = QLabel("💡 输入模板后实时预览")
        preview_hint.setStyleSheet("color: #6c7086; font-size: 11px; padding-left: 4px;")
        preview_layout.addWidget(preview_hint)
        layout.addWidget(preview_group)

        self.rename_pattern.textChanged.connect(self._update_preview)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存模板")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(lambda: self._save_settings([
            ('rename_pattern', self.rename_pattern.text(), 'string', '重命名模板'),
        ]))
        btn_row.addWidget(save_btn)
        reset_btn = QPushButton("重置默认", self)
        reset_btn.clicked.connect(lambda: self._reset_rename())
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return page

    def _create_dedup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("去重策略设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7;")
        layout.addWidget(title)

        group = QGroupBox("默认去重策略")
        form = QFormLayout(group)

        self.dedup_combo = QComboBox()
        for key, desc in DEDUP_STRATEGIES.items():
            self.dedup_combo.addItem(desc, key)
        form.addRow("保留策略:", self.dedup_combo)

        layout.addWidget(group)

        # 说明
        info_group = QGroupBox("策略说明")
        info_layout = QVBoxLayout(info_group)
        for key, desc in DEDUP_STRATEGIES.items():
            explanations = {
                'keep_newest': '当发现重复文件时，保留修改时间最新的文件，删除其余副本',
                'keep_oldest': '当发现重复文件时，保留修改时间最早的文件',
                'keep_shortest_path': '当发现重复文件时，保留路径最短（层级最浅）的文件',
                'manual': '每组重复文件都需要手动确认保留哪个',
            }
            info_layout.addWidget(QLabel(f"  {desc}: {explanations.get(key, '')}"))
        layout.addWidget(info_group)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存策略")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(lambda: self._save_settings([
            ('dedup_strategy', self.dedup_combo.currentData(), 'string', '去重策略'),
        ]))
        btn_row.addWidget(save_btn)
        reset_btn = QPushButton("重置默认", self)
        reset_btn.clicked.connect(lambda: self._reset_dedup())
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return page

    def refresh_data(self):
        self._load_settings()

    def _load_settings(self):
        try:
            # 日志级别
            log_level = self.settings_dao.get('log_level', 'INFO')
            idx = self.log_level_combo.findText(log_level)
            if idx >= 0:
                self.log_level_combo.setCurrentIndex(idx)

            pattern = self.settings_dao.get('rename_pattern', '{date}_{type}_{original_name}')
            self.rename_pattern.setText(pattern)

            strategy = self.settings_dao.get('dedup_strategy', 'keep_newest')
            idx = self.dedup_combo.findData(strategy)
            if idx >= 0:
                self.dedup_combo.setCurrentIndex(idx)

            recursive = self.settings_dao.get('scan_recursive', True)
            self.default_recursive.setChecked(bool(recursive))

            hidden = self.settings_dao.get('include_hidden', False)
            self.include_hidden.setChecked(bool(hidden))

            # 哈希算法
            algo = self.settings_dao.get('hash_algorithm', 'sha256')
            ai = self.hash_algo_combo.findText(algo)
            if ai >= 0:
                self.hash_algo_combo.setCurrentIndex(ai)

            # 最大哈希大小
            max_hash = str(self.settings_dao.get('max_hash_size_mb', 500))
            try:
                self.max_hash_size.setValue(int(max_hash))
            except (ValueError, TypeError):
                pass
        except Exception as e:
            logger.error(f"加载设置失败: {e}")

    def _update_preview(self):
        pattern = self.rename_pattern.text()
        preview = pattern.replace('{date}', '20240315')
        preview = preview.replace('{time}', '143025')
        preview = preview.replace('{type}', '图片')
        preview = preview.replace('{original_name}', '风景照')
        preview = preview.replace('{ext}', '.jpg')
        if not preview.endswith('.jpg'):
            preview += '.jpg'
        self.preview_label.setText(preview)

    _DEFAULTS = {
        'log_level': 'INFO',
        'rename_pattern': '{date}_{type}_{original_name}',
        'dedup_strategy': 'keep_newest',
        'scan_recursive': True,
        'include_hidden': False,
        'hash_algorithm': 'sha256',
        'max_hash_size_mb': 500,
    }

    def _save_settings(self, settings: list):
        """通用保存：批量写入设置项，成功后显示 Toast"""
        try:
            for key, value, stype, *desc in settings:
                desc_str = desc[0] if desc else ''
                self.settings_dao.set(key, value, stype, desc_str)
            notify(self, "设置已保存", 'success', 3000)
        except Exception as e:
            notify(self, f"保存失败: {e}", 'error', 5000)

    def _reset_general(self):
        self.log_level_combo.setCurrentText(self._DEFAULTS['log_level'])

    def _reset_scan(self):
        self.default_recursive.setChecked(self._DEFAULTS['scan_recursive'])
        self.include_hidden.setChecked(self._DEFAULTS['include_hidden'])
        ai = self.hash_algo_combo.findText(self._DEFAULTS['hash_algorithm'])
        if ai >= 0: self.hash_algo_combo.setCurrentIndex(ai)
        self.max_hash_size.setValue(self._DEFAULTS['max_hash_size_mb'])

    def _reset_rename(self):
        self.rename_pattern.setText(self._DEFAULTS['rename_pattern'])

    def _reset_dedup(self):
        idx = self.dedup_combo.findData(self._DEFAULTS['dedup_strategy'])
        if idx >= 0: self.dedup_combo.setCurrentIndex(idx)
