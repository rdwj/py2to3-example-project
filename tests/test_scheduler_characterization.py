# -*- coding: utf-8 -*-
"""
Characterization tests for src/automation/scheduler.py

Captures pre-migration behavior of:
- ScheduledTask with long() IDs and timing logic
- task_stream generator with throw() for cancellation
- TaskWorker execution with sys.exc_type/sys.exc_value
- TaskScheduler queue dispatch with thread.allocate_lock()
- Py2-specific: long literals, thread module, Queue module,
  xrange, sys.exitfunc, sys.exc_type/exc_value, dict.iteritems/itervalues
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time
import Queue

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.automation.scheduler import (
    ScheduledTask, TaskScheduler, TaskWorker, task_stream,
    PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW,
    _STATUS_PENDING, _STATUS_RUNNING, _STATUS_DONE,
    _STATUS_FAILED, _STATUS_CANCELLED,
)
from src.core.exceptions import PlatformError


# ---------------------------------------------------------------------------
# ScheduledTask
# ---------------------------------------------------------------------------

class TestScheduledTask:
    """Characterize task metadata and timing logic."""

    @pytest.mark.py2_behavior
    def test_construction_uses_long_id(self):
        """Captures: task_id assigned via long() (removed in Py3)."""
        # Reset counter for deterministic test
        ScheduledTask._next_id = 0L
        task = ScheduledTask("test_task", lambda: None)
        assert task.task_id >= 1
        assert isinstance(task.task_id, (int, long))

    def test_initial_state(self):
        """Captures: initial field values after construction."""
        task = ScheduledTask("collect", lambda: "data", interval_seconds=60)
        assert task.name == "collect"
        assert task.status == _STATUS_PENDING
        assert task.interval_seconds == 60
        assert task.run_count == 0
        assert task.error_count == 0

    def test_is_due_with_next_run(self):
        """Captures: task is due when now >= next_run."""
        task = ScheduledTask("t", lambda: None, interval_seconds=10)
        task.next_run = time.time() - 1  # set in the past
        assert task.is_due() is True

    def test_is_due_not_yet(self):
        """Captures: task is not due when next_run is in the future."""
        task = ScheduledTask("t", lambda: None, interval_seconds=10)
        task.next_run = time.time() + 3600
        assert task.is_due() is False

    def test_is_due_cancelled(self):
        """Captures: cancelled task is never due."""
        task = ScheduledTask("t", lambda: None)
        task.next_run = time.time() - 1
        task.cancel()
        assert task.is_due() is False

    def test_compute_next_run(self):
        """Captures: next_run = from_time + interval_seconds."""
        task = ScheduledTask("t", lambda: None, interval_seconds=60)
        base = 1000000.0
        task.compute_next_run(from_time=base)
        assert task.next_run == base + 60

    def test_cancel_sets_status(self):
        """Captures: cancel() sets status to cancelled."""
        task = ScheduledTask("t", lambda: None)
        task.cancel()
        assert task.status == _STATUS_CANCELLED

    def test_repr(self):
        """Captures: __repr__ format with name, id, status."""
        task = ScheduledTask("my_task", lambda: None)
        r = repr(task)
        assert "my_task" in r
        assert "pending" in r

    def test_is_due_with_hour_minute(self):
        """Captures: time-of-day scheduling logic."""
        now = time.time()
        lt = time.localtime(now)
        task = ScheduledTask("daily", lambda: None,
                             run_at_hour=lt.tm_hour, run_at_minute=lt.tm_min)
        assert task.is_due(now) is True

    def test_is_due_wrong_hour(self):
        """Captures: task not due when hour doesn't match."""
        task = ScheduledTask("daily", lambda: None, run_at_hour=25)
        assert task.is_due() is False


# ---------------------------------------------------------------------------
# task_stream generator
# ---------------------------------------------------------------------------

class TestTaskStream:
    """Characterize the task_stream generator."""

    def test_yields_from_queue(self):
        """Captures: task_stream yields items from the queue."""
        q = Queue.Queue()
        task = ScheduledTask("t", lambda: None)
        q.put(task)
        gen = task_stream(q, poll_interval=0.1)
        result = gen.next()
        assert result is task

    def test_yields_none_on_timeout(self):
        """Captures: empty queue yields None after poll interval."""
        q = Queue.Queue()
        gen = task_stream(q, poll_interval=0.1)
        result = gen.next()
        assert result is None

    @pytest.mark.py2_behavior
    def test_throw_cancellation(self):
        """Captures: throw(PlatformError, msg) for task cancellation (C8).
        Generator throw() API changed subtly in Py3."""
        q = Queue.Queue()
        gen = task_stream(q, poll_interval=0.1)
        gen.next()  # prime the generator
        # Throw a cancellation signal
        result = gen.throw(PlatformError, "Task cancelled")
        assert result is None

    def test_close_generator(self):
        """Captures: GeneratorExit handling on close()."""
        q = Queue.Queue()
        gen = task_stream(q, poll_interval=0.1)
        gen.next()  # prime
        gen.close()  # should not raise


# ---------------------------------------------------------------------------
# TaskScheduler (no background threads)
# ---------------------------------------------------------------------------

class TestTaskScheduler:
    """Characterize scheduler setup and dispatch logic (without starting workers)."""

    @pytest.fixture
    def scheduler(self):
        s = TaskScheduler(num_workers=0, max_queue_size=100)
        yield s
        # Don't call stop since we never started workers

    def test_schedule_collection(self, scheduler):
        """Captures: schedule_collection registers a periodic task."""
        tid = scheduler.schedule_collection("collect", lambda: "data", 60)
        assert tid in scheduler.registered_tasks
        task = scheduler.registered_tasks[tid]
        assert task.name == "collect"
        assert task.interval_seconds == 60

    def test_schedule_batch_job(self, scheduler):
        """Captures: schedule_batch_job registers a time-of-day task."""
        tid = scheduler.schedule_batch_job("daily_report", lambda: None,
                                            run_at_hour=2, run_at_minute=30)
        task = scheduler.registered_tasks[tid]
        assert task.run_at_hour == 2
        assert task.run_at_minute == 30

    def test_cancel_task(self, scheduler):
        """Captures: cancel_task sets task status to cancelled."""
        tid = scheduler.schedule_collection("t", lambda: None, 60)
        assert scheduler.cancel_task(tid) is True
        assert scheduler.registered_tasks[tid].status == _STATUS_CANCELLED

    def test_cancel_nonexistent_returns_false(self, scheduler):
        """Captures: cancelling a nonexistent task returns False."""
        assert scheduler.cancel_task(99999) is False

    def test_submit_immediate(self, scheduler):
        """Captures: submit_immediate puts task directly on queue."""
        tid = scheduler.submit_immediate("urgent", lambda: "fast")
        assert scheduler.task_queue.qsize() == 1

    def test_get_status(self, scheduler):
        """Captures: status dict structure."""
        scheduler.schedule_collection("t1", lambda: None, 60)
        status = scheduler.get_status()
        assert "running" in status
        assert "workers" in status
        assert "queue_size" in status
        assert "tasks" in status

    def test_check_and_dispatch_enqueues_due_tasks(self, scheduler):
        """Captures: check_and_dispatch enqueues tasks that are due."""
        tid = scheduler.schedule_collection("due_task", lambda: "result", 0)
        task = scheduler.registered_tasks[tid]
        task.next_run = time.time() - 1  # make it due
        scheduler.check_and_dispatch()
        assert scheduler.task_queue.qsize() >= 1

    def test_collect_results_empty(self, scheduler):
        """Captures: collect_results on empty queue returns empty list."""
        results = scheduler.collect_results()
        assert results == []


# ---------------------------------------------------------------------------
# TaskWorker (synchronous task execution test)
# ---------------------------------------------------------------------------

class TestTaskWorkerExecution:
    """Characterize task execution behavior."""

    def test_execute_successful_task(self):
        """Captures: successful execution sets status=done, increments run_count."""
        task_q = Queue.Queue()
        result_q = Queue.Queue()
        worker = TaskWorker(0, task_q, result_q)

        task = ScheduledTask("test", lambda: 42)
        worker._execute_task(task)

        assert task.status == _STATUS_DONE
        assert task.run_count == 1
        tid, success, result, elapsed = result_q.get(timeout=1.0)
        assert success is True
        assert result == 42

    @pytest.mark.py2_behavior
    def test_execute_failing_task_uses_sys_exc_type(self):
        """Captures: failed task uses sys.exc_type/sys.exc_value (G2).
        Removed in Py3; use sys.exc_info() instead."""
        task_q = Queue.Queue()
        result_q = Queue.Queue()
        worker = TaskWorker(0, task_q, result_q)

        def failing():
            raise ValueError("test error")

        task = ScheduledTask("bad", failing)
        worker._execute_task(task)

        assert task.status == _STATUS_FAILED
        assert task.error_count == 1
        assert "ValueError" in task.last_error
        tid, success, error_msg, elapsed = result_q.get(timeout=1.0)
        assert success is False
