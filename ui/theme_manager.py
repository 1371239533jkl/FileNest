"""
主题管理器 - 处理主题切换和各页面的主题适配
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject
from ui.styles import DARK_STYLE, LIGHT_STYLE


class ThemeManager(QObject):
    """管理主题切换和页面级样式微调"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_style(self, theme_name: str) -> str:
        """获取指定主题的全局样式"""
        if theme_name == "light":
            return LIGHT_STYLE
        return DARK_STYLE

    def apply_theme_to_widget(self, widget: QWidget, theme_name: str):
        """
        对单个页面/组件应用主题适配样式。
        不同页面可能需要自定义的微调，留空由全局 QSS 统一处理。
        如有特殊样式需求，可在对应页面中重写。
        """
        if hasattr(widget, 'apply_theme'):
            widget.apply_theme(theme_name)
