"""
去重管理器 - 基于SHA256哈希检测和处理重复文件
"""
import uuid
from typing import Optional, List, Dict, Tuple

from database.db_manager import db
from database.models import FileDAO, OperationHistoryDAO
from utils.logger import logger


class DedupManager:
    """文件去重管理器"""

    def __init__(self):
        self.file_dao = FileDAO(db)
        self.history_dao = OperationHistoryDAO(db)

    def find_duplicates(self) -> Dict[int, List[dict]]:
        """查找所有重复文件组（单次SQL查询）
        返回: {group_id: [file_records...]}
        """
        all_dup_files = self.file_dao.get_all_duplicates()
        groups: Dict[int, List[dict]] = {}
        group_id = 0

        # 按 file_hash 分组（结果已按 file_hash 排序）
        current_hash = None
        current_group: List[dict] = []
        for f in all_dup_files:
            if f['file_hash'] != current_hash:
                if len(current_group) > 1:
                    group_id += 1
                    groups[group_id] = current_group
                    # 更新数据库中的重复标记
                    for f_rec in current_group:
                        self.file_dao.update_duplicate(f_rec['id'], 1, group_id)
                current_hash = f['file_hash']
                current_group = [f]
            else:
                current_group.append(f)

        # 处理最后一组
        if len(current_group) > 1:
            group_id += 1
            groups[group_id] = current_group
            for f_rec in current_group:
                self.file_dao.update_duplicate(f_rec['id'], 1, group_id)

        logger.info(f"发现 {len(groups)} 组重复文件")
        return groups

    def suggest_keep(self, file_group: List[dict],
                     strategy: str = 'keep_newest') -> Tuple[Optional[int], list]:
        """根据策略推荐保留的文件
        返回: (keep_file_id, remove_file_ids)
        """
        if not file_group:
            return None, []

        if strategy == 'keep_newest':
            sorted_files = sorted(file_group,
                key=lambda f: f.get('modify_time') or f.get('create_time') or '',
                reverse=True)
        elif strategy == 'keep_oldest':
            sorted_files = sorted(file_group,
                key=lambda f: f.get('modify_time') or f.get('create_time') or '')
        elif strategy == 'keep_shortest_path':
            sorted_files = sorted(file_group,
                key=lambda f: len(f.get('file_path', '')))
        else:
            sorted_files = file_group

        keep = sorted_files[0]
        remove = sorted_files[1:]
        return keep['id'], [f['id'] for f in remove]

    def remove_duplicates(self, group_id: int, keep_file_id: int,
                          remove_file_ids: List[int]) -> Tuple[str, int]:
        """执行去重 - 标记删除重复文件"""
        batch_id = f"dedup_{uuid.uuid4().hex[:8]}"
        removed = 0

        for fid in remove_file_ids:
            try:
                record = self.file_dao.get_by_id(fid)
                if not record:
                    continue
                self.file_dao.update_status(fid, 'deleted')
                self.history_dao.insert(
                    'dedup', fid, record['file_path'], f"keep={keep_file_id}",
                    batch_id=batch_id)
                removed += 1
            except Exception as e:
                logger.warning(f"去重删除失败 ID={fid}: {e}")

        # 保留文件取消重复标记
        self.file_dao.update_duplicate(keep_file_id, 0, None)

        logger.info(f"去重完成 组{group_id}: 保留ID={keep_file_id}, 删除{removed}个")
        return batch_id, removed

    def auto_dedup(self, strategy: str = 'keep_newest') -> Tuple[int, list]:
        """自动去重所有重复文件"""
        groups = self.find_duplicates()
        total_removed = 0
        batch_ids = []

        for group_id, files in groups.items():
            keep_id, remove_ids = self.suggest_keep(files, strategy)
            if keep_id and remove_ids:
                bid, removed = self.remove_duplicates(group_id, keep_id, remove_ids)
                total_removed += removed
                batch_ids.append(bid)

        logger.info(f"自动去重完成: 共删除 {total_removed} 个重复文件")
        return total_removed, batch_ids

    def get_duplicate_stats(self) -> dict:
        """获取重复文件统计"""
        groups = self.find_duplicates()
        total_groups = len(groups)
        total_files = sum(len(files) for files in groups.values())
        wasted_size = 0
        for files in groups.values():
            sizes = [f.get('file_size', 0) for f in files]
            if sizes:
                wasted_size += sum(sizes) - min(sizes)
        return {
            'groups': total_groups,
            'total_files': total_files,
            'wasted_size': wasted_size,
        }
