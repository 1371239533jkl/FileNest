"""
日期时间工具函数
"""
from datetime import datetime
from typing import Optional


def parse_datetime_safe(
    value, fmt: str = '%Y-%m-%d %H:%M:%S'
) -> Optional[datetime]:
    """安全解析日期时间字符串，失败返回 None

    Args:
        value: 输入值（str / datetime / None）
        fmt: 日期格式，默认 '%Y-%m-%d %H:%M:%S'

    Returns:
        解析后的 datetime 对象，解析失败或输入为空时返回 None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            return None
    return None
