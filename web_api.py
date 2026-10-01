"""Smart File Manager Web API（完整 Web 化，零侵入）。

仅复用 core/database/config，不 import UI 模块；由 server.py include。
端点均走现有安全链路（API Key、回收区、操作历史、二次确认 confirm=true）。
"""
import os
import json
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import FILE_TYPE_NAMES, DEFAULT_RENAME_PATTERN
from database.db_manager import db
from database.models import (
    FileDAO, FileContentDAO, MetadataDAO, ClassificationDAO, OperationHistoryDAO,
    ScanDirectoryDAO, SavedQueryDAO, ClassificationRuleDAO, SystemSettingsDAO,
    TagDAO, VersionRelationDAO, FileEventDAO, TimelineDAO, WorkspaceDAO,
    ArchivePackageDAO, LifecyclePolicyDAO,
)
from core.tag_manager import TagManager
from core.file_manager import FileManager
from core.dedup_manager import DedupManager
from core.content_indexer import ContentIndexer
from core.file_classifier import FileClassifier
from core.cleanup_center import CleanupCenter
from core.lifecycle_service import LifecycleService
from core.index_health import IndexHealthService
from core.archive_service import ArchiveService
from core.operation_history import OperationHistoryManager

router = APIRouter(prefix='/api')

API_KEY = os.environ.get('SFM_API_KEY', '')


def _auth(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='无效的 API Key')


def _confirm(confirm: bool, msg: str = '危险操作需要 confirm=true 确认'):
    if not confirm:
        raise HTTPException(status_code=400, detail=msg)


def _serialize(obj):
    """递归把 datetime/date 转为字符串，保证 JSON 可序列化。"""
    if isinstance(obj, (datetime, date)):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def _brief(row: dict) -> dict:
    """文件记录瘦身：列表页只返回常用字段。"""
    return {
        'id': row.get('id'), 'file_name': row.get('file_name'),
        'file_path': row.get('file_path'), 'file_type': row.get('file_type'),
        'file_extension': row.get('file_extension'),
        'file_size': row.get('file_size'), 'file_hash': row.get('file_hash'),
        'status': row.get('status'), 'is_duplicate': row.get('is_duplicate'),
        'create_time': _serialize(row.get('create_time')),
        'modify_time': _serialize(row.get('modify_time')),
        'scan_time': _serialize(row.get('scan_time')),
    }


# ═══════════ 请求体模型 ═══════════

class ScanReq(BaseModel):
    directory: str
    recursive: bool = True


class TagBody(BaseModel):
    tag: str


class RenameBody(BaseModel):
    file_id: int
    new_name: str


class MoveBody(BaseModel):
    file_id: int
    target_dir: str


class BatchRenameBody(BaseModel):
    file_ids: list[int]
    pattern: Optional[str] = None


class BatchMoveBody(BaseModel):
    file_ids: list[int]
    target_dir: str


class BatchDeleteBody(BaseModel):
    file_ids: list[int]


class BatchTagsBody(BaseModel):
    file_ids: list[int]
    tags: list[str]


class CleanBody(BaseModel):
    file_ids: list[int]
    confirm: bool = False


class DupCleanBody(BaseModel):
    group_id: int
    keep_file_id: int
    remove_file_ids: list[int]
    confirm: bool = False


class RestoreBody(BaseModel):
    conflict_strategy: str = 'error'


class ConfirmBody(BaseModel):
    confirm: bool = False


# ═══════════ 仪表盘 ═══════════

@router.get('/dashboard')
def dashboard(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    tdao = TagDAO(db)

    active_count = fdao.count_active()
    all_tags = tdao.get_all_tags() or []
    cls_row = db.execute_one(
        "SELECT COUNT(DISTINCT file_id) AS cnt FROM file_classifications") or {}
    classified_count = cls_row.get('cnt') or 0
    coverage = round(classified_count / active_count * 100, 1) if active_count else 0.0
    recent_row = db.execute_one(
        "SELECT COUNT(*) AS cnt FROM files WHERE status='active' "
        "AND datetime(scan_time) >= datetime('now', '-7 days')") or {}
    unclassified_row = db.execute_one(
        "SELECT COUNT(*) AS cnt FROM files f WHERE f.status='active' "
        "AND NOT EXISTS (SELECT 1 FROM file_classifications c WHERE c.file_id=f.id)") or {}
    unhashed_row = db.execute_one(
        "SELECT COUNT(*) AS cnt FROM files WHERE status='active' "
        "AND file_hash IS NULL") or {}
    activities = db.execute_query(
        "SELECT operation_type, operation_time, operation_status "
        "FROM operation_history ORDER BY operation_time DESC LIMIT 6") or []

    return {
        'active_count': active_count,
        'deleted_count': fdao.count_deleted(),
        'total_size': fdao.get_total_size(),
        'duplicate_groups': fdao.count_duplicate_groups_by_flag(),
        'duplicate_wasted': fdao.get_duplicate_total_wasted_by_flag(),
        'type_stats': fdao.get_type_stats() or [],
        'type_names': FILE_TYPE_NAMES,
        'size_distribution': fdao.get_size_distribution() or [],
        'top_directories': fdao.get_top_directories(10) or [],
        'monthly_trend': fdao.get_monthly_trend() or [],
        'content_indexed': FileContentDAO(db).count(),
        'scan_directories': _serialize(ScanDirectoryDAO(db).get_all() or []),
        'saved_queries': SavedQueryDAO(db).count(),
        # ── 桌面端仪表盘对齐字段 ──
        'classified_count': classified_count,
        'coverage': coverage,
        'tag_count': len(all_tags),
        'tag_hits': sum((t.get('file_count') or 0) for t in all_tags),
        'recent_7d': recent_row.get('cnt') or 0,
        'unclassified_count': unclassified_row.get('cnt') or 0,
        'unhashed_count': unhashed_row.get('cnt') or 0,
        'recent_activities': _serialize(activities),
    }


# ═══════════ 文件检索 / 详情 ═══════════

@router.get('/files')
def file_search(
    name: Optional[str] = None,
    file_type: Optional[str] = None,
    extension: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    is_duplicate: Optional[int] = None,
    tag: Optional[str] = None,
    classification: Optional[str] = None,   # "type:value"
    content: Optional[str] = None,
    page: int = Query(0, ge=0),
    page_size: int = Query(100, ge=1, le=1000),
    x_api_key: Optional[str] = Header(None),
):
    _auth(x_api_key)
    fdao = FileDAO(db)
    tdao = TagDAO(db)
    cdao = ClassificationDAO(db)

    if content:
        rows = FileContentDAO(db).search(content, limit=page_size + page * page_size)
        total = len(rows)
        ids = [r['id'] for r in rows]
        return {
            'total': total, 'page': page, 'page_size': page_size,
            'items': [_brief(r) for r in _paginate(rows, page, page_size)],
            'tags': tdao.get_all_tags_by_file(ids),
            'classifications': _serialize(cdao.get_by_file_ids(ids)),
            'note': 'content 全文检索结果',
        }

    # 标签/分类交集过滤
    id_scope = None
    if tag:
        id_scope = {r['id'] for r in tdao.get_files_by_tag(tag)}
    if classification and ':' in classification:
        ctype, cvalue = classification.split(':', 1)
        cids = {r['file_id'] for r in fdao.get_classification_paginated(
            ctype, cvalue, 0, 10**9)}
        id_scope = cids if id_scope is None else (id_scope & cids)
    if id_scope is not None and not id_scope:
        return {'total': 0, 'page': page, 'page_size': page_size, 'items': [],
                'tags': {}, 'classifications': {}}

    total = fdao.search_count(name=name, file_type=file_type, extension=extension,
                              min_size=min_size, max_size=max_size,
                              start_date=start_date, end_date=end_date,
                              is_duplicate=is_duplicate)
    rows = fdao.search_paginated(page=page, page_size=page_size, name=name,
                                 file_type=file_type, extension=extension,
                                 min_size=min_size, max_size=max_size,
                                 start_date=start_date, end_date=end_date,
                                 is_duplicate=is_duplicate)
    if id_scope is not None:
        rows = [r for r in rows if r['id'] in id_scope]
    ids = [r['id'] for r in rows]
    return {
        'total': total, 'page': page, 'page_size': page_size,
        'items': [_brief(r) for r in rows],
        'tags': tdao.get_all_tags_by_file(ids),
        'classifications': _serialize(cdao.get_by_file_ids(ids)),
    }


def _paginate(items: list, page: int, page_size: int) -> list:
    start = page * page_size
    return items[start:start + page_size]


# 注：GET /api/files/{file_id} 由 server.py 提供（富详情，向后兼容）。


# ═══════════ 文件写操作 ═══════════

@router.post('/files/rename')
def rename_file(body: RenameBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        op_id = FileManager().rename_file(body.file_id, new_name=body.new_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'file_id': body.file_id, 'op_id': op_id}


@router.post('/files/rename/preview')
def rename_preview(body: BatchRenameBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        plan = FileManager().preview_batch_rename(
            body.file_ids, body.pattern or DEFAULT_RENAME_PATTERN)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'items': _serialize(plan)}


@router.post('/files/rename/batch')
def batch_rename(body: BatchRenameBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        batch_id, results = FileManager().batch_rename(
            body.file_ids, body.pattern or DEFAULT_RENAME_PATTERN)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'batch_id': batch_id, **results}


@router.post('/files/move')
def move_file(body: MoveBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        op_id = FileManager().move_file(body.file_id, body.target_dir)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'file_id': body.file_id, 'op_id': op_id}


@router.post('/files/move/preview')
def move_preview(body: BatchMoveBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        plan = FileManager().preview_move(body.file_ids, body.target_dir)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'items': _serialize(plan)}


@router.post('/files/move/batch')
def batch_move(body: BatchMoveBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    import uuid
    batch_id = str(uuid.uuid4())[:8]
    results = {'success': 0, 'failed': 0, 'errors': []}
    fm = FileManager()
    for fid in body.file_ids:
        try:
            fm.move_file(fid, body.target_dir, batch_id=batch_id)
            results['success'] += 1
        except Exception as e:  # noqa: BLE001
            results['failed'] += 1
            results['errors'].append(f'ID {fid}: {e}')
    return {'batch_id': batch_id, **results}


@router.post('/files/delete')
def delete_file(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        op_id = FileManager().delete_file(file_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'file_id': file_id, 'op_id': op_id,
            'message': '文件已移入回收区'}


@router.post('/files/delete/batch')
def batch_delete(body: BatchDeleteBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    import uuid
    batch_id = str(uuid.uuid4())[:8]
    results = {'success': 0, 'failed': 0, 'errors': []}
    fm = FileManager()
    for fid in body.file_ids:
        try:
            fm.delete_file(fid, batch_id=batch_id)
            results['success'] += 1
        except Exception as e:  # noqa: BLE001
            results['failed'] += 1
            results['errors'].append(f'ID {fid}: {e}')
    return {'batch_id': batch_id, **results}


@router.delete('/files/{file_id}')
def permanent_delete(file_id: int, confirm: bool = False,
                     x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    _confirm(confirm, '永久删除不可恢复，需 confirm=true 确认')
    try:
        FileManager().permanent_delete(file_id, confirm=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'message': '已永久删除并移除数据库记录'}


@router.get('/files/{file_id}/restore/preview')
def restore_preview(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        return _serialize(FileManager().get_restore_preview(file_id))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(e))


@router.post('/files/{file_id}/restore')
def restore_file(file_id: int, body: RestoreBody = None,
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    strategy = body.conflict_strategy if body else 'error'
    try:
        path = FileManager().restore_file(file_id, strategy)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'file_path': path}


@router.post('/files/{file_id}/purge')
def purge_file(file_id: int, confirm: bool = False,
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    _confirm(confirm, '从回收区永久删除不可恢复，需 confirm=true 确认')
    try:
        FileManager().purge_file(file_id, confirm=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'message': '已从回收区永久删除'}


# ═══════════ 回收站 ═══════════

@router.get('/recycle')
def recycle(page: int = Query(0, ge=0),
            page_size: int = Query(100, ge=1, le=1000),
            x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    return {
        'total': fdao.count_deleted(),
        'page': page, 'page_size': page_size,
        'items': [_brief(r) for r in fdao.get_deleted_files(page, page_size)],
    }


# ═══════════ 内容索引 ═══════════

@router.get('/content/search')
def content_search(q: str, limit: int = Query(50, ge=1, le=500),
                   x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = FileContentDAO(db).search(q, limit=limit)
    return {'total': len(rows), 'items': [_brief(r) for r in rows]}


@router.post('/content/index/{file_id}')
def content_index_one(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rec = FileDAO(db).get_by_id(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail='文件不存在')
    result = ContentIndexer().index_records([rec])
    return {'success': result.get('indexed', 0) > 0, **result}


@router.post('/content/index/all')
def content_index_all(limit: int = Query(1000, ge=1, le=10000),
                      x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return ContentIndexer().index_active_files(limit=limit)


@router.get('/content/stats')
def content_stats(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'indexed': FileContentDAO(db).count()}


# ═══════════ 去重 ═══════════

@router.get('/duplicates/by-hash')
def duplicates_by_hash(page: int = Query(0, ge=0),
                       page_size: int = Query(50, ge=1, le=500),
                       x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    return {
        'total': fdao.count_duplicate_groups(),
        'wasted_size': fdao.get_duplicate_total_wasted(),
        'page': page, 'page_size': page_size,
        'items': _serialize(fdao.get_duplicate_groups_paginated(page, page_size)),
    }


@router.get('/duplicates')
def duplicates(page: int = Query(0, ge=0),
               page_size: int = Query(50, ge=1, le=500),
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    return {
        'total': fdao.count_duplicate_groups_by_flag(),
        'wasted_size': fdao.get_duplicate_total_wasted_by_flag(),
        'page': page, 'page_size': page_size,
        'items': _serialize(fdao.get_duplicate_groups_paginated_by_flag(
            page, page_size)),
    }


@router.get('/duplicates/{group_id}')
def duplicate_group_files(group_id: int,
                          x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = FileDAO(db).get_duplicate_group_files_by_flag(group_id)
    return {'group_id': group_id, 'files': [_brief(r) for r in rows]}


@router.post('/duplicates/{group_id}/suggest')
def suggest_keep(group_id: int, strategy: str = 'keep_newest',
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    files = FileDAO(db).get_duplicate_group_files_by_flag(group_id)
    if not files:
        raise HTTPException(status_code=404, detail='重复组不存在')
    keep_id, removals = DedupManager().suggest_keep(files, strategy)
    return {'group_id': group_id, 'strategy': strategy,
            'keep_file_id': keep_id,
            'remove_file_ids': [r['id'] for r in removals],
            'remove_total_size': sum(r.get('file_size') or 0 for r in removals)}


@router.post('/duplicates/clean')
def remove_duplicates(body: DupCleanBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    _confirm(body.confirm, '去重清理会把重复文件移入回收区，需 confirm=true 确认')
    message, count = DedupManager().remove_duplicates(
        body.group_id, body.keep_file_id, body.remove_file_ids)
    return {'success': True, 'message': message, 'removed': count}


# ═══════════ 标签 ═══════════

@router.get('/tags/full')
def tags_full(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    tdao = TagDAO(db)
    tags = tdao.get_all_tags() or []
    result = []
    for t in tags:
        result.append({'tag_name': t['tag_name'],
                       'file_count': t['file_count'],
                       'aliases': tdao.get_aliases(t['tag_name'])})
    return {'total': len(result), 'tags': result,
            'tree': _serialize(tdao.get_tag_tree() or [])}


@router.post('/tags')
def create_tag(body: TagBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    TagDAO(db).create_tag(body.tag)
    return {'success': True, 'tag': body.tag.strip()}


@router.delete('/tags/{tag_name}')
def delete_tag(tag_name: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    TagDAO(db).delete_tag(tag_name)
    return {'success': True, 'tag': tag_name}


@router.post('/tags/rename')
def rename_tag(old_name: str, new_name: str,
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        TagDAO(db).rename_tag(old_name, new_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'old': old_name, 'new': new_name}


@router.post('/tags/merge')
def merge_tag(source: str, target: str,
              x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    try:
        n = TagDAO(db).merge_tag(source, target)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'source': source, 'target': target, 'moved': n}


@router.post('/tags/batch-add')
def batch_add_tags(body: BatchTagsBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    n = TagDAO(db).batch_add_tags(body.file_ids, body.tags)
    return {'success': True, 'added': n}


@router.get('/tags/{tag_name}/files')
def files_by_tag(tag_name: str, page: int = Query(0, ge=0),
                 page_size: int = Query(100, ge=1, le=1000),
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    tdao = TagDAO(db)
    return {
        'total': tdao.count_files_by_tag(tag_name),
        'page': page, 'page_size': page_size,
        'items': [_brief(r) for r in tdao.get_files_by_tag_paginated(
            tag_name, page, page_size)],
    }


@router.post('/tags/{tag_name}/parent')
def set_tag_parent(tag_name: str, parent: Optional[str] = None,
                   x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not TagDAO(db).set_parent(tag_name, parent):
        raise HTTPException(status_code=400, detail='设置失败（标签不存在或会形成环）')
    return {'success': True}


@router.post('/tags/{tag_name}/color')
def set_tag_color(tag_name: str, color: Optional[str] = None,
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    TagDAO(db).set_color(tag_name, color)
    return {'success': True}


@router.post('/tags/{tag_name}/aliases')
def add_alias(tag_name: str, alias: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not TagDAO(db).add_alias(alias, tag_name):
        raise HTTPException(status_code=400, detail='别名已被占用')
    return {'success': True}


@router.delete('/tags/aliases/{alias}')
def delete_alias(alias: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    TagDAO(db).delete_alias(alias)
    return {'success': True}


# ═══════════ 分类 ═══════════

@router.get('/classification')
def classification(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = ClassificationDAO(db).get_distinct_values() or []
    grouped = {}
    for r in rows:
        grouped.setdefault(r['classification_type'], []).append({
            'value': r['classification_value'], 'count': r['cnt']})
    return {'types': grouped,
            'rules': _serialize(ClassificationRuleDAO(db).get_all() or [])}


@router.post('/classification/apply-all')
def classify_all(limit: int = Query(0, ge=0),
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    cdao = ClassificationDAO(db)
    classifier = FileClassifier()
    files = fdao.get_all_active()
    if limit > 0:
        files = files[:limit]
    stats = {'classified': 0, 'failed': 0, 'errors': []}
    for rec in files:
        try:
            # 内存分类不落库，由这里统一重建（先清旧再批量插入）
            result = classifier._classify_file_in_memory(rec)
            if result:
                cdao.delete_by_file_id(rec['id'])
                cdao.batch_insert(
                    [(rec['id'], t, v, conf) for t, v, conf in result])
                stats['classified'] += 1
        except Exception as e:  # noqa: BLE001
            stats['failed'] += 1
            if len(stats['errors']) < 10:
                stats['errors'].append(f'{rec.get("file_path")}: {e}')
    return {'total': len(files), **stats}


@router.post('/classification/rules')
def create_rule(rule_name: str, rule_type: str, rule_pattern: str,
                target_category: str, priority: int = 0,
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rid = ClassificationRuleDAO(db).insert(
        rule_name, rule_type, rule_pattern, target_category, priority)
    return {'success': True, 'id': rid}


@router.put('/classification/rules/{rule_id}')
def update_rule(rule_id: int, rule_name: str, rule_type: str,
                rule_pattern: str, target_category: str, priority: int = 0,
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ClassificationRuleDAO(db).update(
        rule_id, rule_name, rule_type, rule_pattern, target_category, priority)
    return {'success': True}


@router.post('/classification/rules/{rule_id}/toggle')
def toggle_rule(rule_id: int, enabled: bool = True,
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ClassificationRuleDAO(db).toggle_enabled(rule_id, enabled)
    return {'success': True}


@router.delete('/classification/rules/{rule_id}')
def delete_rule(rule_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ClassificationRuleDAO(db).delete(rule_id)
    return {'success': True}


# ═══════════ 生命周期 ═══════════

@router.get('/lifecycle/policies')
def lifecycle_policies(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(LifecyclePolicyDAO(db).get_all() or [])}


@router.post('/lifecycle/policies')
def create_policy(name: str, target_type: str, target_value: str,
                  days_threshold: int = 30, action: str = 'remind',
                  archive_dir: Optional[str] = None, enabled: bool = True,
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    pid = LifecyclePolicyDAO(db).create(
        name, target_type, target_value, days_threshold, action, archive_dir,
        enabled)
    return {'success': True, 'id': pid}


@router.put('/lifecycle/policies/{policy_id}')
def update_policy(policy_id: int, body: dict,
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    allowed = {'name', 'target_type', 'target_value', 'days_threshold',
               'action', 'archive_dir', 'enabled'}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail='没有可更新的字段')
    if 'enabled' in update:
        update['enabled'] = int(bool(update['enabled']))
    LifecyclePolicyDAO(db).update(policy_id, **update)
    return {'success': True}


@router.delete('/lifecycle/policies/{policy_id}')
def delete_policy(policy_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    LifecyclePolicyDAO(db).delete(policy_id)
    return {'success': True}


# ═══════════ 清理中心 ═══════════

@router.get('/cleanup/analyze')
def cleanup_analyze(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    result = CleanupCenter().analyze()
    counts = {}
    items = []
    for k, v in result.items():
        counts[k] = len(v)
        for i in v:
            items.append({'file_id': i['file_id'], 'file_path': i['file_path'],
                          'file_name': i['file_name'], 'file_size': i['file_size'],
                          'category': i['category'], 'reason': i['reason']})
    return {'counts': counts, 'items': items}


@router.post('/cleanup/execute')
def cleanup_execute(body: CleanBody, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    _confirm(body.confirm, '清理执行会把文件移入回收区，需 confirm=true 确认')
    if not body.file_ids:
        raise HTTPException(status_code=400, detail='file_ids 不能为空')
    fdao = FileDAO(db)
    items = []
    for fid in body.file_ids:
        rec = fdao.get_by_id(fid)
        if rec:
            items.append({'file_id': fid, 'file_path': rec['file_path'],
                          'file_name': rec['file_name'],
                          'file_size': rec['file_size'],
                          'category': 'manual', 'reason': 'Web 手动清理',
                          'record': rec})
    if not items:
        raise HTTPException(status_code=404, detail='没有可清理的文件')
    return {'success': True, **CleanupCenter().execute_cleanup(items)}


@router.get('/cleanup/exclusions')
def cleanup_exclusions(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(CleanupCenter().list_exclusions() or [])}


@router.post('/cleanup/exclusions')
def add_exclusion(path_pattern: str, reason: str = '',
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    CleanupCenter().add_exclusion(path_pattern, reason)
    return {'success': True}


@router.delete('/cleanup/exclusions')
def remove_exclusion(path_pattern: str,
                     x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    CleanupCenter().remove_exclusion(path_pattern)
    return {'success': True}


@router.get('/cleanup/false-positives')
def cleanup_false_positives(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = db.execute_query(
        "SELECT * FROM cleanup_false_positives ORDER BY create_time DESC")
    return {'items': _serialize(rows)}


@router.post('/cleanup/false-positives')
def mark_false_positive(file_path: str, reason: str = '',
                        x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    CleanupCenter().mark_false_positive(file_path, reason)
    return {'success': True}


@router.delete('/cleanup/false-positives')
def remove_false_positive(file_path: str,
                          x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    CleanupCenter().remove_false_positive(file_path)
    return {'success': True}


# ═══════════ 生命周期执行 ═══════════

@router.get('/lifecycle/check')
def lifecycle_check(enabled_only: bool = True,
                    x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    results = LifecycleService().check_all(enabled_only=enabled_only)
    return {'policies': _serialize(results)}


@router.post('/lifecycle/run/{policy_id}')
def lifecycle_run(policy_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    svc = LifecycleService()
    policy = LifecyclePolicyDAO(db).get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail='策略不存在')
    matches = svc.match_files(policy)
    if not matches:
        return {'success': True, 'message': '没有命中文件', 'match_count': 0,
                'action': policy.get('action')}
    result = svc.execute(policy, matches)
    return {'success': True, 'match_count': len(matches), **result}


# ═══════════ 时间线 ═══════════

@router.get('/timeline')
def timeline(mode: str = Query('all', pattern='^(all|operations|external)$'),
             op_type: Optional[str] = None,
             start_date: Optional[str] = None,
             end_date: Optional[str] = None,
             path_prefix: Optional[str] = None,
             limit: int = Query(200, ge=1, le=2000),
             x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = TimelineDAO().get_combined(
        mode=mode, op_type=op_type, start_date=start_date,
        end_date=end_date, path_prefix=path_prefix, limit=limit)
    return {'total': len(rows), 'items': _serialize(rows)}


# ═══════════ 索引健康 ═══════════

@router.get('/health/index')
def index_health(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    report = IndexHealthService().inspect()
    return _serialize(report)


@router.post('/health/index/repair')
def index_repair(confirm: bool = False,
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    _confirm(confirm, '修复会删除磁盘上已不存在的记录，需 confirm=true 确认')
    report = IndexHealthService().inspect()
    result = IndexHealthService().repair(report)
    return {'success': True, **result}


# ═══════════ 扫描目录管理 ═══════════

@router.get('/scan/directories')
def scan_directories(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(ScanDirectoryDAO(db).get_all() or [])}


@router.post('/scan/directories')
def add_scan_directory(directory: str, recursive: bool = True,
                       x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    sdao = ScanDirectoryDAO(db)
    if sdao.exists(directory):
        return {'success': True, 'message': '目录已存在', 'id': None}
    did = sdao.insert(directory, recursive)
    return {'success': True, 'id': did}


@router.post('/scan/directories/{dir_id}/toggle')
def toggle_scan_directory(dir_id: int, active: bool = True,
                          x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ScanDirectoryDAO(db).toggle_active(dir_id, active)
    return {'success': True}


@router.delete('/scan/directories/{dir_id}')
def delete_scan_directory(dir_id: int,
                          x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ScanDirectoryDAO(db).delete(dir_id)
    return {'success': True}


# ═══════════ 智能集合（已保存搜索） ═══════════

@router.get('/saved-queries')
def saved_queries(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(SavedQueryDAO(db).get_all() or [])}


@router.post('/saved-queries')
def save_query(name: str, params: dict,
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    qid = SavedQueryDAO(db).upsert(name, params)
    return {'success': True, 'id': qid}


@router.get('/saved-queries/{name}/run')
def run_saved_query(name: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    q = SavedQueryDAO(db).get_by_name(name)
    if not q:
        raise HTTPException(status_code=404, detail='集合不存在')
    params = q.get('params') or {}
    fdao = FileDAO(db)
    rows = fdao.search(**{k: v for k, v in params.items()
                          if k in ('name', 'file_type', 'extension',
                                   'min_size', 'max_size', 'start_date',
                                   'end_date', 'is_duplicate')})
    return {'total': len(rows), 'items': [_brief(r) for r in rows]}


@router.delete('/saved-queries/{name}')
def delete_saved_query(name: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    SavedQueryDAO(db).delete(name)
    return {'success': True}


# ═══════════ 操作历史与撤销 ═══════════

@router.get('/history')
def operation_history(op_type: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      batch_id: Optional[str] = None,
                      limit: int = Query(200, ge=1, le=2000),
                      x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = OperationHistoryDAO(db).search(
        op_type=op_type, start_date=start_date, end_date=end_date,
        batch_id=batch_id, limit=limit)
    return {'total': len(rows), 'items': _serialize(rows)}


@router.get('/history/undoable')
def undoable_operations(limit: int = Query(100, ge=1, le=1000),
                        x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = OperationHistoryManager().get_undoable_operations(limit)
    return {'items': _serialize(rows)}


@router.post('/history/{op_id}/undo')
def undo_operation(op_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not OperationHistoryManager().undo_operation(op_id):
        raise HTTPException(status_code=400, detail='撤销失败（记录不存在或不可撤销）')
    return {'success': True, 'op_id': op_id}


@router.post('/history/batch/{batch_id}/undo')
def undo_batch(batch_id: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    result = OperationHistoryManager().undo_batch(batch_id)
    return {'success': result.get('ok', False), **result}


# ═══════════ 工作区 ═══════════

@router.get('/workspaces')
def workspaces(only_active: bool = False,
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(WorkspaceDAO().get_all(only_active))}


@router.post('/workspaces')
def create_workspace(name: str, root_path: str, description: str = '',
                     rule_scope: str = 'all', tag_scope: str = 'all',
                     ai_allowed: bool = True,
                     x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    wid = WorkspaceDAO().create(name, root_path, description, rule_scope,
                                tag_scope, ai_allowed)
    return {'success': True, 'id': wid}


@router.put('/workspaces/{ws_id}')
def update_workspace(ws_id: int, body: dict,
                     x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    allowed = {'name', 'root_path', 'description', 'rule_scope', 'tag_scope',
               'ai_allowed', 'is_active'}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail='没有可更新的字段')
    WorkspaceDAO().update(ws_id, **update)
    return {'success': True}


@router.delete('/workspaces/{ws_id}')
def delete_workspace(ws_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    WorkspaceDAO().delete(ws_id)
    return {'success': True}


# ═══════════ 归档包 ═══════════

@router.get('/archives')
def archives(status: Optional[str] = None,
             x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(ArchiveService().list_packages(status))}


@router.post('/archives')
def create_archive(package_name: str, output_dir: str,
                   source_paths: list[str] = None,
                   file_ids: list[int] = None,
                   x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not source_paths and not file_ids:
        raise HTTPException(status_code=400,
                            detail='需要 source_paths 或 file_ids 之一')
    paths = list(source_paths or [])
    if file_ids:
        fdao = FileDAO(db)
        for fid in file_ids:
            rec = fdao.get_by_id(fid)
            if rec and rec.get('file_path'):
                paths.append(rec['file_path'])
    try:
        pkg = ArchiveService().create_package(
            paths, output_dir, package_name=package_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {'success': True, 'package': _serialize(pkg)}


@router.post('/archives/{pkg_id}/status')
def update_archive_status(pkg_id: int, status: str,
                          x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ArchivePackageDAO().update_status(pkg_id, status)
    return {'success': True}


@router.delete('/archives/{pkg_id}')
def delete_archive(pkg_id: int, delete_file: bool = False,
                   x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ArchiveService().delete_package(pkg_id, delete_file=delete_file)
    return {'success': True}


# ═══════════ 版本关系 ═══════════

@router.get('/relations')
def relations(status: str = Query('pending', pattern='^(pending|confirmed|dismissed)$'),
              x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(VersionRelationDAO().get_by_status(status))}


@router.post('/relations/{relation_id}/status')
def relation_status(relation_id: int, status: str,
                    x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    VersionRelationDAO().set_status(relation_id, status)
    return {'success': True}


@router.delete('/relations/{relation_id}')
def delete_relation(relation_id: int,
                    x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    VersionRelationDAO().remove(relation_id)
    return {'success': True}


# ═══════════ 系统设置 ═══════════

@router.get('/settings')
def settings(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return {'items': _serialize(SystemSettingsDAO(db).get_all() or [])}


@router.post('/settings')
def set_setting(key: str, value: str, setting_type: str = 'string',
                description: Optional[str] = None,
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    SystemSettingsDAO(db).set(key, value, setting_type, description)
    return {'success': True}


@router.delete('/settings/{key}')
def delete_setting(key: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    db.execute_update("DELETE FROM system_settings WHERE setting_key = ?", (key,))
    return {'success': True}


# ═══════════ 文件事件 ═══════════

@router.get('/events')
def file_events(event_type: Optional[str] = None,
                start_date: Optional[str] = None,
                end_date: Optional[str] = None,
                path_prefix: Optional[str] = None,
                limit: int = Query(200, ge=1, le=2000),
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rows = FileEventDAO().search(event_type=event_type, start_date=start_date,
                                 end_date=end_date, path_prefix=path_prefix,
                                 limit=limit)
    return {'total': len(rows), 'items': _serialize(rows)}


@router.delete('/events/older-than/{days}')
def delete_old_events(days: int = 90,
                      x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    n = FileEventDAO().delete_older_than(days)
    return {'success': True, 'deleted': n}


# ═══════════ 分类目录分布（浏览） ═══════════

@router.get('/classification/{cls_type}/{cls_value}/files')
def classification_files(cls_type: str, cls_value: str,
                         page: int = Query(0, ge=0),
                         page_size: int = Query(100, ge=1, le=1000),
                         x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    rows = fdao.get_classification_paginated(cls_type, cls_value, page, page_size)
    return {
        'total': fdao.count_by_classification(cls_type, cls_value),
        'page': page, 'page_size': page_size,
        'items': [_brief(r) for r in rows],
    }


# ═══════════ AI 能力 ═══════════

def _ai_layer():
    """懒加载 AILayer（AI 后端依赖配置，失败返回 None 时降级为规则提示）。"""
    try:
        from core.ai_layer import AILayer
        return AILayer()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f'AI 层不可用: {e}')


def _fmt_size(n) -> str:
    """人类可读大小（与桌面端 format_size 语义一致，供 AI 提示词使用）。"""
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


@router.get('/ai/insights')
def ai_insights(x_api_key: Optional[str] = Header(None)):
    """仪表盘 AI 文件洞察（对齐桌面端 generate_dashboard_insights）。"""
    _auth(x_api_key)
    layer = _ai_layer()
    if not getattr(layer, 'enabled', False):
        return {'enabled': False, 'insight': None}
    fdao = FileDAO(db)
    type_stats = fdao.get_type_stats() or []
    monthly = fdao.get_monthly_trend() or []
    top_dirs = fdao.get_top_directories(3) or []
    type_dist = ', '.join(
        f"{FILE_TYPE_NAMES.get(r.get('file_type'), r.get('file_type'))} {r.get('count')}个"
        for r in type_stats[:5])
    monthly_text = ', '.join(
        f"{r.get('month', '')}:{r.get('count', 0)}个" for r in monthly[-6:])
    top_dirs_text = ', '.join(
        f"{r.get('dir_path', '')}:{_fmt_size(r.get('total_size'))}" for r in top_dirs[:3])
    try:
        insight = layer.generate_dashboard_insights(
            total_files=fdao.count_active(),
            total_size=_fmt_size(fdao.get_total_size()),
            dup_groups=fdao.count_duplicate_groups_by_flag(),
            wasted=_fmt_size(fdao.get_duplicate_total_wasted_by_flag()),
            type_distribution=type_dist,
            top_dirs=top_dirs_text,
            monthly_trend=monthly_text,
        )
    except Exception as e:  # noqa: BLE001
        return {'enabled': True, 'insight': None, 'error': str(e)}
    return {'enabled': True, 'insight': insight}


# ═══════════ AI 模型配置（Web 设置页） ═══════════

class AIProviderBody(BaseModel):
    provider_id: str
    name: str = ''
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    models: str = ''
    timeout: float = 60.0


def _mask_key(k: str) -> str:
    """API Key 掩码：仅保留首尾各 4 位，避免明文回传浏览器。"""
    k = k or ''
    if len(k) <= 8:
        return '*' * len(k)
    return k[:4] + '*' * (len(k) - 8) + k[-4:]


def _reload_ai() -> bool:
    """配置变更后重载 AILayer 单例后端，使新配置对后续请求立即生效。"""
    try:
        from core.ai_layer import AILayer
        AILayer().reload_backend()
        return True
    except Exception:  # noqa: BLE001
        return False


@router.get('/ai/providers')
def ai_providers(x_api_key: Optional[str] = Header(None)):
    """列出 AI 提供商（api_key 掩码）与内置模板。"""
    _auth(x_api_key)
    from core.ai_model_config import AIModelConfigManager, BUILTIN_PROVIDERS
    mgr = AIModelConfigManager()
    active = mgr.active_provider_id
    items = []
    for p in mgr.list_providers():
        d = p.to_dict()
        d['has_key'] = bool(d.get('api_key'))
        d['api_key'] = _mask_key(d.get('api_key'))
        d['active'] = (p.provider_id == active)
        items.append(d)
    return {
        'active_provider': active,
        'providers': items,
        'templates': [
            {'provider_id': k, 'name': v['name'], 'base_url': v['base_url'],
             'models': v.get('models', ''),
             'default_model': v.get('default_model', ''),
             'timeout': v.get('timeout', 60)}
            for k, v in BUILTIN_PROVIDERS.items()
        ],
    }


@router.post('/ai/providers')
def ai_provider_save(body: AIProviderBody,
                     x_api_key: Optional[str] = Header(None)):
    """新增 / 更新 AI 提供商。api_key 为空或等于掩码值时沿用已存密钥。"""
    _auth(x_api_key)
    from core.ai_model_config import AIModelConfigManager, AIModelProvider
    pid = (body.provider_id or '').strip()
    if not pid:
        raise HTTPException(status_code=400, detail='provider_id 不能为空')
    mgr = AIModelConfigManager()
    old = mgr.get_provider(pid)
    api_key = body.api_key or ''
    if old and (not api_key or api_key == _mask_key(old.api_key)):
        api_key = old.api_key
    ok = mgr.add_provider(AIModelProvider(
        provider_id=pid,
        name=body.name or pid,
        base_url=body.base_url,
        api_key=api_key,
        model=body.model,
        models=body.models,
        timeout=body.timeout or 60.0,
    ))
    if not ok:
        raise HTTPException(status_code=400, detail='保存失败')
    return {'success': True, 'reloaded': _reload_ai()}


@router.delete('/ai/providers/{provider_id}')
def ai_provider_delete(provider_id: str,
                       x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    from core.ai_model_config import AIModelConfigManager
    if not AIModelConfigManager().delete_provider(provider_id):
        raise HTTPException(status_code=404, detail='提供商不存在')
    return {'success': True, 'reloaded': _reload_ai()}


@router.post('/ai/providers/{provider_id}/activate')
def ai_provider_activate(provider_id: str,
                         x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    from core.ai_model_config import AIModelConfigManager
    if not AIModelConfigManager().set_active(provider_id):
        raise HTTPException(status_code=404, detail='提供商不存在')
    return {'success': True, 'active_provider': provider_id,
            'reloaded': _reload_ai()}


@router.post('/ai/providers/{provider_id}/test')
def ai_provider_test(provider_id: str,
                     x_api_key: Optional[str] = Header(None)):
    """测试提供商连通性（真实发送一条极短请求）。"""
    _auth(x_api_key)
    from core.ai_model_config import AIModelConfigManager
    from core.ai_backends import OpenAICompatibleBackend
    p = AIModelConfigManager().get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail='提供商不存在')
    if not p.api_key:
        return {'success': False, 'error': '未配置 API Key'}
    try:
        backend = OpenAICompatibleBackend(
            api_key=p.api_key, base_url=p.base_url, model=p.model,
            timeout=min(p.timeout or 20, 30))
        r = backend.chat([{'role': 'user', 'content': 'ping'}], max_tokens=16)
        return {'success': True, 'model': r.model,
                'reply': (r.content or '')[:100], 'latency_ms': r.latency_ms}
    except Exception as e:  # noqa: BLE001
        return {'success': False, 'error': str(e)[:300]}


@router.get('/ai/status')
def ai_status(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    from core.ai_layer import AILayer
    layer = AILayer()
    backend = getattr(layer, '_backend', None)
    model = getattr(backend, 'model', None) if backend else None
    backend_type = 'local' if backend and backend.__class__.__name__.lower().startswith('ollama') else 'cloud'
    return {
        'enabled': backend is not None,
        'backend': backend.__class__.__name__ if backend else None,
        'backend_type': backend_type,
        'model': model,
    }


@router.post('/ai/describe')
def ai_describe(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rec = FileDAO(db).get_by_id(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail='文件不存在')
    layer = _ai_layer()
    description = layer.describe_file(rec)
    return {'success': True, 'description': description}


@router.post('/ai/question')
def ai_question(summary: str, question: str,
                x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    layer = _ai_layer()
    answer = layer.answer_question(summary, question)
    return {'success': True, 'answer': answer}


@router.post('/ai/summarize')
def ai_summarize(search_query: str, file_ids: list[int],
                 x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    fdao = FileDAO(db)
    files = [r for r in (fdao.get_by_id(fid) for fid in file_ids) if r]
    layer = _ai_layer()
    summary = layer.summarize_results(search_query, files, len(files))
    return {'success': True, 'summary': summary}


@router.post('/ai/explain')
def ai_explain(query: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    layer = _ai_layer()
    explanation = layer.explain_search_intent(query)
    return {'success': True, 'explanation': explanation}


@router.post('/ai/chat')
def ai_chat(message: str, x_api_key: Optional[str] = Header(None)):
    """单轮 AI 助手：解析意图 → 执行搜索 → 生成摘要。"""
    _auth(x_api_key)
    try:
        from core.ai_chat import AiConversation
        from utils.logger import logger as _log
        _log.info('web ai_chat: %s', message)
    except Exception:  # noqa: BLE001
        pass
    # 复用搜索页的 AI 解析链路：先按关键词搜索，再让 AI 解释意图
    fdao = FileDAO(db)
    rows = (fdao.search(name=message) or [])[:20]
    layer = _ai_layer()
    summary = layer.summarize_results(message, rows, len(rows))
    return {'success': True, 'matches': len(rows), 'summary': summary}


class ChatStreamBody(BaseModel):
    message: str


def _sse(obj: dict) -> str:
    """SSE 事件编码（data: <json>\\n\\n）。"""
    return 'data: ' + json.dumps(obj, ensure_ascii=False) + '\n\n'


@router.post('/ai/chat/stream')
def ai_chat_stream(body: ChatStreamBody,
                   x_api_key: Optional[str] = Header(None)):
    """AI 助手流式对话（SSE）：先检索匹配文件，再作为上下文流式生成回答。"""
    _auth(x_api_key)
    message = (body.message or '').strip()

    def gen():
        try:
            fdao = FileDAO(db)
            rows = (fdao.search(name=message) or [])[:20]
            yield _sse({'type': 'meta', 'matches': len(rows)})

            layer = _ai_layer()
            if not getattr(layer, 'enabled', False):
                yield _sse({'type': 'error', 'message': 'AI 未启用（未配置后端模型）'})
                return

            files_text = '\n'.join(
                f"- {r.get('file_name')} | {_fmt_size(r.get('file_size'))} | {r.get('file_path')}"
                for r in rows[:10]) or '（未匹配到文件）'
            messages = [
                {'role': 'system',
                 'content': '你是「智能文件管家」AI 助手。请基于用户索引库中的文件回答，'
                            '使用简体中文、简洁分点，不要编造不存在的文件。'},
                {'role': 'user',
                 'content': f'用户问题：{message}\n\n'
                            f'当前索引库中匹配到的文件（最多 10 条）：\n{files_text}'},
            ]
            for chunk in layer.chat_stream(messages=messages, max_tokens=800,
                                           temperature=0.3):
                delta = getattr(chunk, 'content_delta', None)
                if delta:
                    yield _sse({'type': 'delta', 'text': delta})
        except Exception as e:  # noqa: BLE001
            yield _sse({'type': 'error', 'message': str(e)})
            return
        yield _sse({'type': 'done'})

    return StreamingResponse(
        gen(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.get('/tags/{tag_name}/stats')
def tag_stats(tag_name: str, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    tdao = TagDAO(db)
    row = db.execute_one(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(f.file_size), 0) AS size "
        "FROM file_tags ft JOIN files f ON f.id = ft.file_id "
        "WHERE ft.tag_name = ? AND f.status = 'active'", (tag_name,))
    return {'tag': tag_name,
            'file_count': tdao.count_files_by_tag(tag_name),
            'total_size': row.get('size', 0) if row else 0}
