"""
主窗口 - 侧边导航 + 内容面板
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QStackedWidget, QLabel, QPushButton,
    QMessageBox, QSplitter, QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence

from config import APP_NAME, APP_VERSION, WINDOW_WIDTH, WINDOW_HEIGHT, MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT
from ui.styles import DARK_STYLE, LIGHT_STYLE
from ui.theme_manager import ThemeManager
from ui.toast import show_toast, ToastType
from ui.scan_tab import ScanTab
from ui.classify_tab import ClassifyTab
from ui.search_tab import SearchTab
from ui.history_tab import HistoryTab
from ui.recycle_bin_tab import RecycleBinTab
from ui.dashboard_tab import DashboardTab
from ui.duplicates_tab import DuplicatesTab
from ui.settings_tab import SettingsTab
from ui.tags_tab import TagsTab
from ui.onboarding import OnboardingDialog
from database.db_manager import db
from database.models import SystemSettingsDAO
from utils.display_utils import get_platform_font
from utils.logger import logger


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self._current_theme = "dark"
        self._init_database()
        self._init_theme_manager()
        self._init_ui()
        self._apply_theme(self._current_theme)
        self._show_onboarding_if_needed()

    def _init_database(self):
        try:
            db.init_database()
            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            QMessageBox.critical(
                self, "数据库错误",
                f"无法连接MySQL数据库，请检查config.py中的数据库配置。\n\n错误: {e}")

    def _init_theme_manager(self):
        self.theme_manager = ThemeManager()

    def _apply_theme(self, theme_name):
        self._current_theme = theme_name
        style = DARK_STYLE if theme_name == "dark" else LIGHT_STYLE
        self.setStyleSheet(style)

        if hasattr(self, 'theme_btn'):
            self.theme_btn.setText(" 🌙 浅色" if theme_name == "dark" else " ☀️ 深色")

        if hasattr(self, 'version_label'):
            c = "#585b70" if theme_name == "dark" else "#acb0be"
            self.version_label.setStyleSheet(f"font-size: 11px; color: {c}; background: transparent; border: none;")

        # 通知各页面主题变更
        if hasattr(self, 'scan_tab'):
            self.theme_manager.apply_theme_to_widget(self.dashboard_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.scan_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.classify_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.search_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.history_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.recycle_bin_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.duplicates_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.tags_tab, theme_name)
            self.theme_manager.apply_theme_to_widget(self.settings_tab, theme_name)

    def _toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new_theme)
        logger.info(f"切换主题: {new_theme}")

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏 ──
        header = QWidget()
        header.setFixedHeight(60)
        header.setObjectName("headerBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        title.setFont(get_platform_font(16))
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 主题切换按钮
        self.theme_btn = QPushButton(" 🌙 浅色")
        self.theme_btn.setObjectName("themeToggleBtn")
        self.theme_btn.setFixedHeight(32)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self.theme_btn)

        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setStyleSheet("font-size: 11px; color: #585b70; background: transparent; border: none;")
        header_layout.addWidget(self.version_label)

        layout.addWidget(header)

        # ── 主体区域：侧边导航 + 内容面板 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(0)  # 隐藏分割手柄

        # 左侧导航
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navSidebar")
        self.nav_list.setFixedWidth(180)
        self.nav_list.setMinimumWidth(140)
        self.nav_list.setMaximumWidth(220)
        self.nav_list.setSpacing(2)

        nav_items = [
            ("  📊  仪表盘"),
            ("  📂  扫描管理"),
            ("  📁  分类管理"),
            ("  🔍  文件搜索"),
            ("  📋  操作历史"),
            ("  ♻️  回收区"),
            ("  🔁  重复文件"),
            ("  🏷️  标签管理"),
            ("  ⚙️  系统设置"),
        ]
        for text in nav_items:
            self.nav_list.addItem(text)

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self.nav_list)

        # 右侧内容面板
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentPanel")

        self.dashboard_tab = DashboardTab(self)
        self.scan_tab = ScanTab(self)
        self.classify_tab = ClassifyTab(self)
        self.search_tab = SearchTab(self)
        self.history_tab = HistoryTab(self)
        self.recycle_bin_tab = RecycleBinTab(self)
        self.duplicates_tab = DuplicatesTab(self)
        self.tags_tab = TagsTab(self)
        self.settings_tab = SettingsTab(self)

        self.stack.addWidget(self.dashboard_tab)
        self.stack.addWidget(self.scan_tab)
        self.stack.addWidget(self.classify_tab)
        self.stack.addWidget(self.search_tab)
        self.stack.addWidget(self.history_tab)
        self.stack.addWidget(self.recycle_bin_tab)
        self.stack.addWidget(self.duplicates_tab)
        self.stack.addWidget(self.tags_tab)
        self.stack.addWidget(self.settings_tab)

        splitter.addWidget(self.stack)

        # 设置初始比例（导航:内容 = 180:剩余）
        splitter.setSizes([180, WINDOW_WIDTH - 180])
        layout.addWidget(splitter, 1)

        # 默认选中第一个
        self.nav_list.setCurrentRow(0)

        # ── 底部状态栏 ──
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("appStatusBar")
        self.status_bar.setFixedHeight(28)
        self.status_bar.showMessage("就绪")
        self.setStatusBar(self.status_bar)

        # ── 全局快捷键 ──
        self._undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self._on_undo_shortcut)

        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._on_search_shortcut)

        self._refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self._refresh_shortcut.activated.connect(self._on_refresh_shortcut)

        self._refresh_shortcut2 = QShortcut(QKeySequence("F5"), self)
        self._refresh_shortcut2.activated.connect(self._on_refresh_shortcut)

        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        self._delete_shortcut.activated.connect(self._on_delete_shortcut)

        self._rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self._rename_shortcut.activated.connect(self._on_rename_shortcut)

    # ── 反馈方法（供子页面调用） ──

    def show_toast(self, message: str,
                   toast_type: ToastType = ToastType.INFO,
                   duration_ms: int = 3000):
        """在当前内容面板弹出 Toast 通知"""
        current = self.stack.currentWidget()
        show_toast(current, message, toast_type, duration_ms, self._current_theme)

    def set_status(self, message: str, timeout_ms: int = 5000):
        """设置状态栏消息"""
        self.status_bar.showMessage(message, timeout_ms)

    def switch_to_tab(self, index: int):
        """切换到指定导航页"""
        if 0 <= index < self.nav_list.count():
            self.nav_list.setCurrentRow(index)

    def _on_undo_shortcut(self):
        """Ctrl+Z 触发当前页面的撤销操作"""
        current = self.stack.currentWidget()
        if hasattr(current, 'undo_last'):
            current.undo_last()
        else:
            has_undo = hasattr(current, 'history_mgr') or \
                       hasattr(current, '_context_menu') or \
                       hasattr(current, 'refresh_data')
            if has_undo:
                idx = self.stack.currentIndex()
                names = ["仪表盘", "扫描管理", "分类管理", "文件搜索", "操作历史", "回收区", "重复文件", "标签管理", "系统设置"]
                self.show_toast(f"当前页面({names[idx]})不支持撤销", ToastType.INFO, 2000)

    def _on_search_shortcut(self):
        """Ctrl+F 切换到搜索页并聚焦搜索框"""
        self.switch_to_tab(3)  # 搜索页 index=3
        if hasattr(self.search_tab, 'focus_search'):
            self.search_tab.focus_search()

    def _on_refresh_shortcut(self):
        """Ctrl+R / F5 刷新当前页面"""
        current = self.stack.currentWidget()
        if hasattr(current, 'refresh_data'):
            current.refresh_data()
            self.set_status("已刷新", 2000)

    def _on_delete_shortcut(self):
        """Delete 触发当前页面的删除操作"""
        current = self.stack.currentWidget()
        if hasattr(current, 'delete_selected'):
            current.delete_selected()

    def _on_rename_shortcut(self):
        """F2 触发当前页面的重命名操作"""
        current = self.stack.currentWidget()
        if hasattr(current, 'rename_selected'):
            current.rename_selected()

    def _on_nav_changed(self, index):
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        widget = self.stack.widget(index)
        if hasattr(widget, 'refresh_data'):
            widget.refresh_data()

    def closeEvent(self, event):
        from core.file_watcher import WatcherManager
        WatcherManager.get_instance().disable()
        db.close()
        event.accept()

    def _show_onboarding_if_needed(self):
        """首次启动时显示引导对话框"""
        try:
            settings_dao = SystemSettingsDAO(db)
            if not settings_dao.get('onboarding_done', False):
                dialog = OnboardingDialog(self)
                dialog.exec()
                settings_dao.set('onboarding_done', '1', 'bool', '引导已完成')
                logger.info("首次启动引导已显示")
        except Exception as e:
            logger.debug(f"引导对话框异常: {e}")
