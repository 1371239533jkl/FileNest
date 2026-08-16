"""测试增量索引落库：事件合并、created/deleted/moved 落库、失败重试。"""
import os
import shutil
import tempfile
import pytest
from unittest.mock import patch

from database.db_manager import DBManager
from database.models import FileDAO
from core.index_updater import merge_events, IncrementalIndexUpdater
from core.file_watcher import FileChangeEvent


@pytest.fixture()
def temp_db(tmp_path):
    """每个测试独立的临时 SQLite 数据库"""
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    return mgr


@pytest.fixture()
def updater(temp_db):
    """注入临时数据库的增量索引更新器"""
    with patch('core.index_updater.db', temp_db):
        yield IncrementalIndexUpdater()


@pytest.fixture()
def file_dao(temp_db):
    return FileDAO(temp_db)


# ═══ 事件合并 ═══

class TestMergeEvents:
    def test_same_path_keeps_last(self):
        events = [
            FileChangeEvent('created', '/a/b.txt'),
            FileChangeEvent('modified', '/a/b.txt'),
        ]
        merged = merge_events(events)
        assert len(merged) == 1
        assert merged[0].event_type == 'modified'

    def test_distinct_paths_kept(self):
        events = [
            FileChangeEvent('created', '/a/1.txt'),
            FileChangeEvent('created', '/a/2.txt'),
        ]
        assert len(merge_events(events)) == 2

    def test_order_stable(self):
        events = [
            FileChangeEvent('created', '/a/2.txt'),
            FileChangeEvent('created', '/a/1.txt'),
        ]
        paths = [e.path for e in merge_events(events)]
        assert paths == ['/a/2.txt', '/a/1.txt']


# ═══ 落库行为 ═══

class TestIncrementalApply:
    def _make_file(self, path, content='hello'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_created_inserts_record(self, updater, file_dao, tmp_path):
        path = self._make_file(str(tmp_path / 'new.txt'))
        stats = updater.apply([FileChangeEvent('created', path)])
        assert stats['applied'] == 1
        record = file_dao.get_by_path(path)
        assert record is not None
        assert record['status'] == 'active'

    def test_deleted_marks_record(self, updater, file_dao, tmp_path):
        path = self._make_file(str(tmp_path / 'gone.txt'))
        updater.apply([FileChangeEvent('created', path)])
        os.remove(path)
        stats = updater.apply([FileChangeEvent('deleted', path)])
        assert stats['applied'] == 1
        record = file_dao.get_by_path(path)
        assert record is None  # get_by_path 只查 active
        by_id = file_dao.get_by_id(1)
        assert by_id['status'] == 'deleted'

    def test_moved_updates_path(self, updater, file_dao, tmp_path):
        src = self._make_file(str(tmp_path / 'src.txt'))
        dest = str(tmp_path / 'dest.txt')
        updater.apply([FileChangeEvent('created', src)])
        os.rename(src, dest)
        stats = updater.apply([FileChangeEvent('moved', src, dest_path=dest)])
        assert stats['applied'] == 1
        assert file_dao.get_by_path(dest) is not None
        assert file_dao.get_by_path(src) is None

    def test_modified_upserts_size(self, updater, file_dao, tmp_path):
        path = self._make_file(str(tmp_path / 'm.txt'), 'a')
        updater.apply([FileChangeEvent('created', path)])
        self._make_file(path, 'a' * 5000)
        updater.apply([FileChangeEvent('modified', path)])
        record = file_dao.get_by_path(path)
        assert record['file_size'] == 5000

    def test_created_missing_file_skipped(self, updater):
        stats = updater.apply([FileChangeEvent('created', '/nonexistent/x.txt')])
        assert stats['applied'] == 1  # 不存在的文件静默跳过，不算失败

    def test_failure_is_isolated(self, updater):
        """一个事件失败不阻断同批其他事件"""
        real = updater.file_dao
        with patch.object(updater, '_apply_one') as mock:
            mock.side_effect = [RuntimeError('boom'),
                                None, None]
            events = [FileChangeEvent('created', '/a/1.txt'),
                      FileChangeEvent('created', '/a/2.txt'),
                      FileChangeEvent('created', '/a/3.txt')]
            stats = updater.apply(events)
        assert stats['applied'] == 2
        assert stats['failed'] == 1
        assert len(stats['errors']) == 1

    def test_retry_then_succeed(self, updater, tmp_path):
        """首次失败、重试成功的路径不应计入 failed"""
        real = updater.file_dao
        path = self._make_file(str(tmp_path / 'r.txt'))
        calls = {'n': 0}

        def flaky(ev):
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('first attempt fails')
            return real.insert({
                'file_path': path, 'file_name': 'r.txt',
                'file_extension': '.txt', 'file_type': 'document',
                'file_size': 5, 'create_time': None, 'modify_time': None,
            })

        with patch.object(updater, '_apply_one', side_effect=flaky):
            stats = updater.apply([FileChangeEvent('created', path)])
        assert stats['applied'] == 1
        assert stats['failed'] == 0
        assert calls['n'] == 2
