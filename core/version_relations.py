"""P1-08 文件版本关系 —— 启发式识别"修改稿/最终版"文件族。

只基于库内元数据（名称模式 + 同目录 + 同扩展名 + 修改时间）产出候选关系，
写入 file_relations（pending），由用户在 UI 中确认或解除——推荐结果不改变真实路径。
"""
import re
from typing import Optional

from utils.logger import logger

# 常见版本后缀标记（去掉后 base 相同 → 同族候选）
_VERSION_SUFFIX = re.compile(
    r'[\s._-]*'
    r'(?:\(\d+\)|\[\d+\]|v\d+|版本\d*|final|最终版?|修改稿?|定稿|副本|copy|new|新|draft|old|旧|backup|备份)',
    re.IGNORECASE,
)


def _base_name(file_name: str) -> str:
    """去掉扩展名与版本标记后的族名（小写比较）"""
    stem = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
    return _VERSION_SUFFIX.sub('', stem).strip().lower()


def _time_key(record: dict):
    """可比较的时间键（ISO 字符串截断后可直接比较）"""
    return str(record.get('modify_time') or '')[:19]


def detect_version_candidates(db_manager=None, max_per_dir: int = 200) -> int:
    """扫描库内文件，识别版本族候选并写入 file_relations（pending）。

    规则：同目录 + 同扩展名 + 去版本标记后族名一致 + 修改时间不同。
    置信度：按时间相邻链 0.8，族首尾 0.6（纯启发式，仅作推荐排序）。
    返回新增候选数。同族文件太多跳过（防误报风暴）。
    """
    if db_manager is not None:
        db_ = db_manager
    else:
        from database.db_manager import db
        db_ = db
    from database.models import VersionRelationDAO

    rows = db_.execute_query(
        "SELECT id, file_name, file_path, modify_time "
        "FROM files WHERE status = 'active'") or []

    # (dir, ext, family) → [records]
    families: dict = {}
    for r in rows:
        fp = (r.get('file_path') or '').replace('\\', '/')
        dir_path = fp.rsplit('/', 1)[0] if '/' in fp else ''
        ext = ('.' + r['file_name'].rsplit('.', 1)[1].lower()
               if '.' in r['file_name'] else '')
        family = _base_name(r['file_name'])
        if not family:
            continue
        families.setdefault((dir_path, ext, family), []).append(r)

    dao = VersionRelationDAO(db_)
    added = 0
    for members in families.values():
        if len(members) < 2 or len(members) > max_per_dir:
            continue
        members.sort(key=_time_key)
        for i in range(len(members) - 1):
            a, b = members[i], members[i + 1]
            if _time_key(a) == _time_key(b):
                continue
            if dao.upsert_suggestion(a['id'], b['id'], 0.8):
                added += 1
        if len(members) > 2:
            if dao.upsert_suggestion(members[0]['id'], members[-1]['id'], 0.6):
                added += 1
    logger.info(f"版本关系候选: 新增 {added} 条")
    return added
