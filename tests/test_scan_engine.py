"""扫描内核：单/多进程一致性与哈希正确性（不依赖 PyQt6）。"""
import os
import shutil
import tempfile

import pytest

from core import scan_engine as se

N = 80  # 超过 hash_many 的并行阈值（64），确保真的走进程池


@pytest.fixture()
def tree():
    root = tempfile.mkdtemp(prefix='filenest-scan-')
    for i in range(N):
        d = os.path.join(root, f'd{i % 3}', f's{i % 2}')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'f{i}.txt'), 'wb') as f:
            f.write(b'x' * (i * 13 + 1))
    hidden = os.path.join(root, '.hidden')
    with open(hidden, 'wb') as f:
        f.write(b'h')
    if os.name == 'nt':
        # Windows 上"点开头"不算隐藏，必须打上 FILE_ATTRIBUTE_HIDDEN
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 0x2)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_collect_counts_all_files(tree):
    rows = se.collect(tree, include_hidden=False)
    assert len(rows) == N
    assert len({r['file_path'] for r in rows}) == N


def test_hidden_skipped_and_included(tree):
    assert len(se.collect(tree, include_hidden=False)) == N
    assert len(se.collect(tree, include_hidden=True)) == N + 1


def test_record_fields(tree):
    rows = {r['file_name']: r for r in se.collect(tree)}
    r = rows['f5.txt']
    assert r['file_type'] == 'document'
    assert r['file_size'] == 5 * 13 + 1
    assert r['file_extension'] == '.txt'


def test_hash_many_matches_single(tree):
    paths = [r['file_path'] for r in se.collect(tree)]
    one = se.hash_many(paths, workers=1)
    many = se.hash_many(paths, workers=3)
    assert one == many
    assert all(h and len(h) == 64 for h in one)


def test_missing_file_returns_none(tree):
    assert se.hash_many([os.path.join(tree, 'nope.txt')], workers=1) == [None]
