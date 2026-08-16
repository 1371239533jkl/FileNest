"""Local, opt-in extracted-text indexing for supported document formats.

增量策略：以「文件修改指纹」（size:mtime）判断内容是否变化，
指纹未变则跳过重新提取，变化或首次索引才更新，减少重复 IO。
单文件失败不阻断批次（由 index_records 隔离并记录）。
"""
import os

from core.file_reader import can_read_content, read_file_content
from database.db_manager import db
from database.models import FileDAO, FileContentDAO
from utils.logger import logger


class ContentIndexer:
    def __init__(self):
        self.file_dao = FileDAO(db)
        self.content_dao = FileContentDAO(db)

    @staticmethod
    def _fingerprint(path: str) -> str:
        """基于文件大小与修改时间的指纹。文件不可读时返回空串。"""
        try:
            st = os.stat(path)
        except OSError:
            return ''
        return f"{st.st_size}:{int(st.st_mtime)}"

    def index_file(self, record: dict, max_chars: int = 20000) -> str:
        """索引单个文件。

        Returns:
            'indexed'  成功写入正文索引
            'skipped'  指纹未变化，无需重新提取（或格式不支持）
            'failed'   提取失败（记录在案，下次可重试）
        """
        path = record.get('file_path', '')
        if not path or not can_read_content(path):
            return 'skipped'

        fingerprint = self._fingerprint(path)
        if not fingerprint:
            return 'skipped'
        if record.get('content_fingerprint') == fingerprint:
            return 'skipped'

        content = read_file_content(path, max_chars=max_chars)
        if not content:
            return 'failed'
        self.content_dao.upsert(record['id'], content)
        self.file_dao.update_content_fingerprint(record['id'], fingerprint)
        return 'indexed'

    def index_active_files(self, limit: int = 1000) -> dict:
        return self.index_records(self.file_dao.get_all_active()[:limit])

    def index_records(self, records: list[dict]) -> dict:
        result = {'indexed': 0, 'skipped': 0, 'failed': 0}
        for record in records:
            try:
                status = self.index_file(record)
                result[status] = result.get(status, 0) + 1
            except Exception as exc:
                result['failed'] += 1
                logger.warning('内容索引失败 %s: %s', record.get('file_path'), exc)
        return result
