"""API：后台扫描任务、SSE、缩略图与 token（不依赖 PyQt6）。"""
import os
import tempfile
import time

import config
import database.db_manager as dbm
from fastapi.testclient import TestClient

import server

FILES = 6


def _prepare_db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    config.DB_PATH = path
    dbm.db.db_path = path
    return path


def _teardown(path):
    dbm.db.close()
    try:
        os.unlink(path)
    except OSError:
        pass  # Windows 上连接可能仍被 lifespan 线程持有，交给临时目录清理


def test_scan_task_completes_and_events_stream(tmp_path):
    path = _prepare_db()
    root = tmp_path / 'docs'
    root.mkdir()
    for i in range(FILES):
        (root / f'f{i}.txt').write_bytes(b'x' * (i + 1))

    try:
        with TestClient(server.app) as client:
            res = client.post('/api/scan/start', json={'directory': str(root)})
            assert res.status_code == 200, res.text
            task_id = res.json()['task_id']

            deadline = time.time() + 15
            task = {}
            while time.time() < deadline:
                task = client.get(f'/api/tasks/{task_id}').json()
                if task['status'] != 'running':
                    break
                time.sleep(0.05)

            assert task['status'] == 'done', task
            assert task['result']['written'] == FILES

            events = client.get('/api/events')
            assert events.status_code == 200
            assert 'data:' in events.text
    finally:
        _teardown(path)


def test_files_cursor_pagination_has_no_duplicates(tmp_path):
    path = _prepare_db()
    root = tmp_path / 'many'
    root.mkdir()
    for i in range(25):
        (root / f'f{i:02d}.txt').write_bytes(b'x' * (i + 1))

    try:
        with TestClient(server.app) as client:
            task_id = client.post(
                '/api/scan/start',
                json={'directory': str(root), 'compute_hash': False},
            ).json()['task_id']
            for _ in range(200):
                if client.get(f'/api/tasks/{task_id}').json()['status'] != 'running':
                    break
                time.sleep(0.05)

            ids, cursor = [], ''
            for _ in range(10):
                res = client.get('/api/files', params={'page_size': 10, 'cursor': cursor})
                assert res.status_code == 200, res.text
                body = res.json()
                ids.extend(item['id'] for item in body['items'])
                cursor = body['next_cursor']
                if cursor is None:
                    break

            assert len(ids) == 25
            assert len(set(ids)) == 25
    finally:
        _teardown(path)


def test_thumb_returns_jpeg(tmp_path):
    from PIL import Image

    path = _prepare_db()
    image = tmp_path / 'a.png'
    Image.new('RGB', (400, 300), (10, 20, 30)).save(image)
    try:
        with TestClient(server.app) as client:
            res = client.get('/api/thumb', params={'path': str(image), 'size': 64})
            assert res.status_code == 200, res.text
            assert res.headers['content-type'] == 'image/jpeg'
            assert len(res.content) > 200

            missing = client.get('/api/thumb', params={'path': str(tmp_path / 'nope.png')})
            assert missing.status_code == 404

            not_image = tmp_path / 'a.txt'
            not_image.write_text('x', encoding='utf-8')
            assert client.get(
                '/api/thumb', params={'path': str(not_image)}).status_code == 400
    finally:
        _teardown(path)


def test_health_public_but_api_needs_token(tmp_path, monkeypatch):
    path = _prepare_db()
    try:
        with TestClient(server.app) as client:
            assert client.get('/health').status_code == 200

            monkeypatch.setattr(server, 'API_KEY', 'secret')
            assert client.get('/api/tasks').status_code == 401
            assert client.get(
                '/api/tasks', headers={'x-api-key': 'wrong'}).status_code == 401
            assert client.get(
                '/api/tasks', headers={'x-api-key': 'secret'}).status_code == 200
    finally:
        _teardown(path)
