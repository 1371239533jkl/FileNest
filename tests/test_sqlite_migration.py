"""
ponytail: SQLite 迁移验证 — 验证 DBManager + DAO 全部接口正确性。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import db
from database.models import (
    FileDAO, MetadataDAO, ClassificationDAO, OperationHistoryDAO,
    ScanDirectoryDAO, ClassificationRuleDAO, SystemSettingsDAO, TagDAO
)


def test_db_init():
    """幂等初始化"""
    db.init_database()
    assert os.path.exists(db.db_path)
    print("[PASS] DB init")


def test_file_crud():
    dao = FileDAO(db)
    # Insert
    fid = dao.insert({
        'file_path': '/test/hello.py',
        'file_name': 'hello.py',
        'file_extension': '.py',
        'file_type': 'code',
        'file_size': 1024,
    })
    assert fid > 0
    print(f"[PASS] Insert (id={fid})")

    # Get by id
    f = dao.get_by_id(fid)
    assert f['file_name'] == 'hello.py'
    print(f"[PASS] get_by_id: {f['file_name']}")

    # Get by path
    f = dao.get_by_path('/test/hello.py')
    assert f is not None
    print("[PASS] get_by_path")

    # Search via FTS5
    results = dao.search(name='hello')
    assert len(results) >= 1
    print(f"[PASS] FTS5 search 'hello': {len(results)} results")

    # Search count
    cnt = dao.search_count(name='hello')
    assert cnt >= 1
    print(f"[PASS] FTS5 count: {cnt}")

    # Update
    dao.update_name(fid, 'world.py', '/test/world.py')
    f2 = dao.get_by_id(fid)
    assert f2['file_name'] == 'world.py'
    print("[PASS] rename")

    # FTS5 tracks rename
    results2 = dao.search(name='world')
    assert len(results2) >= 1
    print(f"[PASS] FTS5 after rename: {len(results2)}")

    # Search without name (no FTS5 join)
    results3 = dao.search(file_type='code')
    assert len(results3) >= 1
    print(f"[PASS] search by file_type: {len(results3)}")

    # Paginated
    paged = dao.search_paginated(page=0, page_size=10)
    assert len(paged) >= 1
    print(f"[PASS] search_paginated")

    # Active count
    active = dao.count_active()
    assert active >= 1
    print(f"[PASS] count_active: {active}")

    # Type stats
    stats = dao.get_type_stats()
    print(f"[PASS] get_type_stats: {len(stats)} categories")

    # Monthly trend
    trend = dao.get_monthly_trend()
    print(f"[PASS] get_monthly_trend: {len(trend)} months")

    # Size distribution
    dist = dao.get_size_distribution()
    print(f"[PASS] get_size_distribution: {len(dist)} ranges")

    # Top directories (Python-side aggregation)
    top = dao.get_top_directories(limit=5)
    print(f"[PASS] get_top_directories: {len(top)} dirs")

    # Upsert (same path should update)
    fid2 = dao.insert({
        'file_path': '/test/hello.py',
        'file_name': 'hello_v2.py',
        'file_extension': '.py',
        'file_type': 'code',
        'file_size': 2048,
    })
    assert fid2 > 0
    f3 = dao.get_by_path('/test/hello.py')
    assert f3['file_name'] == 'hello_v2.py'
    assert f3['file_size'] == 2048
    print("[PASS] upsert (ON CONFLICT)")

    # Cleanup
    dao.delete_record(fid)
    dao.delete_record(fid2)
    print("[PASS] cleanup")


def test_system_settings():
    dao = SystemSettingsDAO(db)
    val = dao.get('rename_pattern')
    assert val is not None
    print(f"[PASS] get rename_pattern: {val}")

    dao.set('_test_key', '_test_value', 'string', 'test')
    assert dao.get('_test_key') == '_test_value'
    print("[PASS] set/get")

    # int type
    dao.set('_test_int', '42', 'int')
    assert dao.get('_test_int') == 42
    print("[PASS] int type coercion")

    # bool type
    dao.set('_test_bool', 'true', 'bool')
    assert dao.get('_test_bool') is True
    print("[PASS] bool type coercion")

    all_settings = dao.get_all()
    print(f"[PASS] get_all: {len(all_settings)} settings")


def test_tags():
    dao = TagDAO(db)
    # Create file first
    fdao = FileDAO(db)
    fid = fdao.insert({
        'file_path': '/test/tag_test.txt',
        'file_name': 'tag_test.txt',
        'file_extension': '.txt',
        'file_type': 'document',
        'file_size': 100,
    })

    dao.add_tag(fid, '测试标签')
    tags = dao.get_tags_by_file(fid)
    assert len(tags) == 1
    assert tags[0]['tag_name'] == '测试标签'
    print(f"[PASS] add_tag + get_tags_by_file")

    all_tags = dao.get_all_tags()
    print(f"[PASS] get_all_tags: {len(all_tags)} tags")

    dao.remove_tag(fid, '测试标签')
    tags2 = dao.get_tags_by_file(fid)
    assert len(tags2) == 0
    print("[PASS] remove_tag")

    fdao.delete_record(fid)


def test_scan_dirs():
    dao = ScanDirectoryDAO(db)
    did = dao.insert('/test/scan_dir', True)
    assert did > 0
    assert dao.exists('/test/scan_dir')
    print(f"[PASS] insert + exists (id={did})")

    active = dao.get_active()
    print(f"[PASS] get_active: {len(active)} dirs")

    dao.delete(did)


def test_classification():
    cls_dao = ClassificationDAO(db)
    fdao = FileDAO(db)
    fid = fdao.insert({
        'file_path': '/test/cls_test.pdf',
        'file_name': 'cls_test.pdf',
        'file_extension': '.pdf',
        'file_type': 'document',
        'file_size': 500,
    })

    cid = cls_dao.insert(fid, 'by_keyword', '报告')
    assert cid > 0
    print(f"[PASS] insert classification (id={cid})")

    vals = cls_dao.get_distinct_values('by_keyword')
    print(f"[PASS] get_distinct_values: {len(vals)} values")

    fdao.delete_record(fid)


if __name__ == '__main__':
    print("=== SQLite Migration Test Suite ===\n")
    test_db_init()
    test_file_crud()
    test_system_settings()
    test_tags()
    test_scan_dirs()
    test_classification()
    print("\n=== ALL TESTS PASSED ===")
