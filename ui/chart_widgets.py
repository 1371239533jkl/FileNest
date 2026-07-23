"""
轻量级图表组件 - 使用 QPainter 绘制，无外部依赖
"""
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from utils.display_utils import format_size



# Catppuccin 色板（深/浅色主题通用）
_PALETTE = [
    '#cba6f7', '#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8',
    '#94e2d5', '#fab387', '#74c7ec', '#b4befe', '#eba0ac',
    '#f5c2e7', '#89dceb',
]


class StatCard(QFrame):
    """统计卡片：数值 + 标签 + 子标题 + 图标"""
    clicked = pyqtSignal()

    def __init__(self, label: str, value: str = "-", color: str = '#cba6f7',
                 icon: str = '', parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Three text rows need a stable vertical budget.  A smaller minimum
        # lets the dashboard compress the value label when another card grows.
        self.setMinimumHeight(124)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # 标题行：图标 + 标签
        header_layout = QHBoxLayout()
        if icon:
            self._icon_label = QLabel(icon)
            self._icon_label.setMinimumHeight(22)
            self._icon_label.setStyleSheet(
                f"font-size: 16px; color: {color}; border: none; background: transparent;")
            header_layout.addWidget(self._icon_label)
        self._text_label = QLabel(label)
        self._text_label.setMinimumHeight(22)
        self._text_label.setStyleSheet(
            f"font-size: 12px; color: #a0a0b0; border: none; background: transparent;")
        header_layout.addWidget(self._text_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 数值
        self._value_label = QLabel(value)
        self._value_label.setMinimumHeight(42)
        self._value_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._value_label.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: #ffffff; "
            f"border: none; background: transparent;")
        layout.addWidget(self._value_label)

        # 子标题
        self._sub_label = QLabel("")
        self._sub_label.setMinimumHeight(20)
        self._sub_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._sub_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._sub_label.setStyleSheet(
            f"font-size: 12px; color: {color}; border: none; background: transparent;")
        layout.addWidget(self._sub_label)

    def set_value(self, value: str):
        self._value_label.setText(value)

    def set_sub(self, text: str):
        self._sub_label.setText(text)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)



class PieChartWidget(QWidget):
    """饼图组件：用于文件类型分布"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        self._data: list[dict] = []  # [{label, value, color}]
        self._title = ""

    def set_data(self, data: list[dict], title: str = ""):
        """data: [{label: str, value: int|float}, ...]"""
        self._title = title
        self._data = []
        for i, item in enumerate(data):
            self._data.append({
                'label': item.get('label', ''),
                'value': item.get('value', 0),
                'color': item.get('color', _PALETTE[i % len(_PALETTE)]),
            })
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        total = sum(d['value'] for d in self._data)
        if total == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        title_h = 24 if self._title else 0

        # 饼图区域
        pie_size = min(w - 140, h - title_h - 20)
        pie_size = max(pie_size, 80)
        cx = pie_size // 2 + 10
        cy = title_h + (h - title_h - pie_size) // 2 + pie_size // 2

        # 绘制扇区
        angle_start = 90 * 16  # Qt 角度单位是 1/16 度
        for d in self._data:
            span = int(d['value'] / total * 360 * 16)
            painter.setPen(QPen(QColor('#1e1e2e'), 1))
            painter.setBrush(QBrush(QColor(d['color'])))
            rect = QRectF(cx - pie_size // 2, cy - pie_size // 2,
                          pie_size, pie_size)
            painter.drawPie(rect, angle_start, span)
            angle_start += span

        # 绘制图例
        legend_x = pie_size + 30
        legend_y = title_h + 20
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        for d in self._data:
            if legend_y > h - 10:
                break
            # 色块
            painter.setBrush(QBrush(QColor(d['color'])))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(legend_x, legend_y, 12, 12)
            # 文字
            pct = d['value'] / total * 100 if total else 0
            text = f"{d['label']}  {pct:.1f}%"
            painter.setPen(QColor('#cdd6f4'))
            painter.drawText(legend_x + 18, legend_y + 11, text)
            legend_y += 20

        # 标题
        if self._title:
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor('#cdd6f4'))
            painter.drawText(10, 18, self._title)

        painter.end()


class BarChartWidget(QWidget):
    """水平柱状图组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 180)
        self._data: list[dict] = []
        self._title = ""
        self._show_size = False

    def set_data(self, data: list[dict], title: str = "", show_size: bool = False):
        """data: [{label, value}, ...]  value 为数值"""
        self._title = title
        self._show_size = show_size
        self._data = []
        for i, item in enumerate(data):
            self._data.append({
                'label': item.get('label', ''),
                'value': item.get('value', 0),
                'color': item.get('color', _PALETTE[i % len(_PALETTE)]),
            })
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        title_h = 24 if self._title else 0
        max_val = max(d['value'] for d in self._data) or 1
        n = len(self._data)
        bar_area_h = h - title_h - 10
        bar_h = min(24, max(12, bar_area_h // n - 4))
        gap = 4

        label_width = 100  # 左侧标签宽度
        bar_max_width = w - label_width - 80  # 右侧留出显示数值

        font = QFont("Segoe UI", 9)
        painter.setFont(font)

        for i, d in enumerate(self._data):
            y = title_h + 10 + i * (bar_h + gap)
            if y + bar_h > h:
                break

            # 标签
            painter.setPen(QColor('#cdd6f4'))
            label = d['label'][:12]
            painter.drawText(4, y + bar_h - 4, label)

            # 柱状条
            bar_w = int(d['value'] / max_val * bar_max_width)
            bar_w = max(bar_w, 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(d['color'])))
            painter.drawRoundedRect(
                QRectF(label_width, y, bar_w, bar_h), 3, 3)

            # 数值
            val_text = format_size(d['value']) if self._show_size else str(d['value'])
            painter.setPen(QColor('#a6adc8'))
            painter.drawText(label_width + bar_w + 6, y + bar_h - 4, val_text)

        # 标题
        if self._title:
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor('#cdd6f4'))
            painter.drawText(10, 18, self._title)

        painter.end()


class TrendChartWidget(QWidget):
    """折线趋势图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 180)
        self._data: list[dict] = []  # [{label, value}]
        self._title = ""

    def set_data(self, data: list[dict], title: str = ""):
        self._title = title
        self._data = list(reversed(data))  # 时间正序
        self.update()

    def paintEvent(self, event):
        if len(self._data) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        title_h = 24 if self._title else 0
        pad_l, pad_r, pad_b = 50, 20, 30
        chart_w = w - pad_l - pad_r
        chart_h = h - title_h - pad_b - 10

        max_val = max(d['value'] for d in self._data) or 1
        n = len(self._data)
        step_x = chart_w / max(n - 1, 1)

        # 网格线
        painter.setPen(QPen(QColor('#45475a'), 1, Qt.PenStyle.DotLine))
        for i in range(4):
            y = title_h + 10 + chart_h * i / 3
            painter.drawLine(pad_l, int(y), w - pad_r, int(y))

        # 折线
        points = []
        for i, d in enumerate(self._data):
            x = pad_l + i * step_x
            y = title_h + 10 + chart_h * (1 - d['value'] / max_val)
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor('#89b4fa'), 2))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        # 数据点
        painter.setBrush(QBrush(QColor('#cba6f7')))
        painter.setPen(Qt.PenStyle.NoPen)
        for p in points:
            painter.drawEllipse(p, 4, 4)

        # X 轴标签
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(QColor('#a6adc8'))
        for i, d in enumerate(self._data):
            if n > 6 and i % 2 != 0:
                continue
            x = pad_l + i * step_x
            painter.drawText(int(x - 20), h - 8, d.get('label', ''))

        # Y 轴
        painter.drawText(4, title_h + 14, str(max_val))
        painter.drawText(4, title_h + 10 + chart_h, "0")

        # 标题
        if self._title:
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor('#cdd6f4'))
            painter.drawText(10, 18, self._title)

        painter.end()
