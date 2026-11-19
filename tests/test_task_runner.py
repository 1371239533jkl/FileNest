"""后台任务注册表（无 Qt）。"""
import threading
import time

from core.task_runner import TaskRunner


def _wait(runner, task_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = runner.get(task_id)
        if task['status'] != 'running':
            return task
        time.sleep(0.01)
    raise AssertionError('task did not finish')


def test_success_records_result_and_progress():
    runner = TaskRunner()

    def job(progress, cancel):
        progress(1, 2)
        progress(2, 2)
        return {'written': 2}

    done = _wait(runner, runner.submit('demo', job).id)
    assert done['status'] == 'done'
    assert done['result'] == {'written': 2}
    assert done['percent'] == 100


def test_failure_is_captured():
    runner = TaskRunner()

    def job(progress, cancel):
        raise RuntimeError('boom')

    done = _wait(runner, runner.submit('boom', job).id)
    assert done['status'] == 'failed'
    assert 'boom' in done['error']


def test_cancel_sets_event():
    runner = TaskRunner()
    started = threading.Event()

    def job(progress, cancel):
        started.set()
        while not cancel.is_set():
            time.sleep(0.01)
        return {'stopped': True}

    task = runner.submit('long', job)
    assert started.wait(2)
    assert runner.cancel(task.id) is True
    done = _wait(runner, task.id)
    assert done['status'] == 'cancelled'


def test_snapshot_counts_running():
    runner = TaskRunner()
    release = threading.Event()
    runner.submit('hold', lambda progress, cancel: release.wait(2) or {})
    assert runner.snapshot()['running'] == 1
    release.set()


def test_unknown_task_returns_none():
    assert TaskRunner().get(999) is None
    assert TaskRunner().cancel(999) is False
