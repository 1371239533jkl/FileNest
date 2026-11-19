"""API：后台扫描任务与 SSE 事件流（不依赖 PyQt6）。"""
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
        dbm.db.close()
        try:
            os.unlink(path)
        except OSError:
            pass  # Windows 上连接可能仍被 lifespan 线程持有，交给临时目录清理
