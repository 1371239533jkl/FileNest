"""
Embedding 向量服务 —— 语义搜索的核心。

ponytail: 最小实现，不引入向量数据库。
- 向量存在 SQLite 的 file_embeddings 表（BLOB 存 float32 二进制）
- 搜索时全量加载到内存算余弦相似度
- 适用规模：万级文件，单次搜索 < 100ms
- 升级路径：文件量 > 5 万时换 faiss 或 sqlite-vss

依赖：AILayer.embeddings() 生成向量，numpy 算相似度。
"""

import math
import os
import struct
import sqlite3
from typing import Optional

from config import DB_PATH
from core.ai_layer import AILayer
from utils.logger import logger


# ── 向量工具 ──

def _pack_vector(vec: list[float]) -> bytes:
    """float list → binary (float32 little-endian)"""
    return struct.pack(f'<{len(vec)}f', *vec)


def _unpack_vector(data: bytes) -> list[float]:
    """binary → float list"""
    if not data:
        return []
    n = len(data) // 4
    return list(struct.unpack(f'<{n}f', data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度，纯 Python 实现，避免 numpy 依赖。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── 数据库表 ──

_EMBEDDING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS file_embeddings (
    file_id INTEGER PRIMARY KEY,
    embedding BLOB NOT NULL,
    dim INTEGER NOT NULL,
    model TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_emb_model ON file_embeddings(model);
"""


def _ensure_table(conn: sqlite3.Connection):
    conn.executescript(_EMBEDDING_TABLE_SQL)


# ── 主服务 ──

class EmbeddingService:
    """文件 embedding 管理 + 语义搜索。"""

    def __init__(self, ai_layer: Optional[AILayer] = None, embed_model: Optional[str] = None):
        self._ai = ai_layer or AILayer()
        # ponytail: 对话模型不支持 /embeddings，向量模型需单独指定（如 text-embedding-v4）
        self._embed_model = embed_model or None
        self._db_path = DB_PATH
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        _ensure_table(self._conn)
        # 缓存：model -> dim
        self._dim_cache: dict[str, int] = {}

    # ── 公共 API ──

    def is_available(self) -> bool:
        """embedding 能力是否可用。"""
        return self._ai.enabled

    def get_dim(self, model: str) -> int:
        """获取当前模型的向量维度。"""
        if model in self._dim_cache:
            return self._dim_cache[model]
        # 用一个短文本探测维度
        vecs = self._ai.embeddings(["probe"], model=self._embed_model)
        if vecs and vecs[0]:
            dim = len(vecs[0])
            self._dim_cache[model] = dim
            return dim
        return 0

    def upsert_file(self, file_id: int, text: str) -> bool:
        """为单个文件生成并存储 embedding。

        Returns:
            True 成功，False 失败
        """
        if not self.is_available():
            return False
        try:
            vecs = self._ai.embeddings([text], model=self._embed_model)
            if not vecs or not vecs[0]:
                return False
            vec = vecs[0]
            dim = len(vec)
            model = self._embed_model or getattr(self._ai._backend, "model", "unknown")
            now = __import__("time").time()
            blob = _pack_vector(vec)
            self._conn.execute(
                """INSERT OR REPLACE INTO file_embeddings
                   (file_id, embedding, dim, model, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_id, blob, dim, model, now),
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Embedding upsert 失败 file_id={file_id}: {e}")
            return False

    def batch_upsert(self, items: list[tuple[int, str]]) -> int:
        """批量生成 embedding。

        Args:
            items: [(file_id, text), ...]

        Returns:
            成功数量
        """
        if not self.is_available() or not items:
            return 0

        # 分批：每批最多 10 个文本
        batch_size = 10
        success = 0
        model = self._embed_model or getattr(self._ai._backend, "model", "unknown")
        now = __import__("time").time()

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            try:
                texts = [t for _, t in batch]
                vecs = self._ai.embeddings(texts, model=self._embed_model)
                if not vecs:
                    continue
                for (fid, _), vec in zip(batch, vecs):
                    if not vec:
                        continue
                    blob = _pack_vector(vec)
                    dim = len(vec)
                    self._conn.execute(
                        """INSERT OR REPLACE INTO file_embeddings
                           (file_id, embedding, dim, model, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (fid, blob, dim, model, now),
                    )
                    success += 1
                self._conn.commit()
            except Exception as e:
                logger.error(f"Embedding 批量 upsert 失败 batch {i}: {e}")

        return success

    def search(self, query: str, top_k: int = 20,
               file_ids: Optional[list[int]] = None) -> list[tuple[int, float]]:
        """语义搜索：返回最相似的 file_id 列表。

        Args:
            query: 查询文本
            top_k: 返回数量
            file_ids: 限定在这些 file_id 中搜索（可选）

        Returns:
            [(file_id, score), ...] 按相似度降序
        """
        if not self.is_available():
            return []

        # 生成查询向量（必须与建索引时同一向量模型，否则 404 且维度不匹配）
        qvecs = self._ai.embeddings([query], model=self._embed_model)
        if not qvecs or not qvecs[0]:
            return []
        qvec = qvecs[0]

        # 加载所有 embedding
        try:
            if file_ids:
                placeholders = ",".join("?" * len(file_ids))
                rows = self._conn.execute(
                    f"SELECT file_id, embedding FROM file_embeddings "
                    f"WHERE file_id IN ({placeholders})",
                    file_ids,
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT file_id, embedding FROM file_embeddings"
                ).fetchall()

            if not rows:
                return []

            # 计算相似度
            results = []
            for row in rows:
                fid = row[0]
                vec = _unpack_vector(row[1])
                sim = cosine_similarity(qvec, vec)
                if sim > 0:  # 只保留正相关
                    results.append((fid, sim))

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    def count_embedded(self) -> int:
        """已生成 embedding 的文件数。"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM file_embeddings"
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def delete_file(self, file_id: int):
        """删除文件的 embedding。"""
        try:
            self._conn.execute(
                "DELETE FROM file_embeddings WHERE file_id = ?",
                (file_id,),
            )
            self._conn.commit()
        except Exception:
            pass

    def clear_all(self):
        """清空所有 embedding（模型切换时用）。"""
        try:
            self._conn.execute("DELETE FROM file_embeddings")
            self._conn.commit()
        except Exception:
            pass
