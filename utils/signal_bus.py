"""
PyQt6信号总线 - 模块间通信
"""
from PyQt6.QtCore import QObject, pyqtSignal


class SignalBus(QObject):
    """全局信号总线"""

    # 扫描相关
    scan_started = pyqtSignal()
    scan_progress = pyqtSignal(int, int, str)  # current, total, file_path
    scan_finished = pyqtSignal(int, int)  # new_count, total_count
    scan_error = pyqtSignal(str)

    # 分类相关
    classify_started = pyqtSignal()
    classify_progress = pyqtSignal(int, int)
    classify_finished = pyqtSignal(int)
    classify_error = pyqtSignal(str)

    # 文件操作
    file_renamed = pyqtSignal(int, str, str)  # file_id, old_name, new_name
    file_moved = pyqtSignal(int, str, str)  # file_id, old_path, new_path
    file_deleted = pyqtSignal(int)  # file_id
    files_deduped = pyqtSignal(int)  # removed_count

    # 操作历史
    operation_undone = pyqtSignal(int)  # operation_id
    batch_undone = pyqtSignal(str)  # batch_id

    # 数据库
    db_connected = pyqtSignal()
    db_error = pyqtSignal(str)

    # 通用
    status_message = pyqtSignal(str)
    data_changed = pyqtSignal()  # 通知UI刷新数据


signal_bus = SignalBus()
