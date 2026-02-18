# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/scheduler.py

Tests task scheduling, worker threads, Queue usage, sys.exitfunc, and
generator throw() API. Mocks threading to avoid actual thread creation.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import time
import pytest
from unittest import mock
import queue

from src.automation.scheduler import (
    ScheduledTask, TaskWorker, TaskScheduler, task_stream,
    PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW,
    _STATUS_PENDING, _STATUS_RUNNING, _STATUS_DONE, _STATUS_FAILED, _STATUS_CANCELLED
)
from src.core.exceptions import PlatformError


# ============================================================================
# ScheduledTask Tests
# ============================================================================

def test_scheduled_task_init_minimal():
    """Test ScheduledTask initialization with minimal parameters."""
    def dummy_func():
        pass

    task = ScheduledTask("test_task", dummy_func)

    assert task.name == "test_task"
    assert task.callable_obj == dummy_func
    assert task.args == ()
    assert task.kwargs == {}
    assert task.priority == PRIORITY_NORMAL
    assert task.status == _STATUS_PENDING
    assert task.run_count == 0
    assert task.error_count == 0


def test_scheduled_task_init_full():
    """Test ScheduledTask initialization with all parameters."""
    def sample_func(a, b, c=None):
        return a + b

    task = ScheduledTask(
        "full_task",
        sample_func,
        args=(1, 2),
        kwargs={"c": 3},
        interval_seconds=60,
        run_at_hour=14,
        run_at_minute=30,
        days_of_week=[0, 2, 4],  # Mon, Wed, Fri
        priority=PRIORITY_HIGH
    )

    assert task.name == "full_task"
    assert task.args == (1, 2)
    assert task.kwargs == {"c": 3}
    assert task.interval_seconds == 60
    assert task.run_at_hour == 14
    assert task.run_at_minute == 30
    assert task.days_of_week == [0, 2, 4]
    assert task.priority == PRIORITY_HIGH


def test_scheduled_task_unique_ids():
    """Test that each task gets a unique ID (long type)."""
    def dummy():
        pass

    task1 = ScheduledTask("task1", dummy)
    task2 = ScheduledTask("task2", dummy)

    assert task1.task_id != task2.task_id
    # In Python 3, only int type exists
    assert isinstance(task1.task_id, int)


def test_scheduled_task_is_due_interval():
    """Test is_due for interval-based tasks."""
    def dummy():
        pass

    task = ScheduledTask("interval_task", dummy, interval_seconds=60)
    task.next_run = time.time() + 30

    # Not due yet
    assert task.is_due() is False

    # Set to past time
    task.next_run = time.time() - 5
    assert task.is_due() is True


def test_scheduled_task_is_due_cancelled():
    """Test that cancelled tasks are never due."""
    def dummy():
        pass

    task = ScheduledTask("cancelled_task", dummy, interval_seconds=10)
    task.next_run = time.time() - 100
    task.status = _STATUS_CANCELLED

    assert task.is_due() is False


def test_scheduled_task_is_due_hourly():
    """Test is_due for time-of-day scheduled tasks."""
    def dummy():
        pass

    now = time.time()
    lt = time.localtime(now)

    # Create task for current hour and minute
    task = ScheduledTask("hourly_task", dummy, run_at_hour=lt.tm_hour, run_at_minute=lt.tm_min)

    # Should be due (first run)
    assert task.is_due(now) is True

    # Mark as run
    task.last_run = now

    # Should not be due again in same minute
    assert task.is_due(now + 1) is False


def test_scheduled_task_is_due_day_of_week():
    """Test is_due respects days_of_week constraint."""
    def dummy():
        pass

    now = time.time()
    lt = time.localtime(now)
    current_weekday = lt.tm_wday

    # Schedule for different day
    other_day = (current_weekday + 1) % 7
    task = ScheduledTask(
        "weekly_task",
        dummy,
        run_at_hour=lt.tm_hour,
        run_at_minute=lt.tm_min,
        days_of_week=[other_day]
    )

    assert task.is_due(now) is False

    # Schedule for current day
    task.days_of_week = [current_weekday]
    assert task.is_due(now) is True


def test_scheduled_task_compute_next_run():
    """Test computing next run time for interval tasks."""
    def dummy():
        pass

    task = ScheduledTask("interval_task", dummy, interval_seconds=120)
    now = time.time()

    task.compute_next_run(now)

    assert task.next_run is not None
    assert task.next_run > now
    assert abs(task.next_run - (now + 120)) < 1


def test_scheduled_task_cancel():
    """Test cancelling a task."""
    def dummy():
        pass

    task = ScheduledTask("cancellable", dummy)
    assert task.status == _STATUS_PENDING

    task.cancel()
    assert task.status == _STATUS_CANCELLED


def test_scheduled_task_repr():
    """Test string representation."""
    def dummy():
        pass

    task = ScheduledTask("repr_test", dummy)
    repr_str = repr(task)

    assert "repr_test" in repr_str
    assert str(task.task_id) in repr_str
    assert _STATUS_PENDING in repr_str


# ============================================================================
# task_stream Generator Tests
# ============================================================================

def test_task_stream_yields_from_queue():
    """Test task_stream yields tasks from queue."""
    q = queue.Queue()
    stream = task_stream(q, poll_interval=0.1)

    # Queue is empty, should yield None
    result = next(stream)
    assert result is None


def test_task_stream_yields_task():
    """Test task_stream yields actual task when available."""
    q = queue.Queue()
    def dummy():
        pass
    task = ScheduledTask("stream_task", dummy)
    q.put(task)

    stream = task_stream(q, poll_interval=0.1)
    result = next(stream)

    assert result == task


def test_task_stream_generator_exit(capsys):
    """Test task_stream handles GeneratorExit."""
    q = queue.Queue()
    stream = task_stream(q, poll_interval=0.1)

    next(stream)  # Prime the generator
    stream.close()  # Trigger GeneratorExit

    captured = capsys.readouterr()
    assert "Task stream shutting down" in captured.out


def test_task_stream_throw_platform_error(capsys):
    """Test task_stream handles thrown PlatformError (generator throw() API)."""
    q = queue.Queue()
    stream = task_stream(q, poll_interval=0.1)

    next(stream)  # Prime the generator
    result = stream.throw(PlatformError, PlatformError("Test cancellation"))

    assert result is None
    captured = capsys.readouterr()
    assert "Task stream cancellation" in captured.out


# ============================================================================
# TaskWorker Tests
# ============================================================================

def test_task_worker_init():
    """Test TaskWorker initialization."""
    task_q = queue.Queue()
    result_q = queue.Queue()

    worker = TaskWorker(0, task_q, result_q)

    assert worker.worker_id == 0
    assert worker.task_queue == task_q
    assert worker.result_queue == result_q
    assert worker._running is False


@mock.patch("_thread.start_new_thread")
def test_task_worker_start(mock_thread, capsys):
    """Test starting worker thread (thread.start_new_thread usage)."""
    task_q = queue.Queue()
    result_q = queue.Queue()
    worker = TaskWorker(1, task_q, result_q)

    worker.start()

    assert worker._running is True
    mock_thread.assert_called_once()
    captured = capsys.readouterr()
    assert "Worker 1 started" in captured.out


def test_task_worker_execute_task_success(capsys):
    """Test successful task execution."""
    task_q = queue.Queue()
    result_q = queue.Queue()
    worker = TaskWorker(0, task_q, result_q)

    def success_func(x, y):
        return x + y

    task = ScheduledTask("add_task", success_func, args=(5, 3))
    worker._execute_task(task)

    assert task.status == _STATUS_DONE
    assert task.run_count == 1
    assert task.error_count == 0

    # Check result queue
    task_id, success, result, elapsed = result_q.get(timeout=1)
    assert success is True
    assert result == 8


def test_task_worker_execute_task_failure(capsys):
    """Test failed task execution (exception handling)."""
    task_q = queue.Queue()
    result_q = queue.Queue()
    worker = TaskWorker(0, task_q, result_q)

    def failing_func():
        raise ValueError("Intentional failure")

    task = ScheduledTask("fail_task", failing_func)

    # Mock sys.exc_type and sys.exc_value for legacy exception access
    with mock.patch("sys.exc_type", new=ValueError):
        with mock.patch("sys.exc_value", new=ValueError("Intentional failure")):
            worker._execute_task(task)

    assert task.status == _STATUS_FAILED
    assert task.error_count == 1
    assert task.last_error is not None
    assert "ValueError" in task.last_error or "Intentional failure" in task.last_error

    # Check result queue
    task_id, success, error_msg, elapsed = result_q.get(timeout=1)
    assert success is False


# ============================================================================
# TaskScheduler Tests
# ============================================================================

def test_task_scheduler_init():
    """Test TaskScheduler initialization."""
    scheduler = TaskScheduler(num_workers=3, max_queue_size=100)

    assert scheduler._num_workers == 3
    assert scheduler.task_queue.maxsize == 100
    assert scheduler._running is False
    assert len(scheduler.workers) == 0


def test_task_scheduler_sys_exitfunc():
    """Test that sys.exitfunc is set during init (G3 - legacy cleanup hook)."""
    original_exitfunc = getattr(sys, "exitfunc", None)

    scheduler = TaskScheduler()
    assert sys.exitfunc == scheduler._cleanup

    # Restore original
    if original_exitfunc:
        sys.exitfunc = original_exitfunc


@mock.patch("src.automation.scheduler.TaskWorker")
def test_task_scheduler_start(mock_worker_class, capsys):
    """Test starting scheduler workers."""
    scheduler = TaskScheduler(num_workers=2)

    scheduler.start()

    assert scheduler._running is True
    assert len(scheduler.workers) == 2
    captured = capsys.readouterr()
    assert "Scheduler started with 2 workers" in captured.out


def test_task_scheduler_stop():
    """Test stopping scheduler."""
    scheduler = TaskScheduler(num_workers=2)
    scheduler._running = True

    # Mock workers
    scheduler.workers = [mock.MagicMock() for _ in range(2)]

    scheduler.stop()

    assert scheduler._running is False
    # Should have put None sentinels for each worker
    assert scheduler.task_queue.qsize() == 2


def test_task_scheduler_schedule_collection(capsys):
    """Test scheduling periodic data collection."""
    scheduler = TaskScheduler()

    def collect_data(sensor_id):
        return f"Data from {sensor_id}"

    task_id = scheduler.schedule_collection(
        "temp_collection",
        collect_data,
        interval=60,
        args=("TEMP_001",),
        priority=PRIORITY_HIGH
    )

    assert task_id in scheduler.registered_tasks
    task = scheduler.registered_tasks[task_id]
    assert task.name == "temp_collection"
    assert task.interval_seconds == 60
    assert task.next_run is not None

    captured = capsys.readouterr()
    assert "Scheduled collection" in captured.out
    assert "60s" in captured.out


def test_task_scheduler_schedule_batch_job(capsys):
    """Test scheduling batch job at specific time."""
    scheduler = TaskScheduler()

    def batch_process():
        return "Batch complete"

    task_id = scheduler.schedule_batch_job(
        "nightly_batch",
        batch_process,
        run_at_hour=2,
        run_at_minute=30,
        days_of_week=[1, 3, 5]  # Tue, Thu, Sat
    )

    assert task_id in scheduler.registered_tasks
    task = scheduler.registered_tasks[task_id]
    assert task.run_at_hour == 2
    assert task.run_at_minute == 30
    assert task.days_of_week == [1, 3, 5]

    captured = capsys.readouterr()
    assert "Scheduled batch" in captured.out
    assert "02:30" in captured.out


def test_task_scheduler_schedule_report():
    """Test scheduling report (wrapper around schedule_batch_job)."""
    scheduler = TaskScheduler()

    def generate_report():
        return "Report"

    task_id = scheduler.schedule_report("daily_report", generate_report, run_at_hour=8)

    assert task_id in scheduler.registered_tasks


def test_task_scheduler_submit_immediate():
    """Test submitting task for immediate execution."""
    scheduler = TaskScheduler()

    def immediate_func():
        return "Done"

    task_id = scheduler.submit_immediate("urgent_task", immediate_func)

    assert task_id in scheduler.registered_tasks
    # Should be in queue
    assert scheduler.task_queue.qsize() == 1


def test_task_scheduler_cancel_task(capsys):
    """Test cancelling a registered task."""
    scheduler = TaskScheduler()

    def dummy():
        pass

    task_id = scheduler.schedule_collection("cancel_me", dummy, interval=30)

    result = scheduler.cancel_task(task_id)

    assert result is True
    assert scheduler.registered_tasks[task_id].status == _STATUS_CANCELLED
    captured = capsys.readouterr()
    assert "Cancelled task" in captured.out


def test_task_scheduler_cancel_task_not_found():
    """Test cancelling non-existent task."""
    scheduler = TaskScheduler()
    result = scheduler.cancel_task(99999)
    assert result is False


def test_task_scheduler_cancel_via_stream(capsys):
    """Test cancelling task via generator throw() (C8 - generator throw API)."""
    scheduler = TaskScheduler()

    def dummy():
        pass

    task_id = scheduler.schedule_collection("stream_cancel", dummy, interval=30)

    # Create a mock stream
    stream = mock.MagicMock()

    result = scheduler.cancel_via_stream(stream, task_id)

    assert result is True
    assert scheduler.registered_tasks[task_id].status == _STATUS_CANCELLED
    # Should have called throw with two positional arguments (Py2 style)
    stream.throw.assert_called_once()

    captured = capsys.readouterr()
    assert "Sent cancellation to stream" in captured.out


def test_task_scheduler_check_and_dispatch_due_task():
    """Test dispatching tasks that are due."""
    scheduler = TaskScheduler()

    def dummy():
        return "Result"

    task_id = scheduler.schedule_collection("dispatch_test", dummy, interval=60)

    # Make task due by setting next_run to past
    scheduler.registered_tasks[task_id].next_run = time.time() - 10

    scheduler.check_and_dispatch()

    # Task should be in queue
    assert scheduler.task_queue.qsize() == 1


def test_task_scheduler_check_and_dispatch_priority_order():
    """Test that tasks are dispatched in priority order."""
    scheduler = TaskScheduler()

    def dummy():
        pass

    # Create tasks with different priorities
    id_low = scheduler.schedule_collection("low", dummy, interval=60, priority=PRIORITY_LOW)
    id_high = scheduler.schedule_collection("high", dummy, interval=60, priority=PRIORITY_HIGH)
    id_normal = scheduler.schedule_collection("normal", dummy, interval=60, priority=PRIORITY_NORMAL)

    # Make all due
    for tid in [id_low, id_high, id_normal]:
        scheduler.registered_tasks[tid].next_run = time.time() - 10

    scheduler.check_and_dispatch()

    # High priority should be first
    first_task = scheduler.task_queue.get(timeout=1)
    assert first_task.priority == PRIORITY_HIGH


def test_task_scheduler_check_and_dispatch_queue_full(capsys):
    """Test handling when queue is full."""
    scheduler = TaskScheduler(max_queue_size=1)

    def dummy():
        pass

    # Fill the queue
    scheduler.task_queue.put("blocker")

    task_id = scheduler.schedule_collection("deferred", dummy, interval=60)
    scheduler.registered_tasks[task_id].next_run = time.time() - 10

    capsys.readouterr()  # Clear
    scheduler.check_and_dispatch()

    captured = capsys.readouterr()
    assert "queue full" in captured.out


def test_task_scheduler_collect_results():
    """Test collecting results from result queue."""
    scheduler = TaskScheduler()

    # Put some results
    scheduler.result_queue.put((1, True, "result1", 0.5))
    scheduler.result_queue.put((2, False, "error", 0.2))

    results = scheduler.collect_results(limit=10)

    assert len(results) == 2
    assert results[0][0] == 1
    assert results[1][0] == 2


def test_task_scheduler_collect_results_limit():
    """Test result collection respects limit."""
    scheduler = TaskScheduler()

    for i in range(10):
        scheduler.result_queue.put((i, True, f"result{i}", 0.1))

    results = scheduler.collect_results(limit=5)

    assert len(results) == 5


def test_task_scheduler_cleanup(capsys):
    """Test cleanup method (called via sys.exitfunc)."""
    scheduler = TaskScheduler(num_workers=2)
    scheduler._running = True
    scheduler.workers = [mock.MagicMock(), mock.MagicMock()]

    scheduler._cleanup()

    assert scheduler._running is False
    captured = capsys.readouterr()
    assert "Scheduler cleanup" in captured.out


def test_task_scheduler_get_status():
    """Test retrieving scheduler status."""
    scheduler = TaskScheduler(num_workers=2)

    def dummy():
        pass

    scheduler.schedule_collection("status_task", dummy, interval=60)
    scheduler._running = True

    status = scheduler.get_status()

    assert status["running"] is True
    assert status["workers"] == 0  # Not started yet
    assert "tasks" in status
    assert len(status["tasks"]) == 1
