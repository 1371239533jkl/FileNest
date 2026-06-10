"""
MySQL数据库连接管理器（线程安全）
使用 threading.local() 为每个线程维护独立的数据库连接，
避免 QThread 工作线程与 UI 线程共享同一连接导致的数据竞争。
"""
import threading
import pymysql
from pymysql.cursors import DictCursor
import os

from config import MYSQL_CONFIG
from utils.logger import logger


class DBManager:
    """MySQL数据库管理类（线程安全）"""

    def __init__(self):
        self.config = MYSQL_CONFIG.copy()
        self._local = threading.local()

    def _get_local_connection(self):
        """获取当前线程的数据库连接，若不存在或已断开则重新创建"""
        conn = getattr(self._local, 'connection', None)
        if conn is None or not self._is_alive(conn):
            conn = pymysql.connect(**self.config)
            self._local.connection = conn
        return conn

    # 兼容旧接口：外部仍可通过 get_connection() 获取当前线程连接
    def get_connection(self):
        return self._get_local_connection()

    @staticmethod
    def _is_alive(conn):
        try:
            conn.ping(reconnect=False)
            return True
        except Exception:
            return False

    def close(self):
        """关闭当前线程的数据库连接"""
        conn = getattr(self._local, 'connection', None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None

    def execute_query(self, sql, params=None):
        conn = self._get_local_connection()
        with conn.cursor(DictCursor) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def execute_one(self, sql, params=None):
        conn = self._get_local_connection()
        with conn.cursor(DictCursor) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def execute_update(self, sql, params=None):
        conn = self._get_local_connection()
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, params)
                conn.commit()
                return affected
        except Exception as e:
            conn.rollback()
            raise e

    def execute_insert(self, sql, params=None):
        conn = self._get_local_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e

    def execute_many(self, sql, params_list):
        conn = self._get_local_connection()
        try:
            with conn.cursor() as cursor:
                affected = cursor.executemany(sql, params_list)
                conn.commit()
                return affected
        except Exception as e:
            conn.rollback()
            raise e

    def init_database(self):
        """读取并执行初始化SQL脚本（幂等：已初始化则跳过）"""
        sql_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'init_database.sql'
        )
        if not os.path.exists(sql_path):
            raise FileNotFoundError(f"初始化脚本不存在: {sql_path}")

        # ---------- 前置检测：仅日志记录，不做跳过 ----------
        # CREATE TABLE IF NOT EXISTS 和 INSERT IGNORE 保证了重复执行的幂等性
        test_conn = None
        try:
            test_conn = pymysql.connect(**self.config)
            with test_conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM system_settings")
                row = cursor.fetchone()
                if row and row[0] > 0:
                    logger.info("数据库已初始化，继续执行 DDL (CREATE TABLE IF NOT EXISTS 幂等)")
        except Exception:
            pass
        finally:
            if test_conn:
                test_conn.close()

        # ---------- 执行完整初始化 ----------
        # 先不指定数据库连接，执行CREATE DATABASE
        config_no_db = self.config.copy()
        config_no_db.pop('database', None)
        conn = pymysql.connect(**config_no_db)
        try:
            with open(sql_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            statements = []
            current = []
            for line in sql_content.split('\n'):
                stripped = line.strip()
                if stripped.startswith('--') or not stripped:
                    continue
                current.append(line)
                if stripped.endswith(';'):
                    statements.append('\n'.join(current))
                    current = []

            with conn.cursor() as cursor:
                for stmt in statements:
                    stmt = stmt.strip()
                    if stmt:
                        cursor.execute(stmt)
                conn.commit()
        finally:
            conn.close()

        # 重新连接到新创建的数据库（关闭当前线程的旧连接，下次访问时自动重建）
        self.close()
        self._get_local_connection()

        logger.info("数据库初始化完成")


# 全局单例
db = DBManager()
