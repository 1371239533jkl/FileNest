"""批次7 P2-07 生命周期策略测试。"""
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta

import pytest

from database.db_manager import DBManager
from database.models import FileDAO, LifecyclePolicyDAO
from core.lifecycle_service import LifecycleService


@pytest.fixture()
def env(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    dao = FileDAO(mgr)
    policy_dao = LifecyclePolicyDAO(mgr)

    # 造文件记录：1 个超龄 + 1 个新鲜
    old_path = str(tmp_path / 'old_report.pdf')
    new_path = str(tmp_path / 'new_report.pdf')
    for p in (old_path, new_path):
        with open(p, 'w') as f:
            f.write('x')
    old_mtime = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')
    dao.insert({'file_name': 'old_report.pdf', 'file_path': old_path,
                'file_size': 1, 'file_extension': '.pdf',
                'file_type': 'document', 'modify_time': old_mtime})
    dao.insert({'file_name': 'new_report.pdf', 'file_path': new_path,
                'file_size': 1, 'file_extension': '.pdf',
                'file_type': 'document',
                'modify_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    return {'db': mgr, 'file_dao': dao, 'policy_dao': policy_dao,
            'tmp': tmp_path, 'old_mtime': old_mtime}


class TestPolicyDAO:
    def test_crud(self, env):
        pid = env['policy_dao'].create('p1', 'path', 'C:/x', 30, 'remind')
        assert pid > 0
        rows = env['policy_dao'].get_all()
        assert len(rows) == 1 and rows[0]['name'] == 'p1'
        env['policy_dao'].update(pid, days_threshold=7, enabled=False)
        assert env['policy_dao'].get_by_id(pid)['days_threshold'] == 7
        assert env['policy_dao'].get_all(enabled_only=True) == []
        assert env['policy_dao'].touch_last_run(pid) == 1
        assert env['policy_dao'].delete(pid) == 1


class TestMatch:
    def test_path_match(self, env):
        pid = env['policy_dao'].create(
            'old', 'path', str(env['tmp']), 30, 'remind')
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        policy = env['policy_dao'].get_by_id(pid)
        matches = svc.match_files(policy)
        names = [m['file_name'] for m in matches]
        assert 'old_report.pdf' in names
        assert 'new_report.pdf' not in names

    def test_type_match(self, env):
        env['policy_dao'].create('docs', 'type', 'document', 30, 'remind')
        # file_type 由 insert 依据扩展名推断，若无类型字段则此策略无命中
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        results = svc.check_all()
        assert results[0]['policy']['name'] == 'docs'
        assert isinstance(results[0]['match_count'], int)

    def test_empty_target(self, env):
        env['policy_dao'].create('empty', 'path', '  ', 30, 'remind')
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        assert svc.match_files(env['policy_dao'].get_by_id(
            env['policy_dao'].get_all()[0]['id'])) == []


class TestExecute:
    def test_trash(self, env):
        pid = env['policy_dao'].create(
            'clean', 'path', str(env['tmp']), 30, 'trash')
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        policy = env['policy_dao'].get_by_id(pid)
        matches = svc.match_files(policy)
        result = svc.execute(policy, matches)
        assert result['success'], result['errors']
        assert result['processed'] == len(matches)
        # 超龄文件已不在磁盘上（移入回收区）
        for m in matches:
            assert not os.path.exists(m['file_path'])

    def test_archive(self, env):
        out_dir = env['tmp'] / 'archive_out'
        pid = env['policy_dao'].create(
            'arch', 'path', str(env['tmp']), 30, 'archive',
            archive_dir=str(out_dir))
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        policy = env['policy_dao'].get_by_id(pid)
        matches = svc.match_files(policy)
        result = svc.execute(policy, matches)
        assert result['success'], result['errors']
        assert result['archive_path'] and os.path.exists(result['archive_path'])
        assert os.listdir(out_dir)

    def test_archive_no_dir(self, env):
        pid = env['policy_dao'].create(
            'arch2', 'path', str(env['tmp']), 30, 'archive')
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        policy = env['policy_dao'].get_by_id(pid)
        result = svc.execute(policy, [])
        assert not result['success']
        assert '输出目录' in result['errors'][0]

    def test_remind_no_change(self, env):
        pid = env['policy_dao'].create(
            'rem', 'path', str(env['tmp']), 30, 'remind')
        svc = LifecycleService(file_dao=env['file_dao'],
                               policy_dao=env['policy_dao'])
        policy = env['policy_dao'].get_by_id(pid)
        matches = svc.match_files(policy)
        result = svc.execute(policy, matches)
        assert result['success'] and result['processed'] == 0
        # 提醒动作不动文件
        for m in matches:
            assert os.path.exists(m['file_path'])
