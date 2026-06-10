"""
测试 OperationHistoryManager（撤销操作）
使用真实临时文件 + mock DB 层，不依赖 MySQL
"""
import os
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock


class TestOperationHistoryUndo:
    """测试 _undo_rename / _undo_move / _undo_delete"""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp(prefix='sfm_op_hist_')
        # mock DB，让 OperationHistoryManager 不连真实数据库
        self.patcher = patch('core.operation_history.db')
        self.mock_db = self.patcher.start()

        from core.operation_history import OperationHistoryManager
        self.mgr = OperationHistoryManager()
        # 替换 DAO 为 mock
        self.mgr.file_dao = MagicMock()
        self.mgr.history_dao = MagicMock()

    def teardown_method(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── 撤销重命名 ──

    def test_undo_rename_success(self):
        """正常撤销重命名：文件从 new_path 回到 old_path"""
        old_path = os.path.join(self.test_dir, 'old_name.txt')
        new_path = os.path.join(self.test_dir, 'new_name.txt')
        # 模拟重命名后状态：文件已在 new_path
        with open(new_path, 'w') as f:
            f.write('content')

        self.mgr._undo_rename(42, old_path, new_path)

        assert os.path.exists(old_path)
        assert not os.path.exists(new_path)
        self.mgr.file_dao.update_name.assert_called_once_with(
            42, 'old_name.txt', old_path)

    def test_undo_rename_current_not_found(self):
        """撤销重命名时当前文件不存在"""
        with pytest.raises(FileNotFoundError):
            self.mgr._undo_rename(
                42,
                os.path.join(self.test_dir, 'old.txt'),
                os.path.join(self.test_dir, 'nonexistent.txt'))

    def test_undo_rename_old_path_occupied(self):
        """撤销重命名时旧路径被占用"""
        old_path = os.path.join(self.test_dir, 'old.txt')
        new_path = os.path.join(self.test_dir, 'new.txt')
        with open(old_path, 'w') as f:
            f.write('occupied')
        with open(new_path, 'w') as f:
            f.write('content')

        with pytest.raises(FileExistsError):
            self.mgr._undo_rename(42, old_path, new_path)

    # ── 撤销移动 ──

    def test_undo_move_success(self):
        """正常撤销移动：文件从新位置回到旧位置"""
        old_dir = os.path.join(self.test_dir, 'dir_a')
        new_dir = os.path.join(self.test_dir, 'dir_b')
        os.makedirs(old_dir)
        os.makedirs(new_dir)
        old_path = os.path.join(old_dir, 'file.txt')
        new_path = os.path.join(new_dir, 'file.txt')
        with open(new_path, 'w') as f:
            f.write('data')

        self.mgr._undo_move(99, old_path, new_path)

        assert os.path.exists(old_path)
        assert not os.path.exists(new_path)
        self.mgr.file_dao.update_name.assert_called_once()

    def test_undo_move_old_dir_recreated(self):
        """撤销移动时旧目录不存在会自动创建"""
        old_path = os.path.join(self.test_dir, 'gone_dir', 'file.txt')
        new_path = os.path.join(self.test_dir, 'here', 'file.txt')
        os.makedirs(os.path.dirname(new_path))
        with open(new_path, 'w') as f:
            f.write('data')

        self.mgr._undo_move(1, old_path, new_path)

        assert os.path.exists(old_path)
        assert os.path.isdir(os.path.dirname(old_path))

    # ── 撤销删除 ──

    def test_undo_delete_from_trash(self):
        """从回收区恢复文件"""
        old_path = os.path.join(self.test_dir, 'original.txt')
        trash_path = os.path.join(self.test_dir, '.trash', 'abc_original.txt')
        os.makedirs(os.path.dirname(trash_path))
        with open(trash_path, 'w') as f:
            f.write('recovered')

        self.mgr._undo_delete(7, old_path, trash_path)

        assert os.path.exists(old_path)
        assert not os.path.exists(trash_path)
        self.mgr.file_dao.update_status.assert_called_once_with(7, 'active')

    def test_undo_delete_permanent_raises(self):
        """永久删除的文件不可撤销"""
        with pytest.raises(RuntimeError, match="永久删除"):
            self.mgr._undo_delete(7, '/some/path', 'permanent')

    def test_undo_delete_trash_missing(self):
        """回收区文件不存在时仅恢复数据库状态"""
        old_path = os.path.join(self.test_dir, 'gone.txt')
        trash_path = os.path.join(self.test_dir, '.trash', 'nonexistent.txt')

        # 不应抛异常，仅记录警告
        self.mgr._undo_delete(7, old_path, trash_path)

        self.mgr.file_dao.update_status.assert_called_once_with(7, 'active')
        assert not os.path.exists(old_path)

    def test_undo_delete_none_trash_path(self):
        """trash_path 为 None 时仅恢复数据库状态"""
        self.mgr._undo_delete(7, '/any/path', None)
        self.mgr.file_dao.update_status.assert_called_once_with(7, 'active')

    # ── undo_operation 集成 ──

    def test_undo_operation_rename(self):
        """undo_operation 分发到 _undo_rename"""
        old_path = os.path.join(self.test_dir, 'a.txt')
        new_path = os.path.join(self.test_dir, 'b.txt')
        with open(new_path, 'w') as f:
            f.write('data')

        self.mgr.history_dao.get_by_id.return_value = {
            'id': 100,
            'operation_type': 'rename',
            'operation_status': 'completed',
            'undo_available': 1,
            'file_id': 42,
            'old_value': old_path,
            'new_value': new_path,
        }

        result = self.mgr.undo_operation(100)
        assert result is True
        self.mgr.history_dao.mark_undone.assert_called_once_with(100)

    def test_undo_operation_not_completed_raises(self):
        """状态不是 completed 时不可撤销"""
        self.mgr.history_dao.get_by_id.return_value = {
            'id': 101,
            'operation_status': 'undone',
            'undo_available': 0,
        }
        with pytest.raises(ValueError, match="不可撤销"):
            self.mgr.undo_operation(101)

    # ── undo_batch ──

    def test_undo_batch_reverse_order(self):
        """批量撤销按逆序执行"""
        old1 = os.path.join(self.test_dir, 'old1.txt')
        new1 = os.path.join(self.test_dir, 'new1.txt')
        old2 = os.path.join(self.test_dir, 'old2.txt')
        new2 = os.path.join(self.test_dir, 'new2.txt')
        for p in (new1, new2):
            with open(p, 'w') as f:
                f.write('x')

        ops = [
            {'id': 1, 'operation_type': 'rename', 'operation_status': 'completed',
             'undo_available': 1, 'file_id': 10,
             'old_value': old1, 'new_value': new1},
            {'id': 2, 'operation_type': 'rename', 'operation_status': 'completed',
             'undo_available': 1, 'file_id': 11,
             'old_value': old2, 'new_value': new2},
        ]
        self.mgr.history_dao.get_by_batch.return_value = ops
        # undo_operation 内部会再次调用 get_by_id
        self.mgr.history_dao.get_by_id.side_effect = \
            lambda oid: next((o for o in ops if o['id'] == oid), None)

        result = self.mgr.undo_batch('batch_abc')

        assert result['success'] == 2
        assert result['failed'] == 0
        # 逆序：先撤销 id=2，再撤销 id=1
        calls = self.mgr.history_dao.mark_undone.call_args_list
        assert calls[0].args[0] == 2
        assert calls[1].args[0] == 1
