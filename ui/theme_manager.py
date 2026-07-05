"""
主题管理器 - 处理主题切换和各页面的主题适配
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject


class ThemeManager(QObject):
    """管理主题切换和页面级样式微调"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def apply_theme_to_widget(self, widget: QWidget, theme_name: str):
        """
        对单个页面/组件应用主题适配样式。
        不同页面可能需要自定义的微调，留空由全局 QSS 统一处理。
        如有特殊样式需求，可在对应页面中重写。
        """
        if hasattr(widget, 'apply_theme'):
            widget.apply_theme(theme_name)
