#!/usr/bin/env python
"""
smart-file-manager 综合测试脚本
一次性运行：语法检查 → 导入测试 → 单元测试 → 功能断言 → pyflakes 静态分析
有问题报 red，全绿收工。
"""
import os
import sys
import subprocess
import glob

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 切换到项目根目录，让相对路径正常工作
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)
PASS = 0
FAIL = 0


def test(name: str, status: bool, detail: str = ""):
    global PASS, FAIL
    if status:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}")
        if detail:
            print(f"    └─ {detail}")


def check_syntax():
    """1. 语法检查：全部 .py 文件"""
    print("\n═══ 1. 语法检查 ═══")
    files = (glob.glob("*.py") + glob.glob("database/*.py") +
             glob.glob("core/*.py") + glob.glob("ui/*.py") +
             glob.glob("utils/*.py") + glob.glob("tests/*.py"))
    all_ok = True
    for f in sorted(files):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", f],
            capture_output=True, text=True, cwd=PROJECT_DIR)
        if result.returncode != 0:
            all_ok = False
            test(f"语法: {f}", False, result.stderr.strip())
    if all_ok:
        test(f"语法: {len(files)} 个文件", True)


def check_imports():
    """2. 导入测试：验证所有模块可正常导入"""
    print("\n═══ 2. 导入测试 ═══")
    sys.path.insert(0, PROJECT_DIR)
    errors = []

    # core 模块统一导出
    try:
        from core import (FileClassifier, FileManager, FileScanWorker,
                          DedupManager, OperationHistoryManager, TagManager,
                          extract_metadata, get_file_type, calculate_hash,
                          is_hidden_file)
    except Exception as e:
        errors.append(f"core 导出: {e}")

    # database
    try:
        from database.db_manager import db
        from database.models import (FileDAO, TagDAO, ClassificationDAO,
                                     MetadataDAO, ScanDirectoryDAO,
                                     ClassificationRuleDAO, SystemSettingsDAO)
    except Exception as e:
        errors.append(f"database: {e}")

    # utils
    try:
        from utils.display_utils import format_size, truncate_path
        from utils.date_utils import parse_datetime_safe
        from utils.logger import logger
    except Exception as e:
        errors.append(f"utils: {e}")

    if errors:
        for e in errors:
            test("导入", False, e)
    else:
        test("导入: 全部模块加载正常", True)


def check_pytest():
    """3. 运行现有的 pytest 单元测试"""
    print("\n═══ 3. 单元测试 ═══")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        capture_output=True, text=True, cwd=PROJECT_DIR)
    if result.returncode == 0:
        # 提取通过数
        for line in result.stdout.split("\n"):
            if "passed" in line and "failed" not in line:
                test("pytest: 全部通过", True)
                break
        else:
            test("pytest: 全部通过", True)
    else:
        failed = 0
        for line in result.stdout.split("\n"):
            if "FAILED" in line:
                failed += 1
                test("pytest", False, line.strip())
        if failed == 0:
            test("pytest", False, result.stderr.strip())


def check_functional():
    """4. 功能断言测试：工具函数边界"""
    print("\n═══ 4. 功能断言 ═══")
    sys.path.insert(0, PROJECT_DIR)
    from utils.display_utils import format_size, truncate_path
    from utils.date_utils import parse_datetime_safe
    errors = []

    # format_size
    cases = [
        (0, "0 B"), (1, "1 B"), (1023, "1023 B"),
        (1024, "1.0 KB"), (1500, "1.5 KB"), (1024 * 1024, "1.0 MB"),
        (1536 * 1024, "1.5 MB"), (1024 ** 3, "1.00 GB"),
    ]
    for val, expected in cases:
        if format_size(val) != expected:
            errors.append(f"format_size({val}) → {format_size(val)}, 期望 {expected}")

    # truncate_path
    if truncate_path("", 60) != "":
        errors.append("truncate_path('', 60) 应返回 ''")
    if truncate_path(None, 60) != "":
        errors.append("truncate_path(None, 60) 应返回 ''")
    if not truncate_path("x" * 100, 60).startswith("..."):
        errors.append("truncate_path 长路径应截断")
    if len(truncate_path("x" * 100, 60)) != 60:
        errors.append("truncate_path 截断后长度应为 60")

    # parse_datetime_safe
    if parse_datetime_safe(None) is not None:
        errors.append("parse_datetime_safe(None) 应返回 None")
    if parse_datetime_safe("") is not None:
        errors.append("parse_datetime_safe('') 应返回 None")
    if parse_datetime_safe("not-a-date") is not None:
        errors.append("parse_datetime_safe('not-a-date') 应返回 None")
    if parse_datetime_safe("2024-01-15 10:30:00") is None:
        errors.append("parse_datetime_safe('2024-01-15 10:30:00') 应返回 datetime")

    if errors:
        for e in errors:
            test("功能断言", False, e)
    else:
        test(f"功能断言: {len(cases) + 6} 个用例全部通过", True)


def check_pyflakes():
    """5. pyflakes 静态分析"""
    print("\n═══ 5. 静态分析 (pyflakes) ═══")
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes",
         "core/", "database/", "utils/", "ui/",
         "config.py", "main.py"],
        capture_output=True, text=True, cwd=PROJECT_DIR)
    if result.returncode == 0:
        test("pyflakes: 无警告", True)
    else:
        # 过滤预存的白名单警告
        known_issues = [
            "QComboBox", "QFormLayout",
            "'PyQt6.QtCore.Qt' imported but unused",
            "'sys' imported but unused", "'os' imported but unused",
            # core/__init__.py 的 re-export 是 pyflakes 假阳性
            "core/__init__.py",
            # pre-existing
            "ui/history_tab.py",
        ]
        new_warnings = []
        for line in result.stdout.split("\n"):
            if line.strip():
                if not any(k in line for k in known_issues):
                    new_warnings.append(line.strip())
        if new_warnings:
            for w in new_warnings:
                test("pyflakes 新警告", False, w)
        else:
            test("pyflakes: 无新增警告", True)


def main():
    print("=" * 55)
    print("   smart-file-manager 综合测试脚本")
    print("=" * 55)

    check_syntax()
    check_imports()
    check_pytest()
    check_functional()
    check_pyflakes()

    print("\n" + "=" * 55)
    print(f"   结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("   🟢 全部通过")
    else:
        print(f"   🔴 有 {FAIL} 项失败，请检查")
    print("=" * 55)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
