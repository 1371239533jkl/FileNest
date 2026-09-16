"""
知识图谱对话框（批次7 P2-05 第一期）。

QGraphicsView 可视化：中心节点居中，邻居按 kind 环形分组排布；
点击节点在右侧显示详情并可「以它为中心」重新构建。
支持文件 / 标签 / 目录三种中心。
"""
import math
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QGraphicsView, QGraphicsScene, QGraphicsTextItem,
    QListWidget, QListWidgetItem, QSplitter, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QPainter

from core.knowledge_graph import GraphService
from utils.logger import logger

KIND_COLORS = {
    'file': ('#89b4fa', '#1e1e2e'),
    'tag': ('#f9e2af', '#1e1e2e'),
    'dir': ('#a6e3a1', '#1e1e2e'),
}
EDGE_COLORS = {
    'tag': '#f9e2af', 'tag-mate': '#6c7086',
    'version': '#f5c2e7', 'same-dir': '#a6e3a1',
    'duplicate': '#f38ba8',
}
NODE_RADIUS = {'file': 10, 'tag': 14, 'dir': 16}


class GraphNodeItem(QGraphicsTextItem):
    """简单圆形节点（椭圆 + 标签文字，一体命中区域）。"""

    def __init__(self, node: dict, radius: float, color: str, parent=None):
        super().__init__(parent)
        self.node = node
        self.radius = radius
        self.color = color

    def boundingRect(self) -> QRectF:
        return QRectF(-self.radius, -self.radius - 14,
                      self.radius * 2, self.radius * 2 + 20)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(self.color), 2))
        painter.setBrush(QBrush(QColor(self.color)))
        painter.drawEllipse(-self.radius, -self.radius,
                            self.radius * 2, self.radius * 2)
        painter.setPen(QPen(QColor('#cdd6f4')))
        f = QFont()
        f.setPointSize(8)
        painter.setFont(f)
        label = self.node['label']
        if len(label) > 16:
            label = label[:15] + '…'
        painter.drawText(QRectF(-60, self.radius + 2, 120, 18),
                         Qt.AlignmentFlag.AlignCenter, label)


class KnowledgeGraphDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("知识图谱")
        self.setMinimumSize(900, 600)
        self.service = GraphService()
        self._node_items = {}
        self._init_ui()

    # ── UI ────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部：中心类型 + 关键词 + 构建
        top = QHBoxLayout()
        top.addWidget(QLabel("中心:"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("🏷 标签", 'tag')
        self.kind_combo.addItem("📄 文件", 'file')
        self.kind_combo.addItem("📁 目录", 'dir')
        top.addWidget(self.kind_combo)
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText(
            "标签名 / 文件名关键词 / 目录路径，回车构建")
        self.keyword_edit.returnPressed.connect(self._build)
        top.addWidget(self.keyword_edit, 1)
        build_btn = QPushButton("🕸 构建图谱")
        build_btn.setObjectName("primaryBtn")
        build_btn.clicked.connect(self._build)
        top.addWidget(build_btn)
        layout.addLayout(top)

        # 中部：图 + 右侧栏
        splitter = QSplitter()
        self.view = QGraphicsView()
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(-450, -300, 900, 600)
        self.view.setScene(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        splitter.addWidget(self.view)

        side = QWidget()
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.addWidget(QLabel("节点详情:"))
        self.detail_list = QListWidget()
        self.detail_list.itemClicked.connect(self._on_detail_item)
        side_l.addWidget(self.detail_list, 1)
        recent_btn = QPushButton("⭐ 枢纽文件 Top10")
        recent_btn.clicked.connect(self._show_hubs)
        side_l.addWidget(recent_btn)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.hint_label = QLabel("输入中心关键词后点「构建图谱」")
        self.hint_label.setStyleSheet("color: #a6adc8;")
        layout.addWidget(self.hint_label)

    # ── 构建 ──────────────────────────────────────────────────

    def _build(self, kind: str = None, value=None):
        kind = kind or self.kind_combo.currentData()
        value = value if value is not None else self.keyword_edit.text().strip()
        if value == '' or value is None:
            QMessageBox.information(self, "提示", "请输入中心关键词")
            return
        graph = self.service.neighborhood(kind, value)
        if not graph['nodes']:
            QMessageBox.information(self, "无结果", "没有找到匹配的中心节点")
            return
        self._render(graph)
        self.hint_label.setText(
            f"节点 {len(graph['nodes'])} ｜ 边 {len(graph['edges'])} —— "
            f"点击节点查看详情，双击以其为中心重建")

    def _render(self, graph: dict):
        self.scene.clear()
        self._node_items.clear()
        nodes = graph['nodes']
        edges = graph['edges']
        center_node = nodes[0]
        center_id = center_node['id']

        # 边（先画，位于节点下层）
        pos = {}
        pos[center_id] = (0, 0)
        others = [n for n in nodes if n['id'] != center_id]
        # 环形布局：按 kind 分三圈段
        groups = {}
        for n in others:
            groups.setdefault(n['kind'], []).append(n)
        angle = 0.0
        R = 170.0
        for gk, gnodes in groups.items():
            step = 2 * math.pi / max(len(groups) * 0 + sum(len(v) for v in groups.values()), 1)
            for n in gnodes:
                r = R + (30 if n['kind'] == 'file' else 0)
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                pos[n['id']] = (x, y)
                angle += step
        for e in edges:
            if e['src'] in pos and e['dst'] in pos:
                x1, y1 = pos[e['src']]
                x2, y2 = pos[e['dst']]
                pen = QPen(QColor(EDGE_COLORS.get(e['kind'], '#6c7086')), 1.4)
                self.scene.addLine(x1, y1, x2, y2, pen)

        # 节点
        for n in nodes:
            is_center = n['id'] == center_id
            radius = NODE_RADIUS.get(n['kind'], 10) + (4 if is_center else 0)
            color = KIND_COLORS.get(n['kind'], ('#89b4fa',))[0]
            item = GraphNodeItem(n, radius, color)
            x, y = pos.get(n['id'], (0, 0))
            item.setPos(x, y)
            item.setData(0, n)
            self.scene.addItem(item)
            self._node_items[n['id']] = item
            item.mousePressEvent = self._make_node_click(n)
            item.mouseDoubleClickEvent = self._make_node_dclick(n)

    # ── 交互 ──────────────────────────────────────────────────

    def _make_node_click(self, node: dict):
        def handler(event):
            self._show_detail(node)
        return handler

    def _make_node_dclick(self, node: dict):
        def handler(event):
            self._recenter(node)
        return handler

    def _recenter(self, node: dict):
        n = node
        if n['kind'] == 'file':
            self.kind_combo.setCurrentIndex(self.kind_combo.findData('file'))
            self._build('file', n['ref'])
        elif n['kind'] == 'tag':
            self.kind_combo.setCurrentIndex(self.kind_combo.findData('tag'))
            self._build('tag', n['ref'])
        elif n['kind'] == 'dir':
            self.kind_combo.setCurrentIndex(self.kind_combo.findData('dir'))
            self._build('dir', n['ref'])

    def _show_detail(self, node: dict):
        self.detail_list.clear()
        rows = [
            ('类型', {'file': '📄 文件', 'tag': '🏷 标签',
                      'dir': '📁 目录'}.get(node['kind'], node['kind'])),
            ('名称', node['label']),
            ('详情', node.get('detail', '')),
        ]
        for k, v in rows:
            QListWidgetItem(f"{k}: {v}", self.detail_list)
        # 相关动作：以它为中心
        act = QListWidgetItem("🔁 以此为中心重建图谱（或双击节点）")
        act.setData(Qt.ItemDataRole.UserRole, node)
        self.detail_list.addItem(act)

    def _show_hubs(self):
        self.detail_list.clear()
        hubs = self.service.hub_files(10)
        self.detail_list.addItem(QListWidgetItem("⭐ 枢纽文件（连接度最高）"))
        for i, h in enumerate(hubs, 1):
            item = QListWidgetItem(f"{i}. {h['file_name']}  (score {h['score']})")
            item.setToolTip(h['file_path'])
            item.setData(Qt.ItemDataRole.UserRole,
                         {'kind': 'file', 'value': h['id']})
            self.detail_list.addItem(item)
        if not hubs:
            self.detail_list.addItem(QListWidgetItem("（暂无数据，先扫描并打标签）"))

    def _on_detail_item(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and 'kind' in data:
            self._recenter({'kind': data['kind'], 'ref': data['value'],
                            'label': item.text()})
