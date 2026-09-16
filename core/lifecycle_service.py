"""
生命周期策略引擎（批次7 P2-07）。

按策略匹配超龄文件（超过 N 天未修改），动作三种：
- remind  : 仅提醒（不改动文件，UI 汇报匹配清单）
- archive : 打包归档（复用 ArchiveService）→ 原文件移入回收区（可撤销）
- trash   : 直接移入回收区（复用 FileManager.delete_file，可撤销）

安全设计：
- 不做物理删除，一切写操作走回收区 + 操作历史（与清理中心同级别安全性）
- 执行前由调用方（UI）用 OperationPlan 预演确认
- 每次检查后更新 last_run_at，供 UI 展示
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional

from database.db_manager import db
from database.models import FileDAO, TagDAO, LifecyclePolicyDAO, OperationHistoryDAO
from core.archive_service import ArchiveService
from core.file_manager import FileManager
from utils.logger import logger

ACTIONS = ('remind', 'archive', 'trash')
TARGET_TYPES = ('path', 'type', 'tag')


class LifecycleService:
    """生命周期策略：检查 + 预演 + 执行。"""

    def __init__(self, file_dao=None, tag_dao=None, policy_dao=None,
                 archive_service=None, file_manager=None):
        self.file_dao = file_dao or FileDAO(db)
        self.tag_dao = tag_dao or TagDAO(db)
        self.policy_dao = policy_dao or LifecyclePolicyDAO(db)
        self.archive_service = archive_service or ArchiveService()
        if file_manager is not None:
            self.file_manager = file_manager
        else:
            # 注入与 file_dao 相同的库，保证测试/多库场景一致
            from database.models import OperationHistoryDAO
            self.file_manager = FileManager(
                file_dao=self.file_dao,
                history_dao=OperationHistoryDAO(self.file_dao.db))

    # ── 匹配 ──────────────────────────────────────────────────

    def match_files(self, policy: dict) -> List[dict]:
        """返回策略命中的超龄文件列表（status=active）。"""
        target_type = policy.get('target_type', 'path')
        target_value = (policy.get('target_value') or '').strip()
        threshold = int(policy.get('days_threshold') or 30)
        if not target_value:
            return []
        cutoff = datetime.now() - timedelta(days=threshold)

        if target_type == 'path':
            records = self.file_dao.db.execute_query(
                "SELECT * FROM files WHERE status = 'active' AND file_path LIKE ?",
                (target_value.rstrip('\\/') + '%',)) or []
        elif target_type == 'type':
            records = self.file_dao.db.execute_query(
                "SELECT * FROM files WHERE status = 'active' AND file_type = ?",
                (target_value,)) or []
        elif target_type == 'tag':
            records = self.tag_dao.get_files_by_tag(target_value) or []
        else:
            logger.warning(f"未知 target_type: {target_type}")
            return []

        matched = []
        for r in records:
            mtime = self._parse_time(r.get('modify_time') or r.get('create_time'))
            if mtime and mtime < cutoff:
                matched.append(r)
        matched.sort(key=lambda r: r.get('modify_time') or '')
        return matched

    @staticmethod
    def _parse_time(value) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(str(value)[:19], fmt)
            except ValueError:
                continue
        return None

    # ── 检查 ──────────────────────────────────────────────────

    def check_all(self, enabled_only: bool = True) -> List[dict]:
        """检查全部策略，返回 [{'policy', 'matches', 'match_count'}]。"""
        results = []
        for policy in self.policy_dao.get_all(enabled_only=enabled_only):
            try:
                matches = self.match_files(policy)
            except Exception as e:  # noqa: BLE001
                logger.error(f"策略 {policy.get('name')} 检查失败: {e}")
                matches = []
            results.append({
                'policy': policy,
                'matches': matches,
                'match_count': len(matches),
            })
            self.policy_dao.touch_last_run(policy['id'])
        return results

    # ── 执行 ──────────────────────────────────────────────────

    def execute(self, policy: dict, matches: List[dict],
                progress_cb=None) -> dict:
        """
        执行策略动作。调用方需先经 UI 预演确认。

        返回 {'success', 'action', 'processed', 'failed', 'archive_path', 'errors'}
        """
        action = policy.get('action', 'remind')
        errors: List[str] = []
        processed = 0
        archive_path = None

        if action == 'remind':
            return {'success': True, 'action': action, 'processed': 0,
                    'failed': 0, 'archive_path': None, 'errors': []}

        if action == 'archive':
            archive_dir = (policy.get('archive_dir') or '').strip()
            if not archive_dir:
                return {'success': False, 'action': action, 'processed': 0,
                        'failed': 0, 'archive_path': None,
                        'errors': ['归档动作需要先配置输出目录']}
            try:
                os.makedirs(archive_dir, exist_ok=True)
            except OSError as e:
                return {'success': False, 'action': action, 'processed': 0,
                        'failed': 0, 'archive_path': None,
                        'errors': [f'无法创建输出目录: {e}']}
            paths = [r['file_path'] for r in matches if r.get('file_path')]
            result = self.archive_service.create_package(
                paths, archive_dir,
                package_name=f"lifecycle_{policy.get('name', 'pkg')}"
                             f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            if not result.get('success'):
                return {'success': False, 'action': action, 'processed': 0,
                        'failed': 0, 'archive_path': None,
                        'errors': [result.get('error') or '归档失败']}
            archive_path = result.get('archive_path')

        # archive 成功后 / trash：移入回收区（同一 batch 便于整批撤销）
        batch_id = datetime.now().strftime('lifecycle_%Y%m%d%H%M%S%f')
        for r in matches:
            fid = r.get('id')
            try:
                if self.file_manager.delete_file(fid, batch_id=batch_id):
                    processed += 1
                else:
                    errors.append(f"{r.get('file_path')}: 移入回收区失败")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{r.get('file_path')}: {e}")
            if progress_cb:
                progress_cb(processed, len(matches))
        if processed:
            self._record_history(policy, action, processed, archive_path)

        return {'success': not errors or processed > 0, 'action': action,
                'processed': processed, 'failed': len(errors),
                'archive_path': archive_path, 'errors': errors[:20]}

    @staticmethod
    def _record_history(policy: dict, action: str, count: int,
                        archive_path: Optional[str]):
        """策略执行写入操作历史（file_id 用 policy id，old_value 存摘要）。"""
        try:
            summary = (f"生命周期策略「{policy.get('name')}」{action} {count} 个文件"
                       + (f"，归档: {archive_path}" if archive_path else ''))
            OperationHistoryDAO(db).insert(
                'lifecycle', policy['id'], summary, policy.get('name'),
                status='completed')
        except Exception as e:  # noqa: BLE001
            logger.warning(f"生命周期执行记录失败: {e}")
