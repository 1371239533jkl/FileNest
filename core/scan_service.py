"""扫描入库服务：遍历 → 并行哈希 → 单事务批量落库（Qt 无关）。

替代 server.py 里"逐文件 walk + 逐行 commit"的内联实现。
台账：遍历 1.64×（单次 stat），哈希冷盘 14×/热缓存 2.2×，写入 3×（单事务）。
"""
import time
from typing import Callable, Optional

from core import scan_engine
from database.models import FileDAO


class ScanService:
    def __init__(self, db, file_dao: Optional[FileDAO] = None):
        self.db = db
        self.file_dao = file_dao or FileDAO(db)

    def scan(self, root: str, recursive: bool = True, compute_hash: bool = True,
             progress: Optional[Callable[[int, int], None]] = None,
             cancel: Optional[Callable[[], bool]] = None) -> dict:
        """扫描目录并入库；返回 {scanned, written, hashed, elapsed_s}。

        路径已存在时按 file_path 覆盖（FileDAO.insert 的 upsert 语义），可重复扫描。
        """
        started = time.perf_counter()
        records = scan_engine.collect(root, recursive=recursive)
        total = len(records)

        hashed = 0
        if compute_hash and records:
            digests = scan_engine.hash_many([r['file_path'] for r in records])
            for record, digest in zip(records, digests):
                record['file_hash'] = digest
                if digest:
                    hashed += 1

        written = 0
        with self.db.transaction():
            for i, record in enumerate(records):
                if cancel and cancel():
                    break
                self.file_dao.insert(record)
                written += 1
                if progress and (i % 200 == 0 or i == total - 1):
                    progress(i + 1, total)

        return {
            'scanned': total,
            'written': written,
            'hashed': hashed,
            'elapsed_s': round(time.perf_counter() - started, 3),
        }
