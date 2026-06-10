"""
文件操作管理 - 重命名、移动、删除
删除的文件移至应用本地回收区(.trash/)，支持在应用内一键恢复。
"""
import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from config import DEFAULT_RENAME_PATTERN, FILE_TYPE_NAMES
from database.db_manager import db
from database.models import FileDAO, OperationHistoryDAO
from utils.date_utils import parse_datetime_safe
from utils.logger import logger

# 应用本地回收区（与 logs 同级）
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRASH_DIR = os.path.join(_APP_DIR, '.trash')


def _move_to_trash(file_path: str) -> str:
    """将文件移至本地回收区，返回回收区路径"""
    os.makedirs(_TRASH_DIR, exist_ok=True)
    trash_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file_path)}"
    trash_path = os.path.join(_TRASH_DIR, trash_name)
    trash_path = FileManager._ensure_unique_path(trash_path)
    shutil.move(file_path, trash_path)
    logger.info(f"文件已移至回收区: {trash_path}")
    return trash_path


def _restore_from_trash(trash_path: str, original_path: str) -> None:
    """从回收区恢复文件到原路径"""
    if not os.path.exists(trash_path):
        raise FileNotFoundError(f"回收区文件不存在: {trash_path}")
    parent = os.path.dirname(original_path)
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(original_path):
        raise FileExistsError(f"原路径已被占用: {original_path}")
    shutil.move(trash_path, original_path)
    logger.info(f"从回收区恢复: {trash_path} -> {original_path}")


class FileManager:
    """文件操作管理器"""

    def __init__(self):
        self.file_dao = FileDAO(db)
        self.history_dao = OperationHistoryDAO(db)

    def rename_file(self, file_id: int, new_name: Optional[str] = None,
                    pattern: Optional[str] = None, batch_id: Optional[str] = None) -> Optional[int]:
        """重命名文件
        new_name: 直接指定新文件名
        pattern: 使用模板生成新文件名
        """
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")

        old_path = record.get('file_path')
        if not old_path or not isinstance(old_path, str):
            raise ValueError(f"文件路径无效: id={file_id}")
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"文件不存在: {old_path}")

        old_name = record['file_name']

        if new_name is None:
            if pattern is None:
                pattern = DEFAULT_RENAME_PATTERN
            new_name = self._generate_name(record, pattern)

        # 确保扩展名一致
        old_ext = record['file_extension']
        if not new_name.lower().endswith(old_ext.lower()):
            new_name = new_name + old_ext

        # 构建新路径
        parent = os.path.dirname(old_path)
        new_path = os.path.join(parent, new_name)

        # 避免覆盖
        new_path = self._ensure_unique_path(new_path)
        new_name = os.path.basename(new_path)

        # 路径安全校验：确保新文件未逃逸出父目录
        self._validate_path_safety(parent, new_path, "重命名")

        if old_path == new_path:
            return None

        # 执行重命名
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            logger.error(f"重命名文件失败: {old_path} -> {new_path}, 错误: {e}")
            raise RuntimeError(f"重命名失败: {e}") from e

        # 更新数据库
        self.file_dao.update_name(file_id, new_name, new_path)
        if not record.get('original_name'):
            db.execute_update(
                "UPDATE files SET original_name = %s WHERE id = %s",
                (old_name, file_id))

        # 记录操作历史
        op_id = self.history_dao.insert(
            'rename', file_id, old_path, new_path, batch_id=batch_id)

        logger.info(f"重命名: {old_name} -> {new_name}")
        return op_id

    def batch_rename(self, file_ids: list, pattern: Optional[str] = None) -> Tuple[str, dict]:
        """批量重命名"""
        batch_id = str(uuid.uuid4())[:8]
        results = {'success': 0, 'failed': 0, 'errors': []}

        for fid in file_ids:
            try:
                self.rename_file(fid, pattern=pattern, batch_id=batch_id)
                results['success'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"ID {fid}: {e}")
                logger.warning(f"批量重命名失败 ID={fid}: {e}")

        return batch_id, results

    def move_file(self, file_id: int, target_dir: str,
                  batch_id: Optional[str] = None) -> Optional[int]:
        """移动文件到目标目录"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")

        old_path = record.get('file_path')
        if not old_path or not isinstance(old_path, str):
            raise ValueError(f"文件路径无效: id={file_id}")
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"文件不存在: {old_path}")

        os.makedirs(target_dir, exist_ok=True)
        new_path = os.path.join(target_dir, record['file_name'])
        new_path = self._ensure_unique_path(new_path)

        # 路径安全校验：确保目标文件未逃逸出 target_dir
        self._validate_path_safety(target_dir, new_path, "移动")

        try:
            shutil.move(old_path, new_path)
        except OSError as e:
            logger.error(f"移动文件失败: {old_path} -> {new_path}, 错误: {e}")
            raise RuntimeError(f"移动失败: {e}") from e

        new_name = os.path.basename(new_path)
        self.file_dao.update_name(file_id, new_name, new_path)

        op_id = self.history_dao.insert(
            'move', file_id, old_path, new_path, batch_id=batch_id)

        logger.info(f"移动: {old_path} -> {new_path}")
        return op_id

    def delete_file(self, file_id: int, batch_id: Optional[str] = None) -> Optional[int]:
        """删除文件（移至回收区 + 标记数据库）
        new_value 记录回收区路径，撤销时可自动恢复文件。
        """
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")

        old_path = record['file_path']
        trash_path = None
        if os.path.exists(old_path):
            try:
                trash_path = _move_to_trash(old_path)
            except Exception as e:
                logger.warning(f"移至回收区失败: {old_path}, 错误: {e}")

        self.file_dao.update_status(file_id, 'deleted')

        op_id = self.history_dao.insert(
            'delete', file_id, old_path, trash_path, batch_id=batch_id)

        logger.info(f"删除（进回收区）: {old_path} -> {trash_path}")
        return op_id

    def permanent_delete(self, file_id: int, batch_id: Optional[str] = None) -> None:
        """永久删除文件（直接从磁盘删除，不经过回收区）"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")

        file_path = record['file_path']
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning(f"永久删除失败: {file_path}, 错误: {e}")
                raise RuntimeError(f"永久删除失败: {e}") from e

        self.file_dao.update_status(file_id, 'deleted')
        self.history_dao.insert(
            'delete', file_id, file_path, 'permanent',
            batch_id=batch_id)

        logger.info(f"永久删除: {file_path}")

    def restore_file(self, file_id: int) -> None:
        """从回收区恢复文件到原路径（供 UI 调用）"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")
        if record['status'] != 'deleted':
            raise ValueError(f"文件未被删除，无法恢复: id={file_id}")

        # 精确查找该文件最近一次删除/去重操作记录
        op = self.history_dao.get_latest_delete(file_id)
        trash_path = None
        if op:
            nv = op.get('new_value')
            if nv and nv not in ('permanent', 'recycle_bin') and os.path.exists(nv):
                trash_path = nv

        original_path = record['file_path']
        if trash_path:
            _restore_from_trash(trash_path, original_path)
        else:
            raise FileNotFoundError("回收区中找不到该文件，无法恢复")

        self.file_dao.update_status(file_id, 'active')
        self.history_dao.insert('restore', file_id, trash_path, original_path)
        logger.info(f"恢复文件: {original_path}")

    def purge_file(self, file_id: int, update_status: bool = True) -> None:
        """从回收区永久删除文件（删除磁盘回收区副本 + 更新数据库状态为 purged）"""
        record = self.file_dao.get_by_id(file_id)
        if not record:
            raise ValueError(f"文件记录不存在: id={file_id}")

        # 查找回收区路径并删除
        op = self.history_dao.get_latest_delete(file_id)
        if op:
            nv = op.get('new_value')
            if nv and nv not in ('permanent', 'recycle_bin') and os.path.exists(nv):
                try:
                    os.remove(nv)
                    logger.info(f"已从回收区永久删除: {nv}")
                except OSError as e:
                    logger.warning(f"删除回收区文件失败: {nv} - {e}")

        # 更新状态为 purged，使其从回收区列表消失
        if update_status:
            self.file_dao.update_status(file_id, 'purged')

        # 记录操作历史
        self.history_dao.insert(
            'delete', file_id, record.get('file_path'), 'permanent')

    @staticmethod
    def _validate_path_safety(expected_base: str, target_path: str, operation_name: str) -> None:
        """校验目标路径是否在预期的基础目录内，防止路径遍历攻击"""
        base_real = os.path.realpath(expected_base)
        target_real = os.path.realpath(target_path)
        if os.path.commonpath([base_real, target_real]) != base_real:
            raise PermissionError(
                f"[安全拦截] {operation_name}操作检测到路径逃逸风险："
                f"{target_path} 不在允许目录 {expected_base} 内"
            )

    def _generate_name(self, record: dict, pattern: str) -> str:
        """根据模板生成文件名"""
        mtime = record.get('modify_time') or record.get('create_time') or datetime.now()
        dt = parse_datetime_safe(mtime)
        if dt is None:
            dt = datetime.now()

        # 获取原文件名（不含扩展名）
        name_without_ext = Path(record['file_name']).stem
        file_type = FILE_TYPE_NAMES.get(record.get('file_type', 'other'), '其他')

        name = pattern.replace('{date}', dt.strftime('%Y%m%d'))
        name = name.replace('{time}', dt.strftime('%H%M%S'))
        name = name.replace('{type}', file_type)
        name = name.replace('{original_name}', name_without_ext)
        name = name.replace('{ext}', record.get('file_extension', ''))

        return name

    @staticmethod
    def _ensure_unique_path(file_path: str) -> str:
        """确保文件路径唯一，避免覆盖"""
        if not os.path.exists(file_path):
            return file_path

        p = Path(file_path)
        stem = p.stem
        ext = p.suffix
        parent = p.parent
        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{ext}"
            if not os.path.exists(new_path):
                return str(new_path)
            counter += 1
