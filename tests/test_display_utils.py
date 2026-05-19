"""测试 display_utils 工具函数"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.display_utils import format_size, truncate_path


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(1) == "1 B"
        assert format_size(1023) == "1023 B"

    def test_kb(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1500) == "1.5 KB"
        assert format_size(1024 * 1024 - 1) == "1024.0 KB"

    def test_mb(self):
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(2 * 1024 * 1024) == "2.0 MB"
        assert format_size(1536 * 1024) == "1.5 MB"

    def test_gb(self):
        assert format_size(1024 * 1024 * 1024) == "1.00 GB"
        assert format_size(2 * 1024 * 1024 * 1024) == "2.00 GB"

    def test_float_input(self):
        assert format_size(500.5) == "500.5 B"
        assert format_size(1024.0) == "1.0 KB"


class TestTruncatePath:
    def test_short_path(self):
        assert truncate_path("hello.txt", 60) == "hello.txt"
        assert truncate_path("", 60) == ""
        assert truncate_path(None, 60) == ""

    def test_exact_length(self):
        path = "x" * 59
        assert truncate_path(path, 60) == path

    def test_truncated(self):
        path = "x" * 100
        result = truncate_path(path, 60)
        assert result.startswith("...")
        assert len(result) == 60

    def test_custom_max_len(self):
        path = "x" * 50
        assert truncate_path(path, 30).startswith("...")
        assert len(truncate_path(path, 30)) == 30
