"""测试多阶段重复检测与安全清理中心。"""
import os
import shutil
import pytest
from unittest.mock import patch

from database.db_manager import DBManager
from database.models import FileDAO
from core.multistage_dedup import MultistageDedupDetector, find_duplicates_multistage
from core.cleanup_center import CleanupCenter


@pytest.fixture()
def temp_db(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    return mgr


@pytest.fixture()
def file_dao(temp_db):
    return FileDAO(temp_db)


def _insert(file_dao, tmp_path, name, content, size=None):
    """在临时目录写文件并入库，返回 record。"""
    path = os.path.join(str(tmp_path), name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    info = {
        'file_path': path, 'file_name': name, 'original_name': None,
        'file_extension': os.path.splitext(name)[1], 'file_type': 'document',
        'file_size': size if size is not None else len(content.encode()),
        'file_hash': None, 'create_time': None, 'modify_time': None,
    }
    file_id = file_dao.insert(info)
    return file_dao.get_by_id(file_id)


class TestMultistageDedup:
    def test_no_duplicates(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'a.txt', 'aaa')
        _insert(file_dao, tmp_path, 'b.txt', 'bbb')
        with patch('core.multistage_dedup.db', temp_db):
            stats = MultistageDedupDetector(file_dao).run()
        assert stats['dup_groups'] == 0
        assert stats['dup_files'] == 0

    def test_identical_files_detected(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'a.txt', 'same content')
        _insert(file_dao, tmp_path, 'b.txt', 'same content')
        with patch('core.multistage_dedup.db', temp_db):
            stats = MultistageDedupDetector(file_dao).run()
        assert stats['dup_groups'] == 1
        assert stats['dup_files'] == 2

    def test_same_size_different_content_not_dup(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'a.txt', 'AAAA')
        _insert(file_dao, tmp_path, 'b.txt', 'BBBB')
        with patch('core.multistage_dedup.db', temp_db):
            stats = MultistageDedupDetector(file_dao).run()
        assert stats['dup_groups'] == 0

    def test_missing_file_not_marked(self, temp_db, file_dao, tmp_path):
        rec1 = _insert(file_dao, tmp_path, 'a.txt', 'same')
        _insert(file_dao, tmp_path, 'b.txt', 'same')
        os.remove(rec1['file_path'])  # 源文件缺失，完整哈希返回 None
        with patch('core.multistage_dedup.db', temp_db):
            stats = MultistageDedupDetector(file_dao).run()
        # 缺失文件无法确认，不构成重复组
        assert stats['dup_groups'] == 0
        assert stats['dup_files'] == 0

    def test_resume_skips_computed(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'a.txt', 'same content')
        _insert(file_dao, tmp_path, 'b.txt', 'same content')
        with patch('core.multistage_dedup.db', temp_db):
            detector = MultistageDedupDetector(file_dao)
            stats1 = detector.run()
            stats2 = detector.run()  # 再次运行：续算应跳过已 full 的记录
        assert stats1['full_computed'] == 2
        assert stats2['full_computed'] == 0  # 全部续算跳过
        assert stats2['dup_groups'] == 1

    def test_find_duplicates_compat(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'a.txt', 'dup data')
        _insert(file_dao, tmp_path, 'b.txt', 'dup data')
        with patch('core.multistage_dedup.db', temp_db):
            groups = find_duplicates_multistage()
        assert len(groups) == 1
        assert len(list(groups.values())[0]) == 2

    def test_main_page_dao_reads_detection_results(self, temp_db, file_dao, tmp_path):
        """主页面 DAO 应能读取多阶段检测标记的重复组。"""
        _insert(file_dao, tmp_path, 'a.txt', 'dup content')
        _insert(file_dao, tmp_path, 'b.txt', 'dup content')
        with patch('core.multistage_dedup.db', temp_db):
            MultistageDedupDetector(file_dao).run()
        assert file_dao.count_duplicate_groups_by_flag() == 1
        groups = file_dao.get_duplicate_groups_paginated_by_flag(page=0, page_size=50)
        assert len(groups) == 1
        assert groups[0]['file_count'] == 2
        assert groups[0]['wasted_size'] > 0
        files = file_dao.get_duplicate_group_files_by_flag(groups[0]['group_id'])
        assert len(files) == 2
        assert file_dao.get_duplicate_total_wasted_by_flag() > 0

    def test_main_page_dao_empty_before_detection(self, temp_db, file_dao, tmp_path):
        """未运行多阶段检测时，主页面重复组应为空（权威结果来自检测）。"""
        _insert(file_dao, tmp_path, 'a.txt', 'dup content')
        _insert(file_dao, tmp_path, 'b.txt', 'dup content')
        assert file_dao.count_duplicate_groups_by_flag() == 0


class TestCleanupCenter:
    def test_analyze_categories(self, temp_db, file_dao, tmp_path):
        # 空文件
        _insert(file_dao, tmp_path, 'empty.txt', '', size=0)
        # 临时文件
        _insert(file_dao, tmp_path, 'cache.tmp', 'temp')
        with patch('core.cleanup_center.db', temp_db):
            center = CleanupCenter(file_dao=file_dao)
            result = center.analyze()
        paths = [item['file_path'] for item in result['all']]
        assert any('empty.txt' in p for p in paths)
        assert any('cache.tmp' in p for p in paths)

    def test_exclusion_filters(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'cache.tmp', 'temp')
        with patch('core.cleanup_center.db', temp_db):
            center = CleanupCenter(file_dao=file_dao)
            center.add_exclusion(str(tmp_path), '测试目录')
            result = center.analyze()
        assert result['all'] == []

    def test_false_positive_filters(self, temp_db, file_dao, tmp_path):
        _insert(file_dao, tmp_path, 'cache.tmp', 'temp')
        with patch('core.cleanup_center.db', temp_db):
            center = CleanupCenter(file_dao=file_dao)
            # 先分析得到 path，再标记误报
            result = center.analyze()
            target = result['all'][0]['file_path']
            center.mark_false_positive(target)
            result2 = center.analyze()
        assert len(result2['all']) == 0

    def test_execute_cleanup_moves_to_trash(self, temp_db, file_dao, tmp_path):
        import core.file_manager as fm
        _insert(file_dao, tmp_path, 'cache.tmp', 'temp')
        original_trash = fm._TRASH_DIR
        trash = os.path.join(str(tmp_path), '.trash_test')
        fm._TRASH_DIR = trash
        try:
            with patch('core.cleanup_center.db', temp_db):
                center = CleanupCenter(file_dao=file_dao)
                result = center.analyze()
                target = result['all'][0]
                outcome = center.execute_cleanup([target])
            assert outcome['moved'] == 1
            # 文件已移出原位置
            assert not os.path.exists(target['file_path'])
            # 记录标记为 deleted
            assert file_dao.get_by_id(target['file_id'])['status'] == 'deleted'
        finally:
            fm._TRASH_DIR = original_trash
