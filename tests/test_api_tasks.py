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


def test_files_filters(tmp_path):
    path = _prepare_db()
    root = tmp_path / 'filter'
    root.mkdir()
    (root / 'alpha_1.txt').write_bytes(b'a' * 10)
    (root / 'alpha_2.txt').write_bytes(b'a' * 20)
    (root / 'beta.txt').write_bytes(b'b' * 30)

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

            by_name = client.get('/api/files', params={'name': 'alpha'}).json()
            assert by_name['total'] == 2
            assert {item['file_name'] for item in by_name['items']} == {'alpha_1.txt', 'alpha_2.txt'}

            by_size = client.get('/api/files', params={'min_size': 25}).json()
            assert by_size['total'] == 1
            assert by_size['items'][0]['file_name'] == 'beta.txt'

            by_type = client.get('/api/files', params={'file_type': 'image'}).json()
            assert by_type['total'] == 0 and by_type['items'] == []
    finally:
        _teardown(path)


def test_duplicate_suggest_and_clean(tmp_path):
    """去重建议与清理：suggest 返回 id 列表（曾因按 dict 取值 500），clean 把副本移入回收区。"""
    path = _prepare_db()
    root = tmp_path / 'dups'
    root.mkdir()
    first = root / 'a.txt'
    second = root / 'b.txt'
    for target in (first, second):
        target.write_bytes(b'same-content')

    try:
        with TestClient(server.app) as client:
            task_id = client.post(
                '/api/scan/start',
                json={'directory': str(root), 'compute_hash': True},
            ).json()['task_id']
            for _ in range(200):
                if client.get(f'/api/tasks/{task_id}').json()['status'] != 'running':
                    break
                time.sleep(0.05)

            rows = dbm.db.execute_query(
                "SELECT id FROM files WHERE status='active' ORDER BY id")
            ids = [row['id'] for row in rows]
            assert len(ids) == 2
            dbm.db.execute_update(
                'UPDATE files SET is_duplicate=1, duplicate_group_id=99 WHERE id IN (?,?)',
                tuple(ids))

            suggestion = client.post(
                '/api/duplicates/99/suggest?strategy=keep_newest')
            assert suggestion.status_code == 200, suggestion.text
            body = suggestion.json()
            assert isinstance(body['keep_file_id'], int)
            assert body['remove_file_ids'] == [
                ids[0] if body['keep_file_id'] == ids[1] else ids[1]]
            assert body['remove_total_size'] == len(b'same-content')

            cleaned = client.post('/api/duplicates/clean', json={
                'group_id': 99,
                'keep_file_id': body['keep_file_id'],
                'remove_file_ids': body['remove_file_ids'],
                'confirm': True,
            })
            assert cleaned.status_code == 200, cleaned.text
            assert cleaned.json()['removed'] == 1

            remaining = [p for p in (first, second) if p.exists()]
            assert len(remaining) == 1
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
