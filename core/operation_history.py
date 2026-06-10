"""
操作历史管理 - 记录与撤销
"""
import os
import shutil
from typing import Optional

from database.db_manager import db
from database.models import FileDAO, OperationHistoryDAO
from utils.logger import logger


class OperationHistoryManager:
    """操作历史管理器"""

    def __init__(self):
        self.file_dao = FileDAO(db)
        self.history_dao = OperationHistoryDAO(db)

    def undo_operation(self, operation_id: int) -> bool:
        """撤销单个操作"""
        op = self.history_dao.get_by_id(operation_id)
        if not op:
            raise ValueError(f"操作记录不存在: id={operation_id}")
        if op['operation_status'] != 'completed':
            raise ValueError(f"操作不可撤销: 状态={op['operation_status']}")
        if not op['undo_available']:
            raise ValueError("该操作不支持撤销")

        op_type = op['operation_type']
        file_id = op['file_id']
        old_value = op['old_value']
        new_value = op['new_value']

        try:
            if op_type == 'rename':
                self._undo_rename(file_id, old_value, new_value)
            elif op_type == 'move':
                self._undo_move(file_id, old_value, new_value)
            elif op_type == 'delete':
                self._undo_delete(file_id, old_value, new_value)
            elif op_type == 'dedup':
                self._undo_delete(file_id, old_value, new_value)
            else:
                raise ValueError(f"不支持撤销的操作类型: {op_type}")

            self.history_dao.mark_undone(operation_id)
            # 记录还原操作
            self.history_dao.insert('restore', file_id, new_value, old_value)
            logger.info(f"撤销操作 ID={operation_id} 类型={op_type}")
            return True
        except Exception as e:
            logger.error(f"撤销失败 ID={operation_id}: {e}")
            raise

    def undo_batch(self, batch_id: str) -> dict:
        """撤销一批操作（按逆序）"""
        ops = self.history_dao.get_by_batch(batch_id)
        if not ops:
            raise ValueError(f"未找到批次: {batch_id}")

        success = 0
        failed = 0
        errors = []

        # 逆序撤销
        for op in reversed(ops):
            if op['operation_status'] != 'completed' or not op['undo_available']:
                continue
            try:
                self.undo_operation(op['id'])
                success += 1
            except Exception as e:
                failed += 1
                errors.append(str(e))

        logger.info(f"批量撤销 batch={batch_id}: 成功{success}, 失败{failed}")
        return {'success': success, 'failed': failed, 'errors': errors}

    def _undo_rename(self, file_id: int, old_path: str, new_path: str) -> None:
        """撤销重命名"""
        if not os.path.exists(new_path):
            raise FileNotFoundError(f"当前文件不存在: {new_path}")
        if os.path.exists(old_path):
            raise FileExistsError(f"原路径已被占用: {old_path}")

        os.rename(new_path, old_path)
        old_name = os.path.basename(old_path)
        self.file_dao.update_name(file_id, old_name, old_path)

    def _undo_move(self, file_id: int, old_path: str, new_path: str) -> None:
        """撤销移动"""
        if not os.path.exists(new_path):
            raise FileNotFoundError(f"当前文件不存在: {new_path}")
        if os.path.exists(old_path):
            raise FileExistsError(f"原路径已被占用: {old_path}")

        old_dir = os.path.dirname(old_path)
        os.makedirs(old_dir, exist_ok=True)
        shutil.move(new_path, old_path)
        old_name = os.path.basename(old_path)
        self.file_dao.update_name(file_id, old_name, old_path)

    def _undo_delete(self, file_id: int, old_path: str, trash_path: str = None) -> None:
        """撤销删除：从本地回收区恢复文件，或仅恢复数据库状态"""
        if trash_path and os.path.exists(trash_path):
            # 回收区文件存在，恢复到原路径
            old_dir = os.path.dirname(old_path)
            os.makedirs(old_dir, exist_ok=True)
            if os.path.exists(old_path):
                raise FileExistsError(f"原路径已被占用，无法恢复: {old_path}")
            shutil.move(trash_path, old_path)
            logger.info(f"从回收区恢复文件: {trash_path} -> {old_path}")
        elif trash_path == 'permanent':
            raise RuntimeError("永久删除的文件无法撤销")
        else:
            # 回收区路径未知或文件已不存在，仅恢复数据库状态
            logger.warning(
                f"回收区文件不存在或未记录路径 (trash_path={trash_path})，"
                f"仅恢复数据库状态，磁盘文件需手动恢复")

        self.file_dao.update_status(file_id, 'active')

    def get_recent_operations(self, limit: int = 100,
                              op_type: Optional[str] = None) -> list:
        return self.history_dao.get_recent(limit, op_type)

    def get_undoable_operations(self, limit: int = 100) -> list:
        return self.history_dao.get_undoable(limit)

    def search_operations(self, **kwargs) -> list:
        return self.history_dao.search(**kwargs)
