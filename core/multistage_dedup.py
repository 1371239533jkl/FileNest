"""多阶段重复检测 —— 大小 → 快速哈希 → 完整哈希三级确认。

设计目标（对应 ROADMAP P0-11）：
1. 未完成完整校验的文件不得标记为确定重复（hash_state 保护）；
2. 中断后可续算：已完成的阶段通过 hash_state 跳过，避免重复计算；
3. 大目录下先按大小粗筛，再快速哈希（文件头部）过滤，最后完整哈希确认，
   把昂贵的全文件读取限制在真正可疑的候选组内。
"""
import hashlib
import os
from typing import Dict, List, Optional, Tuple

from database.db_manager import db
from database.models import FileDAO
from utils.logger import logger

# 快速哈希只读文件头部 N 字节（避免对候选组内全部文件做全量读取）
FAST_HASH_READ_BYTES = 64 * 1024  # 64KB
# 阶段标记
STATE_SIZE = 'size'   # 已按大小分组
STATE_FAST = 'fast'   # 已计算快速哈希
STATE_FULL = 'full'   # 已计算完整哈希并确认


class MultistageDedupDetector:
    """按大小→快速哈希→完整哈希三级确认重复文件。"""

    def __init__(self, file_dao: Optional[FileDAO] = None):
        self.file_dao = file_dao or FileDAO(db)

    # ── 对外入口 ──────────────────────────────────────────────

    def run(self, progress_cb=None, reset: bool = False) -> Dict[str, int]:
        """执行完整的多阶段重复检测。

        Args:
            progress_cb: 可选回调 (stage: str, current: int, total: int, path: str)
            reset: True 强制从头重算（清空全部哈希状态）；
                   False（默认）保留已完成阶段，中断后续算跳过已 full 的记录。

        Returns:
            {'size_groups': int, 'fast_groups': int, 'dup_groups': int,
             'dup_files': int, 'fast_computed': int, 'full_computed': int}
        """
        stats = {'size_groups': 0, 'fast_groups': 0, 'dup_groups': 0,
                 'dup_files': 0, 'fast_computed': 0, 'full_computed': 0}

        if reset:
            # 强制重算：清空所有哈希状态
            self.file_dao.reset_hash_state()
        # 清除旧的重复标记（无论续算与否，标记都基于旧结果，必须重算）
        db.execute_update(
            "UPDATE files SET is_duplicate = 0, duplicate_group_id = NULL "
            "WHERE status = 'active'")

        # 阶段 1：按大小分组（候选组）
        size_groups = self._group_by_size()
        stats['size_groups'] = len(size_groups)
        if progress_cb:
            progress_cb('size', 0, len(size_groups), '按大小筛选候选组')

        # 阶段 2：组内计算快速哈希，再按快速哈希分组
        fast_groups: List[List[dict]] = []
        for idx, group in enumerate(size_groups):
            if progress_cb:
                progress_cb('fast', idx + 1, len(size_groups),
                            group[0].get('file_path', '') if group else '')
            for record in group:
                if record.get('hash_state') in (STATE_FAST, STATE_FULL):
                    continue  # 续算：跳过已完成快速哈希的记录
                fast_hash = self._compute_fast_hash(record['file_path'])
                if fast_hash is not None:
                    self.file_dao.update_fast_hash(record['id'], fast_hash)
                    self.file_dao.update_hash_state(record['id'], STATE_FAST)
                    # 同步内存 record，供后续分组直接使用
                    record['fast_hash'] = fast_hash
                    record['hash_state'] = STATE_FAST
                    stats['fast_computed'] += 1
            # 同组内按 fast_hash 再分组
            by_fast: Dict[str, List[dict]] = {}
            for record in group:
                fh = record.get('fast_hash') or ''
                by_fast.setdefault(fh, []).append(record)
            for fh, sub in by_fast.items():
                if len(sub) > 1 and fh:
                    fast_groups.append(sub)
        stats['fast_groups'] = len(fast_groups)

        # 阶段 3：快速哈希相同者计算完整哈希，确认重复
        groups: Dict[int, List[dict]] = {}
        group_id = 0
        for idx, group in enumerate(fast_groups):
            if progress_cb:
                progress_cb('full', idx + 1, len(fast_groups),
                            group[0].get('file_path', '') if group else '')
            full_map: Dict[str, List[dict]] = {}
            for record in group:
                full_hash = record.get('file_hash')
                if not full_hash or record.get('hash_state') != STATE_FULL:
                    full_hash = self._compute_full_hash(record['file_path'])
                    if full_hash is None:
                        continue
                    self.file_dao.update_hash(record['id'], full_hash)
                    self.file_dao.update_hash_state(record['id'], STATE_FULL)
                    # 同步内存 record
                    record['file_hash'] = full_hash
                    record['hash_state'] = STATE_FULL
                    stats['full_computed'] += 1
                full_map.setdefault(full_hash, []).append(record)
            for full_hash, sub in full_map.items():
                if len(sub) > 1:
                    group_id += 1
                    groups[group_id] = sub
                    for record in sub:
                        self.file_dao.update_duplicate(record['id'], 1, group_id)
                    stats['dup_files'] += len(sub)

        stats['dup_groups'] = len(groups)
        logger.info(
            f"多阶段去重完成: 大小组 {stats['size_groups']}, 快哈希组 "
            f"{stats['fast_groups']}, 重复组 {stats['dup_groups']}, "
            f"重复文件 {stats['dup_files']}")
        return stats

    # ── 内部实现 ──────────────────────────────────────────────

    def _group_by_size(self) -> List[List[dict]]:
        """按 file_size 分组，只保留同大小 > 1 的候选组。"""
        rows = self.file_dao.db.execute_query(
            """SELECT file_size FROM files
               WHERE status = 'active'
               GROUP BY file_size HAVING COUNT(*) > 1""")
        if not rows:
            return []
        groups: List[List[dict]] = []
        for row in rows:
            records = self.file_dao.db.execute_query(
                "SELECT * FROM files WHERE status = 'active' AND file_size = ?",
                (row['file_size'],))
            if len(records) > 1:
                groups.append(records)
        return groups

    @staticmethod
    def _compute_fast_hash(path: str) -> Optional[str]:
        """计算文件头部快速哈希（sha256 前 64KB）。文件不可读返回 None。"""
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                h.update(f.read(FAST_HASH_READ_BYTES))
            return h.hexdigest()
        except (IOError, OSError) as e:
            logger.warning(f"快速哈希失败: {path} - {e}")
            return None

    @staticmethod
    def _compute_full_hash(path: str, block_size: int = 65536) -> Optional[str]:
        """计算完整文件 sha256。文件不可读返回 None。"""
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                while True:
                    block = f.read(block_size)
                    if not block:
                        break
                    h.update(block)
            return h.hexdigest()
        except (IOError, OSError) as e:
            logger.warning(f"完整哈希失败: {path} - {e}")
            return None


def find_duplicates_multistage(progress_cb=None) -> Dict[int, List[dict]]:
    """便捷入口：返回 {group_id: [file_records...]}，与旧 DedupManager 兼容。"""
    detector = MultistageDedupDetector()
    detector.run(progress_cb=progress_cb)
    groups: Dict[int, List[dict]] = {}
    for row in detector.file_dao.db.execute_query(
            "SELECT * FROM files WHERE is_duplicate = 1 AND status = 'active' "
            "ORDER BY duplicate_group_id"):
        gid = row['duplicate_group_id']
        groups.setdefault(gid, []).append(row)
    return groups
