"""Real spawn/process fault tests; no database, network or model loading."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.delivery.executor import (
    ExecutorBusy, ExecutorUnavailable, SpawnExecutor, WorkerChannel,
)


def fake_worker(channel, dsn, warmup):
    channel.ready()
    while (job := channel.receive()) is not None:
        mode = job.get("mode", "ok")
        if mode == "crash":
            os._exit(17)
        if mode == "hang":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
            channel.event(job, "tool_call", {"child_pid": child.pid})
            time.sleep(120)
        if mode == "slow":
            time.sleep(0.4)
        channel.event(job, "before_llm", {"user": "可重建输入"}, model_visible=True)
        channel.result(job, {"final_answer": "done", "memory_candidates": []})


def job(mode="ok", seconds=4):
    return {"run_id": f"run-{time.time_ns()}", "owner": "owner-a", "thread_id": "business-thread",
            "merchant_id": "demo", "query": "GMV", "mode": mode,
            "deadline": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
            "max_seconds": seconds}


def until(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError("condition did not become true")


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def create(**callbacks):
    return SpawnExecutor("", callbacks.get("on_event", lambda *a, **k: None),
                         callbacks.get("on_result", lambda *a: None),
                         callbacks.get("on_failure", lambda *a: None),
                         warmup=False, worker_target=fake_worker)


def test_spawn_slot_and_success_callback_order():
    events, results = [], []
    ex = create(on_event=lambda *a, **k: events.append((a, k)), on_result=lambda *a: results.append(a))
    with pytest.raises(ExecutorUnavailable):
        ex.submit(job())
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job("slow"))
        assert ex.busy
        with pytest.raises(ExecutorBusy):
            ex.submit(job())
        until(lambda: len(results) == 1)
        assert events[0][0][1] == "before_llm"
        assert events[0][1]["model_visible"] is True
        assert results[0][1]["final_answer"] == "done"
        until(lambda: ex.ready and not ex.busy)
    finally:
        ex.close()
    assert not ex.ready and not ex.busy


def test_timeout_reaps_detached_tool_and_restarts_worker():
    children, failures, results = [], [], []
    ex = create(on_event=lambda j, t, p, **k: children.append(p["child_pid"]) if "child_pid" in p else None,
                on_result=lambda *a: results.append(a), on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job("hang", seconds=0.8))
        until(lambda: bool(children))
        until(lambda: bool(failures))
        assert failures[0][1]["code"] == "run_timeout"
        until(lambda: not alive(children[0]))
        assert not results
        assert ex.wait_ready(8)
        ex.submit(job())
        until(lambda: len(results) == 1)
    finally:
        ex.close()


def test_process_death_marks_failed_and_can_run_next_job():
    failures, results = [], []
    ex = create(on_result=lambda *a: results.append(a), on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job("crash"))
        until(lambda: bool(failures))
        assert failures[0][1]["code"] == "worker_died"
        assert ex.wait_ready(8)
        ex.submit(job())
        until(lambda: bool(results))
    finally:
        ex.close()


def test_rejected_event_is_not_acknowledged_or_followed_by_result():
    failures, results = [], []
    def reject(*a, **k):
        raise RuntimeError("budget exhausted")
    ex = create(on_event=reject, on_result=lambda *a: results.append(a), on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job())
        until(lambda: bool(failures))
        assert not results
        assert failures[0][1]["code"] == "event_rejected"
    finally:
        ex.close()


def test_close_reaps_active_tool_and_never_restarts():
    children, failures = [], []
    ex = create(on_event=lambda j, t, p, **k: children.append(p["child_pid"]) if "child_pid" in p else None,
                on_failure=lambda *a: failures.append(a))
    ex.start()
    assert ex.wait_ready(8)
    ex.submit(job("hang", seconds=30))
    until(lambda: bool(children))
    ex.close()
    until(lambda: not alive(children[0]))
    assert not ex.ready and not ex.busy
    assert failures[0][1]["code"] == "server_restarted"
    ex.close()


def test_result_crossing_deadline_cannot_turn_into_success():
    failures, results = [], []
    ex = create(on_result=lambda *a: results.append(a), on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job("slow", seconds=0.15))
        until(lambda: bool(failures))
        time.sleep(0.5)
        assert not results
        assert failures[0][1]["code"] == "run_timeout"
    finally:
        ex.close()


def test_budget_rejection_preserves_public_error_code():
    failures = []
    class BudgetFailure(RuntimeError):
        code = "budget_exceeded"
    def reject(*a, **k):
        raise BudgetFailure("cap reached")
    ex = create(on_event=reject, on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job())
        until(lambda: bool(failures))
        assert failures[0][1]["code"] == "budget_exceeded"
    finally:
        ex.close()


def test_slow_event_commit_cannot_delay_worker_deadline_cleanup():
    failures, results = [], []
    entered, release = threading.Event(), threading.Event()
    def slow(*a, **k):
        entered.set()
        release.wait(10)
    ex = create(on_event=slow, on_failure=lambda *a: failures.append(a),
                on_result=lambda *a: results.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        ex.submit(job(seconds=0.4))
        assert entered.wait(3)
        until(lambda: bool(failures), timeout=4)
        assert not release.is_set()
        assert not results
        assert failures[0][1]["code"] == "run_timeout"
    finally:
        release.set()
        ex.close()


def abrupt_parent(connection):
    children = []
    ex = create(on_event=lambda j, t, p, **k: children.append(p["child_pid"]) if "child_pid" in p else None)
    ex.start()
    if not ex.wait_ready(8):
        os._exit(18)
    ex.submit(job("hang", seconds=30))
    until(lambda: bool(children))
    connection.send((ex._process.pid, children[0]))
    connection.close()
    os._exit(0)


def test_abrupt_api_parent_death_reaps_worker_and_detached_tool():
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    parent = ctx.Process(target=abrupt_parent, args=(send,))
    parent.start()
    send.close()
    assert receive.poll(10)
    worker_pid, tool_pid = receive.recv()
    receive.close()
    parent.join(timeout=5)
    assert parent.exitcode == 0
    until(lambda: not alive(worker_pid))
    until(lambda: not alive(tool_pid))


def ack_window_parent(connection):
    # 子进程等ACK时终止API，故障不能靠200ms轮询碰巧先看到父死亡。
    def callback(j, t, p, **kwargs):
        if "child_pid" in p:
            connection.send((os.getpid(), ex._process.pid, p["child_pid"]))
            os._exit(0)
    ex = create(on_event=callback)
    ex.start()
    assert ex.wait_ready(8)
    ex.submit(job("hang", seconds=30))
    time.sleep(60)


def test_parent_death_during_event_ack_reaps_detached_tool():
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    parent = ctx.Process(target=ack_window_parent, args=(send,))
    parent.start()
    send.close()
    assert receive.poll(10)
    parent_pid, worker_pid, tool_pid = receive.recv()
    receive.close()
    try:
        parent.join(timeout=5)
        assert parent.exitcode == 0
        until(lambda: not alive(worker_pid))
        until(lambda: not alive(tool_pid), timeout=2)
    finally:
        for pid in (worker_pid, tool_pid):
            if alive(pid):
                os.kill(pid, signal.SIGKILL)


def no_read_once_worker(channel, dsn, warmup):
    from pathlib import Path
    marker = Path(dsn)
    if marker.exists():
        fake_worker(channel, dsn, warmup)
        return
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
    marker.write_text(str(child.pid))
    channel.ready()
    time.sleep(120)


def test_nonreading_worker_large_payload_does_not_block_submit_or_deadline(tmp_path):
    failures, results, dispatch_errors = [], [], []
    returned = threading.Event()
    marker = tmp_path / "worker-first-start"
    ex = SpawnExecutor(str(marker), lambda *a, **k: None, lambda *a: results.append(a),
                       lambda *a: failures.append(a), warmup=False, worker_target=no_read_once_worker)
    ex.start()
    assert ex.wait_ready(8)
    worker_pid, tool_pid = ex._process.pid, int(marker.read_text())
    request = job(seconds=0.8)
    request["context"] = {"large_history": "x" * (2 * 1024 * 1024)}
    def submit():
        try:
            ex.submit(request)
        except Exception as exc:
            dispatch_errors.append(type(exc).__name__)
        finally:
            returned.set()
    caller = threading.Thread(target=submit, daemon=True)
    caller.start()
    try:
        assert returned.wait(0.5), "IPC backpressure blocked task admission"
        assert not dispatch_errors
        until(lambda: bool(failures), timeout=4)
        assert failures[0][1]["code"] == "run_timeout"
        until(lambda: not alive(worker_pid) and not alive(tool_pid))
        assert ex.wait_ready(8)
        ex.submit(job())
        until(lambda: bool(results))
        assert len(failures) == 1
    finally:
        # 修复前send持状态锁会阻塞close，先杀本测试拥有的worker解除管道写阻塞。
        if not returned.is_set() and alive(worker_pid):
            os.kill(worker_pid, signal.SIGKILL)
            returned.wait(3)
        ex.close()
        if alive(tool_pid):
            os.kill(tool_pid, signal.SIGKILL)
        caller.join(timeout=2)


def test_late_sender_failure_cannot_recycle_a_new_job(monkeypatch):
    failures, results = [], []
    blocked, release = threading.Event(), threading.Event()
    ex = create(on_result=lambda *a: results.append(a), on_failure=lambda *a: failures.append(a))
    ex.start()
    try:
        assert ex.wait_ready(8)
        old = job(seconds=0.2)
        original = ex._send_for_job
        def delayed_failure(connection, request, message):
            if request["run_id"] == old["run_id"]:
                blocked.set()
                release.wait(10)
                raise OSError("old connection write failed after restart")
            return original(connection, request, message)
        monkeypatch.setattr(ex, "_send_for_job", delayed_failure)
        ex.submit(old)
        assert blocked.wait(2)
        until(lambda: bool(failures), timeout=4)
        assert ex.wait_ready(8)
        new = job("slow")
        ex.submit(new)
        release.set()
        until(lambda: bool(results))
        assert results[0][0]["run_id"] == new["run_id"]
        assert len(failures) == 1 and failures[0][0]["run_id"] == old["run_id"]
    finally:
        release.set()
        ex.close()
