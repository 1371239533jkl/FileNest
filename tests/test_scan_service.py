"""扫描入库服务：遍历 → 哈希 → 单事务落库（不依赖 PyQt6）。"""
import os
import shutil
import tempfile

import pytest

from core.scan_service import ScanService
from database.db_manager import DBManager


@pytest.fixture()
def env():
    root = tempfile.mkdtemp(prefix='filenest-svc-')
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    for i in range(30):
        d = os.path.join(root, f'd{i % 3}')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'f{i}.txt'), 'wb') as f:
            f.write(b'y' * (i + 1))
    db = DBManager(db_path)
    db.init_database()
    yield root, db
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    os.unlink(db_path)


def test_scan_writes_all_records(env):
    root, db = env
    result = ScanService(db).scan(root)
    assert result['scanned'] == 30
    assert result['written'] == 30
    assert result['hashed'] == 30
    assert db.execute_one('SELECT COUNT(*) AS n FROM files')['n'] == 30


def test_rescan_is_idempotent(env):
    root, db = env
    svc = ScanService(db)
    svc.scan(root)
    svc.scan(root)
    assert db.execute_one('SELECT COUNT(*) AS n FROM files')['n'] == 30


def test_hash_persisted_and_stable(env):
    root, db = env
    ScanService(db).scan(root)
    row = db.execute_one(
        "SELECT file_hash FROM files WHERE file_name = 'f7.txt'")
    assert row['file_hash'] and len(row['file_hash']) == 64

    # 同名不同内容 → 重扫后哈希更新
    path = os.path.join(root, 'd1', 'f7.txt')
    with open(path, 'wb') as f:
        f.write(b'changed')
    ScanService(db).scan(root)
    assert db.execute_one(
        "SELECT file_hash FROM files WHERE file_name = 'f7.txt'")['file_hash'] != row['file_hash']


def test_without_hash_leaves_null(env):
    root, db = env
    ScanService(db).scan(root, compute_hash=False)
    assert db.execute_one(
        'SELECT COUNT(*) AS n FROM files WHERE file_hash IS NULL')['n'] == 30


def test_cancel_stops_writing(env):
    root, db = env
    calls = {'n': 0}

    def cancel():
        calls['n'] += 1
        return calls['n'] > 5

    result = ScanService(db).scan(root, compute_hash=False, cancel=cancel)
    assert result['written'] < 30
    assert db.execute_one('SELECT COUNT(*) AS n FROM files')['n'] == result['written']
