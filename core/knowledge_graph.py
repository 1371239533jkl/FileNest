"""
文件知识图谱（批次7 P2-05 第一期）。

从现有数据动态构建图，不引入新表：
- 节点：文件(file)、标签(tag)、目录(dir)
- 边：tag（文件↔标签）、version（confirmed 版本关系）、
      tag-mate（共享标签的文件对）、same-dir（同目录文件）、duplicate（重复组）

提供两类查询：
- neighborhood：以文件/标签/目录为中心的一度邻域
- hub_files：按「标签数+已确认关系数+重复标记」排序的枢纽文件
"""
import os
from typing import List, Optional

from database.db_manager import db
from database.models import FileDAO, TagDAO, VersionRelationDAO
from utils.logger import logger

MAX_TAG_MATES = 8      # 每个标签最多扩展的同伴文件
MAX_DIR_MATES = 8      # 同目录最多扩展的文件
MAX_HUB_LIMIT = 50


class GraphService:
    """知识图谱：邻域查询 + 枢纽分析。"""

    def __init__(self, file_dao=None, tag_dao=None, relation_dao=None,
                 db_manager=None):
        self.db = db_manager or db
        self.file_dao = file_dao or FileDAO(self.db)
        self.tag_dao = tag_dao or TagDAO(self.db)
        self.relation_dao = relation_dao or VersionRelationDAO(self.db)

    # ── 工具 ──────────────────────────────────────────────────

    @staticmethod
    def _file_node(rec: dict) -> dict:
        return {
            'id': f"file:{rec['id']}",
            'kind': 'file',
            'label': rec.get('file_name') or os.path.basename(rec.get('file_path', '')),
            'detail': rec.get('file_path', ''),
            'ref': rec['id'],
        }

    @staticmethod
    def _dir_of(path: str) -> str:
        return os.path.dirname(path or '').replace('\\', '/')

    def _add_node(self, nodes: dict, node: dict):
        nodes.setdefault(node['id'], node)

    def _add_edge(self, edges: list, src: str, dst: str, kind: str):
        key = (src, dst, kind)
        rkey = (dst, src, kind)
        if key not in edges and rkey not in edges:
            edges.append({'src': src, 'dst': dst, 'kind': kind})

    # ── 邻域 ──────────────────────────────────────────────────

    def file_neighborhood(self, file_id: int,
                          include_same_dir: bool = True) -> dict:
        """以文件为中心：标签、版本关系、共享标签同伴、同目录。"""
        nodes, edges = {}, []
        rec = self.file_dao.get_by_id(file_id)
        if not rec:
            return {'nodes': [], 'edges': []}
        center = self._file_node(rec)
        self._add_node(nodes, center)

        # 标签 + 共享标签的同伴文件
        for t in self.tag_dao.get_tags_by_file(file_id) or []:
            tag_name = t['tag_name']
            tid = f"tag:{tag_name}"
            self._add_node(nodes, {'id': tid, 'kind': 'tag', 'label': f'#{tag_name}',
                                   'detail': '标签', 'ref': tag_name})
            self._add_edge(edges, center['id'], tid, 'tag')
            mates = [m for m in (self.tag_dao.get_files_by_tag(tag_name) or [])
                     if m['id'] != file_id][:MAX_TAG_MATES]
            for m in mates:
                mid = f"file:{m['id']}"
                self._add_node(nodes, self._file_node(m))
                self._add_edge(edges, tid, mid, 'tag-mate')

        # 已确认的版本关系
        for rel in self.relation_dao.get_relations_for_file(file_id) or []:
            other_id = (rel['file_id_b'] if rel['file_id_a'] == file_id
                        else rel['file_id_a'])
            other = self.file_dao.get_by_id(other_id)
            if other:
                oid = f"file:{other_id}"
                self._add_node(nodes, self._file_node(other))
                self._add_edge(edges, center['id'], oid,
                               rel.get('relation') or 'version')

        # 同目录
        if include_same_dir:
            dir_path = self._dir_of(rec.get('file_path', ''))
            if dir_path:
                did = f"dir:{dir_path}"
                self._add_node(nodes, {'id': did, 'kind': 'dir',
                                       'label': os.path.basename(dir_path) or dir_path,
                                       'detail': dir_path, 'ref': dir_path})
                self._add_edge(edges, center['id'], did, 'same-dir')
                like = dir_path.replace('/', os.sep) + os.sep
                for m in (self.file_dao.db.execute_query(
                        "SELECT * FROM files WHERE status='active' AND file_path LIKE ? "
                        "AND id != ? LIMIT ?",
                        (like + '%', file_id, MAX_DIR_MATES)) or []):
                    mid = f"file:{m['id']}"
                    self._add_node(nodes, self._file_node(dict(m)))
                    self._add_edge(edges, did, mid, 'same-dir')

        return {'nodes': list(nodes.values()), 'edges': edges}

    def tag_neighborhood(self, tag_name: str, max_files: int = 25) -> dict:
        """以标签为中心：标签 + 其下文件。"""
        nodes, edges = {}, []
        tid = f"tag:{tag_name}"
        self._add_node(nodes, {'id': tid, 'kind': 'tag', 'label': f'#{tag_name}',
                               'detail': '标签', 'ref': tag_name})
        for m in (self.tag_dao.get_files_by_tag(tag_name) or [])[:max_files]:
            fid = f"file:{m['id']}"
            self._add_node(nodes, self._file_node(dict(m)))
            self._add_edge(edges, tid, fid, 'tag')
        return {'nodes': list(nodes.values()), 'edges': edges}

    def directory_neighborhood(self, dir_path: str, max_files: int = 25) -> dict:
        """以目录为中心：目录 + 其下文件。"""
        nodes, edges = {}, []
        dir_path = dir_path.rstrip('\\/')
        did = f"dir:{dir_path}"
        self._add_node(nodes, {'id': did, 'kind': 'dir',
                               'label': os.path.basename(dir_path) or dir_path,
                               'detail': dir_path, 'ref': dir_path})
        like = dir_path.replace('/', os.sep) + os.sep
        for m in (self.file_dao.db.execute_query(
                "SELECT * FROM files WHERE status='active' AND file_path LIKE ? "
                "LIMIT ?", (like + '%', max_files)) or []):
            fid = f"file:{m['id']}"
            self._add_node(nodes, self._file_node(dict(m)))
            self._add_edge(edges, did, fid, 'same-dir')
        return {'nodes': list(nodes.values()), 'edges': edges}

    def neighborhood(self, kind: str, value, **kw) -> dict:
        """统一入口：kind ∈ file|tag|dir。"""
        try:
            if kind == 'file':
                return self.file_neighborhood(int(value), **kw)
            if kind == 'tag':
                return self.tag_neighborhood(str(value), **kw)
            if kind == 'dir':
                return self.directory_neighborhood(str(value), **kw)
        except Exception as e:  # noqa: BLE001
            logger.error(f"知识图谱邻域查询失败: {e}")
        return {'nodes': [], 'edges': []}

    # ── 枢纽 ──────────────────────────────────────────────────

    def hub_files(self, limit: int = 10) -> List[dict]:
        """枢纽文件：标签数 + 已确认关系数 + 重复标记 的加权度数。"""
        rows = self.db.execute_query(
            """
            SELECT * FROM (
                SELECT f.id, f.file_name, f.file_path, f.file_size,
                       (SELECT COUNT(*) FROM file_tags t WHERE t.file_id = f.id) * 2
                       + (SELECT COUNT(*) FROM file_relations r
                          WHERE r.status = 'confirmed'
                            AND (r.file_id_a = f.id OR r.file_id_b = f.id)) * 3
                       + (CASE WHEN f.is_duplicate = 1 THEN 1 ELSE 0 END) AS score
                FROM files f
                WHERE f.status = 'active'
            ) WHERE score > 0
            ORDER BY score DESC, file_name
            LIMIT ?
            """, (min(limit, MAX_HUB_LIMIT),)) or []
        return [dict(r) for r in rows]

    # ── 中心候选（搜索框联想） ────────────────────────────────

    def search_centers(self, keyword: str, limit: int = 10) -> List[dict]:
        """按关键词返回可作为图中心的候选（文件/标签/目录）。"""
        kw = (keyword or '').strip()
        result: List[dict] = []
        if not kw:
            return result
        like = f"%{kw}%"
        for r in (self.db.execute_query(
                "SELECT id, file_name, file_path FROM files "
                "WHERE status='active' AND file_name LIKE ? LIMIT ?",
                (like, limit)) or []):
            result.append({'kind': 'file', 'value': r['id'],
                           'label': r['file_name'], 'detail': r['file_path']})
        for t in (self.db.execute_query(
                "SELECT tag_name FROM tags WHERE tag_name LIKE ? LIMIT ?",
                (like, limit)) or []):
            result.append({'kind': 'tag', 'value': t['tag_name'],
                           'label': f"#{t['tag_name']}", 'detail': '标签'})
        for r in (self.db.execute_query(
                "SELECT DISTINCT file_path FROM files WHERE status='active' "
                "AND file_path LIKE ? LIMIT ?",
                (kw.replace('/', os.sep) + '%', limit)) or []):
            d = self._dir_of(r['file_path'])
            if d and not any(x['value'] == d for x in result):
                result.append({'kind': 'dir', 'value': d,
                               'label': os.path.basename(d) or d, 'detail': d})
        return result[:limit * 2]
