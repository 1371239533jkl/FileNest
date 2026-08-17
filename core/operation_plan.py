"""操作计划与预演 —— 高风险批量操作先生成可审计的变更计划，再由用户确认。

OperationPlan 覆盖：批量移动、删除（入回收区）、归档和批量重命名。
计划内容：影响范围、冲突、不可逆项、预计释放空间。
计划有过期时间，执行前重新校验文件状态，避免基于陈旧信息执行。
"""
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from utils.display_utils import format_size

# 计划默认有效期（秒）
PLAN_TTL_SECONDS = 600


@dataclass
class PlanItem:
    """计划中的单个文件操作项"""
    file_id: int
    old_path: str
    new_path: str = ''
    action: str = 'move'           # move | delete | rename
    conflict: bool = False          # 目标冲突（存在同名）
    irreversible: bool = False      # 是否不可逆（如物理删除）
    reason: str = ''
    size: int = 0


@dataclass
class OperationPlan:
    """一次批量操作的完整计划，执行前需 validate()。"""
    action: str                     # 'move' | 'delete' | 'rename' | 'archive'
    items: List[PlanItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = PLAN_TTL_SECONDS
    note: str = ''

    # ── 统计 ──
    @property
    def total_size(self) -> int:
        return sum(item.size for item in self.items)

    @property
    def freed_space(self) -> int:
        """预计释放空间：仅删除/移动出扫描范围的项计入。"""
        if self.action == 'delete':
            return self.total_size
        return 0

    @property
    def conflict_count(self) -> int:
        return sum(1 for item in self.items if item.conflict)

    @property
    def irreversible_count(self) -> int:
        return sum(1 for item in self.items if item.irreversible)

    # ── 生命周期 ──
    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) - self.created_at > self.ttl_seconds

    # ── 校验 ──
    def validate(self, file_dao=None) -> List[str]:
        """执行前校验：计划过期、源文件缺失/已变化、目标冲突。

        返回问题列表；为空表示可安全执行。file_dao 缺省时不查库，仅做静态校验。
        """
        problems: List[str] = []
        if self.is_expired():
            problems.append("计划已过期，请重新生成")
        for item in self.items:
            if not os.path.exists(item.old_path):
                problems.append(f"源文件已不存在: {item.old_path}")
                continue
            if file_dao is not None:
                record = file_dao.get_by_id(item.file_id)
                if not record:
                    problems.append(f"记录缺失: {item.old_path}")
                    continue
                if item.old_path != record.get('file_path'):
                    problems.append(f"路径已变化，需重新校验: {item.old_path}")
            if item.conflict and item.new_path:
                problems.append(f"目标冲突: {item.new_path}")
        return problems

    # ── 摘要 ──
    def summary(self) -> str:
        lines = [f"操作计划：{self.action}，共 {len(self.items)} 项"]
        if self.note:
            lines.append(f"说明：{self.note}")
        lines.append(f"涉及大小：{format_size(self.total_size)}")
        if self.action == 'delete':
            lines.append(f"预计释放空间：{format_size(self.freed_space)}")
        if self.conflict_count:
            lines.append(f"冲突：{self.conflict_count} 项")
        if self.irreversible_count:
            lines.append(f"不可逆：{self.irreversible_count} 项")
        if self.is_expired():
            lines.append("⚠️ 计划已过期")
        return "\n".join(lines)


class OperationPlanBuilder:
    """从批量操作参数构建 OperationPlan。"""

    def __init__(self, file_dao=None):
        self.file_dao = file_dao

    def build(self, action: str, records: List[dict], target: str = '',
              note: str = '') -> OperationPlan:
        """根据文件记录构建计划。

        Args:
            action: move | delete | rename
            records: 文件记录列表（需含 id/file_path/file_size）
            target: move 的目标目录 / rename 的目标命名模板
            note: 计划说明
        """
        plan = OperationPlan(action=action, note=note)
        seen_targets = set()

        for rec in records:
            old_path = rec.get('file_path', '')
            size = rec.get('file_size') or 0
            if action == 'delete':
                item = PlanItem(
                    file_id=rec['id'], old_path=old_path, action='delete',
                    irreversible=False, reason='移入回收区，可撤销', size=size)
            elif action == 'rename':
                new_name = self._render_rename(rec, target)
                new_path = os.path.join(os.path.dirname(old_path), new_name) if old_path else ''
                conflict = self._is_conflict(new_path, old_path, seen_targets)
                item = PlanItem(
                    file_id=rec['id'], old_path=old_path, new_path=new_path,
                    action='rename', conflict=conflict,
                    reason='目标名称已存在，将自动追加序号' if conflict else '',
                    size=size)
            else:  # move
                new_path = os.path.join(target, os.path.basename(old_path)) if old_path else ''
                conflict = self._is_conflict(new_path, old_path, seen_targets)
                item = PlanItem(
                    file_id=rec['id'], old_path=old_path, new_path=new_path,
                    action='move', conflict=conflict,
                    reason='目标名称已存在，将自动追加序号' if conflict else '',
                    size=size)
            plan.items.append(item)
        return plan

    def _render_rename(self, rec: dict, pattern: str) -> str:
        """渲染重命名模板。支持 {date} {type} {original_name} {ext}。"""
        if not pattern:
            return rec.get('file_name', '')
        from config import DEFAULT_RENAME_PATTERN
        pattern = pattern or DEFAULT_RENAME_PATTERN
        name = os.path.splitext(rec.get('file_name') or '')[0]
        ext = rec.get('file_extension') or os.path.splitext(rec.get('file_name') or '')[1]
        rendered = pattern.replace('{date}', '')
        rendered = rendered.replace('{type}', rec.get('file_type') or '')
        rendered = rendered.replace('{original_name}', name)
        rendered = rendered.replace('{ext}', ext)
        return rendered

    def _is_conflict(self, new_path: str, old_path: str, seen: set) -> bool:
        if not new_path or new_path == old_path:
            return False
        conflict = os.path.exists(new_path) or new_path in seen
        seen.add(new_path)
        return conflict
