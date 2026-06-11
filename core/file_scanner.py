"""
文件扫描器 - 目录遍历、哈希计算、增量扫描
"""
import os
import hashlib
import ctypes
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    FILE_TYPES, HASH_BLOCK_SIZE, MAX_FILE_SIZE_FOR_HASH, INCLUDE_HIDDEN_FILES
)
from database.db_manager import db
from database.models import FileDAO, ScanDirectoryDAO
from utils.logger import logger


def get_file_type(extension: str) -> str:
    ext = extension.lower()
    for ftype, extensions in FILE_TYPES.items():
        if ext in extensions:
            return ftype
    return 'other'


def calculate_hash(file_path: str, block_size: int = HASH_BLOCK_SIZE) -> Optional[str]:
    h = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                block = f.read(block_size)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except (IOError, OSError) as e:
        logger.warning(f"无法计算哈希: {file_path} - {e}")
        return None


def get_file_info(file_path: str) -> dict:
    p = Path(file_path)
    stat = p.stat()
    ext = p.suffix.lower()
    return {
        'file_path': str(p),
        'file_name': p.name,
        'original_name': None,
        'file_extension': ext,
        'file_type': get_file_type(ext),
        'file_size': stat.st_size,
        'create_time': datetime.fromtimestamp(stat.st_ctime),
        'modify_time': datetime.fromtimestamp(stat.st_mtime),
    }


def is_hidden_file(file_path: str) -> bool:
    """跨平台检测文件是否为隐藏文件

    Windows: 通过 GetFileAttributesW 检测 FILE_ATTRIBUTE_HIDDEN (0x2)
    Linux/macOS: 通过文件名是否以 '.' 开头判断
    """
    if os.name == 'nt':
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(file_path)
            if attrs == -1:  # INVALID_FILE_ATTRIBUTES
                return False
            return bool(attrs & 2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            return False
    return Path(file_path).name.startswith('.')


def _format_eta(seconds: float) -> str:
    """将秒数格式化为友好的 ETA 字符串"""
    if seconds < 0:
        return "即将完成"
    if seconds < 60:
        return f"约 {int(seconds)} 秒"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"约 {minutes} 分 {secs} 秒"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"约 {hours} 时 {minutes} 分"


class FileScanWorker(QThread):
    """文件扫描工作线程"""
    progress = pyqtSignal(int, int, str)  # current, total, path
    progress_eta = pyqtSignal(str)  # ETA 字符串
    finished = pyqtSignal(int, int)  # new_count, total_count
    error = pyqtSignal(str)

    def __init__(self, directory: str, recursive: bool = True,
                 compute_hash: bool = True, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.recursive = recursive
        self.compute_hash = compute_hash
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            file_dao = FileDAO(db)
            scan_dao = ScanDirectoryDAO(db)

            # 收集所有文件路径
            all_files = []
            root_path = Path(self.directory)
            if self.recursive:
                iterator = root_path.rglob('*')
            else:
                iterator = root_path.glob('*')

            for p in iterator:
                if self._cancelled:
                    return
                if not p.is_file():
                    continue
                if not INCLUDE_HIDDEN_FILES and is_hidden_file(str(p)):
                    continue
                all_files.append(str(p))

            total = len(all_files)
            new_count = 0
            start_time = time.time()  # 记录扫描开始时间

            # 预加载该目录下已有文件记录（字典键为 file_path），避免 N+1 查询
            existing_paths = {}
            preload_failed = False
            try:
                for rec in file_dao.get_by_directory(self.directory):
                    existing_paths[rec['file_path']] = rec
            except Exception:
                logger.warning("预加载已有文件记录失败，回退到逐条查询")
                preload_failed = True

            for i, fp in enumerate(all_files):
                if self._cancelled:
                    return
                self.progress.emit(i + 1, total, fp)

                # 每 20 个文件或每 500ms 发射一次 ETA
                if (i + 1) % 20 == 0 or i + 1 == total:
                    elapsed = time.time() - start_time
                    if i > 0:
                        avg_time = elapsed / (i + 1)
                        remaining_files = total - (i + 1)
                        eta_seconds = avg_time * remaining_files
                        eta_str = _format_eta(eta_seconds)
                        self.progress_eta.emit(eta_str)
                    else:
                        self.progress_eta.emit("计算中...")

                # 检查是否已存在（优先内存字典，预加载失败则回退逐条查询）
                if preload_failed:
                    existing = file_dao.get_by_path(fp)
                else:
                    existing = existing_paths.get(fp)
                if existing:
                    # 增量：检查文件是否被修改
                    try:
                        stat = os.stat(fp)
                        db_mtime = existing.get('modify_time')
                        if db_mtime and datetime.fromtimestamp(stat.st_mtime) <= db_mtime:
                            continue
                    except OSError:
                        continue

                try:
                    info = get_file_info(fp)
                except (OSError, PermissionError) as e:
                    logger.warning(f"跳过文件: {fp} - {e}")
                    continue

                # 计算哈希
                if self.compute_hash and info['file_size'] <= MAX_FILE_SIZE_FOR_HASH:
                    info['file_hash'] = calculate_hash(fp)

                if existing:
                    # 更新已有记录
                    file_dao.update_status(existing['id'], 'active')
                    if info.get('file_hash'):
                        file_dao.update_hash(existing['id'], info['file_hash'])
                else:
                    file_dao.insert(info)
                    new_count += 1

            # 更新扫描目录信息
            if not scan_dao.exists(self.directory):
                scan_dao.insert(self.directory, self.recursive)
            dirs = scan_dao.get_all()
            for d in dirs:
                if d['directory_path'] == self.directory:
                    scan_dao.update_scan_time(d['id'], total)
                    break

            self.finished.emit(new_count, total)
            logger.info(f"扫描完成: {self.directory}, 新文件: {new_count}, 总计: {total}")
        except Exception as e:
            logger.error(f"扫描出错: {e}")
            self.error.emit(str(e))
