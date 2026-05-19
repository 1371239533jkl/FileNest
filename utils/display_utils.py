"""
显示工具函数 - UI 中重复的格式化逻辑统一抽取
"""
from typing import Union

# 文件类型 → Emoji 图标映射
FILE_TYPE_ICONS = {
    'image': '🖼️ ',
    'document': '📄 ',
    'code': '💻 ',
    'video': '🎬 ',
    'audio': '🎵 ',
    'archive': '📦 ',
    'executable': '⚙️ ',
    'font': '🔤 ',
    'other': '📄 ',
}

# 文件类型 → 颜色标签（十六进制，用于行/标签着色）
FILE_TYPE_COLORS = {
    'image': '#a6e3a1',     # 绿色
    'document': '#89b4fa',  # 蓝色
    'code': '#fab387',      # 橙色
    'video': '#f38ba8',     # 红色
    'audio': '#cba6f7',     # 紫色
    'archive': '#f9e2af',   # 黄色
    'executable': '#94e2d5',# 青色
    'font': '#bac2de',      # 灰色
    'other': '#a6adc8',     # 浅灰
}


def get_file_icon(file_type: str) -> str:
    """根据文件类型返回 emoji 图标（含后缀空格）"""
    return FILE_TYPE_ICONS.get(file_type, FILE_TYPE_ICONS['other'])


def get_file_color(file_type: str) -> str:
    """根据文件类型返回对应的颜色十六进制值"""
    return FILE_TYPE_COLORS.get(file_type, FILE_TYPE_COLORS['other'])


def format_size(size_bytes: Union[int, float]) -> str:
    """将字节数格式化为可读的大小字符串"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def truncate_path(file_path: str, max_len: int = 60) -> str:
    """截断长路径，保留末尾部分"""
    if not file_path:
        return ""
    if len(file_path) < max_len:
        return file_path
    return "..." + file_path[-(max_len - 3):]
