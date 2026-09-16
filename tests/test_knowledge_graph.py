"""批次7 P2-05 知识图谱测试。"""
import pytest

from database.db_manager import DBManager
from database.models import FileDAO, TagDAO
from core.knowledge_graph import GraphService


@pytest.fixture()
def env(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    file_dao = FileDAO(mgr)
    tag_dao = TagDAO(mgr)

    # 两个共享标签的文件 + 一个孤立文件
    ids = []
    for i, name in enumerate(['a_v1.pdf', 'a_v2.pdf', 'lonely.txt']):
        p = str(tmp_path / name)
        ids.append(file_dao.insert({
            'file_name': name, 'file_path': p, 'file_size': 1,
            'file_extension': '.pdf' if name.endswith('pdf') else '.txt',
            'file_type': 'document',
            'modify_time': '2026-01-01 00:00:00'}))
    mgr.execute_update(
        "INSERT OR IGNORE INTO tags (tag_name, create_time) VALUES "
        "('报告', '2026-01-01 00:00:00')")
    mgr.execute_update(
        "INSERT INTO file_tags (file_id, tag_name, create_time) VALUES "
        "(?, ?, ?), (?, ?, ?)",
        (ids[0], '报告', '2026-01-01 00:00:00',
         ids[1], '报告', '2026-01-01 00:00:00'))
    mgr.execute_update(
        "INSERT INTO file_relations (file_id_a, file_id_b, relation, "
        "confidence, status, create_time) VALUES (?, ?, 'version', 0.9, "
        "'confirmed', '2026-01-01 00:00:00')",
        (ids[0], ids[1]))
    return {'db': mgr, 'file_dao': file_dao, 'tag_dao': tag_dao,
            'ids': ids, 'tmp': tmp_path}


class TestNeighborhood:
    def test_file_neighborhood(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        g = svc.file_neighborhood(env['ids'][0])
        kinds = {n['kind'] for n in g['nodes']}
        assert 'file' in kinds and 'tag' in kinds and 'dir' in kinds
        labels = {n['label'] for n in g['nodes']}
        assert '#报告' in labels
        assert 'a_v2.pdf' in labels          # 共享标签 + 版本关系
        edge_kinds = {e['kind'] for e in g['edges']}
        assert 'tag' in edge_kinds and 'version' in edge_kinds

    def test_tag_neighborhood(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        g = svc.tag_neighborhood('报告')
        assert any(n['id'] == 'tag:报告' for n in g['nodes'])
        file_labels = [n['label'] for n in g['nodes'] if n['kind'] == 'file']
        assert 'a_v1.pdf' in file_labels and 'a_v2.pdf' in file_labels

    def test_dir_neighborhood(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        g = svc.directory_neighborhood(str(env['tmp']))
        assert len([n for n in g['nodes'] if n['kind'] == 'file']) >= 3

    def test_missing_file(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        assert svc.file_neighborhood(99999) == {'nodes': [], 'edges': []}

    def test_unified_entry(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        g = svc.neighborhood('tag', '报告')
        assert g['nodes']
        assert svc.neighborhood('bad', 'x') == {'nodes': [], 'edges': []}


class TestHubAndSearch:
    def test_hub_files(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        hubs = svc.hub_files(10)
        # 两个共享标签 + 版本关系的文件应为枢纽
        names = {h['file_name'] for h in hubs}
        assert 'a_v1.pdf' in names and 'a_v2.pdf' in names
        assert 'lonely.txt' not in names

    def test_search_centers(self, env):
        svc = GraphService(file_dao=env['file_dao'], tag_dao=env['tag_dao'],
                           db_manager=env['db'])
        result = svc.search_centers('a_v')
        assert any(r['kind'] == 'file' and r['label'] == 'a_v1.pdf'
                   for r in result)
        result2 = svc.search_centers('报告')
        assert any(r['kind'] == 'tag' for r in result2)
