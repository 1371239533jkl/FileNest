"""计算内核对比：遍历（旧 os.walk+stat vs 新单次 stat）与哈希（单进程 vs 多进程）。

    python bench/run_compute.py --root bench/data/20k --workers 8
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import scan_engine as se  # noqa: E402


def _timed(fn, runs=2):
    best, out = None, None
    for _ in range(runs):
        t = time.perf_counter()
        out = fn()
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
    return best, out


def scan_legacy(root):
    """旧实现口径：os.walk + 每文件 os.stat（隐藏属性判断还会再多一次 syscall）。"""
    n = total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            st = os.stat(os.path.join(dirpath, name))
            n += 1
            total += st.st_size
    return n, total


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='bench/data/20k')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--json')
    a = ap.parse_args(argv)

    t_legacy, (n_legacy, _) = _timed(lambda: scan_legacy(a.root))
    t_scan, rows = _timed(lambda: se.collect(a.root))
    assert n_legacy == len(rows), (n_legacy, len(rows))

    paths = [r['file_path'] for r in rows]
    mb = sum(r['file_size'] for r in rows) / (1 << 20)

    t_hash_1, h_1 = _timed(lambda: se.hash_many(paths, 1), runs=1)
    t_hash_n, h_n = _timed(lambda: se.hash_many(paths, a.workers), runs=1)
    assert h_1 == h_n, '并行哈希结果与串行不一致'

    result = {
        'root': a.root,
        'files': len(paths),
        'mb': round(mb, 1),
        'workers': a.workers,
        'scan_legacy_s': round(t_legacy, 3),
        'scan_engine_s': round(t_scan, 3),
        'scan_speedup': round(t_legacy / t_scan, 2),
        'hash_serial_s': round(t_hash_1, 3),
        'hash_parallel_s': round(t_hash_n, 3),
        'hash_speedup': round(t_hash_1 / t_hash_n, 2),
        'hash_mb_per_s_serial': round(mb / t_hash_1, 1),
        'hash_mb_per_s_parallel': round(mb / t_hash_n, 1),
    }
    for k, v in result.items():
        print(f'  {k:24} {v}')

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'written: {a.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
