"""Baseline metrics for the pre-refactor codebase. Stdlib only.

Deliberately imports nothing from the project: core/ pulls PyQt6, which is
absent in a bare interpreter. These are "raw capability" numbers; UI metrics
(first paint, frame time) need Electron/Qt and are recorded after P2.

    python bench/run_all.py --root bench/data/1k --json bench/results/baseline.json
    python bench/run_all.py --selftest
"""
import argparse
import hashlib
import json
import math
import os
import platform
import random
import shutil
import sqlite3
import struct
import sys
import tempfile
import time

BLOCK = 1 << 20


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def _timeit(fn, runs=3):
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return _median(times)


def scan_tree(root):
    """os.walk + stat per file — same shape as core/file_scanner.py."""
    n = total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            st = os.stat(os.path.join(dirpath, name))
            n += 1
            total += st.st_size
    return n, total


def hash_tree(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            h = hashlib.sha256()
            with open(os.path.join(dirpath, name), 'rb') as f:
                while True:
                    block = f.read(BLOCK)
                    if not block:
                        break
                    h.update(block)
            h.digest()


def _vectors(n, dim, seed=7):
    rng = random.Random(seed)
    rows = [struct.pack(f'<{dim}f', *[rng.uniform(-1, 1) for _ in range(dim)])
            for _ in range(n)]
    query = struct.pack(f'<{dim}f', *[rng.uniform(-1, 1) for _ in range(dim)])
    return rows, query


def cosine_scan(rows, query, dim):
    """Current implementation shape: unpack every blob, pure-Python dot."""
    qv = struct.unpack(f'<{dim}f', query)
    nq = math.sqrt(sum(x * x for x in qv))
    best = 0.0
    for blob in rows:
        v = struct.unpack(f'<{dim}f', blob)
        dot = 0.0
        for a, b in zip(qv, v):
            dot += a * b
        nv = math.sqrt(sum(x * x for x in v))
        if nv:
            best = max(best, dot / (nq * nv))
    return best


def group_hashes(hashes, threshold=8):
    """Current implementation shape: O(n^2), int(hex,16) parsed per comparison."""
    n = len(hashes)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if bin(int(hashes[i], 16) ^ int(hashes[j], 16)).count('1') <= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    return sum(1 for i in range(n) if find(i) == i)


def sqlite_bench(rows=5000, deep_rows=50000):
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    # 与应用一致的持久化配置，否则 per-row commit 会被严重高估
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, '
                 'size INTEGER, scan_time REAL)')
    conn.execute('CREATE INDEX idx_scan_time ON files(scan_time)')
    data = [(f'/x/{i}.bin', i * 17, float(i)) for i in range(rows)]

    t0 = time.perf_counter()
    for row in data:
        conn.execute('INSERT INTO files(path, size, scan_time) VALUES (?,?,?)', row)
        conn.commit()
    per_row = time.perf_counter() - t0

    conn.execute('DELETE FROM files')
    conn.commit()
    t0 = time.perf_counter()
    conn.executemany('INSERT INTO files(path, size, scan_time) VALUES (?,?,?)', data)
    conn.commit()
    batch = time.perf_counter() - t0

    big = [(f'/y/{i}.bin', i, float(i)) for i in range(deep_rows)]
    conn.executemany('INSERT INTO files(path, size, scan_time) VALUES (?,?,?)', big)
    conn.commit()

    def page(offset):
        conn.execute('SELECT id, path FROM files ORDER BY scan_time DESC '
                     'LIMIT 100 OFFSET ?', (offset,)).fetchall()

    shallow = _timeit(lambda: page(0), 3)
    deep = _timeit(lambda: page(deep_rows - 100), 3)

    conn.close()
    os.unlink(tmp.name)
    return {'per_row_commit_s': per_row, 'batch_commit_s': batch,
            'page_first_s': shallow, 'page_deep_s': deep}


def run(root, runs=3):
    n, total = scan_tree(root)
    scan_s = _timeit(lambda: scan_tree(root), runs)
    hash_s = _timeit(lambda: hash_tree(root), runs)

    rows, query = _vectors(2000, 768)
    cosine_s = _timeit(lambda: cosine_scan(rows, query, 768), 1)

    rng = random.Random(11)
    hashes = [f'{rng.getrandbits(64):016x}' for _ in range(1500)]
    group_s = _timeit(lambda: group_hashes(hashes), 1)

    db = sqlite_bench()

    return {
        'dataset': {'files': n, 'mb': round(total / (1 << 20), 1)},
        'metrics': {
            'scan_files_per_s': round(n / scan_s),
            'scan_s': round(scan_s, 3),
            'hash_mb_per_s': round(total / (1 << 20) / hash_s, 1),
            'cosine_2k_x768_ms': round(cosine_s * 1000, 1),
            'cosine_per_query_us': round(cosine_s * 1e6 / 2000, 1),
            'group_1500_s': round(group_s, 3),
            'sqlite_per_row_5k_s': round(db['per_row_commit_s'], 3),
            'sqlite_batch_5k_s': round(db['batch_commit_s'], 3),
            'page_first_ms': round(db['page_first_s'] * 1000, 2),
            'page_deep_ms': round(db['page_deep_s'] * 1000, 2),
        },
    }


def selftest():
    root = tempfile.mkdtemp(prefix='filenest-bench-')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gen_dataset as gd
        info = gd.generate(root, 40, seed=1, budget_mb=4, force=True)
        other = tempfile.mkdtemp(prefix='filenest-bench-')
        info2 = gd.generate(other, 40, seed=1, budget_mb=4, force=True)
        shutil.rmtree(other)
        assert info['tree_hash'] == info2['tree_hash'], 'dataset not deterministic'

        n, total = scan_tree(root)
        assert n == info['files'], f'scan {n} != {info["files"]}'
        hash_tree(root)
        rows, query = _vectors(5, 8)
        assert cosine_scan(rows, query, 8) != 0
        assert group_hashes(['0' * 16, '0' * 16, 'f' * 16]) == 2
        db = sqlite_bench(rows=50, deep_rows=200)
        assert db['batch_commit_s'] > 0 and db['per_row_commit_s'] > 0
        print('selftest ok: deterministic dataset, scan/hash/cosine/group/sqlite all ran')
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='bench/data/1k')
    ap.add_argument('--json')
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if not os.path.isdir(a.root):
        raise SystemExit(f'{a.root} 不存在，先跑 bench/gen_dataset.py')

    result = run(a.root, a.runs)
    result['env'] = {
        'python': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count(),
    }
    print(f"dataset: {result['dataset']['files']} files, "
          f"{result['dataset']['mb']} MB")
    for k, v in result['metrics'].items():
        print(f'  {k:24} {v}')

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'written: {a.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
