"""感知哈希相似图片检测 —— 识别缩放、压缩或轻微编辑后的同一张图片。

与 multistage_dedup（字节级完全重复）互补：本模块用 dHash 感知哈希，
只对 file_type='image' 的记录计算，结果存 files.perceptual_hash 列（增量续算）。
分组完全在内存中按汉明距离阈值合并，不落库——阈值可随时调整重算。
"""
import os
from typing import Callable, Optional

from utils.logger import logger

# 感知哈希失败标记（区分"还没算"和"算不了"，重算时跳过坏文件）
_HASH_FAILED = '__failed__'


def dhash(path: str, hash_size: int = 8) -> Optional[str]:
    """计算图片 dHash（9x8 灰度差分 → 64bit hex 字符串）。失败返回 None。"""
    try:
        from PIL import Image
        with Image.open(path) as img:
            gray = img.convert('L').resize((hash_size + 1, hash_size))
            px = list(gray.getdata())
        bits = 0
        for row in range(hash_size):
            for col in range(hash_size):
                left = px[row * (hash_size + 1) + col]
                right = px[row * (hash_size + 1) + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return f'{bits:016x}'
    except Exception as e:
        logger.debug(f"dHash 计算失败 ({path}): {e}")
        return None


def hamming_distance(a: str, b: str) -> int:
    """两个 hex 哈希的汉明距离"""
    return bin(int(a, 16) ^ int(b, 16)).count('1')


class SimilarityManager:
    """相似图片检测：感知哈希计算（增量落库）+ 内存分组。"""

    def __init__(self, db_manager=None):
        if db_manager is not None:
            self._db = db_manager
        else:
            from database.db_manager import db
            self._db = db

    def compute_hashes(self, progress_cb: Optional[Callable[[int, int, str], None]] = None,
                       reset: bool = False,
                       cancel_check: Optional[Callable[[], bool]] = None) -> dict:
        """为未计算感知哈希的图片计算 dHash 并写入 files.perceptual_hash。

        reset=True 时清空全部重算；返回 {'computed','failed','skipped'}。
        """
        computed = failed = skipped = 0
        rows = self._db.execute_query(
            "SELECT id, file_path FROM files "
            "WHERE file_type = 'image' AND status = 'active' "
            + ("AND perceptual_hash IS NOT NULL" if not reset else "")
        ) or []
        total = len(rows)
        for i, r in enumerate(rows):
            if cancel_check and cancel_check():
                break
            if progress_cb:
                progress_cb(i + 1, total, r.get('file_path', ''))
            h = dhash(r['file_path'])
            self._db.execute_update(
                "UPDATE files SET perceptual_hash = ? WHERE id = ?",
                (h or _HASH_FAILED, r['id']))
            if h:
                computed += 1
            else:
                failed += 1
        return {'computed': computed, 'failed': failed, 'skipped': skipped}

    def get_groups(self, threshold: int = 8, min_group: int = 2) -> list[list[dict]]:
        """按汉明距离阈值分组已建哈希的图片。

        threshold: 0~64，越小越严格（0 等价感知级完全相同；8 适合缩放/压缩识别）。
        ponytail: 组内全并查集 O(n²)，图片万级以下一次性可接受；
        更大库存再升级 BK-tree（改 get_groups 一处即可）。
        每组附带 label：全部 file_hash 相同 → '完全重复'，否则 '视觉相似'。
        """
        rows = self._db.execute_query(
            "SELECT id, file_name, file_path, file_size, file_hash, perceptual_hash "
            "FROM files WHERE file_type = 'image' AND status = 'active' "
            "AND perceptual_hash IS NOT NULL AND perceptual_hash != ?",
            (_HASH_FAILED,),
        ) or []
        n = len(rows)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            hi = int(rows[i]['perceptual_hash'], 16)
            for j in range(i + 1, n):
                if hamming_distance(rows[i]['perceptual_hash'],
                                    rows[j]['perceptual_hash']) <= threshold:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj

        groups: dict[int, list] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(rows[i])
        result = []
        for members in groups.values():
            if len(members) < min_group:
                continue
            hashes = {m.get('file_hash') for m in members if m.get('file_hash')}
            label = '完全重复' if not hashes or len(hashes) == 1 else '视觉相似'
            result.append({'label': label, 'files': members})
        result.sort(key=lambda g: -len(g['files']))
        return result

    def stats(self) -> dict:
        """图片总数 / 已建哈希数（UI 进度展示用）"""
        total = self._db.execute_one(
            "SELECT COUNT(*) AS n FROM files "
            "WHERE file_type='image' AND status='active'") or {'n': 0}
        done = self._db.execute_one(
            "SELECT COUNT(*) AS n FROM files "
            "WHERE file_type='image' AND status='active' "
            "AND perceptual_hash IS NOT NULL") or {'n': 0}
        return {'total': total['n'], 'hashed': done['n']}


def find_similar_images(threshold: int = 8) -> list[list[dict]]:
    """便捷入口：直接对现有哈希分组"""
    return SimilarityManager().get_groups(threshold=threshold)
