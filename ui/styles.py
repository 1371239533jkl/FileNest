"""
统一QSS样式定义 - 双主题系统
深色主题：Catppuccin Mocha（ #1e1e2e 基底）
浅色主题：Catppuccin Latte（ #eff1f5 基底）
"""

# ──────── 深色主题 ────────
DARK_STYLE = """
/* ===== 全局 ===== */
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QWidget#headerBar {
    background-color: #181825;
    border-bottom: 2px solid #313244;
}

QWidget#contentPanel {
    background-color: #1e1e2e;
    border: none;
}

/* ===== 侧边导航 ===== */
QListWidget#navSidebar {
    background-color: #181825;
    color: #cdd6f4;
    border: none;
    border-right: 2px solid #313244;
    outline: none;
    padding: 8px 0;
    font-size: 14px;
}
QListWidget#navSidebar::item {
    padding: 12px 16px;
    border-radius: 0;
    margin: 0;
}
QListWidget#navSidebar::item:selected {
    background-color: #313244;
    color: #cba6f7;
    font-weight: bold;
    border-left: 3px solid #cba6f7;
}
QListWidget#navSidebar::item:hover:!selected {
    background-color: #252536;
    color: #cdd6f4;
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
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#themeToggleBtn:hover {
    background-color: #45475a;
    border-color: #585b70;
}

/* 标签页（兼容使用QTabWidget的子页面） */
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 100px;
}
QTabBar::tab:selected {
    background-color: #313244;
    color: #cba6f7;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #252536;
    color: #cdd6f4;
}

/* 分割器 */
QSplitter::handle {
    background-color: #313244;
}

/* 按钮 */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}
QPushButton#primaryBtn {
    background-color: #cba6f7;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #b4befe;
}
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #eba0ac;
}
QPushButton#successBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border: none;
}
QPushButton#successBtn:hover {
    background-color: #94e2d5;
}

/* 输入框 */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #cba6f7;
    selection-color: #1e1e2e;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #cba6f7;
}

/* 下拉框 */
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}

/* 表格 */
QTableWidget {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 6px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 6px 8px;
}
QTableWidget::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}
QHeaderView::section {
    background-color: #313244;
    color: #a6adc8;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #45475a;
    font-weight: bold;
}

/* 树形视图 */
QTreeWidget {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    outline: none;
}
QTreeWidget::item {
    padding: 6px 4px;
}
QTreeWidget::item:selected {
    background-color: #45475a;
}
QTreeWidget::item:hover {
    background-color: #313244;
}

/* 进度条 */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #cba6f7;
    border-radius: 6px;
}

/* 滚动条 */
QScrollBar:vertical {
    background-color: #181825;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #181825;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 5px;
    min-width: 30px;
}

/* 复选框 */
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #45475a;
    border-radius: 4px;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #cba6f7;
    border-color: #cba6f7;
}

/* 列表 */
QListWidget {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
}
QListWidget::item:selected {
    background-color: #45475a;
    color: #cba6f7;
}
QListWidget::item:hover {
    background-color: #313244;
}

/* 日期选择 */
QDateEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
}

/* 分组框 */
QGroupBox {
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    color: #a6adc8;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* 标签 */
QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #cba6f7;
    background: transparent;
    border: none;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #a6adc8;
    background: transparent;
    border: none;
}
QLabel#statLabel {
    font-size: 24px;
    font-weight: bold;
    color: #cba6f7;
}

/* 消息框 */
QMessageBox {
    background-color: #1e1e2e;
}
QMessageBox QLabel {
    color: #cdd6f4;
}

/* 状态栏 */
QStatusBar#appStatusBar {
    background-color: #181825;
    border-top: 1px solid #313244;
    color: #a6adc8;
    font-size: 12px;
    padding: 0 12px;
}
QStatusBar#appStatusBar::item {
    border: none;
}
"""


# ──────── 浅色主题 ────────
LIGHT_STYLE = """
/* ===== 全局 ===== */
QMainWindow, QWidget {
    background-color: #eff1f5;
    color: #4c4f69;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QWidget#headerBar {
    background-color: #e6e9ef;
    border-bottom: 2px solid #ccd0da;
}

QWidget#contentPanel {
    background-color: #eff1f5;
    border: none;
}

/* ===== 侧边导航 ===== */
QListWidget#navSidebar {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: none;
    border-right: 2px solid #ccd0da;
    outline: none;
    padding: 8px 0;
    font-size: 14px;
}
QListWidget#navSidebar::item {
    padding: 12px 16px;
    border-radius: 0;
    margin: 0;
}
QListWidget#navSidebar::item:selected {
    background-color: #ccd0da;
    color: #8839ef;
    font-weight: bold;
    border-left: 3px solid #8839ef;
}
QListWidget#navSidebar::item:hover:!selected {
    background-color: #dce0e8;
    color: #4c4f69;
}

/* 主题切换按钮 */
QPushButton#themeToggleBtn {
    background-color: #ccd0da;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#themeToggleBtn:hover {
    background-color: #bcc0cc;
    border-color: #acb0be;
}

/* 标签页（兼容） */
QTabWidget::pane {
    border: 1px solid #ccd0da;
    background-color: #eff1f5;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #e6e9ef;
    color: #6c6f85;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 100px;
}
QTabBar::tab:selected {
    background-color: #ccd0da;
    color: #8839ef;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #dce0e8;
    color: #4c4f69;
}

/* 分割器 */
QSplitter::handle {
    background-color: #ccd0da;
}

/* 按钮 */
QPushButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #bcc0cc;
    border-color: #acb0be;
}
QPushButton:pressed {
    background-color: #acb0be;
}
QPushButton:disabled {
    background-color: #eff1f5;
    color: #bcc0cc;
    border-color: #ccd0da;
}
QPushButton#primaryBtn {
    background-color: #8839ef;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #9c5af0;
}
QPushButton#dangerBtn {
    background-color: #e64553;
    color: #ffffff;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #ea6a76;
}
QPushButton#successBtn {
    background-color: #40a02b;
    color: #ffffff;
    border: none;
}
QPushButton#successBtn:hover {
    background-color: #57b940;
}

/* 输入框 */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #8839ef;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #8839ef;
}

/* 下拉框 */
QComboBox {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    selection-background-color: #ccd0da;
}

/* 表格 */
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f5f5f9;
    color: #4c4f69;
    gridline-color: #ccd0da;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    selection-background-color: #dce0e8;
}
QTableWidget::item {
    padding: 6px 8px;
}
QTableWidget::item:selected {
    background-color: #dce0e8;
    color: #4c4f69;
}
QHeaderView::section {
    background-color: #e6e9ef;
    color: #6c6f85;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #ccd0da;
    font-weight: bold;
}

/* 树形视图 */
QTreeWidget {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    outline: none;
}
QTreeWidget::item {
    padding: 6px 4px;
}
QTreeWidget::item:selected {
    background-color: #dce0e8;
}
QTreeWidget::item:hover {
    background-color: #e6e9ef;
}

/* 进度条 */
QProgressBar {
    background-color: #ccd0da;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #4c4f69;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #8839ef;
    border-radius: 6px;
}

/* 滚动条 */
QScrollBar:vertical {
    background-color: #e6e9ef;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #bcc0cc;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #acb0be;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #e6e9ef;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #bcc0cc;
    border-radius: 5px;
    min-width: 30px;
}

/* 复选框 */
QCheckBox {
    color: #4c4f69;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #bcc0cc;
    border-radius: 4px;
    background-color: #e6e9ef;
}
QCheckBox::indicator:checked {
    background-color: #8839ef;
    border-color: #8839ef;
}

/* 列表 */
QListWidget {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
}
QListWidget::item:selected {
    background-color: #dce0e8;
    color: #8839ef;
}
QListWidget::item:hover {
    background-color: #e6e9ef;
}

/* 日期选择 */
QDateEdit {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 8px 12px;
}

/* 分组框 */
QGroupBox {
    border: 1px solid #ccd0da;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    color: #6c6f85;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* 标签 */
QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #8839ef;
    background: transparent;
    border: none;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #6c6f85;
    background: transparent;
    border: none;
}
QLabel#statLabel {
    font-size: 24px;
    font-weight: bold;
    color: #8839ef;
}

/* 消息框 */
QMessageBox {
    background-color: #eff1f5;
}
QMessageBox QLabel {
    color: #4c4f69;
}

/* 状态栏 */
QStatusBar#appStatusBar {
    background-color: #e6e9ef;
    border-top: 1px solid #ccd0da;
    color: #6c6f85;
    font-size: 12px;
    padding: 0 12px;
}
QStatusBar#appStatusBar::item {
    border: none;
}
"""

# 别名，兼容旧引用
MAIN_STYLE = DARK_STYLE
