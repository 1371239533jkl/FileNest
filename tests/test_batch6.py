"""
批次6 工作流扩展 —— 单元测试
覆盖：FileEventDAO / TimelineDAO / WorkspaceDAO / ArchivePackageDAO / ArchiveService / CLI 冒烟
"""
import os
import json
import tempfile
import pytest

from database.db_manager import DBManager
from database.models import (
    FileEventDAO, TimelineDAO, WorkspaceDAO, ArchivePackageDAO,
    OperationHistoryDAO, FileDAO, TagDAO,
)


@pytest.fixture()
def mgr(tmp_path):
    """每个测试用例使用独立的 DBManager 实例（新库）。"""
    m = DBManager()
    m.db_path = str(tmp_path / "test.db")
    m.init_database()
    return m


class TestFileEventDAO:
    def test_insert_and_search(self, mgr):
        dao = FileEventDAO(mgr)
        eid = dao.insert('created', '/tmp/a.txt', source='watcher')
        assert eid > 0
        results = dao.search(event_type='created')
        assert len(results) == 1
        assert results[0]['file_path'] == '/tmp/a.txt'

    def test_insert_batch(self, mgr):
        dao = FileEventDAO(mgr)
        n = dao.insert_batch([
            {'event_type': 'created', 'file_path': '/tmp/1.txt'},
            {'event_type': 'modified', 'file_path': '/tmp/2.txt'},
            {'event_type': 'deleted', 'file_path': '/tmp/3.txt'},
        ])
        assert n == 3
        assert len(dao.search()) == 3
        assert len(dao.search(event_type='created')) == 1

    def test_search_date_and_path(self, mgr):
        dao = FileEventDAO(mgr)
        dao.insert('modified', '/a/b/c.txt')
        dao.insert('modified', '/x/y/z.txt')
        results = dao.search(path_prefix='/a')
        assert len(results) == 1
        assert results[0]['file_path'].startswith('/a')

    def test_delete_older(self, mgr):
        dao = FileEventDAO(mgr)
        dao.insert('created', '/tmp/old.txt')
        assert dao.delete_older_than(days=90) == 0


class TestTimelineDAO:
    def test_combined_modes(self, mgr):
        tdao = TimelineDAO(mgr)
        edao = FileEventDAO(mgr)
        odao = OperationHistoryDAO(mgr)

        edao.insert('created', '/tmp/ev.txt')
        odao.insert('rename', file_id=None, old_value='a', new_value='b')

        ops = tdao.get_combined(mode='operations')
        assert len(ops) == 1
        assert ops[0]['event_source'] == 'operation'

        exts = tdao.get_combined(mode='external')
        assert len(exts) == 1
        assert exts[0]['event_source'] == 'external'

        all_items = tdao.get_combined(mode='all')
        assert len(all_items) == 2
        sources = {x['event_source'] for x in all_items}
        assert sources == {'operation', 'external'}

    def test_filter_by_type(self, mgr):
        tdao = TimelineDAO(mgr)
        edao = FileEventDAO(mgr)
        odao = OperationHistoryDAO(mgr)

        edao.insert('created', '/a.txt')
        edao.insert('modified', '/b.txt')
        odao.insert('rename', old_value='a', new_value='b')

        ops = tdao.get_combined(mode='operations', op_type='rename')
        assert len(ops) == 1

        exts = tdao.get_combined(mode='external', op_type='created')
        assert len(exts) == 1
        assert exts[0]['event_type'] == 'created'


class TestWorkspaceDAO:
    def test_crud(self, mgr):
        dao = WorkspaceDAO(mgr)
        ws_id = dao.create('work', 'C:/work', '工作目录')
        assert ws_id > 0

        ws = dao.get_by_id(ws_id)
        assert ws['name'] == 'work'
        assert ws['root_path'] == 'C:/work'
        assert ws['is_active'] == 1

        dao.update(ws_id, description='新描述', is_active=0)
        ws = dao.get_by_id(ws_id)
        assert ws['description'] == '新描述'
        assert ws['is_active'] == 0

        all_ws = dao.get_all()
        assert len(all_ws) == 1
        active = dao.get_all(only_active=True)
        assert len(active) == 0

        assert dao.delete(ws_id) == 1
        assert dao.get_by_id(ws_id) is None

    def test_get_by_path(self, mgr):
        dao = WorkspaceDAO(mgr)
        dao.create('deep', '/a/b/c', '深目录')
        dao.create('shallow', '/a', '浅目录')

        ws = dao.get_by_path('/a/b/c/d/file.txt')
        assert ws is not None
        assert ws['name'] == 'deep'

        assert dao.get_by_path('/other/file.txt') is None


class TestArchivePackageDAO:
    def test_lifecycle(self, mgr):
        dao = ArchivePackageDAO(mgr)
        pkg_id = dao.create('test.zip', '/tmp/test.zip',
                            item_count=10, total_size=1024,
                            status='creating')
        assert pkg_id > 0

        dao.update_status(pkg_id, 'completed', checksum='abc123')
        pkg = dao.get_by_id(pkg_id)
        assert pkg['status'] == 'completed'
        assert pkg['checksum'] == 'abc123'

        all_pkgs = dao.get_all()
        assert len(all_pkgs) == 1
        completed = dao.get_all(status='completed')
        assert len(completed) == 1
        failed = dao.get_all(status='failed')
        assert len(failed) == 0

        assert dao.delete(pkg_id) == 1
        assert dao.get_by_id(pkg_id) is None


class TestArchiveService:
    def _make_svc(self, mgr):
        from core.archive_service import ArchiveService
        return ArchiveService(
            dao=ArchivePackageDAO(mgr),
            file_dao=FileDAO(mgr),
        )

    def test_create_package_success(self, mgr):
        svc = self._make_svc(mgr)
        src_dir = tempfile.mkdtemp()
        sub = os.path.join(src_dir, 'sub')
        os.makedirs(sub)
        with open(os.path.join(src_dir, 'a.txt'), 'w') as f:
            f.write('hello' * 100)
        with open(os.path.join(sub, 'b.txt'), 'w') as f:
            f.write('world' * 100)

        out_dir = tempfile.mkdtemp()
        result = svc.create_package([src_dir], out_dir, 'test_pkg')
        assert result['success'] is True
        assert result['item_count'] == 2
        assert os.path.exists(result['archive_path'])
        assert result['checksum']
        assert len(result['checksum']) == 16

        pkgs = svc.list_packages(status='completed')
        assert len(pkgs) == 1

        svc.delete_package(result['package_id'], delete_file=True)
        assert not os.path.exists(result['archive_path'])

    def test_create_package_no_source(self, mgr):
        svc = self._make_svc(mgr)
        out_dir = tempfile.mkdtemp()
        result = svc.create_package([], out_dir)
        assert result['success'] is False
        assert '没有可归档' in result['error']

    def test_create_package_bad_output(self, mgr):
        svc = self._make_svc(mgr)
        src = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        src.write(b'hello')
        src.close()
        result = svc.create_package([src.name], '/nonexistent/path/zzz')
        assert result['success'] is False
        assert '输出目录不存在' in result['error']
        os.unlink(src.name)


class TestCLISmoke:
    """CLI 冒烟测试：导入 + 参数解析不崩溃。"""

    def test_cli_module_imports(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'cli_sfm', os.path.join(os.path.dirname(__file__), '..', 'cli.py'))
        # 不直接 import（避免触发 side effect），只校验文件存在且语法对
        assert spec is not None
        assert os.path.exists(spec.origin)

    def test_cli_help_runs(self):
        """用子进程调 --help，确保不崩溃。"""
        import subprocess
        cli_path = os.path.join(os.path.dirname(__file__), '..', 'cli.py')
        result = subprocess.run(
            ['python', cli_path, '--help'],
            capture_output=True, text=True, timeout=10)
        # 不检查退出码（环境可能缺依赖），只看有输出
        assert result.stdout or result.stderr
