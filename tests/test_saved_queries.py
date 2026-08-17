"""测试智能集合（saved_queries）DAO：增改查删、JSON 参数存取。"""
import pytest

from database.db_manager import DBManager
from database.models import SavedQueryDAO


@pytest.fixture()
def dao(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    return SavedQueryDAO(mgr)


class TestSavedQueryDAO:
    def test_insert_and_get(self, dao):
        dao.upsert('大文件', {'min_size': 104857600})
        row = dao.get_by_name('大文件')
        assert row is not None
        assert row['params']['min_size'] == 104857600

    def test_upsert_same_name_updates(self, dao):
        dao.upsert('集合', {'file_type': 'image'})
        dao.upsert('集合', {'file_type': 'video'})
        assert dao.count() == 1
        row = dao.get_by_name('集合')
        assert row['params']['file_type'] == 'video'

    def test_get_all_ordered(self, dao):
        dao.upsert('a', {'name': 'a'})
        dao.upsert('b', {'name': 'b'})
        rows = dao.get_all()
        assert len(rows) == 2
        # 每个都有可用的 params dict
        for row in rows:
            assert isinstance(row['params'], dict)

    def test_delete(self, dao):
        dao.upsert('临时', {})
        assert dao.count() == 1
        dao.delete('临时')
        assert dao.count() == 0
        assert dao.get_by_name('临时') is None

    def test_params_json_roundtrip(self, dao):
        params = {'name': '合同', 'file_type': 'document', 'start_date': '2026-01-01 00:00:00'}
        dao.upsert('合同', params)
        row = dao.get_by_name('合同')
        assert row['params'] == params
