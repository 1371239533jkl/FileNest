"""增量索引落库 —— 将文件变化事件合并后批量写入 files 表。

职责：
1. 事件风暴合并：同一路径的多个事件只保留最终状态；
2. 落库：created/modified → upsert，deleted → 标记 deleted，moved → 更新路径；
3. 失败隔离与重试：单文件失败不阻断批次，重试 N 次后记录错误。
"""
import os
from typing import List, Optional

from database.db_manager import db
from database.models import FileDAO
from utils.logger import logger

_MAX_RETRIES = 2  # 每个事件最多重试次数（不含首次）


def merge_events(events: list) -> list:
    """合并同一路径的多个事件，保留每个路径的最终状态。

    moved 事件按 src_path 归并；created/modified 归并为同一键，后者覆盖前者。
    返回顺序稳定的事件列表。
    """
    merged = {}
    order = []
    for ev in events:
        key = ev.path
        if key not in merged:
            order.append(key)
        merged[key] = ev
    return [merged[k] for k in order]


class IncrementalIndexUpdater:
    """将文件变化事件应用到数据库索引。

    纯逻辑、无 Qt 依赖，可在任何线程调用；调用方负责线程调度。
    """

    def __init__(self, file_dao: Optional[FileDAO] = None):
        self.file_dao = file_dao or FileDAO(db)

    def apply(self, events: list) -> dict:
        """处理一批事件，返回统计 {'applied', 'failed', 'errors': [...]}。"""
        result = {'applied': 0, 'failed': 0, 'errors': []}
        for ev in merge_events(events):
            ok = False
            last_err = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    self._apply_one(ev)
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001 - 单事件失败不阻断批次
                    last_err = exc
            if ok:
                result['applied'] += 1
            else:
                result['failed'] += 1
                message = f"{ev.event_type} {ev.path}: {last_err}"
                result['errors'].append(message)
                logger.warning('增量落库失败: %s', message)
        return result

    # ── 单事件处理 ──────────────────────────────────────────────

    def _apply_one(self, ev) -> None:
        if ev.event_type == 'deleted':
            self._apply_deleted(ev.path)
        elif ev.event_type == 'moved':
            self._apply_moved(ev)
        else:  # created / modified
            self._apply_upsert(ev.path)

    def _apply_deleted(self, path: str) -> None:
        """标记删除：不物理删除文件，只把记录标记为 deleted。"""
        self.file_dao.delete_by_path(path)

    def _apply_moved(self, ev) -> None:
        """移动：把旧路径记录更新为新路径。若旧记录不存在则按新路径 upsert。"""
        src = ev.path
        dest = getattr(ev, 'dest_path', '') or ''
        if not dest:
            self._apply_upsert(src)
            return
        record = self.file_dao.get_by_path(src)
        if record:
            new_name = os.path.basename(dest)
            self.file_dao.update_name(record['id'], new_name, dest)
        elif os.path.exists(dest):
            self._apply_upsert(dest)

    def _apply_upsert(self, path: str) -> None:
        """新增/修改：重新读取文件信息并 upsert 到 files 表。"""
        if not os.path.exists(path):
            # 事件与落库之间文件可能已消失（如瞬态临时文件），静默跳过
            return
        from core.file_scanner import get_file_info
        info = get_file_info(path)
        if info['file_size'] > 0:
            from core.file_scanner import calculate_hash, MAX_FILE_SIZE_FOR_HASH
            if info['file_size'] <= MAX_FILE_SIZE_FOR_HASH:
                info['file_hash'] = calculate_hash(path)
        self.file_dao.insert(info)
