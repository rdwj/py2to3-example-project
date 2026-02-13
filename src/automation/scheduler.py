# -*- coding: utf-8 -*-
"""
Task scheduler for the Legacy Industrial Data Platform.

Manages periodic data collection, batch processing, and report generation.
Tasks are submitted to a thread-safe queue and executed by worker threads
on configurable schedules -- cron-like intervals, fixed-delay repeats, or
one-shot deferred execution.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import time
import atexit
import _thread
import queue

from core.exceptions import PlatformError

PRIORITY_HIGH = 0
PRIORITY_NORMAL = 5
PRIORITY_LOW = 10
_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_DONE = "done"
_STATUS_FAILED = "failed"
_STATUS_CANCELLED = "cancelled"


class ScheduledTask:
    """A schedulable unit of work with timing and priority metadata."""

    _next_id = 0

    def __init__(self, name, callable_obj, args=None, kwargs=None,
                 interval_seconds=None, run_at_hour=None, run_at_minute=0,
                 days_of_week=None, priority=PRIORITY_NORMAL):
        ScheduledTask._next_id += 1
        self.task_id = int(ScheduledTask._next_id)
        self.name = name
        self.callable_obj = callable_obj
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.interval_seconds = interval_seconds
        self.run_at_hour = run_at_hour
        self.run_at_minute = run_at_minute
        self.days_of_week = days_of_week
        self.priority = priority
        self.status = _STATUS_PENDING
        self.last_run = None
        self.next_run = None
        self.run_count = 0
        self.error_count = 0
        self.last_error = None

    def is_due(self, now=None):
        if now is None:
            now = time.time()
        if self.status == _STATUS_CANCELLED:
            return False
        if self.next_run is not None and now >= self.next_run:
            return True
        if self.run_at_hour is None:
            return False
        lt = time.localtime(now)
        if lt.tm_hour != self.run_at_hour or lt.tm_min != self.run_at_minute:
            return False
        if self.days_of_week is not None and lt.tm_wday not in self.days_of_week:
            return False
        if self.last_run is not None:
            prev = time.localtime(self.last_run)
            if prev.tm_hour == lt.tm_hour and prev.tm_min == lt.tm_min and prev.tm_mday == lt.tm_mday:
                return False
        return True

    def compute_next_run(self, from_time=None):
        if self.interval_seconds is not None:
            self.next_run = (from_time or time.time()) + self.interval_seconds

    def cancel(self):
        self.status = _STATUS_CANCELLED

    def __repr__(self):
        return "ScheduledTask(%r, id=%d, status=%s)" % (self.name, self.task_id, self.status)


def task_stream(task_queue, poll_interval=1.0):
    """Generator that yields tasks from the queue.  Supports ``throw()``
    for injecting cancellation signals from the scheduler."""
    while True:
        try:
            try:
                yield task_queue.get(block=True, timeout=poll_interval)
            except queue.Empty:
                yield None
        except GeneratorExit:
            print("Task stream shutting down")
            return
        except PlatformError as e:
            print("Task stream cancellation: %s" % e)
            yield None


class TaskWorker:
    """Executes tasks from the shared queue via ``_thread.start_new_thread()``."""

    def __init__(self, worker_id, task_queue, result_queue):
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self._running = False

    def start(self):
        self._running = True
        _thread.start_new_thread(self._run_loop, ())
        print("Worker %d started" % self.worker_id)

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                task = self.task_queue.get(block=True, timeout=2.0)
            except queue.Empty:
                continue
            if task is None:
                break
            self._execute_task(task)
        print("Worker %d exiting" % self.worker_id)

    def _execute_task(self, task):
        task.status = _STATUS_RUNNING
        t0 = time.time()
        print("Worker %d executing %r" % (self.worker_id, task.name))
        try:
            result = task.callable_obj(*task.args, **task.kwargs)
            task.status = _STATUS_DONE
            task.last_run = time.time()
            task.run_count += 1
            self.result_queue.put((task.task_id, True, result, time.time() - t0))
        except Exception as e:
            task.status = _STATUS_FAILED
            task.error_count += 1
            exc_info = sys.exc_info()
            exc_name = exc_info[0].__name__ if exc_info[0] else "Unknown"
            exc_msg = str(exc_info[1]) if exc_info[1] else str(e)
            task.last_error = "%s: %s" % (exc_name, exc_msg)
            self.result_queue.put((task.task_id, False, task.last_error, time.time() - t0))
            print("Task %r failed: %s" % (task.name, task.last_error))


class TaskScheduler:
    """Central scheduler using ``queue.Queue`` for dispatch and
    ``atexit`` for graceful shutdown."""

    def __init__(self, num_workers=2, max_queue_size=500):
        self.task_queue = queue.Queue(maxsize=max_queue_size)
        self.result_queue = queue.Queue()
        self.workers = []
        self.registered_tasks = {}
        self._num_workers = num_workers
        self._running = False
        self._lock = _thread.allocate_lock()
        atexit.register(self._cleanup)

    def start(self):
        self._running = True
        for i in range(self._num_workers):
            w = TaskWorker(i, self.task_queue, self.result_queue)
            w.start()
            self.workers.append(w)
        print("Scheduler started with %d workers" % self._num_workers)

    def stop(self):
        self._running = False
        for _ in self.workers:
            self.task_queue.put(None)
        self.workers = []

    def schedule_collection(self, name, func, interval, args=None, priority=PRIORITY_NORMAL):
        """Schedule periodic data collection every *interval* seconds."""
        task = ScheduledTask(name, func, args=args, interval_seconds=interval, priority=priority)
        task.compute_next_run()
        self._lock.acquire()
        try:
            self.registered_tasks[task.task_id] = task
        finally:
            self._lock.release()
        print("Scheduled collection %r every %ds" % (name, interval))
        return task.task_id

    def schedule_batch_job(self, name, func, run_at_hour, run_at_minute=0,
                           days_of_week=None, args=None):
        """Schedule a batch job at a specific time of day."""
        task = ScheduledTask(name, func, args=args, run_at_hour=run_at_hour,
                             run_at_minute=run_at_minute, days_of_week=days_of_week)
        self._lock.acquire()
        try:
            self.registered_tasks[task.task_id] = task
        finally:
            self._lock.release()
        print("Scheduled batch %r at %02d:%02d" % (name, run_at_hour, run_at_minute))
        return task.task_id

    def schedule_report(self, name, func, run_at_hour, days_of_week=None):
        return self.schedule_batch_job(name, func, run_at_hour, days_of_week=days_of_week)

    def submit_immediate(self, name, func, args=None, kwargs=None):
        task = ScheduledTask(name, func, args=args, kwargs=kwargs, priority=PRIORITY_HIGH)
        self.task_queue.put(task)
        return task.task_id

    def cancel_task(self, task_id):
        self._lock.acquire()
        try:
            task = self.registered_tasks.get(task_id)
            if task is not None:
                task.cancel()
                print("Cancelled task %r" % task.name)
                return True
            return False
        finally:
            self._lock.release()

    def cancel_via_stream(self, stream, task_id):
        """Cancel a running task by throwing PlatformError into the
        task_stream generator."""
        self._lock.acquire()
        try:
            task = self.registered_tasks.get(task_id)
            if task is None:
                return False
            task.cancel()
        finally:
            self._lock.release()
        stream.throw(PlatformError, "Task %d cancelled" % task_id)
        print("Sent cancellation to stream for task %d" % task_id)
        return True

    def check_and_dispatch(self):
        """Check registered tasks and enqueue any that are due."""
        now = time.time()
        self._lock.acquire()
        try:
            due = [t for t in self.registered_tasks.values() if t.is_due(now)]
        finally:
            self._lock.release()
        for task in sorted(due, key=lambda t: t.priority):
            try:
                self.task_queue.put(task, block=False)
                task.compute_next_run(now)
            except queue.Full:
                print("WARNING: queue full, deferring %r" % task.name)

    def collect_results(self, limit=50):
        results = []
        for _ in range(limit):
            try:
                results.append(self.result_queue.get(block=False))
            except queue.Empty:
                break
        return results

    def _cleanup(self):
        """Shutdown hook registered via atexit."""
        print("Scheduler cleanup: stopping workers")
        self.stop()

    def get_status(self):
        self._lock.acquire()
        try:
            tasks = dict((tid, {"name": t.name, "status": t.status,
                                "runs": t.run_count, "errors": t.error_count})
                         for tid, t in self.registered_tasks.items())
        finally:
            self._lock.release()
        return {"running": self._running, "workers": len(self.workers),
                "queue_size": self.task_queue.qsize(), "tasks": tasks}
