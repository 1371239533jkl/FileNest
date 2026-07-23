"""Small shared registry for background UI tasks.

It deliberately owns task state only. Workers continue to own their actual
business logic, so existing QThread-based modules can migrate incrementally.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class TaskInfo:
    task_id: int
    title: str
    status: str = 'running'
    detail: str = '等待执行'
    progress: Optional[int] = None
    error: str = ''
    worker: object = None
    started_at: datetime = None


class TaskManager(QObject):
    """Application-wide, UI-safe state registry for cancellable workers."""
    task_changed = pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._tasks: list[TaskInfo] = []
        self._next_id = 1

    def register(self, title: str, worker) -> TaskInfo:
        task = TaskInfo(self._next_id, title, worker=worker,
                        started_at=datetime.now())
        self._next_id += 1
        self._tasks.insert(0, task)

        if hasattr(worker, 'progress'):
            worker.progress.connect(
                lambda current, total, *_args, item=task:
                self.update_progress(item, current, total))
        if hasattr(worker, 'error'):
            worker.error.connect(lambda message, item=task: self.fail(item, message))
        if hasattr(worker, 'cancelled'):
            worker.cancelled.connect(lambda item=task: self.cancelled(item))

        # Only connect explicit business-result signals. QThread's inherited
        # ``finished`` is emitted after every terminal state and would overwrite
        # failures/cancellations as completed.
        for signal_name in ('finished', 'done'):
            if signal_name in type(worker).__dict__:
                getattr(worker, signal_name).connect(
                    lambda *_args, item=task: self.complete(item))
                break
        self.task_changed.emit()
        return task

    def tasks(self) -> list[TaskInfo]:
        return list(self._tasks)

    def update_progress(self, task: TaskInfo, current: int, total: int):
        if task.status != 'running':
            return
        task.progress = int(current / total * 100) if total else None
        task.detail = f'{current} / {total}' if total else '正在准备…'
        self.task_changed.emit()

    def complete(self, task: TaskInfo):
        if task.status == 'running':
            task.status, task.detail, task.progress = 'completed', '已完成', 100
            self.task_changed.emit()

    def fail(self, task: TaskInfo, message: str):
        if task.status == 'running':
            task.status, task.detail, task.error = 'failed', '执行失败', str(message)
            self.task_changed.emit()

    def cancelled(self, task: TaskInfo):
        if task.status == 'running':
            task.status, task.detail = 'cancelled', '已取消'
            self.task_changed.emit()

    def cancel(self, task_id: int):
        task = next((item for item in self._tasks if item.task_id == task_id), None)
        if not task or task.status != 'running':
            return
        cancel = getattr(task.worker, 'cancel', None)
        if callable(cancel):
            cancel()
            task.detail = '正在取消…'
        else:
            task.detail = '此任务不可取消'
        self.task_changed.emit()

    def clear_finished(self):
        self._tasks = [item for item in self._tasks if item.status == 'running']
        self.task_changed.emit()
