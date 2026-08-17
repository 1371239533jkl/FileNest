"""
数据访问对象 - 封装各表CRUD操作
ponytail: 全部 %s→? 参数占位符、MySQL 特有语法翻译为 SQLite、FTS5 全文搜索集成。
"""
from datetime import datetime
from collections import defaultdict
import re
from typing import Optional, Any


class FileDAO:
    """文件表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_info: dict) -> int:
        """插入或更新文件记录。如果 file_path 已存在，则更新并重新激活为 active。"""
        sql = """INSERT INTO files
            (file_path, file_name, original_name, file_extension, file_type,
             file_size, file_hash, create_time, modify_time, scan_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
            file_name=excluded.file_name,
            original_name=excluded.original_name,
            file_extension=excluded.file_extension,
            file_type=excluded.file_type,
            file_size=excluded.file_size,
            file_hash=COALESCE(excluded.file_hash, file_hash),
            modify_time=excluded.modify_time,
            scan_time=excluded.scan_time,
            status='active'"""
        return self.db.execute_insert(sql, (
            file_info['file_path'], file_info['file_name'],
            file_info.get('original_name'), file_info['file_extension'],
            file_info['file_type'], file_info['file_size'],
            file_info.get('file_hash'), file_info.get('create_time'),
            file_info.get('modify_time'), datetime.now(), 'active'
        ))

    def get_by_id(self, file_id: int) -> Optional[dict]:
        return self.db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))

    def get_by_path(self, file_path: str) -> Optional[dict]:
        return self.db.execute_one(
            "SELECT * FROM files WHERE file_path = ? AND status = 'active'", (file_path,))

    def get_by_hash(self, file_hash: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM files WHERE file_hash = ? AND status = 'active'", (file_hash,))

    def get_by_directory(self, directory: str) -> list:
        normalized = directory.rstrip('/\\').replace('\\', '/')
        escaped = normalized.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        return self.db.execute_query(
            """SELECT * FROM files WHERE status = 'active'
               AND (REPLACE(file_path, '\\', '/') = ?
                    OR REPLACE(file_path, '\\', '/') LIKE ? ESCAPE '\\')""",
            (normalized, escaped + '/%',))

    def get_all_active(self) -> list:
        return self.db.execute_query(
            "SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC")

    def get_all_active_paginated(self, page: int = 0, page_size: int = 500) -> list:
        offset = page * page_size
        sql = "SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC LIMIT ? OFFSET ?"
        return self.db.execute_query(sql, (page_size, offset))

    def update_name(self, file_id: int, new_name: str, new_path: str) -> int:
        sql = "UPDATE files SET file_name = ?, file_path = ? WHERE id = ?"
        return self.db.execute_update(sql, (new_name, new_path, file_id))

    def update_hash(self, file_id: int, file_hash: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET file_hash = ? WHERE id = ?", (file_hash, file_id))

    def get_content_fingerprint(self, file_id: int) -> Optional[str]:
        row = self.db.execute_one(
            "SELECT content_fingerprint FROM files WHERE id = ?", (file_id,))
        return row['content_fingerprint'] if row else None

    def update_content_fingerprint(self, file_id: int, fingerprint: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET content_fingerprint = ? WHERE id = ?",
            (fingerprint, file_id))

    def update_duplicate(self, file_id: int, is_duplicate: int, group_id: int) -> int:
        return self.db.execute_update(
            "UPDATE files SET is_duplicate = ?, duplicate_group_id = ? WHERE id = ?",
            (is_duplicate, group_id, file_id))

    def update_status(self, file_id: int, status: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET status = ? WHERE id = ?", (status, file_id))

    def delete_record(self, file_id: int) -> int:
        """从数据库中彻底删除文件记录（包括关联的元数据、分类、历史记录）"""
        self.db.execute_update("DELETE FROM file_metadata WHERE file_id = ?", (file_id,))
        self.db.execute_update("DELETE FROM file_classifications WHERE file_id = ?", (file_id,))
        self.db.execute_update("DELETE FROM operation_history WHERE file_id = ?", (file_id,))
        self.db.execute_update("DELETE FROM file_content_fts WHERE file_id = ?", (str(file_id),))
        return self.db.execute_update("DELETE FROM files WHERE id = ?", (file_id,))


    def _build_search_conditions(self, name=None, file_type=None, extension=None,
                                  min_size=None, max_size=None, start_date=None,
                                  end_date=None, is_duplicate=None):
        """构建搜索条件（供 search/search_paginated/search_count 复用）。
        返回 (where_clause, params, use_fts) — use_fts 表示是否需要 JOIN files_fts。"""
        conditions = ["f.status = 'active'"]
        params = []
        use_fts = False

        if name:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", name)
            if tokens:
                use_fts = True
                conditions.append("files_fts MATCH ?")
                params.append(" AND ".join(f'"{token}"*' for token in tokens[:10]))
        if file_type:
            conditions.append("f.file_type = ?")
            params.append(file_type)
        if extension:
            conditions.append("f.file_extension = ?")
            params.append(extension)
        if min_size is not None:
            conditions.append("f.file_size >= ?")
            params.append(min_size)
        if max_size is not None:
            conditions.append("f.file_size <= ?")
            params.append(max_size)
        if start_date:
            conditions.append("f.modify_time >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("f.modify_time <= ?")
            params.append(end_date)
        if is_duplicate is not None:
            conditions.append("f.is_duplicate = ?")
            params.append(is_duplicate)
        return " AND ".join(conditions), params, use_fts

    def search(self, name: Optional[str] = None, file_type: Optional[str] = None,
               extension: Optional[str] = None, min_size: Optional[int] = None,
               max_size: Optional[int] = None, start_date: Optional[str] = None,
               end_date: Optional[str] = None,
               is_duplicate: Optional[int] = None) -> list:
        where, params, use_fts = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        if use_fts:
            sql = f"SELECT f.* FROM files f JOIN files_fts ft ON f.id = ft.rowid WHERE {where} ORDER BY rank"
        else:
            sql = f"SELECT f.* FROM files f WHERE {where} ORDER BY f.modify_time DESC"
        return self.db.execute_query(sql, tuple(params))

    def search_paginated(self, page: int = 0, page_size: int = 100,
                         name=None, file_type=None, extension=None,
                         min_size=None, max_size=None, start_date=None,
                         end_date=None, is_duplicate=None) -> list:
        where, params, use_fts = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        offset = page * page_size
        if use_fts:
            sql = f"SELECT f.* FROM files f JOIN files_fts ft ON f.id = ft.rowid WHERE {where} ORDER BY rank LIMIT ? OFFSET ?"
        else:
            sql = f"SELECT f.* FROM files f WHERE {where} ORDER BY f.modify_time DESC LIMIT ? OFFSET ?"
        params.append(page_size)
        params.append(offset)
        return self.db.execute_query(sql, tuple(params))

    def search_count(self, name=None, file_type=None, extension=None,
                     min_size=None, max_size=None, start_date=None,
                     end_date=None, is_duplicate=None) -> int:
        where, params, use_fts = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        if use_fts:
            sql = f"SELECT COUNT(*) as total FROM files f JOIN files_fts ft ON f.id = ft.rowid WHERE {where}"
        else:
            sql = f"SELECT COUNT(*) as total FROM files f WHERE {where}"
        row = self.db.execute_one(sql, tuple(params))
        return row['total'] if row else 0

    def get_duplicates(self) -> list:
        sql = """SELECT file_hash, COUNT(*) as cnt
                 FROM files WHERE file_hash IS NOT NULL AND status = 'active'
                 GROUP BY file_hash HAVING cnt > 1"""
        return self.db.execute_query(sql)

    def get_all_duplicates(self) -> list:
        sql = """SELECT f.* FROM files f
                 INNER JOIN (
                     SELECT file_hash FROM files
                     WHERE file_hash IS NOT NULL AND status = 'active'
                     GROUP BY file_hash HAVING COUNT(*) > 1
                 ) d ON f.file_hash = d.file_hash
                 WHERE f.status = 'active'
                 ORDER BY f.file_hash"""
        return self.db.execute_query(sql)

    def get_type_stats(self) -> list:
        sql = """SELECT file_type, COUNT(*) as count, SUM(file_size) as total_size
                 FROM files WHERE status = 'active'
                 GROUP BY file_type ORDER BY count DESC"""
        return self.db.execute_query(sql)

    def get_deleted_files(self, page: int = 0, page_size: int = 100) -> list:
        offset = page * page_size
        sql = """SELECT * FROM files WHERE status = 'deleted'
                 ORDER BY scan_time DESC LIMIT ? OFFSET ?"""
        return self.db.execute_query(sql, (page_size, offset))

    def count_deleted(self) -> int:
        row = self.db.execute_one(
            "SELECT COUNT(*) as total FROM files WHERE status = 'deleted'")
        return row['total'] if row else 0

    def count_active(self) -> int:
        row = self.db.execute_one(
            "SELECT COUNT(*) as total FROM files WHERE status = 'active'")
        return row['total'] if row else 0

    def get_classification_paginated(self, cls_type: str, cls_value: str,
                                     page: int = 0, page_size: int = 100) -> list:
        offset = page * page_size
        sql = """SELECT f.* FROM files f
                 JOIN file_classifications c ON f.id = c.file_id
                 WHERE c.classification_type = ? AND c.classification_value = ?
                 AND f.status = 'active'
                 ORDER BY f.scan_time DESC LIMIT ? OFFSET ?"""
        return self.db.execute_query(sql, (cls_type, cls_value, page_size, offset))

    def count_by_classification(self, cls_type: str, cls_value: str) -> int:
        sql = """SELECT COUNT(*) as total FROM files f
                 JOIN file_classifications c ON f.id = c.file_id
                 WHERE c.classification_type = ? AND c.classification_value = ?
                 AND f.status = 'active'"""
        row = self.db.execute_one(sql, (cls_type, cls_value))
        return row['total'] if row else 0

    # ── 磁盘分析 DAO ──

    def get_total_size(self) -> int:
        row = self.db.execute_one(
            "SELECT COALESCE(SUM(file_size), 0) as total FROM files WHERE status = 'active'")
        return row['total'] if row else 0

    def get_size_distribution(self) -> list:
        sql = """SELECT
            CASE
                WHEN file_size < 1024 THEN '0-1KB'
                WHEN file_size < 1048576 THEN '1KB-1MB'
                WHEN file_size < 104857600 THEN '1MB-100MB'
                WHEN file_size < 1073741824 THEN '100MB-1GB'
                ELSE '>1GB'
            END as size_range,
            COUNT(*) as count
            FROM files WHERE status = 'active'
            GROUP BY size_range
            ORDER BY CASE size_range
                WHEN '0-1KB' THEN 1
                WHEN '1KB-1MB' THEN 2
                WHEN '1MB-100MB' THEN 3
                WHEN '100MB-1GB' THEN 4
                ELSE 5
            END"""
        return self.db.execute_query(sql)

    def get_top_directories(self, limit: int = 10) -> list:
        """按文件实际父目录统计总大小（取 Top N）。"""
        rows = self.db.execute_query(
            "SELECT file_path, file_size FROM files WHERE status = 'active'")
        dir_stats = defaultdict(lambda: {'count': 0, 'total_size': 0})
        for row in rows:
            # Do not aggregate by a fixed path depth: Windows user paths share
            # a long prefix, which otherwise hides the directories consuming space.
            normalized = (row.get('file_path') or '').replace('\\', '/').rstrip('/')
            dir_path = normalized.rsplit('/', 1)[0] if '/' in normalized else '根目录'
            if not dir_path:
                dir_path = '根目录'
            dir_stats[dir_path]['count'] += 1
            dir_stats[dir_path]['total_size'] += (row['file_size'] or 0)
        result = sorted(
            dir_stats.items(), key=lambda x: x[1]['total_size'], reverse=True)[:limit]
        return [{'dir_path': k, 'file_count': v['count'], 'total_size': v['total_size']}
                for k, v in result]

    def get_monthly_trend(self) -> list:
        sql = """SELECT
            strftime('%Y-%m', scan_time) as month,
            COUNT(*) as count,
            SUM(file_size) as total_size
            FROM files WHERE status = 'active'
            GROUP BY month ORDER BY month DESC LIMIT 12"""
        return self.db.execute_query(sql)

    # ── 重复文件 DAO ──

    def count_duplicate_groups(self) -> int:
        row = self.db.execute_one(
            """SELECT COUNT(*) as total FROM (
                SELECT file_hash FROM files
                WHERE file_hash IS NOT NULL AND status = 'active'
                GROUP BY file_hash HAVING COUNT(*) > 1
            ) t""")
        return row['total'] if row else 0

    def get_duplicate_groups_paginated(self, page: int = 0, page_size: int = 50) -> list:
        offset = page * page_size
        sql = """SELECT file_hash,
            COUNT(*) as file_count,
            MIN(file_size) as single_size,
            (COUNT(*) - 1) * MIN(file_size) as wasted_size
            FROM files
            WHERE file_hash IS NOT NULL AND status = 'active'
            GROUP BY file_hash HAVING file_count > 1
            ORDER BY wasted_size DESC
            LIMIT ? OFFSET ?"""
        return self.db.execute_query(sql, (page_size, offset))

    def get_duplicate_group_files(self, file_hash: str) -> list:
        return self.db.execute_query(
            """SELECT * FROM files
               WHERE file_hash = ? AND status = 'active'
               ORDER BY modify_time DESC""",
            (file_hash,))

    def get_duplicate_total_wasted(self) -> int:
        row = self.db.execute_one(
            """SELECT COALESCE(SUM(wasted), 0) as total FROM (
                SELECT (COUNT(*) - 1) * MIN(file_size) as wasted
                FROM files
                WHERE file_hash IS NOT NULL AND status = 'active'
                GROUP BY file_hash HAVING COUNT(*) > 1
            ) t""")
        return row['total'] if row else 0

    def delete_by_path(self, file_path: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET status = 'deleted' WHERE file_path = ?", (file_path,))


class FileContentDAO:
    """Local extracted-text index, kept separate from file metadata FTS."""

    def __init__(self, db):
        self.db = db

    def upsert(self, file_id: int, content: str) -> None:
        self.db.execute_update("DELETE FROM file_content_fts WHERE file_id = ?", (str(file_id),))
        self.db.execute_insert(
            "INSERT INTO file_content_fts (file_id, content) VALUES (?, ?)",
            (str(file_id), content))

    def search(self, query: str, limit: int = 100) -> list:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query or '')
        if not tokens:
            return []
        match = " AND ".join(f'"{token}"*' for token in tokens[:10])
        return self.db.execute_query(
            "SELECT f.*, snippet(file_content_fts, 1, '[', ']', '...', 18) AS content_snippet "
            "FROM file_content_fts JOIN files f ON CAST(file_content_fts.file_id AS INTEGER)=f.id "
            "WHERE file_content_fts MATCH ? AND f.status='active' "
            "ORDER BY rank LIMIT ?", (match, limit))

    def count(self) -> int:
        row = self.db.execute_one("SELECT COUNT(*) AS total FROM file_content_fts")
        return row['total'] if row else 0


class MetadataDAO:
    """元数据表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_id: int, metadata: dict) -> int:
        sql = """INSERT INTO file_metadata
            (file_id, width, height, photo_taken_time, camera_model,
             gps_latitude, gps_longitude, pdf_title, pdf_author, pdf_pages,
             video_duration, video_resolution, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
             width=excluded.width, height=excluded.height,
             photo_taken_time=excluded.photo_taken_time, camera_model=excluded.camera_model,
             gps_latitude=excluded.gps_latitude, gps_longitude=excluded.gps_longitude,
             pdf_title=excluded.pdf_title, pdf_author=excluded.pdf_author,
             pdf_pages=excluded.pdf_pages, video_duration=excluded.video_duration,
             video_resolution=excluded.video_resolution, extra_data=excluded.extra_data"""
        return self.db.execute_insert(sql, (
            file_id,
            metadata.get('width'), metadata.get('height'),
            metadata.get('photo_taken_time'), metadata.get('camera_model'),
            metadata.get('gps_latitude'), metadata.get('gps_longitude'),
            metadata.get('pdf_title'), metadata.get('pdf_author'),
            metadata.get('pdf_pages'), metadata.get('video_duration'),
            metadata.get('video_resolution'), metadata.get('extra_data')
        ))

    def get_by_file_id(self, file_id: int) -> Optional[dict]:
        return self.db.execute_one(
            "SELECT * FROM file_metadata WHERE file_id = ?", (file_id,))


class ClassificationDAO:
    """分类记录表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_id: int, cls_type: str, cls_value: str,
               confidence: float = 1.0) -> int:
        sql = """INSERT INTO file_classifications
            (file_id, classification_type, classification_value, classification_time, confidence_score)
            VALUES (?, ?, ?, ?, ?)"""
        return self.db.execute_insert(sql, (
            file_id, cls_type, cls_value, datetime.now(), confidence))

    def batch_insert(self, cls_records: list) -> int:
        """批量插入分类记录，cls_records: [(file_id, cls_type, cls_value, confidence), ...]"""
        if not cls_records:
            return 0
        now = datetime.now()
        sql = """INSERT INTO file_classifications
            (file_id, classification_type, classification_value, classification_time, confidence_score)
            VALUES (?, ?, ?, ?, ?)"""
        params = [(fid, ctype, cval, now, conf) for fid, ctype, cval, conf in cls_records]
        return self.db.execute_many(sql, params)

    def get_by_file_id(self, file_id: int) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_classifications WHERE file_id = ?", (file_id,))

    def get_by_file_ids(self, file_ids: list) -> dict:
        if not file_ids:
            return {}
        placeholders = ','.join(['?'] * len(file_ids))
        rows = self.db.execute_query(
            f"SELECT DISTINCT file_id, classification_value FROM file_classifications "
            f"WHERE file_id IN ({placeholders}) ORDER BY classification_value",
            tuple(file_ids))
        result: dict = {}
        for r in rows:
            result.setdefault(r['file_id'], []).append(r['classification_value'])
        return result

    def get_by_type(self, cls_type: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_classifications WHERE classification_type = ?",
            (cls_type,))

    def get_distinct_values(self, cls_type: Optional[str] = None) -> list:
        if cls_type:
            sql = """SELECT DISTINCT classification_value, COUNT(*) as cnt
                     FROM file_classifications WHERE classification_type = ?
                     GROUP BY classification_value ORDER BY cnt DESC"""
            return self.db.execute_query(sql, (cls_type,))
        sql = """SELECT classification_type, classification_value, COUNT(*) as cnt
                 FROM file_classifications
                 GROUP BY classification_type, classification_value ORDER BY cnt DESC"""
        return self.db.execute_query(sql)

    def delete_by_file_id(self, file_id: int) -> int:
        return self.db.execute_update(
            "DELETE FROM file_classifications WHERE file_id = ?", (file_id,))


class OperationHistoryDAO:
    """操作历史表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, op_type: str, file_id: Optional[int] = None,
               old_value: Optional[str] = None, new_value: Optional[str] = None,
               status: str = 'completed', batch_id: Optional[str] = None,
               error_msg: Optional[str] = None) -> int:
        sql = """INSERT INTO operation_history
            (operation_type, operation_time, file_id, old_value, new_value,
             operation_status, undo_available, error_message, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        undo = 1 if status == 'completed' and op_type in (
            'rename', 'move', 'delete', 'dedup', 'classify') else 0
        return self.db.execute_insert(sql, (
            op_type, datetime.now(), file_id, old_value, new_value,
            status, undo, error_msg, batch_id
        ))

    def get_by_id(self, op_id: int) -> Optional[dict]:
        return self.db.execute_one(
            "SELECT * FROM operation_history WHERE id = ?", (op_id,))

    def get_recent(self, limit: int = 100, op_type: Optional[str] = None) -> list:
        if op_type:
            sql = """SELECT * FROM operation_history WHERE operation_type = ?
                     ORDER BY operation_time DESC LIMIT ?"""
            return self.db.execute_query(sql, (op_type, limit))
        sql = "SELECT * FROM operation_history ORDER BY operation_time DESC LIMIT ?"
        return self.db.execute_query(sql, (limit,))

    def get_by_batch(self, batch_id: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM operation_history WHERE batch_id = ? ORDER BY id", (batch_id,))

    def get_undoable(self, limit: int = 100) -> list:
        sql = """SELECT * FROM operation_history
                 WHERE undo_available = 1 AND operation_status = 'completed'
                 ORDER BY operation_time DESC LIMIT ?"""
        return self.db.execute_query(sql, (limit,))

    def mark_undone(self, op_id: int) -> int:
        return self.db.execute_update(
            "UPDATE operation_history SET operation_status = 'undone', undo_available = 0 WHERE id = ?",
            (op_id,))

    def search(self, op_type: Optional[str] = None, start_date: Optional[str] = None,
               end_date: Optional[str] = None, batch_id: Optional[str] = None,
               limit: int = 200) -> list:
        conditions = []
        params = []
        if op_type:
            conditions.append("operation_type = ?")
            params.append(op_type)
        if start_date:
            conditions.append("operation_time >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("operation_time <= ?")
            params.append(end_date)
        if batch_id:
            conditions.append("batch_id = ?")
            params.append(batch_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM operation_history WHERE {where} ORDER BY operation_time DESC LIMIT ?"
        params.append(limit)
        return self.db.execute_query(sql, tuple(params))

    def get_latest_delete(self, file_id: int) -> Optional[dict]:
        sql = """SELECT * FROM operation_history
                 WHERE file_id = ? AND operation_type IN ('delete', 'dedup')
                 ORDER BY operation_time DESC LIMIT 1"""
        return self.db.execute_one(sql, (file_id,))


class ScanDirectoryDAO:
    """扫描目录表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, directory_path: str, recursive: bool = True) -> int:
        sql = """INSERT INTO scan_directories
            (directory_path, is_active, scan_recursive, create_time)
            VALUES (?, 1, ?, ?)"""
        return self.db.execute_insert(sql, (directory_path, int(recursive), datetime.now()))

    def get_all(self) -> list:
        return self.db.execute_query("SELECT * FROM scan_directories ORDER BY create_time DESC")

    def get_active(self) -> list:
        return self.db.execute_query(
            "SELECT * FROM scan_directories WHERE is_active = 1 ORDER BY create_time DESC")

    def update_scan_time(self, dir_id: int, file_count: int) -> int:
        return self.db.execute_update(
            "UPDATE scan_directories SET last_scan_time = ?, file_count = ? WHERE id = ?",
            (datetime.now(), file_count, dir_id))

    def toggle_active(self, dir_id: int, active: bool) -> int:
        return self.db.execute_update(
            "UPDATE scan_directories SET is_active = ? WHERE id = ?", (int(active), dir_id))

    def delete(self, dir_id: int) -> int:
        return self.db.execute_update("DELETE FROM scan_directories WHERE id = ?", (dir_id,))

    def exists(self, directory_path: str) -> bool:
        row = self.db.execute_one(
            "SELECT id FROM scan_directories WHERE directory_path = ?", (directory_path,))
        return row is not None


class SavedQueryDAO:
    """智能集合（已保存搜索条件）表操作"""

    def __init__(self, db):
        self.db = db

    def upsert(self, name: str, params: dict) -> int:
        """按名称保存集合参数（JSON）。同名则更新，返回记录 id。"""
        import json
        import uuid
        params_json = json.dumps(params, ensure_ascii=False, default=str)
        row = self.db.execute_one(
            "SELECT id FROM saved_queries WHERE name = ?", (name,))
        if row:
            self.db.execute_update(
                "UPDATE saved_queries SET params = ?, update_time = ? WHERE id = ?",
                (params_json, datetime.now(), row['id']))
            return row['id']
        return self.db.execute_insert(
            "INSERT INTO saved_queries (name, params, create_time, update_time) VALUES (?, ?, ?, ?)",
            (name, params_json, datetime.now(), datetime.now()))

    def get_all(self) -> list:
        rows = self.db.execute_query(
            "SELECT * FROM saved_queries ORDER BY update_time DESC")
        import json
        for row in rows:
            try:
                row['params'] = json.loads(row.get('params') or '{}')
            except (TypeError, ValueError):
                row['params'] = {}
        return rows

    def get_by_name(self, name: str) -> dict:
        row = self.db.execute_one(
            "SELECT * FROM saved_queries WHERE name = ?", (name,))
        if not row:
            return None
        import json
        try:
            row['params'] = json.loads(row.get('params') or '{}')
        except (TypeError, ValueError):
            row['params'] = {}
        return row

    def delete(self, name: str) -> int:
        return self.db.execute_update(
            "DELETE FROM saved_queries WHERE name = ?", (name,))

    def count(self) -> int:
        row = self.db.execute_one("SELECT COUNT(*) AS total FROM saved_queries")
        return row['total'] if row else 0


class ClassificationRuleDAO:
    """分类规则表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, rule_name: str, rule_type: str, rule_pattern: str,
               target_category: str, priority: int = 0) -> int:
        sql = """INSERT INTO classification_rules
            (rule_name, rule_type, rule_pattern, target_category, priority, is_enabled, create_time)
            VALUES (?, ?, ?, ?, ?, 1, ?)"""
        return self.db.execute_insert(sql, (
            rule_name, rule_type, rule_pattern, target_category, priority, datetime.now()))

    def get_all(self) -> list:
        return self.db.execute_query(
            "SELECT * FROM classification_rules ORDER BY priority DESC, id")

    def get_enabled(self) -> list:
        return self.db.execute_query(
            "SELECT * FROM classification_rules WHERE is_enabled = 1 ORDER BY priority DESC, id")

    def update(self, rule_id: int, rule_name: str, rule_type: str,
               rule_pattern: str, target_category: str, priority: int) -> int:
        sql = """UPDATE classification_rules SET
            rule_name=?, rule_type=?, rule_pattern=?,
            target_category=?, priority=? WHERE id=?"""
        return self.db.execute_update(sql, (
            rule_name, rule_type, rule_pattern, target_category, priority, rule_id))

    def toggle_enabled(self, rule_id: int, enabled: bool) -> int:
        return self.db.execute_update(
            "UPDATE classification_rules SET is_enabled = ? WHERE id = ?",
            (int(enabled), rule_id))

    def update_priority(self, rule_id: int, priority: int) -> int:
        """仅更新规则优先级（供排序/上移下移使用）"""
        return self.db.execute_update(
            "UPDATE classification_rules SET priority = ? WHERE id = ?",
            (priority, rule_id))

    def delete(self, rule_id: int) -> int:
        return self.db.execute_update("DELETE FROM classification_rules WHERE id = ?", (rule_id,))


class SystemSettingsDAO:
    """系统设置表操作"""

    def __init__(self, db):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute_one(
            "SELECT setting_value, setting_type FROM system_settings WHERE setting_key = ?", (key,))
        if not row:
            return default
        val = row['setting_value']
        st = row['setting_type']
        if st == 'int':
            return int(val)
        if st == 'bool':
            return val in ('1', 'true', 'True')
        return val

    def set(self, key: str, value: Any, setting_type: str = 'string',
            description: Optional[str] = None) -> int:
        sql = """INSERT INTO system_settings (setting_key, setting_value, setting_type, description, update_time)
                 VALUES (?, ?, ?, ?, ?)
                 ON CONFLICT(setting_key) DO UPDATE SET
                 setting_value=excluded.setting_value,
                 setting_type=excluded.setting_type,
                 description=excluded.description,
                 update_time=excluded.update_time"""
        now = datetime.now()
        return self.db.execute_update(sql, (
            key, str(value), setting_type, description, now))

    def get_all(self) -> list:
        return self.db.execute_query("SELECT * FROM system_settings ORDER BY setting_key")


class TagDAO:
    """文件标签表操作"""

    def __init__(self, db):
        self.db = db

    def add_tag(self, file_id: int, tag_name: str) -> int:
        name = tag_name.strip()
        self.db.execute_insert(
            "INSERT OR IGNORE INTO tags (tag_name, create_time) VALUES (?, ?)",
            (name, datetime.now()))
        sql = """INSERT OR IGNORE INTO file_tags (file_id, tag_name, create_time)
                 VALUES (?, ?, ?)"""
        return self.db.execute_insert(sql, (file_id, name, datetime.now()))

    def create_tag(self, tag_name: str) -> int:
        name = tag_name.strip()
        return self.db.execute_insert(
            "INSERT OR IGNORE INTO tags (tag_name, create_time) VALUES (?, ?)",
            (name, datetime.now()))

    def remove_tag(self, file_id: int, tag_name: str) -> int:
        return self.db.execute_update(
            "DELETE FROM file_tags WHERE file_id = ? AND tag_name = ?",
            (file_id, tag_name.strip()))

    def remove_all_tags(self, file_id: int) -> int:
        return self.db.execute_update(
            "DELETE FROM file_tags WHERE file_id = ?", (file_id,))

    def get_tags_by_file(self, file_id: int) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_tags WHERE file_id = ? ORDER BY tag_name", (file_id,))

    def get_files_by_tag(self, tag_name: str) -> list:
        return self.db.execute_query(
            "SELECT f.* FROM files f JOIN file_tags t ON f.id = t.file_id "
            "WHERE t.tag_name = ? AND f.status = 'active' ORDER BY t.create_time DESC",
            (tag_name.strip(),))

    def get_files_by_tag_paginated(self, tag_name: str, page: int = 0, page_size: int = 100) -> list:
        offset = page * page_size
        return self.db.execute_query(
            "SELECT f.* FROM files f JOIN file_tags t ON f.id = t.file_id "
            "WHERE t.tag_name = ? AND f.status = 'active' ORDER BY t.create_time DESC "
            "LIMIT ? OFFSET ?",
            (tag_name.strip(), page_size, offset))

    def count_files_by_tag(self, tag_name: str) -> int:
        row = self.db.execute_one(
            "SELECT COUNT(*) as total FROM file_tags t "
            "JOIN files f ON f.id = t.file_id AND f.status = 'active' "
            "WHERE t.tag_name = ?",
            (tag_name.strip(),))
        return row['total'] if row else 0

    def get_all_tags(self) -> list:
        sql = """SELECT tg.tag_name,
                        COALESCE(t.cnt, 0) as file_count
                 FROM (
                   SELECT DISTINCT tag_name FROM file_tags
                   UNION
                   SELECT tag_name FROM tags
                 ) tg
                 LEFT JOIN (
                   SELECT t.tag_name, COUNT(DISTINCT t.file_id) as cnt
                   FROM file_tags t
                   JOIN files f ON f.id = t.file_id AND f.status = 'active'
                   GROUP BY t.tag_name
                 ) t ON tg.tag_name = t.tag_name
                 ORDER BY file_count DESC, tg.tag_name ASC"""
        return self.db.execute_query(sql)

    def get_all_tags_by_file(self, file_ids: list) -> dict:
        if not file_ids:
            return {}
        placeholders = ','.join(['?'] * len(file_ids))
        rows = self.db.execute_query(
            f"SELECT file_id, tag_name FROM file_tags WHERE file_id IN ({placeholders}) "
            f"ORDER BY tag_name", tuple(file_ids))
        result = {}
        for r in rows:
            result.setdefault(r['file_id'], []).append(r['tag_name'])
        return result

    def rename_tag(self, old_name: str, new_name: str) -> int:
        return self.db.execute_update(
            "UPDATE file_tags SET tag_name = ? WHERE tag_name = ?",
            (new_name.strip(), old_name.strip()))

    def delete_tag(self, tag_name: str) -> int:
        total = self.db.execute_update(
            "DELETE FROM file_tags WHERE tag_name = ?", (tag_name.strip(),))
        total += self.db.execute_update(
            "DELETE FROM tags WHERE tag_name = ?", (tag_name.strip(),))
        return total

    def merge_tag(self, source_name: str, target_name: str) -> int:
        """Merge source associations into target without duplicate links."""
        source = source_name.strip()
        target = target_name.strip()
        if not source or not target:
            raise ValueError('标签名不能为空')
        if source == target:
            raise ValueError('源标签和目标标签不能相同')
        conn = self.db.get_connection()
        try:
            conn.execute('BEGIN')
            conn.execute(
                "INSERT OR IGNORE INTO tags (tag_name, create_time) VALUES (?, ?)",
                (target, datetime.now()))
            cursor = conn.execute(
                "INSERT OR IGNORE INTO file_tags (file_id, tag_name, create_time) "
                "SELECT file_id, ?, create_time FROM file_tags WHERE tag_name = ?",
                (target, source))
            conn.execute("DELETE FROM file_tags WHERE tag_name = ?", (source,))
            conn.execute("DELETE FROM tags WHERE tag_name = ?", (source,))
            conn.commit()
            return cursor.rowcount
        except Exception:
            conn.rollback()
            raise

    def batch_add_tags(self, file_ids: list, tag_names: list) -> int:
        if not file_ids or not tag_names:
            return 0
        params = []
        now = datetime.now()
        for fid in file_ids:
            for tag in tag_names:
                params.append((fid, tag.strip(), now))
        sql = "INSERT OR IGNORE INTO file_tags (file_id, tag_name, create_time) VALUES (?, ?, ?)"
        return self.db.execute_many(sql, params)
