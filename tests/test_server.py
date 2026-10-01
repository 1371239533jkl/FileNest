"""HTTP API 服务测试（批次7 P2-09，tests/test_server.py）。

零侵入验证点：只 import server.py 新增模块，不触碰现有代码。
使用独立临时 SQLite 库 + 固定 API Key，与本机/服务器真实数据完全隔离。
"""
import os
import sys
import tempfile

import pytest

pytest.importorskip('fastapi', reason='需要 fastapi（仅服务端部署安装）')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 独立临时库 + API Key，必须在 import server 之前设置（server 启动时读取）
_TMP = tempfile.mkdtemp(prefix='sfm_api_test_')
os.environ['SFM_DB'] = os.path.join(_TMP, 'test.db')
os.environ['SFM_API_KEY'] = 'test-key'

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

KEY = {'X-API-Key': 'test-key'}


@pytest.fixture()
def client():
    with TestClient(server.app) as c:
        yield c


def _make_file(tmp_path, name: str):
    d = tmp_path / 'docs'
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(b'hello world content')
    return d


def _scan(client, directory):
    r = client.post('/api/scan', json={'directory': str(directory),
                                       'recursive': True}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


# ── 鉴权与健康检查 ────────────────────────────────────────────

def test_health_free(client):
    assert client.get('/health').json() == {
        'status': 'ok', 'service': 'smart-file-manager'}


def test_search_requires_key(client):
    assert client.get('/api/search').status_code == 401


def test_search_with_key(client):
    r = client.get('/api/search', params={'name': 'xyz_not_exist_anywhere'},
                   headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body['total'] == 0
    assert isinstance(body['items'], list)


# ── 扫描与搜索 ────────────────────────────────────────────────

def test_scan_then_search_hit(client, tmp_path):
    d = _make_file(tmp_path, '报告2026.txt')
    assert _scan(client, d)['indexed'] >= 1

    hit = client.get('/api/search', params={'name': '报告', 'limit': 10},
                     headers=KEY)
    assert hit.status_code == 200
    assert hit.json()['total'] >= 1


def test_scan_bad_dir(client):
    r = client.post('/api/scan',
                    json={'directory': 'Z:/no_such_dir_xyz', 'recursive': True},
                    headers=KEY)
    assert r.status_code == 400


# ── 文件详情 ──────────────────────────────────────────────────

def test_file_detail_404(client):
    assert client.get('/api/files/999999', headers=KEY).status_code == 404


def test_file_detail_ok(client, tmp_path):
    d = _make_file(tmp_path, 'detail_me.txt')
    _scan(client, d)
    hit = client.get('/api/search', params={'name': 'detail_me'},
                     headers=KEY).json()
    fid = hit['items'][0]['id']
    detail = client.get(f'/api/files/{fid}', headers=KEY)
    assert detail.status_code == 200
    assert detail.json()['file_name'] == 'detail_me.txt'


# ── 标签 ──────────────────────────────────────────────────────

def test_tag_flow(client, tmp_path):
    d = _make_file(tmp_path, 'tagme.txt')
    _scan(client, d)
    fid = client.get('/api/search', params={'name': 'tagme'},
                     headers=KEY).json()['items'][0]['id']

    add = client.post(f'/api/files/{fid}/tags', json={'tag': '重要'}, headers=KEY)
    assert add.status_code == 200 and add.json()['success']

    tags = client.get(f'/api/files/{fid}/tags', headers=KEY).json()
    assert '重要' in tags['tags']

    all_tags = client.get('/api/tags', headers=KEY).json()
    assert any(t == '重要' for t in all_tags['tags'])

    rm = client.request('DELETE', f'/api/files/{fid}/tags',
                        json={'tag': '重要'}, headers=KEY)
    assert rm.status_code == 200
    tags2 = client.get(f'/api/files/{fid}/tags', headers=KEY).json()
    assert '重要' not in tags2['tags']


# ── 生命周期 ──────────────────────────────────────────────────

def test_lifecycle_check_empty(client):
    r = client.get('/api/lifecycle/check', headers=KEY)
    assert r.status_code == 200
    assert r.json()['total'] == 0


def test_lifecycle_run_404(client):
    assert client.post('/api/lifecycle/run/9999', json={},
                       headers=KEY).status_code == 404
