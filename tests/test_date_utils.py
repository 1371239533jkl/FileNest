"""测试 date_utils 工具函数"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from utils.date_utils import parse_datetime_safe


class TestParseDatetimeSafe:
    def test_valid_string(self):
        dt = parse_datetime_safe("2024-01-15 10:30:00")
        assert dt is not None
        assert isinstance(dt, datetime)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_datetime_input(self):
        now = datetime.now()
        assert parse_datetime_safe(now) is now

    def test_none_input(self):
        assert parse_datetime_safe(None) is None

    def test_empty_string(self):
        assert parse_datetime_safe("") is None

    def test_wrong_format(self):
        assert parse_datetime_safe("2024/01/15") is None

    def test_invalid_date(self):
        assert parse_datetime_safe("2024-13-01 00:00:00") is None

    def test_custom_format(self):
        dt = parse_datetime_safe("2024/01/15", "%Y/%m/%d")
        assert dt is not None
        assert dt.year == 2024

    def test_midnight(self):
        dt = parse_datetime_safe("2024-01-15 00:00:00")
        assert dt is not None
        assert dt.hour == 0
        assert dt.minute == 0
