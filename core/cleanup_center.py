"""安全清理中心 —— 聚合重复、临时、空、长期未用、超大文件清理建议。

特点（对应 ROADMAP P0-12）：
1. 所有建议说明原因（reason）；
2. 执行清理默认进入回收区（可撤销），复用 FileManager 的回收区机制；
3. 支持排除目录（cleanup_exclusions 表）与误报反馈（cleanup_false_positives 表），
   下次分析自动跳过。
"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from database.db_manager import db
from database.models import FileDAO, ClassificationDAO, TagDAO
from core.file_manager import FileManager
from core.rule_engine import CleanupAdvisor
from utils.logger import logger

# 超大文件阈值（500MB）
LARGE_FILE_THRESHOLD = 500 * 1024 * 1024
# 长期未修改阈值（365 天）
OLD_FILE_DAYS = 365


class CleanupCenter:
    """聚合清理建议 + 排除/误报 + 安全执行。"""

    def __init__(self, file_dao: Optional[FileDAO] = None,
                 tag_dao: Optional[TagDAO] = None,
                 cls_dao: Optional[ClassificationDAO] = None):
        self.file_dao = file_dao or FileDAO(db)
        self.tag_dao = tag_dao or TagDAO(db)
        self.cls_dao = cls_dao or ClassificationDAO(db)
        self.file_manager = FileManager()

    # ── 分析 ──────────────────────────────────────────────────

    def analyze(self) -> Dict[str, List[dict]]:
        """聚合全部清理建议，应用排除目录与误报过滤。

        Returns:
            {'duplicates': [...], 'temp': [...], 'empty': [...],
             'old': [...], 'large': [...], 'all': [...]}
            每项为文件记录 + reason。
        """
        advisor = CleanupAdvisor(self.file_dao, self.tag_dao, self.cls_dao)
        report = advisor.analyze()

        exclusions = self._load_exclusions()
        false_positives = self._load_false_positives()

        result = {'duplicates': [], 'temp': [], 'empty': [],
                  'old': [], 'large': [], 'all': []}

        # 重复文件：按组聚合
        for group_id, records in self._duplicate_groups().items():
            for record in records:
                if self._is_filtered(record['file_path'], exclusions, false_positives):
                    continue
                item = self._to_item(record, 'duplicates',
                                     '与组内文件内容完全相同（完整哈希一致），保留一份即可')
                result['duplicates'].append(item)
                result['all'].append(item)

        # 临时文件
        for record in self._temp_files():
            if self._is_filtered(record['file_path'], exclusions, false_positives):
                continue
            item = self._to_item(record, 'temp', '临时/缓存文件，通常可安全删除')
            result['temp'].append(item)
            result['all'].append(item)

        # 空文件
        for record in self._empty_files():
            if self._is_filtered(record['file_path'], exclusions, false_positives):
                continue
            item = self._to_item(record, 'empty', '空文件（0 字节），无内容价值')
            result['empty'].append(item)
            result['all'].append(item)

        # 长期未修改
        for record in self._old_files():
            if self._is_filtered(record['file_path'], exclusions, false_positives):
                continue
            item = self._to_item(record, 'old', f'超过 {OLD_FILE_DAYS} 天未修改，可能已废弃')
            result['old'].append(item)
            result['all'].append(item)

        # 超大文件
        for record in self._large_files():
            if self._is_filtered(record['file_path'], exclusions, false_positives):
                continue
            item = self._to_item(record, 'large',
                                 f'超大文件（≥ {LARGE_FILE_THRESHOLD // (1024*1024)}MB），确认是否仍需保留')
            result['large'].append(item)
            result['all'].append(item)

        return result

    # ── 各类候选 ──────────────────────────────────────────────

    def _duplicate_groups(self) -> Dict[int, List[dict]]:
        rows = self.file_dao.db.execute_query(
            "SELECT * FROM files WHERE is_duplicate = 1 AND status = 'active' "
            "ORDER BY duplicate_group_id")
        groups: Dict[int, List[dict]] = {}
        for row in rows:
            groups.setdefault(row['duplicate_group_id'], []).append(row)
        return groups

    def _temp_files(self) -> List[dict]:
        patterns = CleanupAdvisor._TEMP_PATTERNS
        result = []
        for record in self.file_dao.get_all_active():
            name = record.get('file_name', '')
            if any(re.search(p, name) for p in patterns):
                result.append(record)
        return result

    def _empty_files(self) -> List[dict]:
        return self.file_dao.search(max_size=0)

    def _old_files(self) -> List[dict]:
        threshold = (datetime.now() - timedelta(days=OLD_FILE_DAYS)).strftime('%Y-%m-%d')
        return self.file_dao.search(end_date=threshold + ' 23:59:59')

    def _large_files(self) -> List[dict]:
        return self.file_dao.search(min_size=LARGE_FILE_THRESHOLD)

    # ── 过滤 ──────────────────────────────────────────────────

    @staticmethod
    def _to_item(record: dict, category: str, reason: str) -> dict:
        return {'file_id': record['id'], 'file_path': record.get('file_path', ''),
                'file_name': record.get('file_name', ''),
                'file_size': record.get('file_size', 0),
                'category': category, 'reason': reason,
                'record': record}

    @staticmethod
    def _is_filtered(path: str, exclusions: List[str], false_positives: List[str]) -> bool:
        if not path:
            return True
        normalized = path.replace('\\', '/')
        for pattern in exclusions:
            if pattern.replace('\\', '/') in normalized:
                return True
        return normalized in [fp.replace('\\', '/') for fp in false_positives]

    def _load_exclusions(self) -> List[str]:
        rows = db.execute_query("SELECT path_pattern FROM cleanup_exclusions")
        return [r['path_pattern'] for r in rows]

    def _load_false_positives(self) -> List[str]:
        rows = db.execute_query("SELECT file_path FROM cleanup_false_positives")
        return [r['file_path'].replace('\\', '/') for r in rows]

    # ── 排除/误报 ─────────────────────────────────────────────

    def add_exclusion(self, path_pattern: str, reason: str = '') -> bool:
        try:
            db.execute_insert(
                "INSERT OR IGNORE INTO cleanup_exclusions (path_pattern, reason, create_time) "
                "VALUES (?, ?, ?)",
                (path_pattern, reason, datetime.now()))
            return True
        except Exception as e:
            logger.warning(f"添加排除目录失败: {e}")
            return False

    def remove_exclusion(self, path_pattern: str) -> bool:
        return db.execute_update(
            "DELETE FROM cleanup_exclusions WHERE path_pattern = ?", (path_pattern,)) > 0

    def list_exclusions(self) -> List[dict]:
        return db.execute_query("SELECT * FROM cleanup_exclusions ORDER BY create_time DESC")

    def mark_false_positive(self, file_path: str, reason: str = '') -> bool:
        try:
            db.execute_insert(
                "INSERT OR IGNORE INTO cleanup_false_positives (file_path, reason, create_time) "
                "VALUES (?, ?, ?)",
                (file_path, reason, datetime.now()))
            return True
        except Exception as e:
            logger.warning(f"标记误报失败: {e}")
            return False

    def remove_false_positive(self, file_path: str) -> bool:
        return db.execute_update(
            "DELETE FROM cleanup_false_positives WHERE file_path = ?", (file_path,)) > 0

    # ── 执行清理（安全：入回收区） ────────────────────────────

    def execute_cleanup(self, items: List[dict]) -> Dict[str, int]:
        """将选中的建议项移入回收区并标记删除。

        Returns: {'moved': int, 'failed': int, 'errors': [str]}
        """
        result = {'moved': 0, 'failed': 0, 'errors': []}
        batch_id = None
        for item in items:
            file_id = item.get('file_id')
            record = self.file_dao.get_by_id(file_id) if file_id else None
            if not record:
                result['failed'] += 1
                result['errors'].append(f"记录不存在: {item.get('file_path')}")
                continue
            try:
                from core.file_manager import _move_to_trash
                file_path = record['file_path']
                trash_path = None
                if os.path.exists(file_path):
                    trash_path = _move_to_trash(file_path)
                self.file_dao.update_status(file_id, 'deleted')
                from database.models import OperationHistoryDAO
                history_dao = OperationHistoryDAO(db)
                history_dao.insert('cleanup', file_id, file_path, trash_path,
                                   batch_id=batch_id)
                result['moved'] += 1
            except Exception as e:
                result['failed'] += 1
                result['errors'].append(f"{item.get('file_path')}: {e}")
                logger.warning(f"清理失败 {item.get('file_path')}: {e}")
        return result
