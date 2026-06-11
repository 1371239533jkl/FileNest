"""测试 Phase 3 新增功能：ETA、空状态、文件监控"""
import os
import sys
import tempfile
import time
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.file_scanner import _format_eta, get_file_type, is_hidden_file
from core.file_watcher import FileChangeEvent, DirectoryWatcher, WatcherManager
from ui.empty_state import EmptyStateWidget, create_empty_state, EMPTY_STATES


# ═══ ETA 格式化测试 ═══

class TestFormatEta:
    def test_negative(self):
        assert _format_eta(-1) == "即将完成"
        assert _format_eta(-100) == "即将完成"

    def test_seconds(self):
        assert _format_eta(0) == "约 0 秒"
        assert _format_eta(5) == "约 5 秒"
        assert _format_eta(30.5) == "约 30 秒"
        assert _format_eta(59.9) == "约 59 秒"

    def test_minutes(self):
        assert _format_eta(60) == "约 1 分 0 秒"
        assert _format_eta(90) == "约 1 分 30 秒"
        assert _format_eta(300) == "约 5 分 0 秒"
        assert _format_eta(3599) == "约 59 分 59 秒"

    def test_hours(self):
        assert _format_eta(3600) == "约 1 时 0 分"
        assert _format_eta(5400) == "约 1 时 30 分"
        assert _format_eta(86400) == "约 24 时 0 分"

    def test_float_input(self):
        assert _format_eta(1.5) == "约 1 秒"
        assert _format_eta(120.9) == "约 2 分 0 秒"


# ═══ 文件类型识别测试 ═══

class TestGetFileType:
    def test_image_extensions(self):
        assert get_file_type('.jpg') == 'image'
        assert get_file_type('.JPG') == 'image'
        assert get_file_type('.png') == 'image'
        assert get_file_type('.gif') == 'image'
        assert get_file_type('.bmp') == 'image'
        assert get_file_type('.webp') == 'image'

    def test_document_extensions(self):
        assert get_file_type('.pdf') == 'document'
        assert get_file_type('.doc') == 'document'
        assert get_file_type('.docx') == 'document'
        assert get_file_type('.txt') == 'document'
        assert get_file_type('.md') == 'document'

    def test_video_extensions(self):
        assert get_file_type('.mp4') == 'video'
        assert get_file_type('.avi') == 'video'
        assert get_file_type('.mkv') == 'video'

    def test_audio_extensions(self):
        assert get_file_type('.mp3') == 'audio'
        assert get_file_type('.wav') == 'audio'
        assert get_file_type('.flac') == 'audio'

    def test_archive_extensions(self):
        assert get_file_type('.zip') == 'archive'
        assert get_file_type('.rar') == 'archive'
        assert get_file_type('.7z') == 'archive'

    def test_code_extensions(self):
        assert get_file_type('.py') == 'code'
        assert get_file_type('.js') == 'code'
        assert get_file_type('.ts') == 'code'

    def test_unknown_extension(self):
        assert get_file_type('.xyz') == 'other'
        assert get_file_type('.abc') == 'other'
        assert get_file_type('') == 'other'


# ═══ 隐藏文件检测测试 ═══

class TestIsHiddenFile:
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp(prefix='sfm_test_hidden_')

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normal_file(self):
        path = os.path.join(self.test_dir, 'normal.txt')
        with open(path, 'w') as f:
            f.write('test')
        assert is_hidden_file(path) is False

    def test_dotfile(self):
        """Linux/macOS 风格：以 . 开头的文件"""
        path = os.path.join(self.test_dir, '.hidden')
        with open(path, 'w') as f:
            f.write('test')
        # 在 Windows 上 .开头文件不一定是隐藏属性
        result = is_hidden_file(path)
        assert isinstance(result, bool)


# ═══ FileChangeEvent 测试 ═══

class TestFileChangeEvent:
    def test_basic_event(self):
        event = FileChangeEvent('created', '/path/to/file.txt')
        assert event.event_type == 'created'
        assert event.path == '/path/to/file.txt'
        assert event.is_directory is False

    def test_directory_event(self):
        event = FileChangeEvent('deleted', '/path/to/dir', is_directory=True)
        assert event.event_type == 'deleted'
        assert event.is_directory is True

    def test_repr(self):
        event = FileChangeEvent('modified', '/test.py')
        assert 'modified' in repr(event)
        assert '/test.py' in repr(event)

    def test_all_event_types(self):
        for etype in ['created', 'modified', 'deleted', 'moved']:
            event = FileChangeEvent(etype, '/some/path')
            assert event.event_type == etype


# ═══ DirectoryWatcher 测试 ═══

class TestDirectoryWatcher:
    def test_init(self):
        watcher = DirectoryWatcher()
        assert watcher.is_running() is False
        assert watcher._pending_events == []
        assert watcher._enabled is False

    def test_stop_without_start(self):
        """未启动时调用 stop 不应报错"""
        watcher = DirectoryWatcher()
        watcher.stop()  # 不应抛异常
        assert watcher.is_running() is False

    def test_start_nonexistent_dir(self):
        """不存在的目录不应导致崩溃"""
        watcher = DirectoryWatcher()
        watcher.start(['/nonexistent/path/abc123'])
        assert watcher.is_running() is False

    def test_start_empty_list(self):
        """空目录列表不应启动"""
        watcher = DirectoryWatcher()
        watcher.start([])
        assert watcher.is_running() is False

    def test_start_valid_dir(self):
        """启动有效目录的监控"""
        test_dir = tempfile.mkdtemp(prefix='sfm_watcher_')
        try:
            watcher = DirectoryWatcher()
            watcher.start([test_dir])
            assert watcher.is_running() is True
            watcher.stop()
            assert watcher.is_running() is False
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_is_ignored(self):
        """测试忽略规则"""
        watcher = DirectoryWatcher()
        assert watcher._is_ignored('/path/.git/config') is True
        assert watcher._is_ignored('/path/__pycache__/module.pyc') is True
        assert watcher._is_ignored('/path/.trash/file.txt') is True
        assert watcher._is_ignored('/path/.DS_Store') is True
        assert watcher._is_ignored('/path/normal_file.txt') is False

    def test_debounce_timer(self):
        """防抖计时器初始化"""
        watcher = DirectoryWatcher()
        # QTimer 延迟到 start() 中创建
        assert watcher._debounce_timer is None
        
        # 启动后 QTimer 应该被创建
        import tempfile
        test_dir = tempfile.mkdtemp(prefix='sfm_watcher_timer_')
        try:
            watcher.start([test_dir])
            assert watcher._debounce_timer is not None
            assert watcher._debounce_timer.interval() == 2000
            assert watcher._debounce_timer.isSingleShot() is True
            watcher.stop()
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)


# ═══ WatcherManager 测试 ═══

class TestWatcherManager:
    def test_singleton(self):
        mgr1 = WatcherManager.get_instance()
        mgr2 = WatcherManager.get_instance()
        assert mgr1 is mgr2

    def test_enable_disable(self):
        test_dir = tempfile.mkdtemp(prefix='sfm_watcher_mgr_')
        try:
            mgr = WatcherManager()
            mgr.enable([test_dir])
            assert mgr.is_active() is True
            mgr.disable()
            assert mgr.is_active() is False
        finally:
            mgr.disable()
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_enable_empty_dirs(self):
        mgr = WatcherManager()
        mgr.enable([])
        assert mgr.is_active() is False


# ═══ EmptyState 组件测试 ═══

class TestEmptyStateConfigs:
    def test_all_configs_present(self):
        """验证所有预定义配置都存在"""
        expected_keys = [
            'dashboard', 'scan', 'classify', 'search',
            'history', 'recycle_bin', 'duplicates', 'tags'
        ]
        for key in expected_keys:
            assert key in EMPTY_STATES, f"缺少空状态配置: {key}"

    def test_config_structure(self):
        """验证每个配置都有必要的字段"""
        for key, config in EMPTY_STATES.items():
            assert 'icon' in config, f"{key} 缺少 icon"
            assert 'title' in config, f"{key} 缺少 title"
            assert 'description' in config, f"{key} 缺少 description"
            assert len(config['icon']) > 0, f"{key} 的 icon 为空"
            assert len(config['title']) > 0, f"{key} 的 title 为空"
            assert len(config['description']) > 0, f"{key} 的 description 为空"


class TestCreateEmptyState:
    def test_create_with_valid_key(self):
        widget = create_empty_state('dashboard')
        assert widget is not None
        assert widget.isVisible() is False  # 默认隐藏

    def test_create_with_invalid_key(self):
        """无效 key 应使用默认配置"""
        widget = create_empty_state('nonexistent_key')
        assert widget is not None
        assert widget.isVisible() is False

    def test_create_with_callback(self):
        called = [False]
        def callback():
            called[0] = True
        widget = create_empty_state('scan', action_text="开始扫描",
                                     action_callback=callback)
        assert widget is not None

    def test_default_hidden(self):
        """空状态组件默认不可见"""
        widget = create_empty_state('history')
        assert widget.isVisible() is False
