"""
空状态引导组件 - 当页面没有数据时显示友好的引导信息
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt


class EmptyStateWidget(QWidget):
    """空状态引导组件
    
    用于在表格/列表没有数据时显示友好的引导信息，
    包含图标、标题、描述文字和可选的操作按钮。
    """
    
    def __init__(self, icon: str, title: str, description: str,
                 action_text: str = None, action_callback=None, parent=None):
        super().__init__(parent)
        self._empty_content = (icon, title, description)
        self._init_ui(icon, title, description, action_text, action_callback)
    
    def _init_ui(self, icon: str, title: str, description: str,
                 action_text: str, action_callback):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(16)
        
        # 图标
        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        layout.addWidget(self.icon_label)
        
        # 标题
        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyStateTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; "
            "background: transparent; border: none;")
        layout.addWidget(self.title_label)
        
        # 描述
        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("emptyStateDescription")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(
            "font-size: 13px; "
            "background: transparent; border: none;")
        layout.addWidget(self.desc_label)
        
        # 操作按钮（可选）
        if action_text and action_callback:
            self.action_btn = QPushButton(action_text)
            self.action_btn.setObjectName("primaryBtn")
            self.action_btn.setFixedWidth(160)
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_btn.clicked.connect(action_callback)
            layout.addWidget(self.action_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            self.action_btn = None
        
        layout.addStretch()
        self.setVisible(False)

    def set_content(self, icon: str, title: str, description: str):
        """Reuse the same panel for empty, loading and error states."""
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.desc_label.setText(description)

    def show_loading(self, description: str = "正在加载，请稍候..."):
        self.set_content("…", "正在加载", description)
        if self.action_btn:
            self.action_btn.setVisible(False)
        self.setVisible(True)

    def show_error(self, description: str):
        self.set_content("!", "加载失败", description)
        if self.action_btn:
            self.action_btn.setVisible(True)
        self.setVisible(True)

    def show_empty(self, icon: str = None, title: str = None,
                   description: str = None):
        default_icon, default_title, default_description = self._empty_content
        self.set_content(
            icon or default_icon,
            title or default_title,
            description or default_description)
        if self.action_btn:
            self.action_btn.setVisible(True)
        self.setVisible(True)


# 预定义的空状态配置
EMPTY_STATES = {
    'dashboard': {
        'icon': '📊',
        'title': '还没有任何数据',
        'description': '请先扫描文件目录，仪表盘将展示文件分布、大小统计等信息。',
    },
    'scan': {
        'icon': '📂',
        'title': '还没有配置扫描目录',
        'description': '点击上方"浏览..."按钮选择要扫描的目录，然后点击"开始扫描"。',
    },
    'classify': {
        'icon': '📁',
        'title': '没有找到文件',
        'description': '请先扫描文件，扫描完成后文件会自动分类显示在这里。',
    },
    'search': {
        'icon': '🔍',
        'title': '请输入搜索条件',
        'description': '在上方搜索框输入文件名关键词，或设置其他筛选条件后点击搜索。',
    },
    'history': {
        'icon': '📋',
        'title': '暂无操作记录',
        'description': '对文件进行操作后（如重命名、移动、删除等），历史记录会显示在这里。',
    },
    'recycle_bin': {
        'icon': '♻️',
        'title': '回收区是空的',
        'description': '删除的文件会先进入回收区，可以从这里恢复或永久删除。',
    },
    'duplicates': {
        'icon': '🔁',
        'title': '没有重复文件',
        'description': '扫描时勾选"计算文件哈希"才能检测重复文件。',
    },
    'tags': {
        'icon': '🏷️',
        'title': '还没有创建标签',
        'description': '点击"新建标签"创建第一个标签，然后给文件打标签来组织它们。',
    },
}


def create_empty_state(key: str, action_text: str = None,
                       action_callback=None, parent=None) -> EmptyStateWidget:
    """根据预定义配置创建空状态组件
    
    Args:
        key: 空状态配置的键名（如 'dashboard', 'scan' 等）
        action_text: 可选的操作按钮文字
        action_callback: 操作按钮点击回调
        parent: 父组件
    """
    config = EMPTY_STATES.get(key, {
        'icon': '📭',
        'title': '暂无数据',
        'description': '这里还没有内容。',
    })
    return EmptyStateWidget(
        icon=config['icon'],
        title=config['title'],
        description=config['description'],
        action_text=action_text,
        action_callback=action_callback,
        parent=parent
    )
