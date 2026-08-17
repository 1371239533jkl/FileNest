"""
主窗口 - 侧边导航 + 内容面板
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton,
    QMessageBox, QSplitter, QStatusBar, QComboBox, QDateEdit, QCalendarWidget
)
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtGui import QShortcut, QKeySequence, QPalette, QPainter, QColor

from config import APP_NAME, APP_VERSION, WINDOW_WIDTH, WINDOW_HEIGHT, MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT
from ui.styles import DARK_STYLE, LIGHT_STYLE


# ponytail: 全局修复下拉弹层白边/边框。Qt 在 Windows 风格下给每个 item 之间
# 画 1px separator（呈现为"白边"），且弹层 QFrame 保留 native 调色板。通过
# monkey-patch QComboBox.showPopup，让所有 QComboBox 都强制应用主题底色。
_original_qcombobox_showpopup = QComboBox.showPopup


def _style_combo_popup(combo: QComboBox):
    popup = combo.view().window()
    if popup is combo.window():
        return
    palette = combo.palette()
    background = palette.color(QPalette.ColorRole.Base)
    foreground = palette.color(QPalette.ColorRole.Text)
    popup_palette = popup.palette()
    popup_palette.setColor(QPalette.ColorRole.Window, background)
    popup_palette.setColor(QPalette.ColorRole.Base, background)
    popup_palette.setColor(QPalette.ColorRole.Text, foreground)
    popup.setPalette(popup_palette)
    popup.setAutoFillBackground(True)
    popup.setContentsMargins(0, 0, 0, 0)
    if popup.layout():
        popup.layout().setContentsMargins(0, 0, 0, 0)
    # ponytail: 不设 border，配合 QSS `border: none` + ::item background-color
    # 弹层色，彻底消除"白边"/自适应边框
    popup.setStyleSheet(
        f"background-color: {background.name()}; color: {foreground.name()}; "
        f"border: none; margin: 0; padding: 0;")


def _patched_qcombobox_showpopup(self):
    _original_qcombobox_showpopup(self)
    _style_combo_popup(self)
    QTimer.singleShot(0, lambda: _style_combo_popup(self))


QComboBox.showPopup = _patched_qcombobox_showpopup


# ponytail: 只显示当月日期的日历。
# Qt 走 QCalendarWidget.paintCell 渲染日期格子（同 QTableView 内部布局），
# 但 setDateRange 仅禁用点击不隐藏内容。组合：① setDateRange 锁定当月范围
# 使相邻月 cell 不可点；② 重写 paintCell 对相邻月日期画与背景同色（不留数字）。
#
# 日历弹层是独立顶层窗口，不继承主窗口 QSS：必须把日历样式直接
# setStyleSheet 到控件自身，并让 paintCell 的覆盖色跟随当前主题，
# 否则浅色模式下顶部栏会混入系统默认色、相邻月覆盖色取错（palette
# 不受 QSS 影响）。
from ui.styles import DARK_CALENDAR_QSS, LIGHT_CALENDAR_QSS

_CALENDAR_BG = {'dark': '#1e1e2e', 'light': '#ffffff'}


class MonthOnlyCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = 'dark'
        self._bg_color = QColor(_CALENDAR_BG['dark'])
        self._refresh_range()
        # 当前月变化时（点击左右箭头）重新锁定范围 + 重画
        self.currentPageChanged.connect(lambda *_: self._refresh_range())

    def apply_theme(self, theme_name: str):
        """切换主题：更新覆盖色与日历自身样式表。"""
        self._theme = theme_name
        self._bg_color = QColor(_CALENDAR_BG.get(theme_name, _CALENDAR_BG['dark']))
        qss = DARK_CALENDAR_QSS if theme_name == 'dark' else LIGHT_CALENDAR_QSS
        self.setStyleSheet(qss)
        self._refresh_range()

    def _refresh_range(self):
        y, m = self.yearShown(), self.monthShown()
        self.setMinimumDate(QDate(y, m, 1))
        self.setMaximumDate(QDate(y, m, QDate(y, m, 1).daysInMonth()))
        self._bg_color = QColor(_CALENDAR_BG.get(self._theme, _CALENDAR_BG['dark']))
        self.updateCells()

    def paintCell(self, painter: QPainter, rect, date: QDate):
        if date.month() != self.monthShown() or date.year() != self.yearShown():
            # ponytail: 相邻月日期画与背景同色矩形覆盖，不显示数字
            painter.fillRect(rect, self._bg_color)
            return
        super().paintCell(painter, rect, date)


_original_qdateedit_set_calendar_popup = QDateEdit.setCalendarPopup


def _patched_qdateedit_set_calendar_popup(self, enable: bool):
    _original_qdateedit_set_calendar_popup(self, enable)
    if enable:
        cal = self.calendarWidget()
        if cal is not None and not isinstance(cal, MonthOnlyCalendar):
            new_cal = MonthOnlyCalendar(self)
            # ponytail: 保证两位日期（10-31）不被截断
            new_cal.setMinimumSize(300, 250)
            # 继承宿主窗口当前主题
            from ui.styles import DARK_STYLE  # noqa: F401 仅用于避免循环导入风险
            host = self.window()
            theme = getattr(host, '_current_theme', 'dark') if host is not None else 'dark'
            new_cal.apply_theme(theme)
            self.setCalendarWidget(new_cal)


QDateEdit.setCalendarPopup = _patched_qdateedit_set_calendar_popup
from ui.theme_manager import ThemeManager
from ui.toast import show_toast, ToastType
from ui.scan_tab import ScanTab
from ui.classify_tab import ClassifyTab
from ui.search_tab import SearchTab
from ui.ai_chat_page import AiChatPage
from ui.history_tab import HistoryTab
from ui.recycle_bin_tab import RecycleBinTab
from ui.dashboard_tab import DashboardTab
from ui.duplicates_tab import DuplicatesTab
from ui.settings_tab import SettingsTab
from ui.tags_tab import TagsTab
from ui.command_palette import CommandPalette
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
                f"无法初始化 SQLite 数据库。\n\n错误: {e}")

    def _init_theme_manager(self):
        self.theme_manager = ThemeManager()

    def _apply_theme(self, theme_name):
        self._current_theme = theme_name
        style = DARK_STYLE if theme_name == "dark" else LIGHT_STYLE
        self.setStyleSheet(style)

        if hasattr(self, 'theme_btn'):
            self.theme_btn.setText("🌙" if theme_name == "dark" else "☀️")

        if hasattr(self, 'version_label'):
            c = "#6b6b7b" if theme_name == "dark" else "#64748b"
            self.version_label.setStyleSheet(f"font-size: 11px; color: {c}; background: transparent; border: none;")

        # 通知各页面主题变更
        if hasattr(self, 'stack'):
            for i in range(self.stack.count()):
                w = self.stack.widget(i)
                if w:
                    self.theme_manager.apply_theme_to_widget(w, theme_name)

        # 同步已创建的日历弹层主题（弹层不继承 QSS）
        self._refresh_calendar_themes(theme_name)

    def _refresh_calendar_themes(self, theme_name):
        """遍历所有 QDateEdit，将已创建的 MonthOnlyCalendar 切到当前主题。"""
        for edit in self.findChildren(QDateEdit):
            cal = edit.calendarWidget()
            if isinstance(cal, MonthOnlyCalendar):
                cal.apply_theme(theme_name)

    def _toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new_theme)
        logger.info(f"切换主题: {new_theme}")

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("appCentral")
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
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("themeToggleBtn")
        self.theme_btn.setFixedSize(40, 32)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self.theme_btn)

        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setStyleSheet("font-size: 11px; color: #6b6b7b; background: transparent; border: none;")
        header_layout.addWidget(self.version_label)

        layout.addWidget(header)

        # ── 主体区域：图标导航 + 内容面板 ──
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 左侧图标导航栏
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navSidebar")
        self.nav_list.setFixedWidth(52)
        self.nav_list.setMinimumWidth(52)
        self.nav_list.setMaximumWidth(52)
        self.nav_list.setSpacing(0)
        self.nav_list.setFlow(QListWidget.Flow.TopToBottom)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 图标 + 索引映射
        nav_icons = ["\U0001F4CA", "\U0001F4C2", "\U0001F4C1", "\U0001F50D", "\U0001F916", "\U0001F4CB", "\U0001F504", "\U0001F503", "\U0001F3F7", "\u2699"]
        nav_tips = ["仪表盘", "扫描管理", "分类管理", "文件搜索", "AI 助手", "操作历史", "回收区", "重复文件", "标签管理", "系统设置"]
        for icon, tip in zip(nav_icons, nav_tips):
            item = QListWidgetItem(icon)
            item.setToolTip(tip)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        body_layout.addWidget(self.nav_list, 0)

        # 右侧内容面板
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentPanel")
        self.stack.setContentsMargins(16, 16, 16, 16)

        self.dashboard_tab = DashboardTab(self)
        self.scan_tab = ScanTab(self)
        self.classify_tab = ClassifyTab(self)
        self.search_tab = SearchTab(self)
        self.ai_search_tab = AiChatPage(self)
        self.history_tab = HistoryTab(self)
        self.recycle_bin_tab = RecycleBinTab(self)
        self.duplicates_tab = DuplicatesTab(self)
        self.tags_tab = TagsTab(self)
        self.settings_tab = SettingsTab(self)

        self.stack.addWidget(self.dashboard_tab)
        self.stack.addWidget(self.scan_tab)
        self.stack.addWidget(self.classify_tab)
        self.stack.addWidget(self.search_tab)
        self.stack.addWidget(self.ai_search_tab)
        self.stack.addWidget(self.history_tab)
        self.stack.addWidget(self.recycle_bin_tab)
        self.stack.addWidget(self.duplicates_tab)
        self.stack.addWidget(self.tags_tab)
        self.stack.addWidget(self.settings_tab)

        body_layout.addWidget(self.stack, 1)
        layout.addLayout(body_layout, 1)

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

        self._ai_search_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self._ai_search_shortcut.activated.connect(self._open_ai_search)

        self._cmd_palette_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self._cmd_palette_shortcut.activated.connect(self._open_command_palette)

        # ── 页面间信号连接 ──
        self.search_tab.ai_search_clicked.connect(self._switch_to_ai_search)
        self.ai_search_tab.go_back.connect(self._on_ai_search_back)
        self.ai_search_tab.show_results.connect(self._on_ai_show_results)
        self.ai_search_tab.navigate_to_search.connect(self._on_ai_navigate_to_search)

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
                names = ["仪表盘", "扫描管理", "分类管理", "文件搜索", "AI助手", "操作历史", "回收区", "重复文件", "标签管理", "系统设置"]
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

    def _open_ai_search(self):
        """Ctrl+Shift+F → 切换到 AI 搜索页"""
        self.switch_to_tab(4)  # AI 搜索页 index=4
        if hasattr(self.ai_search_tab, 'focus_search'):
            self.ai_search_tab.focus_search()

    def _switch_to_ai_search(self):
        """从搜索页的 AI 按钮跳转到 AI 搜索页"""
        self.switch_to_tab(4)  # AI 搜索页 index=4
        if hasattr(self.ai_search_tab, 'focus_search'):
            self.ai_search_tab.focus_search()

    def _on_ai_search_back(self):
        """从 AI 搜索页返回文件搜索页"""
        self.switch_to_tab(3)  # 文件搜索页 index=3

    def _on_ai_navigate_to_search(self, params: dict):
        """从 AI 助手工具卡片跳转到搜索 Tab，并回填参数"""
        self.switch_to_tab(3)  # 文件搜索页 index=3
        self.search_tab._apply_search_params(params, source="AI 助手")

    def _on_ai_show_results(self, result: dict):
        """AI 搜索完成后，将结果填入文件搜索表格"""
        self.search_tab.display_ai_results(result)

    def _open_command_palette(self):
        """Ctrl+Shift+P → 打开命令面板"""
        palette = CommandPalette(self, theme=self._current_theme)
        palette.focus_input()
        palette.exec()

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
