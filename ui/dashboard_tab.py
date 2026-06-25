"""
磁盘空间分析仪表盘 - 文件分布、类型占比、趋势分析
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from database.db_manager import db
from database.models import FileDAO
from config import FILE_TYPE_NAMES
from utils.display_utils import format_size
from utils.logger import logger
from ui.chart_widgets import StatCard, PieChartWidget, BarChartWidget, TrendChartWidget
from ui.empty_state import create_empty_state


class _InsightWorker(QThread):
    """后台 AI 洞察分析线程"""
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, ai_layer, stats, parent=None):
        super().__init__(parent)
        self.ai_layer = ai_layer
        self.stats = stats

    def run(self):
        try:
            result = self.ai_layer.generate_dashboard_insights(**self.stats)
            self.done.emit(result or "")
        except Exception as e:
            self.error.emit(str(e))


class DashboardTab(QWidget):
    """磁盘空间分析仪表盘"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dao = FileDAO(db)
        self._insight_worker = None
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

        # ── AI 洞察卡片 ──
        self.insight_card = QFrame()
        self.insight_card.setObjectName("dashboardInsightCard")
        self.insight_card.setVisible(False)
        insight_layout = QVBoxLayout(self.insight_card)
        insight_layout.setContentsMargins(14, 10, 14, 10)
        insight_layout.setSpacing(4)

        insight_header = QHBoxLayout()
        insight_title = QLabel("🤖 AI 洞察")
        insight_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        insight_header.addWidget(insight_title)
        insight_header.addStretch()
        insight_layout.addLayout(insight_header)

        self.insight_label = QLabel("")
        self.insight_label.setWordWrap(True)
        self.insight_label.setStyleSheet("font-size: 10pt; line-height: 1.5;")
        insight_layout.addWidget(self.insight_label)
        self._grid.addWidget(self.insight_card)

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

        # ── 触发 AI 洞察分析 ──
        self._trigger_ai_insight(total_files, total_size, dup_groups, wasted,
                                  type_stats, top_dirs, monthly)

    def _trigger_ai_insight(self, total_files, total_size, dup_groups, wasted,
                             type_stats, top_dirs, monthly):
        """后台触发 AI 仪表盘洞察"""
        from core.ai_layer import AILayer
        ai = AILayer()
        if not ai.enabled:
            self.insight_card.setVisible(False)
            return

        # 构建统计数据文本
        type_dist = ", ".join(
            f"{FILE_TYPE_NAMES.get(r['file_type'], r['file_type'])} {r['count']}个"
            for r in type_stats[:5]
        )
        def _short_dir(r):
            p = r.get('dir_path', '').replace('\\', '/').rstrip('/')
            return p.split('/')[-1][:20] if p else ''

        top_dirs_text = "; ".join(
            f"{_short_dir(r)}({format_size(r.get('total_size', 0))})"
            for r in top_dirs[:3]
        )
        monthly_text = ", ".join(
            f"{r.get('month', '')}:{r.get('count', 0)}个"
            for r in monthly[-6:]
        )

        stats = {
            "total_files": total_files,
            "total_size": format_size(total_size),
            "dup_groups": dup_groups,
            "wasted": format_size(wasted),
            "type_distribution": type_dist,
            "top_dirs": top_dirs_text,
            "monthly_trend": monthly_text,
        }

        self.insight_label.setText("🤖 AI 正在分析磁盘状况...")
        self.insight_card.setVisible(True)

        self._insight_worker = _InsightWorker(ai, stats, self)
        self._insight_worker.done.connect(self._on_insight_done)
        self._insight_worker.error.connect(self._on_insight_error)
        self._insight_worker.start()

    def _on_insight_done(self, text: str):
        if text:
            self.insight_label.setText(text)
            self.insight_card.setVisible(True)
        else:
            self.insight_card.setVisible(False)

    def _on_insight_error(self, err: str):
        self.insight_card.setVisible(False)
        logger.warning(f"仪表盘 AI 洞察失败: {err}")
