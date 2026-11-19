"""Deterministic synthetic dataset for benchmarks. Stdlib only.

    python bench/gen_dataset.py --root bench/data/1k --files 1000
    python bench/gen_dataset.py --root bench/data/10k --files 10000 --budget-mb 400

Layout: root/d00..d19/sub0..sub2/f00000.txt. 10% of files are byte-identical
copies (suffix _dupN) so dedup code paths have something to find.
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import sys

EXTS = ('.txt', '.log', '.bin', '.json', '.md')


def _size(rng, max_kb=4096):
    r = rng.random()
    if r < 0.90:
        size = rng.randint(1 << 10, 64 << 10)
    elif r < 0.99:
        size = rng.randint(64 << 10, 512 << 10)
    else:
        size = rng.randint(512 << 10, 4 << 20)
    return min(size, max_kb << 10)


def generate(root, files, seed=42, budget_mb=80, force=False, max_kb=4096):
    if os.path.isdir(root) and os.listdir(root) and not force:
        raise SystemExit(f'{root} 非空，加 --force 覆盖')
    if force and os.path.isdir(root):
        shutil.rmtree(root)
    rng = random.Random(seed)
    dirs = [os.path.join(root, f'd{i:02d}', f'sub{j}')
            for i in range(20) for j in range(3)]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    paths, total, budget = [], 0, budget_mb << 20
    for i in range(files):
        if total >= budget:
            break
        size = _size(rng, max_kb)
        path = os.path.join(rng.choice(dirs), f'f{i:05d}{rng.choice(EXTS)}')
        with open(path, 'wb') as f:
            f.write(b'\0' * size)
        paths.append(path)
        total += size

    copies = rng.sample(paths, len(paths) // 10) if paths else []
    for k, src in enumerate(copies):
        base, ext = os.path.splitext(src)
        dst = f'{base}_dup{k}{ext}'
        shutil.copyfile(src, dst)
        paths.append(dst)

    walked = sum(len(fns) for _, _, fns in os.walk(root))
    assert walked == len(paths), f'落盘 {walked} != 计划 {len(paths)}'
    return {'files': len(paths), 'bytes': total, 'copies': len(copies),
            'seed': seed, 'tree_hash': tree_hash(root)}


def tree_hash(root):
    h = hashlib.sha256()
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            h.update(f'{os.path.relpath(p, root)}:{os.path.getsize(p)}\n'.encode())
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='bench/data/1k')
    ap.add_argument('--files', type=int, default=1000)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--budget-mb', type=int, default=80)
    ap.add_argument('--max-kb', type=int, default=4096,
                    help='单个文件大小上限，用于生成大量小文件的数据集')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args(argv)

    info = generate(a.root, a.files, a.seed, a.budget_mb, a.force, a.max_kb)
    manifest = os.path.join(a.root, '..', f'manifest-{a.files}.json')
    with open(os.path.normpath(manifest), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
