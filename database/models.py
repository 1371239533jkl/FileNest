"""
数据访问对象 - 封装各表CRUD操作
"""
from datetime import datetime
from typing import Optional, Any


class FileDAO:
    """文件表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_info: dict) -> int:
        sql = """INSERT INTO files
            (file_path, file_name, original_name, file_extension, file_type,
             file_size, file_hash, create_time, modify_time, scan_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        return self.db.execute_insert(sql, (
            file_info['file_path'], file_info['file_name'],
            file_info.get('original_name'), file_info['file_extension'],
            file_info['file_type'], file_info['file_size'],
            file_info.get('file_hash'), file_info.get('create_time'),
            file_info.get('modify_time'), datetime.now(), 'active'
        ))

    def insert_many(self, file_infos: list) -> int:
        sql = """INSERT INTO files
            (file_path, file_name, original_name, file_extension, file_type,
             file_size, file_hash, create_time, modify_time, scan_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        params = [(
            fi['file_path'], fi['file_name'], fi.get('original_name'),
            fi['file_extension'], fi['file_type'], fi['file_size'],
            fi.get('file_hash'), fi.get('create_time'), fi.get('modify_time'),
            datetime.now(), 'active'
        ) for fi in file_infos]
        return self.db.execute_many(sql, params)

    def get_by_id(self, file_id: int) -> Optional[dict]:
        return self.db.execute_one("SELECT * FROM files WHERE id = %s", (file_id,))

    def get_by_path(self, file_path: str) -> Optional[dict]:
        return self.db.execute_one("SELECT * FROM files WHERE file_path = %s AND status = 'active'", (file_path,))

    def get_by_hash(self, file_hash: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM files WHERE file_hash = %s AND status = 'active'", (file_hash,))

    def get_by_directory(self, directory: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM files WHERE file_path LIKE %s AND status = 'active'",
            (directory.rstrip('/\\') + '%',))

    def get_all_active(self) -> list:
        return self.db.execute_query("SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC")

    def get_all_active_paginated(self, page: int = 0, page_size: int = 500) -> list:
        """分页获取活动文件，默认每页 500 条，page 从 0 开始"""
        offset = page * page_size
        sql = "SELECT * FROM files WHERE status = 'active' ORDER BY scan_time DESC LIMIT %s OFFSET %s"
        return self.db.execute_query(sql, (page_size, offset))

    def update_name(self, file_id: int, new_name: str, new_path: str) -> int:
        sql = "UPDATE files SET file_name = %s, file_path = %s WHERE id = %s"
        return self.db.execute_update(sql, (new_name, new_path, file_id))

    def update_hash(self, file_id: int, file_hash: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET file_hash = %s WHERE id = %s", (file_hash, file_id))

    def update_duplicate(self, file_id: int, is_duplicate: int, group_id: int) -> int:
        return self.db.execute_update(
            "UPDATE files SET is_duplicate = %s, duplicate_group_id = %s WHERE id = %s",
            (is_duplicate, group_id, file_id))

    def update_status(self, file_id: int, status: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET status = %s WHERE id = %s", (status, file_id))

    def _build_search_conditions(self, name=None, file_type=None, extension=None,
                                  min_size=None, max_size=None, start_date=None,
                                  end_date=None, is_duplicate=None):
        """构建搜索条件（供 search/search_paginated/search_count 复用）"""
        conditions = ["status = 'active'"]
        params = []
        if name:
            conditions.append("file_name LIKE %s")
            params.append(f"%{name}%")
        if file_type:
            conditions.append("file_type = %s")
            params.append(file_type)
        if extension:
            conditions.append("file_extension = %s")
            params.append(extension)
        if min_size is not None:
            conditions.append("file_size >= %s")
            params.append(min_size)
        if max_size is not None:
            conditions.append("file_size <= %s")
            params.append(max_size)
        if start_date:
            conditions.append("modify_time >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("modify_time <= %s")
            params.append(end_date)
        if is_duplicate is not None:
            conditions.append("is_duplicate = %s")
            params.append(is_duplicate)
        return " AND ".join(conditions), params

    def search(self, name: Optional[str] = None, file_type: Optional[str] = None,
               extension: Optional[str] = None, min_size: Optional[int] = None,
               max_size: Optional[int] = None, start_date: Optional[str] = None,
               end_date: Optional[str] = None,
               is_duplicate: Optional[int] = None) -> list:
        where, params = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        sql = f"SELECT * FROM files WHERE {where} ORDER BY modify_time DESC"
        return self.db.execute_query(sql, tuple(params))

    def search_paginated(self, page: int = 0, page_size: int = 100,
                         name=None, file_type=None, extension=None,
                         min_size=None, max_size=None, start_date=None,
                         end_date=None, is_duplicate=None) -> list:
        """分页搜索，返回当前页结果"""
        where, params = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        offset = page * page_size
        sql = f"SELECT * FROM files WHERE {where} ORDER BY modify_time DESC LIMIT %s OFFSET %s"
        params.extend([page_size, offset])
        return self.db.execute_query(sql, tuple(params))

    def search_count(self, name=None, file_type=None, extension=None,
                     min_size=None, max_size=None, start_date=None,
                     end_date=None, is_duplicate=None) -> int:
        """搜索总数（用于分页计算）"""
        where, params = self._build_search_conditions(
            name, file_type, extension, min_size, max_size, start_date, end_date, is_duplicate)
        sql = f"SELECT COUNT(*) as total FROM files WHERE {where}"
        row = self.db.execute_one(sql, tuple(params))
        return row['total'] if row else 0

    def get_duplicates(self) -> list:
        sql = """SELECT file_hash, COUNT(*) as cnt
                 FROM files WHERE file_hash IS NOT NULL AND status = 'active'
                 GROUP BY file_hash HAVING cnt > 1"""
        return self.db.execute_query(sql)

    def get_all_duplicates(self) -> list:
        """单条SQL查出所有重复文件的完整记录（替代 get_duplicates + 逐个 get_by_hash）"""
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
        """获取已删除文件（供回收区管理页面使用）"""
        offset = page * page_size
        sql = """SELECT * FROM files WHERE status = 'deleted'
                 ORDER BY scan_time DESC LIMIT %s OFFSET %s"""
        return self.db.execute_query(sql, (page_size, offset))

    def count_deleted(self) -> int:
        """已删除文件总数"""
        row = self.db.execute_one(
            "SELECT COUNT(*) as total FROM files WHERE status = 'deleted'")
        return row['total'] if row else 0

    def delete_by_path(self, file_path: str) -> int:
        return self.db.execute_update(
            "UPDATE files SET status = 'deleted' WHERE file_path = %s", (file_path,))


class MetadataDAO:
    """元数据表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_id: int, metadata: dict) -> int:
        sql = """INSERT INTO file_metadata
            (file_id, width, height, photo_taken_time, camera_model,
             gps_latitude, gps_longitude, pdf_title, pdf_author, pdf_pages,
             video_duration, video_resolution, extra_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
             width=VALUES(width), height=VALUES(height),
             photo_taken_time=VALUES(photo_taken_time), camera_model=VALUES(camera_model),
             gps_latitude=VALUES(gps_latitude), gps_longitude=VALUES(gps_longitude),
             pdf_title=VALUES(pdf_title), pdf_author=VALUES(pdf_author),
             pdf_pages=VALUES(pdf_pages), video_duration=VALUES(video_duration),
             video_resolution=VALUES(video_resolution), extra_data=VALUES(extra_data)"""
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
            "SELECT * FROM file_metadata WHERE file_id = %s", (file_id,))


class ClassificationDAO:
    """分类记录表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, file_id: int, cls_type: str, cls_value: str,
               confidence: float = 1.0) -> int:
        sql = """INSERT INTO file_classifications
            (file_id, classification_type, classification_value, classification_time, confidence_score)
            VALUES (%s, %s, %s, %s, %s)"""
        return self.db.execute_insert(sql, (
            file_id, cls_type, cls_value, datetime.now(), confidence))

    def batch_insert(self, cls_records: list) -> int:
        """批量插入分类记录，cls_records: [(file_id, cls_type, cls_value, confidence), ...]"""
        if not cls_records:
            return 0
        now = datetime.now()
        sql = """INSERT INTO file_classifications
            (file_id, classification_type, classification_value, classification_time, confidence_score)
            VALUES (%s, %s, %s, %s, %s)"""
        params = [(fid, ctype, cval, now, conf) for fid, ctype, cval, conf in cls_records]
        return self.db.execute_many(sql, params)

    def get_by_file_id(self, file_id: int) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_classifications WHERE file_id = %s", (file_id,))

    def get_by_file_ids(self, file_ids: list) -> dict:
        """批量查询多个文件的分类，返回 {file_id: [classification_value, ...]}"""
        if not file_ids:
            return {}
        placeholders = ','.join(['%s'] * len(file_ids))
        rows = self.db.execute_query(
            f"SELECT file_id, classification_value FROM file_classifications "
            f"WHERE file_id IN ({placeholders}) ORDER BY classification_value",
            tuple(file_ids))
        result: dict = {}
        for r in rows:
            result.setdefault(r['file_id'], []).append(r['classification_value'])
        return result

    def get_by_type(self, cls_type: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_classifications WHERE classification_type = %s",
            (cls_type,))

    def get_distinct_values(self, cls_type: Optional[str] = None) -> list:
        if cls_type:
            sql = """SELECT DISTINCT classification_value, COUNT(*) as cnt
                     FROM file_classifications WHERE classification_type = %s
                     GROUP BY classification_value ORDER BY cnt DESC"""
            return self.db.execute_query(sql, (cls_type,))
        sql = """SELECT classification_type, classification_value, COUNT(*) as cnt
                 FROM file_classifications
                 GROUP BY classification_type, classification_value ORDER BY cnt DESC"""
        return self.db.execute_query(sql)

    def delete_by_file_id(self, file_id: int) -> int:
        return self.db.execute_update(
            "DELETE FROM file_classifications WHERE file_id = %s", (file_id,))


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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        undo = 1 if status == 'completed' and op_type in ('rename', 'move', 'delete', 'classify') else 0
        return self.db.execute_insert(sql, (
            op_type, datetime.now(), file_id, old_value, new_value,
            status, undo, error_msg, batch_id
        ))

    def get_by_id(self, op_id: int) -> Optional[dict]:
        return self.db.execute_one(
            "SELECT * FROM operation_history WHERE id = %s", (op_id,))

    def get_recent(self, limit: int = 100, op_type: Optional[str] = None) -> list:
        if op_type:
            sql = """SELECT * FROM operation_history WHERE operation_type = %s
                     ORDER BY operation_time DESC LIMIT %s"""
            return self.db.execute_query(sql, (op_type, limit))
        sql = "SELECT * FROM operation_history ORDER BY operation_time DESC LIMIT %s"
        return self.db.execute_query(sql, (limit,))

    def get_by_batch(self, batch_id: str) -> list:
        return self.db.execute_query(
            "SELECT * FROM operation_history WHERE batch_id = %s ORDER BY id", (batch_id,))

    def get_undoable(self, limit: int = 100) -> list:
        sql = """SELECT * FROM operation_history
                 WHERE undo_available = 1 AND operation_status = 'completed'
                 ORDER BY operation_time DESC LIMIT %s"""
        return self.db.execute_query(sql, (limit,))

    def mark_undone(self, op_id: int) -> int:
        return self.db.execute_update(
            "UPDATE operation_history SET operation_status = 'undone', undo_available = 0 WHERE id = %s",
            (op_id,))

    def search(self, op_type: Optional[str] = None, start_date: Optional[str] = None,
               end_date: Optional[str] = None, batch_id: Optional[str] = None,
               limit: int = 200) -> list:
        conditions = []
        params = []
        if op_type:
            conditions.append("operation_type = %s")
            params.append(op_type)
        if start_date:
            conditions.append("operation_time >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("operation_time <= %s")
            params.append(end_date)
        if batch_id:
            conditions.append("batch_id = %s")
            params.append(batch_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM operation_history WHERE {where} ORDER BY operation_time DESC LIMIT %s"
        params.append(limit)
        return self.db.execute_query(sql, tuple(params))

    def get_latest_delete(self, file_id: int) -> Optional[dict]:
        """查找指定文件最近一次删除/去重操作记录（用于回收区恢复）"""
        sql = """SELECT * FROM operation_history
                 WHERE file_id = %s AND operation_type IN ('delete', 'dedup')
                 ORDER BY operation_time DESC LIMIT 1"""
        return self.db.execute_one(sql, (file_id,))


class ScanDirectoryDAO:
    """扫描目录表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, directory_path: str, recursive: bool = True) -> int:
        sql = """INSERT INTO scan_directories
            (directory_path, is_active, scan_recursive, create_time)
            VALUES (%s, 1, %s, %s)"""
        return self.db.execute_insert(sql, (directory_path, int(recursive), datetime.now()))

    def get_all(self) -> list:
        return self.db.execute_query("SELECT * FROM scan_directories ORDER BY create_time DESC")

    def get_active(self) -> list:
        return self.db.execute_query(
            "SELECT * FROM scan_directories WHERE is_active = 1 ORDER BY create_time DESC")

    def update_scan_time(self, dir_id: int, file_count: int) -> int:
        return self.db.execute_update(
            "UPDATE scan_directories SET last_scan_time = %s, file_count = %s WHERE id = %s",
            (datetime.now(), file_count, dir_id))

    def toggle_active(self, dir_id: int, active: bool) -> int:
        return self.db.execute_update(
            "UPDATE scan_directories SET is_active = %s WHERE id = %s", (int(active), dir_id))

    def delete(self, dir_id: int) -> int:
        return self.db.execute_update("DELETE FROM scan_directories WHERE id = %s", (dir_id,))

    def exists(self, directory_path: str) -> bool:
        row = self.db.execute_one(
            "SELECT id FROM scan_directories WHERE directory_path = %s", (directory_path,))
        return row is not None


class ClassificationRuleDAO:
    """分类规则表操作"""

    def __init__(self, db):
        self.db = db

    def insert(self, rule_name: str, rule_type: str, rule_pattern: str,
               target_category: str, priority: int = 0) -> int:
        sql = """INSERT INTO classification_rules
            (rule_name, rule_type, rule_pattern, target_category, priority, is_enabled, create_time)
            VALUES (%s, %s, %s, %s, %s, 1, %s)"""
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
            rule_name=%s, rule_type=%s, rule_pattern=%s,
            target_category=%s, priority=%s WHERE id=%s"""
        return self.db.execute_update(sql, (
            rule_name, rule_type, rule_pattern, target_category, priority, rule_id))

    def toggle_enabled(self, rule_id: int, enabled: bool) -> int:
        return self.db.execute_update(
            "UPDATE classification_rules SET is_enabled = %s WHERE id = %s",
            (int(enabled), rule_id))

    def delete(self, rule_id: int) -> int:
        return self.db.execute_update("DELETE FROM classification_rules WHERE id = %s", (rule_id,))


class SystemSettingsDAO:
    """系统设置表操作"""

    def __init__(self, db):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute_one(
            "SELECT setting_value, setting_type FROM system_settings WHERE setting_key = %s", (key,))
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
        # 使用 INSERT ... ON DUPLICATE KEY UPDATE 来安全地处理并发情况
        sql = """INSERT INTO system_settings (setting_key, setting_value, setting_type, description, update_time)
                 VALUES (%s, %s, %s, %s, %s)
                 ON DUPLICATE KEY UPDATE 
                 setting_value=VALUES(setting_value), 
                 setting_type=VALUES(setting_type), 
                 description=VALUES(description), 
                 update_time=VALUES(update_time)"""
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
        """给文件添加标签，同时确保标签名在独立标签表中存在"""
        name = tag_name.strip()
        # 确保独立标签存在
        self.db.execute_insert(
            "INSERT IGNORE INTO tags (tag_name, create_time) VALUES (%s, %s)",
            (name, datetime.now()))
        # 关联文件和标签
        sql = """INSERT IGNORE INTO file_tags (file_id, tag_name, create_time)
                 VALUES (%s, %s, %s)"""
        return self.db.execute_insert(sql, (file_id, name, datetime.now()))

    def create_tag(self, tag_name: str) -> int:
        """创建独立标签（不关联文件）"""
        name = tag_name.strip()
        return self.db.execute_insert(
            "INSERT IGNORE INTO tags (tag_name, create_time) VALUES (%s, %s)",
            (name, datetime.now()))

    def remove_tag(self, file_id: int, tag_name: str) -> int:
        return self.db.execute_update(
            "DELETE FROM file_tags WHERE file_id = %s AND tag_name = %s",
            (file_id, tag_name.strip()))

    def remove_all_tags(self, file_id: int) -> int:
        return self.db.execute_update(
            "DELETE FROM file_tags WHERE file_id = %s", (file_id,))

    def get_tags_by_file(self, file_id: int) -> list:
        return self.db.execute_query(
            "SELECT * FROM file_tags WHERE file_id = %s ORDER BY tag_name", (file_id,))

    def get_files_by_tag(self, tag_name: str) -> list:
        """获取打某个标签的所有文件ID"""
        return self.db.execute_query(
            "SELECT f.* FROM files f JOIN file_tags t ON f.id = t.file_id "
            "WHERE t.tag_name = %s AND f.status = 'active' ORDER BY t.create_time DESC",
            (tag_name.strip(),))

    def get_all_tags(self) -> list:
        """获取所有标签及其文件数（含独立标签），按文件数降序"""
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
        """批量查多个文件的标签，返回 {file_id: [tag_name, ...]}"""
        if not file_ids:
            return {}
        placeholders = ','.join(['%s'] * len(file_ids))
        rows = self.db.execute_query(
            f"SELECT file_id, tag_name FROM file_tags WHERE file_id IN ({placeholders}) "
            f"ORDER BY tag_name", tuple(file_ids))
        result = {}
        for r in rows:
            result.setdefault(r['file_id'], []).append(r['tag_name'])
        return result

    def rename_tag(self, old_name: str, new_name: str) -> int:
        return self.db.execute_update(
            "UPDATE file_tags SET tag_name = %s WHERE tag_name = %s",
            (new_name.strip(), old_name.strip()))

    def delete_tag(self, tag_name: str) -> int:
        """删除标签（从 file_tags 和 tags 表中同时删除）"""
        total = self.db.execute_update(
            "DELETE FROM file_tags WHERE tag_name = %s", (tag_name.strip(),))
        total += self.db.execute_update(
            "DELETE FROM tags WHERE tag_name = %s", (tag_name.strip(),))
        return total

    def batch_add_tags(self, file_ids: list, tag_names: list) -> int:
        """批量给多个文件加多个标签"""
        if not file_ids or not tag_names:
            return 0
        params = []
        now = datetime.now()
        for fid in file_ids:
            for tag in tag_names:
                params.append((fid, tag.strip(), now))
        sql = "INSERT IGNORE INTO file_tags (file_id, tag_name, create_time) VALUES (%s, %s, %s)"
        return self.db.execute_many(sql, params)
