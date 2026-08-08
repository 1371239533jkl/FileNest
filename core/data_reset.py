"""Safe reset of FileNest's local index data without touching source files."""
from database.db_manager import db


class AppDataResetService:
    """Clear application-managed records while preserving settings and disk files."""

    _COUNT_QUERIES = {
        '文件索引': 'SELECT COUNT(*) AS total FROM files',
        '扫描目录': 'SELECT COUNT(*) AS total FROM scan_directories',
        '标签': 'SELECT COUNT(*) AS total FROM tags',
        '操作记录': 'SELECT COUNT(*) AS total FROM operation_history',
        '正文索引': 'SELECT COUNT(*) AS total FROM file_content_fts',
    }

    def preview(self) -> dict:
        return {
            name: (db.execute_one(query) or {}).get('total', 0)
            for name, query in self._COUNT_QUERIES.items()
        }

    def reset(self) -> dict:
        """Atomically clear only database records maintained by the app."""
        conn = db.get_connection()
        tables = (
            'file_content_fts', 'file_tags', 'file_classifications',
            'file_metadata', 'operation_history', 'tags', 'files',
            'scan_directories', 'classification_rules',
        )
        try:
            conn.execute('BEGIN')
            for table in tables:
                conn.execute(f'DELETE FROM {table}')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        # Restore only application defaults (settings and built-in rules), not
        # user files, tags, scan directories or operation records.
        db.init_database()
        return self.preview()
