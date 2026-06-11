"""
磁盘空间分析仪表盘 - 文件分布、类型占比、趋势分析
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea
)
from PyQt6.QtCore import Qt

from database.db_manager import db
from database.models import FileDAO
from config import FILE_TYPE_NAMES
from utils.display_utils import format_size
from utils.logger import logger
from ui.chart_widgets import StatCard, PieChartWidget, BarChartWidget, TrendChartWidget
from ui.empty_state import create_empty_state


class DashboardTab(QWidget):
    """磁盘空间分析仪表盘"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 顶部标题
        header = QHBoxLayout()
        title = QLabel("📊 磁盘空间分析")
        title.setStyleSheet("font-weight: bold; color: #cba6f7; font-size: 14px;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self.refresh_data)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._content = QWidget()
        self._grid = QVBoxLayout(self._content)
        self._grid.setSpacing(12)

        # ── 统计卡片行 ──
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_total_files = StatCard("活跃文件总数", "-", '#89b4fa')
        self.card_total_size = StatCard("文件总大小", "-", '#a6e3a1')
        self.card_dup_groups = StatCard("重复组数", "-", '#f9e2af')
        self.card_wasted = StatCard("重复浪费空间", "-", '#f38ba8')

        cards_layout.addWidget(self.card_total_files)
        cards_layout.addWidget(self.card_total_size)
        cards_layout.addWidget(self.card_dup_groups)
        cards_layout.addWidget(self.card_wasted)
        self._grid.addLayout(cards_layout)

        # ── 图表行 1：类型分布饼图 + 大小分布柱状图 ──
        charts1 = QHBoxLayout()
        charts1.setSpacing(12)

        self.pie_type = PieChartWidget()
        self.pie_type.setMinimumHeight(280)
        charts1.addWidget(self.pie_type)

        self.bar_size = BarChartWidget()
        self.bar_size.setMinimumHeight(280)
        charts1.addWidget(self.bar_size)

        self._grid.addLayout(charts1)

        # ── 图表行 2：目录占用 + 月度趋势 ──
        charts2 = QHBoxLayout()
        charts2.setSpacing(12)

        self.bar_dirs = BarChartWidget()
        self.bar_dirs.setMinimumHeight(280)
        charts2.addWidget(self.bar_dirs)

        self.trend_monthly = TrendChartWidget()
        self.trend_monthly.setMinimumHeight(280)
        charts2.addWidget(self.trend_monthly)

        self._grid.addLayout(charts2)

        self._grid.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

        # 空状态引导
        self._empty_state = create_empty_state('dashboard', parent=self._content)
        self._grid.insertWidget(0, self._empty_state)

    def refresh_data(self):
        try:
            self._load_stats()
        except Exception as e:
            logger.error(f"加载仪表盘数据失败: {e}")

    def _load_stats(self):
        # ── 统计卡片 ──
        total_files = self.file_dao.count_active()

        # 空状态检测
        if total_files == 0:
            self._empty_state.setVisible(True)
            self.card_total_files.set_value("-")
            self.card_total_size.set_value("-")
            self.card_dup_groups.set_value("-")
            self.card_wasted.set_value("-")
            self.pie_type.set_data([], "文件类型分布")
            self.bar_size.set_data([], "文件大小分布")
            self.bar_dirs.set_data([], "目录占用 Top 10")
            self.trend_monthly.set_data([], "月度扫描趋势")
            return

        self._empty_state.setVisible(False)

        total_size = self.file_dao.get_total_size()
        dup_groups = self.file_dao.count_duplicate_groups()
        wasted = self.file_dao.get_duplicate_total_wasted()

        self.card_total_files.set_value(f"{total_files:,}")
        self.card_total_size.set_value(format_size(total_size))
        self.card_dup_groups.set_value(f"{dup_groups:,}")
        self.card_wasted.set_value(format_size(wasted))

        # ── 类型分布饼图 ──
        type_stats = self.file_dao.get_type_stats()
        pie_data = []
        type_colors = {
            'image': '#f38ba8', 'document': '#89b4fa',
            'video': '#cba6f7', 'audio': '#a6e3a1',
            'archive': '#f9e2af', 'other': '#94e2d5',
        }
        for row in type_stats:
            name = FILE_TYPE_NAMES.get(row['file_type'], row['file_type'])
            pie_data.append({
                'label': name,
                'value': row['count'],
                'color': type_colors.get(row['file_type'], '#a6adc8'),
            })
        self.pie_type.set_data(pie_data, "文件类型分布")

        # ── 大小分布柱状图 ──
        size_dist = self.file_dao.get_size_distribution()
        bar_data = []
        size_colors = ['#94e2d5', '#89b4fa', '#cba6f7', '#f9e2af', '#f38ba8']
        for i, row in enumerate(size_dist):
            bar_data.append({
                'label': row['size_range'],
                'value': row['count'],
                'color': size_colors[i % len(size_colors)],
            })
        self.bar_size.set_data(bar_data, "文件大小分布")

        # ── 目录占用 Top10 ──
        top_dirs = self.file_dao.get_top_directories(10)
        dir_data = []
        for i, row in enumerate(top_dirs):
            dir_path = row.get('dir_path', '')
            # 截取最后一段目录名
            parts = dir_path.replace('\\', '/').rstrip('/').split('/')
            short_name = parts[-1] if parts else dir_path
            if len(short_name) > 14:
                short_name = short_name[:12] + ".."
            dir_data.append({
                'label': short_name,
                'value': row.get('total_size', 0),
                'color': '#74c7ec',
            })
        self.bar_dirs.set_data(dir_data, "目录占用 Top 10", show_size=True)

        # ── 月度趋势 ──
        monthly = self.file_dao.get_monthly_trend()
        trend_data = []
        for row in monthly:
            trend_data.append({
                'label': row.get('month', ''),
                'value': row.get('count', 0),
            })
        self.trend_monthly.set_data(trend_data, "月度扫描趋势")
