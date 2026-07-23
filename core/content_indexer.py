"""Local, opt-in extracted-text indexing for supported document formats."""
from core.file_reader import can_read_content, read_file_content
from database.db_manager import db
from database.models import FileDAO, FileContentDAO
from utils.logger import logger


class ContentIndexer:
    def __init__(self):
        self.file_dao = FileDAO(db)
        self.content_dao = FileContentDAO(db)

    def index_file(self, record: dict, max_chars: int = 20000) -> bool:
        path = record.get('file_path', '')
        if not path or not can_read_content(path):
            return False
        content = read_file_content(path, max_chars=max_chars)
        if not content:
            return False
        self.content_dao.upsert(record['id'], content)
        return True

    def index_active_files(self, limit: int = 1000) -> dict:
        return self.index_records(self.file_dao.get_all_active()[:limit])

    def index_records(self, records: list[dict]) -> dict:
        result = {'indexed': 0, 'skipped': 0, 'failed': 0}
        for record in records:
            try:
                if self.index_file(record):
                    result['indexed'] += 1
                else:
                    result['skipped'] += 1
            except Exception as exc:
                result['failed'] += 1
                logger.warning('内容索引失败 %s: %s', record.get('file_path'), exc)
        return result
