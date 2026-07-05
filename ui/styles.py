"""
统一 QSS 样式定义 — 全新深色主题（暗蓝/深空黑）
配色：背景 #0f0f1a，卡片 #1a1a2e，强调蓝 #3b82f6，绿 #10b981，橙 #f59e0b
ponytail: 从 Catppuccin 旧主题全面替换为设计图暗色风格。
"""

# ──────── 深色主题（Ardot 设计图配色）───────
DARK_STYLE = """
/* ===== 全局 ===== */
QMainWindow {
    background-color: #0f0f1a;
    color: #e8e8ef;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget {
    background-color: transparent;
    color: #e8e8ef;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame {
    background-color: #1a1a2e;
    border: none;
}

QWidget#headerBar {
    background-color: #0f0f1a;
    border-bottom: 1px solid #1e1e2e;
}

QWidget#contentPanel {
    background-color: transparent;
    border: none;
}


/* ===== 侧边图标导航栏 ===== */
QListWidget#navSidebar {
    background-color: #0f0f1a;
    color: #6b6b7b;
    border: none;
    border-right: none;
    outline: none;
    padding: 8px 0;
    font-size: 18px;
    min-width: 52px;
    max-width: 52px;
}
QListWidget#navSidebar::item {
    padding: 10px 4px;
    border-radius: 8px;
    margin: 2px 4px;
    text-align: center;
}
QListWidget#navSidebar::item:selected {
    background-color: #1e1e2e;
    color: #3b82f6;
    font-weight: bold;
    border: none;
}
QListWidget#navSidebar::item:hover:!selected {
    background-color: #1a1a2e;
    color: #a0a0b0;
}

/* 标签云列表 - 深色 */
QListWidget#tagCloudList {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget#tagCloudList::item {
    padding: 0;
    margin: 0;
    border: none;
    background: transparent;
}
QListWidget#tagCloudList::item:selected {
    background: transparent;
    border: none;
}

/* 主题切换按钮 */
QPushButton#themeToggleBtn {
    background-color: #1a1a2e;
    color: #a0a0b0;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#themeToggleBtn:hover {
    background-color: #2a2a3e;
    border-color: #3b82f6;
    color: #e8e8ef;
}

/* 标签页（兼容使用 QTabWidget 的子页面） */
QTabWidget::pane {
    border: none;
    background-color: #0f0f1a;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #1a1a2e;
    color: #6b6b7b;
    padding: 10px 20px;
    margin-right: 4px;
    border-radius: 8px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background-color: #2a2a3e;
    color: #3b82f6;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #2a2a3e;
    color: #e8e8ef;
}

/* 分割器 */
QSplitter::handle {
    background-color: transparent;
}

/* 按钮 */
QPushButton {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #2a2a3e;
    border-color: #3b82f6;
}
QPushButton:pressed {
    background-color: #3b82f6;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #1a1a2e;
    color: #4b4b5b;
    border-color: #2a2a3e;
}
QPushButton#primaryBtn {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #2563eb;
}
QPushButton#dangerBtn {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #dc2626;
}
QPushButton#successBtn {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}
QPushButton#successBtn:hover {
    background-color: #059669;
}
QPushButton#warningBtn {
    background-color: #f59e0b;
    color: #0f0f1a;
    border: none;
    font-weight: bold;
}
QPushButton#warningBtn:hover {
    background-color: #d97706;
}

/* 输入框 */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #3b82f6;
}

/* 下拉框 */
QComboBox {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: 1px solid #2a2a3e;
    selection-background-color: #3b82f6;
    border-radius: 8px;
}

/* 表格 */
QTableWidget, QTableView {
    background-color: #1a1a2e;
    alternate-background-color: #161626;
    color: #e8e8ef;
    gridline-color: #2a2a3e;
    border: none;
    border-radius: 12px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}
QTableWidget::item, QTableView::item {
    padding: 8px 12px;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1a1a2e;
    color: #6b6b7b;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid #2a2a3e;
    font-weight: bold;
}

/* 树形视图 */
QTreeWidget {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: none;
    border-radius: 12px;
    outline: none;
}
QTreeWidget::item {
    padding: 8px 6px;
}
QTreeWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QTreeWidget::item:hover {
    background-color: #2a2a3e;
}

/* 进度条 */
QProgressBar {
    background-color: #1a1a2e;
    border: none;
    border-radius: 8px;
    text-align: center;
    color: #e8e8ef;
    min-height: 24px;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 8px;
}

/* 滚动条 */
QScrollBar:vertical {
    background-color: #0f0f1a;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #3b3b4b;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #5b5b6b;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #0f0f1a;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #3b3b4b;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #5b5b6b;
}

/* 复选框 */
QCheckBox {
    color: #e8e8ef;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #2a2a3e;
    border-radius: 4px;
    background-color: #1a1a2e;
}
QCheckBox::indicator:checked {
    background-color: #3b82f6;
    border-color: #3b82f6;
}

/* 列表 */
QListWidget {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: none;
    border-radius: 8px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
}
QListWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #2a2a3e;
}

/* 日期选择 */
QDateEdit {
    background-color: #1a1a2e;
    color: #e8e8ef;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 8px 12px;
}

/* 分组框 */
QGroupBox {
    border: none;
    border-radius: 12px;
    margin-top: 12px;
    padding-top: 16px;
    color: #a0a0b0;
    font-weight: bold;
    background-color: #1a1a2e;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: #1a1a2e;
}

/* 标签 */
QLabel#titleLabel {
    font-size: 20px;
    font-weight: bold;
    color: #ffffff;
    background: transparent;
    border: none;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #6b6b7b;
    background: transparent;
    border: none;
}
QLabel#statLabel {
    font-size: 28px;
    font-weight: bold;
    color: #3b82f6;
}
QLabel#cardBg {
    background-color: #1a1a2e;
    border-radius: 12px;
    border: none;
}

/* 消息框 */
QMessageBox {
    background-color: #0f0f1a;
}
QMessageBox QLabel {
    color: #e8e8ef;
}

/* 状态栏 */
QStatusBar#appStatusBar {
    background-color: #0f0f1a;
    border-top: 1px solid #1e1e2e;
    color: #6b6b7b;
    font-size: 12px;
    padding: 0 12px;
}
QStatusBar#appStatusBar::item {
    border: none;
}

/* ===== 新增：消除所有 QLabel 默认边框和背景 ===== */
QLabel {
    border: none;
    background: transparent;
}

"""


# ──────── 浅色主题（暂保留结构，后续可细化）───────
LIGHT_STYLE = """
/* ===== 全局 ===== */
QMainWindow {
    background-color: #f5f7fa;
    color: #333333;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget {
    background-color: transparent;
    color: #333333;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame {
    background-color: #ffffff;
    border: none;
}

QWidget#headerBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}

QWidget#contentPanel {
    background-color: transparent;
    border: none;
}


/* ===== 侧边图标导航栏 ===== */
QListWidget#navSidebar {
    background-color: #ffffff;
    color: #94a3b8;
    border: none;
    border-right: none;
    outline: none;
    padding: 8px 0;
    font-size: 18px;
    min-width: 52px;
    max-width: 52px;
}
QListWidget#navSidebar::item {
    padding: 10px 4px;
    border-radius: 8px;
    margin: 2px 4px;
    text-align: center;
}
QListWidget#navSidebar::item:selected {
    background-color: #e2e8f0;
    color: #3b82f6;
    font-weight: bold;
    border: none;
}
QListWidget#navSidebar::item:hover:!selected {
    background-color: #f1f5f9;
    color: #64748b;
}

/* 主题切换按钮 */
QPushButton#themeToggleBtn {
    background-color: #e2e8f0;
    color: #64748b;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#themeToggleBtn:hover {
    background-color: #cbd5e1;
    border-color: #3b82f6;
}

/* 标签页 */
QTabWidget::pane {
    border: none;
    background-color: #f5f7fa;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #e2e8f0;
    color: #64748b;
    padding: 10px 20px;
    margin-right: 4px;
    border-radius: 8px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #3b82f6;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #ffffff;
    color: #333333;
}

/* 分割器 */
QSplitter::handle {
    background-color: transparent;
}

/* 按钮 */
QPushButton {
    background-color: #e2e8f0;
    color: #333333;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #cbd5e1;
    border-color: #3b82f6;
}
QPushButton:pressed {
    background-color: #3b82f6;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #e2e8f0;
    color: #94a3b8;
    border-color: #cbd5e1;
}
QPushButton#primaryBtn {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #2563eb;
}
QPushButton#dangerBtn {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #dc2626;
}
QPushButton#successBtn {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}
QPushButton#successBtn:hover {
    background-color: #059669;
}
QPushButton#warningBtn {
    background-color: #f59e0b;
    color: #0f172a;
    border: none;
    font-weight: bold;
}
QPushButton#warningBtn:hover {
    background-color: #d97706;
}

/* 输入框 */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #3b82f6;
}

/* 下拉框 */
QComboBox {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cbd5e1;
    selection-background-color: #3b82f6;
    border-radius: 8px;
}

/* 表格 */
QTableWidget, QTableView {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #333333;
    gridline-color: #e2e8f0;
    border: none;
    border-radius: 12px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}
QTableWidget::item, QTableView::item {
    padding: 8px 12px;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #ffffff;
    color: #64748b;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    font-weight: bold;
}

/* 树形视图 */
QTreeWidget {
    background-color: #ffffff;
    color: #333333;
    border: none;
    border-radius: 12px;
    outline: none;
}
QTreeWidget::item {
    padding: 8px 6px;
}
QTreeWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QTreeWidget::item:hover {
    background-color: #f1f5f9;
}

/* 进度条 */
QProgressBar {
    background-color: #e2e8f0;
    border: none;
    border-radius: 8px;
    text-align: center;
    color: #333333;
    min-height: 24px;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 8px;
}

/* 滚动条 */
QScrollBar:vertical {
    background-color: #f5f7fa;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #f5f7fa;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #94a3b8;
}

/* 复选框 */
QCheckBox {
    color: #333333;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #cbd5e1;
    border-radius: 4px;
    background-color: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #3b82f6;
    border-color: #3b82f6;
}

/* 列表 */
QListWidget {
    background-color: #ffffff;
    color: #333333;
    border: none;
    border-radius: 8px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
}
QListWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #f1f5f9;
}

/* 日期选择 */
QDateEdit {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
}

/* 分组框 */
QGroupBox {
    border: none;
    border-radius: 12px;
    margin-top: 12px;
    padding-top: 16px;
    color: #64748b;
    font-weight: bold;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: #ffffff;
}

/* 标签 */
QLabel#titleLabel {
    font-size: 20px;
    font-weight: bold;
    color: #0f172a;
    background: transparent;
    border: none;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #64748b;
    background: transparent;
    border: none;
}
QLabel#statLabel {
    font-size: 28px;
    font-weight: bold;
    color: #3b82f6;
}
QLabel#cardBg {
    background-color: #ffffff;
    border-radius: 12px;
    border: none;
}

/* 消息框 */
QMessageBox {
    background-color: #f5f7fa;
}
QMessageBox QLabel {
    color: #333333;
}

/* 状态栏 */
QStatusBar#appStatusBar {
    background-color: #f5f7fa;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 12px;
    padding: 0 12px;
}
QStatusBar#appStatusBar::item {
    border: none;
}

/* ===== 消除所有 QLabel 默认边框和背景 ===== */
QLabel {
    border: none;
    background: transparent;
}
"""

# 别名，兼容旧引用
MAIN_STYLE = DARK_STYLE

