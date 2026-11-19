"""数据层：事务批量提交与 keyset 分页（不依赖 PyQt6）。"""
import os
import sqlite3
import tempfile

import pytest

from database.db_manager import DBManager
from database.models import FileDAO

COLUMNS = '(file_path, file_name, file_extension, file_type, file_size, scan_time)'


def _rows(start, n):
    return [(f'/tmp/f{i}.txt', f'f{i}.txt', '.txt', 'document', i,
             f'2026-01-01 00:00:{i % 60:02d}') for i in range(start, start + n)]


@pytest.fixture()
def db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    mgr = DBManager(path)
    mgr.init_database()
    yield mgr
    mgr.close()
    os.unlink(path)


def test_transaction_defers_commit(db):
    """事务块内不提交：另一连接看不到，退出后一次可见。"""
    other = sqlite3.connect(db.db_path)
    try:
        with db.transaction() as conn:
            conn.executemany(f'INSERT INTO files {COLUMNS} VALUES (?,?,?,?,?,?)',
                             _rows(0, 40))
            assert other.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 0
        assert other.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 40
    finally:
        other.close()


def test_transaction_rolls_back(db):
    """块内异常 → 整批回滚，一行不留。"""
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.execute_many(f'INSERT INTO files {COLUMNS} VALUES (?,?,?,?,?,?)',
                            _rows(0, 10))
            raise RuntimeError('boom')
    assert db.execute_one('SELECT COUNT(*) AS n FROM files')['n'] == 0


def test_keyset_pagination_walks_all_rows_once(db):
    """keyset 分页遍历全集：不重不漏，且按 scan_time 倒序。"""
    dao = FileDAO(db)
    db.execute_many(f'INSERT INTO files {COLUMNS} VALUES (?,?,?,?,?,?)', _rows(0, 7))

    seen, cursor = [], None
    while True:
        page = dao.get_page_after(cursor, page_size=3)
        if not page:
            break
        seen.extend(page)
        cursor = (page[-1]['scan_time'], page[-1]['id'])

    ids = [r['id'] for r in seen]
    assert len(ids) == 7
    assert len(set(ids)) == 7
    assert ids == sorted(ids, reverse=True)


def test_offset_pagination_still_works(db):
    """旧接口保持兼容：keyset 上线不影响既有调用方。"""
    dao = FileDAO(db)
    db.execute_many(f'INSERT INTO files {COLUMNS} VALUES (?,?,?,?,?,?)', _rows(0, 5))
    assert len(dao.get_all_active_paginated(page=0, page_size=2)) == 2
    assert len(dao.get_all_active_paginated(page=2, page_size=2)) == 1
