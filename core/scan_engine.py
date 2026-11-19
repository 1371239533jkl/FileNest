"""Qt 无关的扫描/哈希内核：单次 stat 取全属性 + 多进程并行。

与 core/file_scanner.py 的区别：
- 不依赖 PyQt6，可单独测试与测量（后续 FileScanWorker 只做 Qt 包装）
- 每个文件只 stat 一次（原来 GetFileAttributesW + Path.stat 各一次）
- 大目录按子目录分片，多进程并行遍历与哈希

Windows 隐藏属性/重解析点通过 os.stat_result.st_file_attributes 判断，避免额外 syscall。
"""
import hashlib
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Iterable, Optional

from config import (FILE_TYPES, HASH_BLOCK_SIZE, INCLUDE_HIDDEN_FILES,
                    MAX_FILE_SIZE_FOR_HASH)

_HIDDEN = 0x2
_REPARSE = 0x400


def file_type_of(extension: str) -> str:
    ext = extension.lower()
    for ftype, extensions in FILE_TYPES.items():
        if ext in extensions:
            return ftype
    return 'other'


def _is_hidden(entry, st) -> bool:
    attrs = getattr(st, 'st_file_attributes', None)
    if attrs is not None:
        return bool(attrs & _HIDDEN)
    return entry.name.startswith('.')


def _is_reparse(st) -> bool:
    attrs = getattr(st, 'st_file_attributes', None)
    return bool(attrs and attrs & _REPARSE)


def _walk_one(root: str, recursive: bool, include_hidden: bool) -> list:
    """返回 [(path, size, ctime, mtime)]；每个文件只 stat 一次。"""
    out = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entry_iter = list(os.scandir(current))
        except OSError:
            continue
        for entry in entry_iter:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if entry.is_dir(follow_symlinks=False):
                if recursive and not _is_reparse(st):
                    stack.append(entry.path)
                continue
            if not include_hidden and _is_hidden(entry, st):
                continue
            out.append((entry.path, st.st_size, st.st_ctime, st.st_mtime))
    return out


def _walk_task(args) -> list:
    root, recursive, include_hidden = args
    return _walk_one(root, recursive, include_hidden)


def _workers(n: Optional[int]) -> int:
    return max(1, min(n or 8, os.cpu_count() or 1))


def collect(root: str, recursive: bool = True,
            include_hidden: Optional[bool] = None) -> list:
    """单进程遍历，返回按 files 表字段组织的记录列表。

    不做多进程：22k 文件实测 0.07s，8 进程反而 0.25s（启动成本 > 收益），
    目录遍历受限于单盘 IO，加进程不会更快。
    """
    include_hidden = INCLUDE_HIDDEN_FILES if include_hidden is None else include_hidden
    return [_to_record(row) for row in _walk_one(root, recursive, include_hidden)]


def _to_record(row) -> dict:
    path, size, ctime, mtime = row
    p = os.path.basename(path)
    ext = os.path.splitext(p)[1].lower()
    return {
        'file_path': path,
        'file_name': p,
        'original_name': None,
        'file_extension': ext,
        'file_type': file_type_of(ext),
        'file_size': size,
        'create_time': datetime.fromtimestamp(ctime),
        'modify_time': datetime.fromtimestamp(mtime),
    }


def hash_file(path: str, block_size: int = HASH_BLOCK_SIZE) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _hash_task(path: str) -> Optional[str]:
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE_FOR_HASH:
            return None
        return hash_file(path)
    except OSError:
        return None


def hash_many(paths: Iterable[str], workers: Optional[int] = None) -> list:
    """并行计算 SHA-256；返回与输入同序的列表，失败/超限为 None。"""
    paths = list(paths)
    n = _workers(workers)
    if n <= 1 or len(paths) < 64:
        return [_hash_task(p) for p in paths]
    with ProcessPoolExecutor(max_workers=n) as pool:
        # chunksize 影响跨进程往返次数：小文件多时调大明显更快
        return list(pool.map(_hash_task, paths, chunksize=64))


def _dhash_task(path: str) -> Optional[str]:
    from core.image_similarity import dhash  # 延迟导入：只有图片任务需要 PIL
    return dhash(path)


def dhash_many(paths: Iterable[str], workers: Optional[int] = None) -> list:
    paths = list(paths)
    n = _workers(workers)
    if n <= 1 or len(paths) < 32:
        return [_dhash_task(p) for p in paths]
    with ProcessPoolExecutor(max_workers=n) as pool:
        return list(pool.map(_dhash_task, paths, chunksize=4))
