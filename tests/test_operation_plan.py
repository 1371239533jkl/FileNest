"""测试操作计划模型：构建、统计、过期校验、冲突检测、特殊字符容错。"""
import os
import tempfile
import time
import shutil
import pytest

from core.operation_plan import OperationPlan, OperationPlanBuilder, PLAN_TTL_SECONDS
from core.rule_engine import NLSearchParser


class TestOperationPlan:
    def test_delete_plan_stats(self):
        plan = OperationPlan(action='delete', items=[])
        plan.items = [
            type('I', (), {'file_id': 1, 'old_path': '/a', 'new_path': '',
                           'action': 'delete', 'conflict': False,
                           'irreversible': False, 'reason': '', 'size': 100})(),
            type('I', (), {'file_id': 2, 'old_path': '/b', 'new_path': '',
                           'action': 'delete', 'conflict': True,
                           'irreversible': True, 'reason': '', 'size': 50})(),
        ]
        assert plan.total_size == 150
        assert plan.freed_space == 150
        assert plan.conflict_count == 1
        assert plan.irreversible_count == 1

    def test_expired(self):
        plan = OperationPlan(action='move')
        assert plan.is_expired() is False
        plan.created_at = time.time() - PLAN_TTL_SECONDS - 10
        assert plan.is_expired() is True

    def test_validate_missing_source(self, tmp_path):
        plan = OperationPlan(action='move')
        plan.items = [
            type('I', (), {'file_id': 1, 'old_path': str(tmp_path / 'nope.txt'),
                           'new_path': '', 'action': 'move', 'conflict': False,
                           'irreversible': False, 'reason': '', 'size': 0})()
        ]
        problems = plan.validate()
        assert any('源文件已不存在' in p for p in problems)

    def test_validate_expired(self):
        plan = OperationPlan(action='move')
        plan.created_at = time.time() - PLAN_TTL_SECONDS - 1
        problems = plan.validate()
        assert any('过期' in p for p in problems)

    def test_validate_ok(self, tmp_path):
        f = tmp_path / 'ok.txt'
        f.write_text('x')
        plan = OperationPlan(action='move')
        plan.items = [
            type('I', (), {'file_id': 1, 'old_path': str(f), 'new_path': '',
                           'action': 'move', 'conflict': False,
                           'irreversible': False, 'reason': '', 'size': 1})()
        ]
        assert plan.validate() == []


class TestOperationPlanBuilder:
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp(prefix='sfm_plan_')
        self.src = os.path.join(self.test_dir, 'a.txt')
        with open(self.src, 'w') as f:
            f.write('data')

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _record(self, fid=1, name='a.txt', size=4):
        return {'id': fid, 'file_path': os.path.join(self.test_dir, name),
                'file_name': name, 'file_size': size, 'file_type': 'document',
                'file_extension': '.txt'}

    def test_build_delete(self):
        plan = OperationPlanBuilder().build('delete', [self._record()])
        assert len(plan.items) == 1
        assert plan.items[0].action == 'delete'
        assert plan.items[0].irreversible is False

    def test_build_move_conflict(self):
        target = os.path.join(self.test_dir, 'target')
        os.makedirs(target, exist_ok=True)
        conflict_path = os.path.join(target, 'a.txt')
        with open(conflict_path, 'w') as f:
            f.write('existing')
        plan = OperationPlanBuilder().build('move', [self._record()], target=target)
        assert plan.items[0].conflict is True

    def test_build_move_ok(self):
        target = os.path.join(self.test_dir, 'empty_target')
        os.makedirs(target, exist_ok=True)
        plan = OperationPlanBuilder().build('move', [self._record()], target=target)
        assert plan.items[0].conflict is False

    def test_build_rename(self):
        plan = OperationPlanBuilder().build(
            'rename', [self._record()], target='{type}_{original_name}{ext}')
        assert plan.items[0].new_path.endswith('document_a.txt')

    def test_summary_contains_key_info(self):
        plan = OperationPlanBuilder().build('delete', [self._record()])
        text = plan.summary()
        assert 'delete' in text or 'delete' in text.lower() or '操作计划' in text
        assert '1 项' in text


class TestNLSyntaxRobustness:
    """特殊字符不导致查询错误、语法提示可用"""

    def setup_method(self):
        self.parser = NLSearchParser()

    def test_special_chars_no_crash(self):
        for q in ['a&b|c(d)e[f]g{h}i;j,k', '!!!??', '***', '\\path\\with\\slashes',
                  'null\x00byte', '()[]{}\'"\\', '', '   ']:
            result = self.parser.parse(q)
            assert isinstance(result, dict)

    def test_normal_query_parses(self):
        result = self.parser.parse('大于100MB的图片')
        assert result.get('file_type') == 'image'
        assert result.get('min_size') == 100 * 1024 * 1024

    def test_syntax_help_available(self):
        help_text = NLSearchParser.syntax_help()
        assert '图片' in help_text
        assert 'PDF' in help_text or 'pdf' in help_text

    def test_parse_with_explanation(self):
        result = self.parser.parse_with_explanation('上周的PDF')
        assert 'explanation' in result
        assert 'raw' in result
        assert result['raw'] == '上周的PDF'
