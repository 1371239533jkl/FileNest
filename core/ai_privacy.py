"""
AI 隐私控制台 —— 调用记录 + 目录级禁止 + 数据去向展示。

ponytail: 最小实现。
- 调用记录：SQLite ai_usage_logs 表，记录每次 AI 调用的类型、token、耗时、涉及文件
- 目录级禁止：JSON 配置 ai_privacy.json，存禁止 AI 访问的目录列表
- 数据去向：根据后端类型判断（本地 Ollama = 不出本机，云端 = 发往 API）

升级路径：需要细粒度审计时换数据库表 + 全文检索。
"""

import json
import os
import re
import sqlite3
import time
from typing import Optional

from config import DB_PATH
from utils.logger import logger

# ── PII 脱敏正则 ──
_PII_PATTERNS = [
    # 邮箱
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<邮箱>'),
    # 手机号（11 位，1 开头；前后非数字防误伤长数字）
    (re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'), '<手机号>'),
    # 身份证号（18 位含校验位）
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'), '<身份证>'),
]


def mask_pii_text(text: str) -> str:
    """PII 脱敏核心逻辑（模块级函数，便于独立测试）。

    ponytail: 只脱敏邮箱/手机号/身份证三类明确 PII，不脱敏文件路径
    （路径是文件管理器的核心语义，脱敏会破坏 AI 搜索与问答的正确性）。
    文件名中含 PII 的极端场景接受泄漏，开关可关。
    """
    if not text:
        return text
    for pattern, placeholder in _PII_PATTERNS:
        text = pattern.sub(placeholder, text)
    return text

_CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PRIVACY_CONFIG_FILE = os.path.join(_CONFIG_DIR, "ai_privacy.json")

_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    call_type TEXT NOT NULL,
    model TEXT NOT NULL,
    backend TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    file_paths TEXT,
    success INTEGER DEFAULT 1,
    error_msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_log_time ON ai_usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_log_type ON ai_usage_logs(call_type);
"""


def _ensure_db(conn: sqlite3.Connection):
    conn.executescript(_LOG_TABLE_SQL)


def _default_config() -> dict:
    return {
        "forbidden_dirs": [],
        "forbidden_extensions": [],
        "allow_local_only": False,
        "log_enabled": True,
        "max_files_per_call": 50,
        "pii_masking": True,
    }


class AIPrivacy:
    """AI 隐私控制管理器。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._db_path = DB_PATH
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        _ensure_db(self._conn)
        self._config = self._load_config()

    # ── 配置 ──

    def _load_config(self) -> dict:
        try:
            if os.path.exists(_PRIVACY_CONFIG_FILE):
                with open(_PRIVACY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                # 合并默认值
                defaults = _default_config()
                for k, v in defaults.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
        except Exception as e:
            logger.error(f"加载 AI 隐私配置失败: {e}")
        return _default_config()

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(_PRIVACY_CONFIG_FILE), exist_ok=True)
            with open(_PRIVACY_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存 AI 隐私配置失败: {e}")

    def get_config(self) -> dict:
        return dict(self._config)

    def set_config_value(self, key: str, value):
        self._config[key] = value
        self._save_config()

    # ── PII 字段脱敏 ──

    def mask_pii(self, text: str) -> str:
        """对发送给 AI 的文本做 PII 脱敏（受 pii_masking 开关控制）。"""
        if not text or not self._config.get('pii_masking', True):
            return text
        return mask_pii_text(text)

    # ── 目录级禁止 ──

    def get_forbidden_dirs(self) -> list[str]:
        return list(self._config.get('forbidden_dirs', []))

    def add_forbidden_dir(self, path: str) -> bool:
        """添加禁止 AI 访问的目录。"""
        path = os.path.normpath(path)
        if path not in self._config['forbidden_dirs']:
            self._config['forbidden_dirs'].append(path)
            self._save_config()
            return True
        return False

    def remove_forbidden_dir(self, path: str) -> bool:
        """移除禁止目录。"""
        path = os.path.normpath(path)
        if path in self._config['forbidden_dirs']:
            self._config['forbidden_dirs'].remove(path)
            self._save_config()
            return True
        return False

    def is_path_forbidden(self, file_path: str) -> bool:
        """检查文件路径是否在禁止目录下。"""
        if not file_path:
            return False
        file_path = os.path.normpath(file_path)
        for forbidden in self._config.get('forbidden_dirs', []):
            forbidden = os.path.normpath(forbidden)
            # 精确匹配或子目录
            if file_path == forbidden or file_path.startswith(forbidden + os.sep):
                return True
        return False

    def filter_forbidden_files(self, files: list[dict]) -> tuple[list[dict], list[dict]]:
        """过滤掉禁止目录下的文件。

        Returns:
            (允许的文件, 被过滤的文件)
        """
        allowed = []
        forbidden = []
        for f in files:
            path = f.get('file_path', '') if isinstance(f, dict) else getattr(f, 'file_path', '')
            if self.is_path_forbidden(path):
                forbidden.append(f)
            else:
                allowed.append(f)
        return allowed, forbidden

    # ── 禁止扩展名 ──

    def get_forbidden_extensions(self) -> list[str]:
        return list(self._config.get('forbidden_extensions', []))

    def add_forbidden_extension(self, ext: str) -> bool:
        ext = ext.lower().lstrip('.')
        if ext not in self._config['forbidden_extensions']:
            self._config['forbidden_extensions'].append(ext)
            self._save_config()
            return True
        return False

    def remove_forbidden_extension(self, ext: str) -> bool:
        ext = ext.lower().lstrip('.')
        if ext in self._config['forbidden_extensions']:
            self._config['forbidden_extensions'].remove(ext)
            self._save_config()
            return True
        return False

    # ── 调用记录 ──

    def log_call(self, call_type: str, model: str, backend: str,
                 prompt_tokens: int = 0, completion_tokens: int = 0,
                 latency_ms: int = 0, file_count: int = 0,
                 file_paths: Optional[list[str]] = None,
                 success: bool = True, error_msg: str = ""):
        """记录一次 AI 调用。"""
        if not self._config.get('log_enabled', True):
            return
        try:
            paths_str = ""
            if file_paths:
                # 最多存 10 个路径，避免日志过大
                shown = file_paths[:10]
                paths_str = "\n".join(shown)
                if len(file_paths) > 10:
                    paths_str += f"\n... 还有 {len(file_paths) - 10} 个文件"

            self._conn.execute(
                """INSERT INTO ai_usage_logs
                   (timestamp, call_type, model, backend, prompt_tokens,
                    completion_tokens, total_tokens, latency_ms, file_count,
                    file_paths, success, error_msg)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    time.time(), call_type, model, backend,
                    prompt_tokens, completion_tokens,
                    prompt_tokens + completion_tokens,
                    latency_ms, file_count, paths_str,
                    1 if success else 0, error_msg,
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.debug(f"AI 调用日志写入失败: {e}")

    def get_logs(self, limit: int = 100, call_type: Optional[str] = None,
                 days: Optional[int] = None) -> list[dict]:
        """获取调用日志。

        Args:
            limit: 返回条数
            call_type: 按类型过滤
            days: 最近 N 天
        """
        try:
            sql = "SELECT * FROM ai_usage_logs"
            conditions = []
            params = []

            if call_type:
                conditions.append("call_type = ?")
                params.append(call_type)
            if days:
                conditions.append("timestamp >= ?")
                params.append(time.time() - days * 86400)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取 AI 调用日志失败: {e}")
            return []

    def get_stats(self, days: int = 7) -> dict:
        """获取 AI 使用统计。"""
        try:
            since = time.time() - days * 86400
            row = self._conn.execute(
                """SELECT
                    COUNT(*) as total_calls,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_calls,
                    SUM(total_tokens) as total_tokens,
                    SUM(latency_ms) as total_latency,
                    SUM(file_count) as total_files
                FROM ai_usage_logs WHERE timestamp >= ?""",
                (since,),
            ).fetchone()

            # 按类型统计
            type_rows = self._conn.execute(
                """SELECT call_type, COUNT(*) as cnt, SUM(total_tokens) as tokens
                   FROM ai_usage_logs WHERE timestamp >= ?
                   GROUP BY call_type ORDER BY cnt DESC""",
                (since,),
            ).fetchall()

            return {
                "total_calls": row['total_calls'] or 0,
                "success_calls": row['success_calls'] or 0,
                "total_tokens": row['total_tokens'] or 0,
                "total_latency_ms": row['total_latency'] or 0,
                "total_files": row['total_files'] or 0,
                "by_type": [dict(r) for r in type_rows],
                "days": days,
            }
        except Exception as e:
            logger.error(f"获取 AI 使用统计失败: {e}")
            return {"total_calls": 0, "success_calls": 0, "total_tokens": 0,
                    "total_latency_ms": 0, "total_files": 0, "by_type": [], "days": days}

    def clear_logs(self, days: Optional[int] = None):
        """清空调用日志。

        Args:
            days: 只删除 N 天前的，None 表示全部删除
        """
        try:
            if days:
                self._conn.execute(
                    "DELETE FROM ai_usage_logs WHERE timestamp < ?",
                    (time.time() - days * 86400,),
                )
            else:
                self._conn.execute("DELETE FROM ai_usage_logs")
            self._conn.commit()
        except Exception as e:
            logger.error(f"清空 AI 日志失败: {e}")

    # ── 数据去向 ──

    def get_data_destination(self, backend_type: str,
                              backend_name: str = "") -> dict:
        """获取数据去向说明。

        Args:
            backend_type: "local" 或 "cloud"
            backend_name: 后端名称

        Returns:
            {
                "level": "safe" | "warning" | "danger",
                "title": "...",
                "description": "...",
                "details": ["...", ...]
            }
        """
        if backend_type == "local":
            return {
                "level": "safe",
                "title": "✅ 数据不出本机",
                "description": f"使用本地 {backend_name or 'Ollama'} 模型",
                "details": [
                    "所有 AI 计算在本机完成",
                    "文件内容不会上传到任何服务器",
                    "无需担心数据泄露风险",
                ],
            }
        else:
            return {
                "level": "warning",
                "title": "⚠️ 数据发送到云端",
                "description": f"使用云端 API：{backend_name or '未知'}",
                "details": [
                    "文件内容和查询会发送到 API 服务商",
                    "请确保不包含敏感信息",
                    "可在下方设置禁止 AI 访问的目录",
                    "建议查看服务商的隐私政策",
                ],
            }
