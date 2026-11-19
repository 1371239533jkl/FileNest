"""无 Qt 的后台任务注册表：submit / cancel / 状态快照。

替代 core/task_manager.py（QObject + pyqtSignal）在服务端的角色：
长任务在独立线程执行，前端通过 /api/tasks 与 /api/events 轮询/订阅进度。
"""
import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Task:
    id: int
    name: str
    status: str = 'running'      # running | done | failed | cancelled
    current: int = 0
    total: int = 0
    error: str = ''
    result: Optional[dict] = None
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'name': self.name, 'status': self.status,
            'current': self.current, 'total': self.total, 'error': self.error,
            'result': self.result,
            'percent': int(self.current / self.total * 100) if self.total else 0,
            'started_at': round(self.started_at, 3),
            'finished_at': round(self.finished_at, 3),
        }


class TaskRunner:
    """线程安全的任务注册表；只保留最近 50 条，避免无限增长。"""

    def __init__(self, keep: int = 50):
        self._tasks: dict[int, Task] = {}
        self._cancel: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self._keep = keep

    # ── 对外 ──
    def submit(self, name: str, fn: Callable[[Callable, threading.Event], dict]) -> Task:
        """fn(progress, cancel_event) -> dict；progress(current, total) 上报进度。"""
        task = Task(id=next(self._seq), name=name)
        event = threading.Event()
        with self._lock:
            self._tasks[task.id] = task
            self._cancel[task.id] = event
            self._trim()

        def progress(current: int, total: int):
            with self._lock:
                task.current, task.total = current, total

        def run():
            try:
                result = fn(progress, event)
                task.result = result if isinstance(result, dict) else None
                self._finish(task, 'cancelled' if event.is_set() else 'done')
            except Exception as exc:  # noqa: BLE001 - 任务失败要落到状态里
                self._finish(task, 'failed', str(exc))

        threading.Thread(target=run, name=f'task-{task.id}', daemon=True).start()
        return task

    def cancel(self, task_id: int) -> bool:
        with self._lock:
            event = self._cancel.get(task_id)
            task = self._tasks.get(task_id)
        if not event or not task or task.status != 'running':
            return False
        event.set()
        return True

    def get(self, task_id: int) -> Optional[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def snapshot(self) -> dict:
        with self._lock:
            tasks = [t.to_dict() for t in self._tasks.values()]
        tasks.sort(key=lambda t: t['id'], reverse=True)
        return {'tasks': tasks,
                'running': sum(1 for t in tasks if t['status'] == 'running')}

    # ── 内部 ──
    def _finish(self, task: Task, status: str, error: str = ''):
        with self._lock:
            task.status = status
            task.error = error
            task.finished_at = time.time()
            self._cancel.pop(task.id, None)

    def _trim(self):
        if len(self._tasks) <= self._keep:
            return
        for task_id in sorted(self._tasks)[:len(self._tasks) - self._keep]:
            if self._tasks[task_id].status != 'running':
                self._tasks.pop(task_id, None)
