"""Read-only index consistency checks with explicit, conservative repair."""
import os

from database.db_manager import db


class IndexHealthService:
    def inspect(self) -> dict:
        active = db.execute_query(
            "SELECT id, file_path FROM files WHERE status='active'")
        missing = [row for row in active if not os.path.exists(row['file_path'])]
        orphan_content = db.execute_one(
            "SELECT COUNT(*) AS total FROM file_content_fts c "
            "LEFT JOIN files f ON CAST(c.file_id AS INTEGER)=f.id WHERE f.id IS NULL")
        return {
            'active_files': len(active),
            'missing_records': missing,
            'orphan_content_count': (orphan_content or {}).get('total', 0),
        }

    def repair(self, report: dict) -> dict:
        """Repair only records confirmed missing during the immediately prior check."""
        missing = report.get('missing_records', [])
        repaired = 0
        for row in missing:
            # Re-check immediately before mutation so a file restored between
            # preview and confirmation is never marked deleted.
            if not os.path.exists(row['file_path']):
                repaired += db.execute_update(
                    "UPDATE files SET status='deleted' WHERE id=? AND status='active'",
                    (row['id'],))
        cleaned = db.execute_update(
            "DELETE FROM file_content_fts WHERE file_id NOT IN (SELECT CAST(id AS TEXT) FROM files)")
        return {'marked_deleted': repaired, 'orphan_content_removed': cleaned}
