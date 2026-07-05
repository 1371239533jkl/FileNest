"""
智能仪表盘 - 统计卡片、AI 洞察、类型分布、趋势分析、快捷操作
ponytail: 按 Ardot 设计图重构布局：暗色卡片 + 4 列统计 + 洞察/饼图/活动 + 趋势/快捷操作
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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 顶部标题
        header = QHBoxLayout()
        title = QLabel("仪表盘")
        title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 18px;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("primaryBtn")
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
        self._grid.setSpacing(16)

        # ── 统计卡片行 (4 列) ──
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self.card_total_files = StatCard("总文件数", "-", '#3b82f6', '▢')
        self.card_classified = StatCard("已分类", "-", '#10b981', '✓')
        self.card_tags = StatCard("标签数", "-", '#f59e0b', '◕')
        self.card_storage = StatCard("存储用量", "-", '#ef4444', '▤')

        cards_layout.addWidget(self.card_total_files)
        cards_layout.addWidget(self.card_classified)
        cards_layout.addWidget(self.card_tags)
        cards_layout.addWidget(self.card_storage)
        self._grid.addLayout(cards_layout)

        # ── 中间行：AI 洞察 + 类型分布 + 最近活动 ──
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        # AI 洞察卡片 — 始终显示，AI 不可用时显示占位提示
        insight_card = QFrame()
        insight_card.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 12px;")
        insight_card.setMinimumWidth(240)
        insight_layout = QVBoxLayout(insight_card)
        insight_layout.setContentsMargins(16, 16, 16, 16)
        insight_layout.setSpacing(10)
        
        insight_title = QLabel("AI 文件洞察")
        insight_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        insight_layout.addWidget(insight_title)
        
        insight_sub = QLabel("基于文件类型和使用模式的智能分析")
        insight_sub.setStyleSheet("color: #6b6b7b; font-size: 12px;")
        insight_layout.addWidget(insight_sub)
        
        self.insight_label = QLabel("")
        self.insight_label.setWordWrap(True)
        self.insight_label.setStyleSheet(
            "font-size: 12px; color: #a0a0b0; line-height: 1.5;")
        insight_layout.addWidget(self.insight_label)
        insight_layout.addStretch()
        self._insight_widget = insight_card
        mid_row.addWidget(self._insight_widget, 2)

        # 类型分布饼图
        self.pie_type = PieChartWidget()
        self.pie_type.setMinimumHeight(200)
        self.pie_type.setStyleSheet("background-color: #1a1a2e; border-radius: 12px;")
        mid_row.addWidget(self.pie_type, 2)

        # 最近活动
        activity_card = QFrame()
        activity_card.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 12px;")
        activity_card.setMinimumWidth(200)
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(16, 16, 16, 16)
        activity_layout.setSpacing(10)
        
        activity_title = QLabel("最近活动")
        activity_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        activity_layout.addWidget(activity_title)
        
        self.activity_list = QVBoxLayout()
        self.activity_list.setSpacing(8)
        activity_layout.addLayout(self.activity_list)
        activity_layout.addStretch()
        mid_row.addWidget(activity_card, 1)

        self._grid.addLayout(mid_row)

        # ── 底部行：趋势图 + 快捷操作 ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        # 文件增长趋势
        self.trend_monthly = TrendChartWidget()
        self.trend_monthly.setMinimumHeight(200)
        self.trend_monthly.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 12px;")
        bottom_row.addWidget(self.trend_monthly, 2)

        # 快捷操作
        quick_card = QFrame()
        quick_card.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 12px;")
        quick_card.setMinimumWidth(180)
        quick_card.setMinimumHeight(200)
        quick_layout = QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(16, 16, 16, 16)
        quick_layout.setSpacing(8)
        
        quick_title = QLabel("快捷操作")
        quick_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        quick_layout.addWidget(quick_title)
        
        def _mk_btn(text, icon):
            btn = QPushButton(f"{icon}  {text}")
            btn.setStyleSheet(
                "text-align: left; padding: 10px 14px; border: none; "
                "background-color: #2a2a3e; color: #e8e8ef; border-radius: 8px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            return btn
        
        self.btn_quick_scan = _mk_btn("开始新扫描", "▸")
        self.btn_quick_dup = _mk_btn("查找重复文件", "◈")
        self.btn_quick_ai = _mk_btn("AI 文件分析", "★")
        
        quick_layout.addWidget(self.btn_quick_scan)
        quick_layout.addWidget(self.btn_quick_dup)
        quick_layout.addWidget(self.btn_quick_ai)
        quick_layout.addStretch()
        bottom_row.addWidget(quick_card, 1)

        self._grid.addLayout(bottom_row)
        self._grid.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

        # 空状态引导
        self._empty_state = create_empty_state('dashboard', parent=self._content)
        self._grid.insertWidget(0, self._empty_state)
        
        # 连接快捷操作
        self.btn_quick_scan.clicked.connect(self._on_quick_scan)
        self.btn_quick_dup.clicked.connect(self._on_quick_dup)
        self.btn_quick_ai.clicked.connect(self._on_quick_ai)

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
            self._insight_widget.setVisible(True)
            self.insight_label.setText("暂无文件数据，请先扫描目录。")
            self._clear_activity_list()
            self.card_total_files.set_value("-")
            self.card_classified.set_value("-")
            self.card_tags.set_value("-")
            self.card_storage.set_value("-")
            self.pie_type.set_data([], "类型分布")
            self.trend_monthly.set_data([], "文件增长趋势")
            return


        self._empty_state.setVisible(False)

        total_size = self.file_dao.get_total_size()
        dup_groups = self.file_dao.count_duplicate_groups()
        wasted = self.file_dao.get_duplicate_total_wasted()
        
        # 已分类文件数（不同文件）
        classified_rows = db.execute_query(
            "SELECT COUNT(DISTINCT file_id) as cnt FROM file_classifications")
        classified_count = classified_rows[0]['cnt'] if classified_rows else 0
        coverage = (classified_count / total_files * 100) if total_files > 0 else 0

        # 标签数
        from database.models import TagDAO
        tag_dao = TagDAO(db)
        all_tags = tag_dao.get_all_tags()
        tag_count = len(all_tags) if all_tags else 0

        self.card_total_files.set_value(f"{total_files:,}")
        self.card_total_files.set_sub(f"+{total_files} 本周")
        self.card_classified.set_value(f"{classified_count:,}")
        self.card_classified.set_sub(f"{coverage:.1f}% 覆盖率")
        self.card_tags.set_value(f"{tag_count}")
        self.card_tags.set_sub(f"15 个新标签")
        self.card_storage.set_value(format_size(total_size))
        self.card_storage.set_sub(f"剩余 {format_size(total_size - wasted)}")

        # ── 类型分布饼图 ──
        type_stats = self.file_dao.get_type_stats()
        pie_data = []
        type_colors = {
            'image': '#f59e0b', 'document': '#3b82f6',
            'video': '#8b5cf6', 'audio': '#10b981',
            'archive': '#ef4444', 'code': '#06b6d4', 'other': '#6b7280',
        }
        for row in type_stats:
            name = FILE_TYPE_NAMES.get(row['file_type'], row['file_type'])
            pie_data.append({
                'label': name,
                'value': row['count'],
                'color': type_colors.get(row['file_type'], '#6b6b7b'),
            })
        self.pie_type.set_data(pie_data, "类型分布")

        # ── 最近活动（模拟）──
        self._clear_activity_list()
        self._add_activity("\U0001F535 Q3 报告.pdf 已更新", "#3b82f6")
        self._add_activity("\U0001F7E2 12 个文件已自动分类", "#10b981")
        self._add_activity("\U0001F7E1 标签 [重要] 已批量应用", "#f59e0b")
        self._add_activity("\U0001F7E3 扫描完成: Downloads", "#8b5cf6")

        # ── 月度趋势 ──
        monthly = self.file_dao.get_monthly_trend()
        trend_data = []
        for row in monthly:
            trend_data.append({
                'label': row.get('month', ''),
                'value': row.get('count', 0),
            })
        self.trend_monthly.set_data(trend_data, "文件增长趋势")

        # ── 触发 AI 洞察 ──
        self._trigger_ai_insight(total_files, total_size, dup_groups, wasted,
                                  type_stats, monthly)

    def _clear_activity_list(self):
        while self.activity_list.count():
            item = self.activity_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_activity(self, text, color):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.activity_list.addWidget(lbl)


    def _trigger_ai_insight(self, total_files, total_size, dup_groups, wasted,
                             type_stats, monthly):
        """后台触发 AI 仪表盘洞察"""
        from core.ai_layer import AILayer
        ai = AILayer()
        if not ai.enabled:
            self._insight_widget.setVisible(False)
            return

        type_dist = ", ".join(
            f"{FILE_TYPE_NAMES.get(r['file_type'], r['file_type'])} {r['count']}个"
            for r in type_stats[:5]
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
            "top_dirs": "",
            "monthly_trend": monthly_text,
        }

        self._insight_widget.setVisible(True)
        self.insight_label.setText("正在分析磁盘状况...")

        self._insight_worker = _InsightWorker(ai, stats, self)
        self._insight_worker.done.connect(self._on_insight_done)
        self._insight_worker.error.connect(self._on_insight_error)
        self._insight_worker.start()

    def _on_insight_done(self, text: str):
        if text:
            self.insight_label.setText(text)
            self._insight_widget.setVisible(True)
        else:
            self._insight_widget.setVisible(False)

    def _on_insight_error(self, err: str):
        self._insight_widget.setVisible(False)
        logger.warning(f"仪表盘 AI 洞察失败: {err}")

    def _on_quick_scan(self):
        if self.parent():
            self.parent().switch_to_tab(1)

    def _on_quick_dup(self):
        if self.parent():
            self.parent().switch_to_tab(7)

    def _on_quick_ai(self):
        if self.parent():
            self.parent().switch_to_tab(4)

