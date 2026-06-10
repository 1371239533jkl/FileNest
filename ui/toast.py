"""
Toast 通知组件 - 操作反馈的轻量级提示条
自动在父窗口顶部弹出，3秒后自动消失
"""
from enum import Enum, auto
from typing import Optional
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve
from PyQt6.QtGui import QFont


class ToastType(Enum):
    SUCCESS = auto()
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


# 颜色配置（深色主题）
_TYPE_STYLES = {
    'dark': {
        ToastType.SUCCESS: {
            'bg': '#1e3a2f', 'border': '#a6e3a1', 'text': '#a6e3a1', 'icon': '✅'
        },
        ToastType.ERROR: {
            'bg': '#3a1e22', 'border': '#f38ba8', 'text': '#f38ba8', 'icon': '❌'
        },
        ToastType.WARNING: {
            'bg': '#3a351e', 'border': '#f9e2af', 'text': '#f9e2af', 'icon': '⚠️'
        },
        ToastType.INFO: {
            'bg': '#1e2e3a', 'border': '#89b4fa', 'text': '#89b4fa', 'icon': 'ℹ️'
        },
    },
    'light': {
        ToastType.SUCCESS: {
            'bg': '#d5f5e3', 'border': '#40a02b', 'text': '#2d7b1e', 'icon': '✅'
        },
        ToastType.ERROR: {
            'bg': '#fce8e8', 'border': '#e64553', 'text': '#b91d2b', 'icon': '❌'
        },
        ToastType.WARNING: {
            'bg': '#fef3cd', 'border': '#df8e1d', 'text': '#b07615', 'icon': '⚠️'
        },
        ToastType.INFO: {
            'bg': '#d6eaf8', 'border': '#1e88e5', 'text': '#0d47a1', 'icon': 'ℹ️'
        },
    },
}


class ToastNotification(QFrame):
    """顶部弹出的通知条，自动消失"""

    _current_toast: Optional['ToastNotification'] = None

    def __init__(self, parent: QWidget, message: str,
                 toast_type: ToastType = ToastType.INFO,
                 duration_ms: int = 3000, theme: str = 'dark'):
        super().__init__(parent)
        self._duration = duration_ms
        self._theme = theme
        self._type = toast_type

        # 关闭上一个 toast
        if ToastNotification._current_toast:
            try:
                old = ToastNotification._current_toast
                old.hide()
                old.deleteLater()
            except RuntimeError:
                pass
        ToastNotification._current_toast = self

        self._setup_ui(message)
        self._start_animation()

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_style()

    def _setup_ui(self, message: str):
        style = _TYPE_STYLES[self._theme][self._type]
        self.setObjectName("toastFrame")
        self._apply_style()

        # 水平布局：图标 + 消息
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        icon_label = QLabel(style['icon'])
        icon_label.setFont(QFont("Segoe UI Emoji", 14))
        layout.addWidget(icon_label)

        msg_label = QLabel(message)
        msg_label.setStyleSheet(f"color: {style['text']}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(msg_label)

        layout.addStretch()

        self.setMinimumHeight(44)
        self.setMaximumHeight(44)

        # 自动关闭计时器
        if self._duration > 0:
            QTimer.singleShot(self._duration, self._fade_out)

    def _apply_style(self):
        style = _TYPE_STYLES[self._theme][self._type]
        self.setStyleSheet(f"""
            #toastFrame {{
                background-color: {style['bg']};
                border: 1px solid {style['border']};
                border-radius: 8px;
            }}
        """)

    def _start_animation(self):
        """滑动进入动画"""
        # 使用顶层窗口作为父级，避免被 QStackedWidget 隐藏
        top_level = self.window()
        if top_level and top_level is not self.parent():
            self.setParent(top_level)

        parent_width = self.parent().width() if self.parent() else 400
        self.setFixedWidth(min(parent_width - 40, 500))
        self.adjustSize()

        # 定位在父窗口顶部居中
        x = (parent_width - self.width()) // 2
        self.setGeometry(x, -self.height(), self.width(), self.height())
        self.raise_()
        self.show()

        self._slide_anim = QPropertyAnimation(self, b"geometry", self)
        self._slide_anim.setDuration(200)
        self._slide_anim.setStartValue(self.geometry())
        self._slide_anim.setEndValue(QRect(x, 12, self.width(), self.height()))
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.start()

    def _fade_out(self):
        """滑动消失动画"""
        if not self.isVisible():
            self._cleanup()
            return
        x = (self.parent().width() - self.width()) // 2 if self.parent() else 0
        self._slide_out = QPropertyAnimation(self, b"geometry", self)
        self._slide_out.setDuration(200)
        self._slide_out.setStartValue(self.geometry())
        self._slide_out.setEndValue(QRect(x, -self.height(), self.width(), self.height()))
        self._slide_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._slide_out.finished.connect(self._cleanup)
        self._slide_out.start()
        # 安全兜底：动画异常时强制清理
        QTimer.singleShot(self._slide_out.duration() + 100, self._cleanup)

    def _cleanup(self):
        ToastNotification._current_toast = None
        self.hide()
        self.deleteLater()


def show_toast(parent: QWidget, message: str,
               toast_type: ToastType = ToastType.INFO,
               duration_ms: int = 3000, theme: str = 'dark') -> ToastNotification:
    """便捷函数：在指定父窗口显示一个 Toast 通知"""
    return ToastNotification(parent, message, toast_type, duration_ms, theme)


def notify(widget: QWidget, message: str,
           level: str = 'info', duration_ms: int = 3000):
    """
    终极便捷函数：从任意的 widget 调用，自动向上查找主窗口并显示反馈。
    同时显示 Toast + 更新状态栏。
    level: 'success' / 'error' / 'warning' / 'info'
    """
    try:
        # 向上查找 MainWindow
        p = widget
        while p is not None:
            if hasattr(p, 'show_toast') and hasattr(p, 'set_status'):
                tmap = {
                    'success': ToastType.SUCCESS,
                    'error': ToastType.ERROR,
                    'warning': ToastType.WARNING,
                    'info': ToastType.INFO,
                }
                p.show_toast(message, tmap.get(level, ToastType.INFO), duration_ms)
                p.set_status(message)
                return
            p = p.parent()
    except RuntimeError:
        pass
