"""
SQLite 嵌入式数据库连接管理器（线程安全）
使用 sqlite3 + WAL 模式 + threading.local() 为每个线程维护独立连接。
ponytail: 从 PyMySQL 切换为 sqlite3 标准库，消除外部数据库依赖。
"""
import threading
import sqlite3
import os
from datetime import datetime

from config import DB_PATH
from utils.logger import logger


class DBManager:
    """SQLite 数据库管理类（线程安全）"""

    def __init__(self):
        self.db_path = DB_PATH
        self._local = threading.local()

    def _get_local_connection(self):
        conn = getattr(self._local, 'connection', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")
            self._local.connection = conn
        return conn

    def get_connection(self):
        return self._get_local_connection()

    def close(self):
        conn = getattr(self._local, 'connection', None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None

    @staticmethod
    def _to_dicts(cursor, rows):
        if not rows:
            return []
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def execute_query(self, sql, params=None):
        conn = self._get_local_connection()
        cursor = conn.execute(sql, params or ())
        rows = cursor.fetchall()
        return self._to_dicts(cursor, rows)

    def execute_one(self, sql, params=None):
        conn = self._get_local_connection()
        cursor = conn.execute(sql, params or ())
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

    def execute_update(self, sql, params=None):
        conn = self._get_local_connection()
        try:
            cursor = conn.execute(sql, params or ())
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e

    def execute_insert(self, sql, params=None):
        conn = self._get_local_connection()
        try:
            cursor = conn.execute(sql, params or ())
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e

    def execute_many(self, sql, params_list):
        conn = self._get_local_connection()
        try:
            cursor = conn.executemany(sql, params_list)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e

    def _migrate_files_columns(self, conn):
        """为旧版 files 表补充缺失列（SQLite ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS）。

        新装的库由建表语句直接包含；升级的库通过这里补齐，保证幂等。
        """
        try:
            cols = [row['name'] for row in conn.execute("PRAGMA table_info(files)").fetchall()]
            if 'content_fingerprint' not in cols:
                conn.execute("ALTER TABLE files ADD COLUMN content_fingerprint TEXT")
                logger.info("迁移: files 表新增 content_fingerprint 列")
            conn.commit()
        except Exception as e:
            logger.warning(f"files 表列迁移跳过: {e}")

    def init_database(self):
        """创建数据库表结构（幂等：CREATE TABLE IF NOT EXISTS）"""
        conn = self._get_local_connection()

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                file_path       TEXT            NOT NULL,
                file_name       TEXT            NOT NULL,
                original_name   TEXT,
                file_extension  TEXT            NOT NULL,
                file_type       TEXT            NOT NULL,
                file_size       INTEGER         NOT NULL,
                file_hash       TEXT,
                create_time     TEXT,
                modify_time     TEXT,
                scan_time       TEXT            NOT NULL,
                is_duplicate    INTEGER         DEFAULT 0,
                duplicate_group_id INTEGER,
                content_fingerprint TEXT,
                status          TEXT            DEFAULT 'active'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_file_path ON files(file_path);
            CREATE INDEX IF NOT EXISTS idx_file_name ON files(file_name);
            CREATE INDEX IF NOT EXISTS idx_file_extension ON files(file_extension);
            CREATE INDEX IF NOT EXISTS idx_file_type ON files(file_type);
            CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash);
            CREATE INDEX IF NOT EXISTS idx_duplicate_group ON files(duplicate_group_id);
            CREATE INDEX IF NOT EXISTS idx_scan_time ON files(scan_time);
            CREATE INDEX IF NOT EXISTS idx_type_time ON files(file_type, modify_time);

            CREATE TABLE IF NOT EXISTS file_metadata (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                file_id         INTEGER         NOT NULL UNIQUE,
                width           INTEGER,
                height          INTEGER,
                photo_taken_time TEXT,
                camera_model    TEXT,
                gps_latitude    REAL,
                gps_longitude   REAL,
                pdf_title       TEXT,
                pdf_author      TEXT,
                pdf_pages       INTEGER,
                video_duration  INTEGER,
                video_resolution TEXT,
                extra_data      TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS file_classifications (
                id                  INTEGER     PRIMARY KEY AUTOINCREMENT,
                file_id             INTEGER     NOT NULL,
                classification_type TEXT        NOT NULL,
                classification_value TEXT       NOT NULL,
                classification_time TEXT        NOT NULL,
                confidence_score    REAL        DEFAULT 1.00,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_file_cls_unique
                ON file_classifications(file_id, classification_type, classification_value);
            CREATE INDEX IF NOT EXISTS idx_file_class
                ON file_classifications(file_id, classification_type);

            CREATE TABLE IF NOT EXISTS operation_history (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                operation_type  TEXT            NOT NULL,
                operation_time  TEXT            NOT NULL,
                file_id         INTEGER,
                old_value       TEXT,
                new_value       TEXT,
                operation_status TEXT           DEFAULT 'completed',
                undo_available  INTEGER         DEFAULT 1,
                error_message   TEXT,
                batch_id        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_op_time ON operation_history(operation_time);
            CREATE INDEX IF NOT EXISTS idx_batch ON operation_history(batch_id);
            CREATE INDEX IF NOT EXISTS idx_op_file ON operation_history(file_id);
            CREATE INDEX IF NOT EXISTS idx_op_status ON operation_history(operation_status);

            CREATE TABLE IF NOT EXISTS scan_directories (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                directory_path  TEXT            NOT NULL UNIQUE,
                is_active       INTEGER         DEFAULT 1,
                scan_recursive  INTEGER         DEFAULT 1,
                last_scan_time  TEXT,
                file_count      INTEGER         DEFAULT 0,
                create_time     TEXT            NOT NULL
            );

            CREATE TABLE IF NOT EXISTS classification_rules (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                rule_name       TEXT            NOT NULL,
                rule_type       TEXT            NOT NULL,
                rule_pattern    TEXT            NOT NULL,
                target_category TEXT            NOT NULL,
                priority        INTEGER         DEFAULT 0,
                is_enabled      INTEGER         DEFAULT 1,
                create_time     TEXT            NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rule_priority ON classification_rules(priority);
            CREATE INDEX IF NOT EXISTS idx_rule_enabled ON classification_rules(is_enabled);

            CREATE TABLE IF NOT EXISTS system_settings (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                setting_key     TEXT            NOT NULL UNIQUE,
                setting_value   TEXT            NOT NULL,
                setting_type    TEXT            DEFAULT 'string',
                description     TEXT,
                update_time     TEXT
            );

            CREATE TABLE IF NOT EXISTS file_tags (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                file_id         INTEGER         NOT NULL,
                tag_name        TEXT            NOT NULL,
                create_time     TEXT            NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_file_tag ON file_tags(file_id, tag_name);
            CREATE INDEX IF NOT EXISTS idx_tag_name ON file_tags(tag_name);

            CREATE TABLE IF NOT EXISTS tags (
                id              INTEGER         PRIMARY KEY AUTOINCREMENT,
                tag_name        TEXT            NOT NULL UNIQUE,
                create_time     TEXT            NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                file_name,
                file_path,
                file_extension,
                content='files',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS file_content_fts USING fts5(
                file_id UNINDEXED,
                content,
                tokenize='unicode61'
            );
        """)
        conn.commit()

        # === 轻量迁移：为已存在的 files 表补充列（幂等）===
        self._migrate_files_columns(conn)

        # === FTS5 触发器（幂等：DROP IF EXISTS 后重建）===
        conn.executescript("""
            DROP TRIGGER IF EXISTS files_fts_insert;
            CREATE TRIGGER files_fts_insert AFTER INSERT ON files BEGIN
                INSERT INTO files_fts(rowid, file_name, file_path, file_extension)
                VALUES (new.id, new.file_name, new.file_path, new.file_extension);
            END;

            DROP TRIGGER IF EXISTS files_fts_delete;
            CREATE TRIGGER files_fts_delete AFTER DELETE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, file_name, file_path, file_extension)
                VALUES ('delete', old.id, old.file_name, old.file_path, old.file_extension);
            END;

            DROP TRIGGER IF EXISTS files_fts_update;
            CREATE TRIGGER files_fts_update AFTER UPDATE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, file_name, file_path, file_extension)
                VALUES ('delete', old.id, old.file_name, old.file_path, old.file_extension);
                INSERT INTO files_fts(rowid, file_name, file_path, file_extension)
                VALUES (new.id, new.file_name, new.file_path, new.file_extension);
            END;
        """)
        conn.commit()

        # === 默认数据（幂等：INSERT OR IGNORE）===
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.executemany(
            "INSERT OR IGNORE INTO system_settings (setting_key, setting_value, setting_type, description, update_time) VALUES (?, ?, ?, ?, ?)",
            [
                ('rename_pattern', '{date}_{type}_{original_name}', 'string', '默认重命名模板', now),
                ('dedup_strategy', 'keep_newest', 'string', '默认去重策略', now),
                ('hash_algorithm', 'sha256', 'string', '哈希算法', now),
                ('scan_recursive', '1', 'bool', '默认递归扫描', now),
                ('include_hidden', '0', 'bool', '包含隐藏文件', now),
                ('max_hash_size_mb', '500', 'int', '计算哈希的最大文件大小(MB)', now),
            ])
        conn.executemany(
            "INSERT OR IGNORE INTO classification_rules (rule_name, rule_type, rule_pattern, target_category, priority, is_enabled, create_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ('工作文件', 'keyword', '报告|会议|方案|合同|发票|report|meeting|invoice', '工作', 10, 1, now),
                ('学习资料', 'keyword', '笔记|课件|作业|论文|note|homework|thesis', '学习', 10, 1, now),
                ('生活照片', 'keyword', '照片|旅游|美食|photo|travel|food', '生活', 10, 1, now),
                ('项目文件', 'keyword', '代码|设计|需求|测试|code|design|test', '项目', 10, 1, now),
            ])
        conn.commit()
        logger.info("SQLite 数据库初始化完成")


# 全局单例
db = DBManager()
