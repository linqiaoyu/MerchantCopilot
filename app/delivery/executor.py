"""One spawn worker, acknowledged durable events and bounded process ownership.

Callbacks run in the parent and must commit before returning. The repository is
responsible for fencing its terminal transaction with owner and deadline too.
No graph, embedding, or database modules are imported in the API parent here.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from multiprocessing.connection import Connection
from typing import Callable

_LOG = logging.getLogger(__name__)
_UNSET = object()


class ExecutorUnavailable(RuntimeError):
    pass


class ExecutorBusy(RuntimeError):
    pass


class WorkerStopped(BaseException):
    """A rejected parent ACK must bypass agent deterministic-fallback handlers."""


def _descendants(pid: int) -> set[int]:
    """MCP starts an independent session; include its process tree explicitly."""
    try:
        with subprocess.Popen(["/bin/ps", "-axo", "pid=,ppid="], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as probe:
            try:
                output, _ = probe.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                probe.kill()
                probe.communicate()
                return set()
            probe_pid = probe.pid
        pairs = [tuple(map(int, line.split())) for line in output.splitlines()]
    except (OSError, ValueError, subprocess.SubprocessError):
        return set()
    found = {pid}
    while True:
        children = {child for child, parent in pairs if parent in found}
        if children <= found:
            return found - {pid, probe_pid}
        found.update(children)


def _signal_owned(pids: set[int], sig: int) -> None:
    for pid in pids:
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            pgid = os.getpgid(pid)
            if pgid == pid and pgid != os.getpgrp():
                os.killpg(pgid, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            pass


class WorkerChannel:
    """Injected worker protocol: ready; receive job; ACKed event; result/failure.

    Fake worker targets are module-level functions `(channel, dsn, warmup)`.
    The spawn bootstrap owns session isolation and parent-death cleanup for both
    production and test targets.
    """
    def __init__(self, connection: Connection):
        self.connection = connection
        self._children: set[int] = set()

    def owned_children(self) -> set[int]:
        self._children.update(_descendants(os.getpid()))
        return set(self._children)

    def ready(self) -> None:
        self.connection.send({"kind": "ready", "children": list(self.owned_children())})

    def receive(self) -> dict | None:
        try:
            message = self.connection.recv()
        except EOFError:
            return None
        return message.get("job") if message.get("kind") == "run" else None

    def event(self, job: dict, event_type: str, payload: dict, *, model_visible=False) -> None:
        self.connection.send({"kind": "event", "run_id": job["run_id"], "owner": job["owner"],
                              "event_type": event_type, "payload": payload,
                              "model_visible": model_visible,
                              "children": list(self.owned_children())})
        reply = self.connection.recv()
        if reply.get("kind") != "ack" or not reply.get("accepted"):
            raise WorkerStopped("parent rejected event")

    def result(self, job: dict, result: dict) -> None:
        self.connection.send({"kind": "result", "run_id": job["run_id"], "owner": job["owner"],
                              "result": result})

    def failure(self, job: dict, error: dict) -> None:
        self.connection.send({"kind": "failure", "run_id": job["run_id"], "owner": job["owner"],
                              "error": error})


def _bootstrap(connection, dsn, warmup, target, parent_pid):
    os.setsid()
    done = threading.Event()
    channel = WorkerChannel(connection)

    def watch_parent():
        while not done.wait(0.2):
            if os.getppid() != parent_pid:
                children = channel.owned_children()
                _signal_owned(children, signal.SIGKILL)
                os.killpg(os.getpgrp(), signal.SIGKILL)

    threading.Thread(target=watch_parent, name="delivery-parent-watch", daemon=True).start()
    try:
        target(channel, dsn, warmup)
    except WorkerStopped:
        pass
    except BaseException as exc:
        try:
            connection.send({"kind": "startup_failed", "error_type": type(exc).__name__})
        except (OSError, EOFError):
            pass
    finally:
        # ACK等待可能先收到EOF并退出，不能先停父存活watch留下独立MCP session。
        # 无论正常close、协议断开或初始化异常，worker出口均回收登记过的工具。
        children = channel.owned_children()
        _signal_owned(children, signal.SIGTERM)
        _signal_owned(children, signal.SIGKILL)
        done.set()
        connection.close()


def _agent_worker(channel: WorkerChannel, dsn: str, warmup: bool):
    # 只在spawn子进程加载模型，API父进程不持有BGE/MCP状态。
    if dsn:
        os.environ["DATABASE_URL"] = dsn
    os.environ["MERCHANTCOPILOT_DISABLE_LANGSMITH"] = "1"
    os.environ["LANGSMITH_TRACING"] = "false"
    from app.agent.context import RunContext
    from app.agent.graph_v2 import build_graph_v2
    from app.agent.runtime import run_query
    from app.llm.client import capture_llm_trace, capture_usage, observe_llm
    from app.storage.database import checkpointer_context
    from app.tools.client import _CLIENT

    try:
        if warmup:
            from app.rag.indexer import get_embedder
            from app.rag.retriever import get_reranker
            get_embedder()
            get_reranker()
            _CLIENT._ensure_started()
        channel.ready()
        while (job := channel.receive()) is not None:
            emit = lambda kind, payload, model_visible=False: channel.event(
                job, kind, payload, model_visible=model_visible)
            try:
                context = RunContext(run_id=job["run_id"], thread_id=job["thread_id"],
                                     merchant_id=job["merchant_id"])
                emit("query_ingested", {"query": job["query"], "context": job.get("context", {}),
                                       "thread_id": job["thread_id"],
                                       "completed_context": job.get("completed_context", [])}, True)
                with capture_usage() as usage, capture_llm_trace() as traces, observe_llm(
                    emit, max_tokens=int(job.get("max_tokens", 2048)),
                    completed_context=job.get("completed_context"),
                ):
                    if dsn:
                        with checkpointer_context(dsn) as checkpointer:
                            result = run_query(job["query"], graph=build_graph_v2(checkpointer),
                                               run_context=context, checkpoint_id=job["run_id"],
                                               event_callback=emit, max_actions=3,
                                               analysis_context=job.get("context"))
                    else:
                        result = run_query(job["query"], run_context=context,
                                           checkpoint_id=job["run_id"], event_callback=emit, max_actions=3,
                                           analysis_context=job.get("context"))
                result["llm_usage"] = usage
                result["model_traces"] = traces
                channel.result(job, result)
            except Exception as exc:
                channel.failure(job, {"code": "agent_failed", "error_type": type(exc).__name__})
    finally:
        _CLIENT.close()


class SpawnExecutor:
    def __init__(self, dsn: str, on_event: Callable, on_result: Callable,
                 on_failure: Callable, warmup=True, worker_target=None):
        self.dsn, self.warmup = dsn, warmup
        self.on_event, self.on_result, self.on_failure = on_event, on_result, on_failure
        self.worker_target = worker_target or _agent_worker
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._closed = True
        self._ready = False
        self._job = None
        self._deadline = 0.0
        self._process = None
        self._connection = None
        self._children: set[int] = set()
        self._monitor = None
        self._watchdog = None
        self._sender = None
        self._recycling = False
        self.last_startup_error: str | None = None

    @property
    def ready(self):
        with self._lock:
            return not self._closed and self._ready and not self._recycling

    @property
    def busy(self):
        with self._lock:
            return self._job is not None

    def wait_ready(self, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.ready:
                return True
            if self._closed:
                return False
            time.sleep(0.025)
        return False

    def _spawn_locked(self):
        parent, child = self._ctx.Pipe(duplex=True)
        process = self._ctx.Process(target=_bootstrap,
                                    args=(child, self.dsn, self.warmup, self.worker_target, os.getpid()),
                                    name="merchant-agent-worker", daemon=False)
        process.start()
        child.close()
        self._process, self._connection = process, parent
        self._ready = False
        self._children = set()

    def start(self):
        with self._lock:
            if not self._closed:
                return
            self._closed = False
            self._spawn_locked()
            self._monitor = threading.Thread(target=self._receive, name="delivery-events", daemon=True)
            self._watchdog = threading.Thread(target=self._watch, name="delivery-deadlines", daemon=True)
            self._monitor.start()
            self._watchdog.start()

    def submit(self, job: dict):
        with self._lock:
            if self._job is not None:
                raise ExecutorBusy("analysis slot occupied")
            if not self.ready:
                raise ExecutorUnavailable("agent worker not ready")
            deadline = datetime.fromisoformat(str(job["deadline"]).replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                raise ValueError("deadline must include UTC offset")
            seconds = min(120.0, float(job.get("max_seconds", 120)),
                          (deadline - datetime.now(timezone.utc)).total_seconds())
            if seconds <= 0:
                raise ValueError("deadline already elapsed")
            self._job = dict(job)
            self._deadline = time.monotonic() + seconds
            sender = threading.Thread(target=self._dispatch, args=(self._connection, self._job),
                                      name="delivery-dispatch", daemon=True)
            self._sender = sender
            try:
                sender.start()
            except Exception:
                self._job, self._sender = None, None
                raise

    def _send_for_job(self, connection, job, message):
        # 管道背压不得持状态锁，否则watchdog无法截止；只序列化同一管道的写帧。
        with self._send_lock:
            with self._lock:
                if (connection is not self._connection or self._job is not job
                        or self._closed or self._recycling or time.monotonic() >= self._deadline):
                    return False
            connection.send(message)
            return True

    def _dispatch(self, connection, job):
        try:
            self._send_for_job(connection, job, {"kind": "run", "job": job})
        except Exception:
            self._recycle("dispatch_failed", expected_connection=connection, expected_job=job)
        finally:
            with self._lock:
                if self._sender is threading.current_thread():
                    self._sender = None

    def _send_stop(self, connection):
        try:
            with self._send_lock:
                connection.send({"kind": "stop"})
        except (OSError, EOFError):
            pass

    def _matches(self, message, job):
        return job and message.get("run_id") == job["run_id"] and message.get("owner") == job["owner"]

    def _receive(self):
        while not self._closed:
            with self._lock:
                connection = self._connection
            try:
                if connection is None or not connection.poll(0.05):
                    continue
                message = connection.recv()
            except (EOFError, OSError, TypeError):
                time.sleep(0.05)
                continue
            with self._lock:
                if connection is not self._connection or self._recycling:
                    continue
                self._children.update(message.get("children", []))
                if message["kind"] == "ready":
                    self._ready = True
                    self.last_startup_error = None
                    continue
                if message["kind"] == "startup_failed":
                    self.last_startup_error = message.get("error_type", "WorkerStartupError")
                    continue
                job = self._job
                if not self._matches(message, job):
                    continue
                expired = time.monotonic() >= self._deadline
            if expired:
                self._recycle("run_timeout", expected_connection=connection, expected_job=job)
                continue
            kind = message["kind"]
            if kind == "event":
                try:
                    self.on_event(job, message["event_type"], message["payload"],
                                  model_visible=message.get("model_visible", False))
                except Exception as exc:
                    self._recycle(getattr(exc, "code", "event_rejected"),
                                  expected_connection=connection, expected_job=job)
                    continue
                try:
                    self._send_for_job(connection, job, {"kind": "ack", "accepted": True})
                except (OSError, EOFError):
                    self._recycle("worker_died", expected_connection=connection, expected_job=job)
            elif kind == "result":
                try:
                    self.on_result(job, message["result"])
                except Exception:
                    self._recycle("result_commit_failed", expected_connection=connection, expected_job=job)
                    continue
                with self._lock:
                    if self._job is job:
                        self._job = None
            elif kind == "failure":
                self._recycle(message.get("error", {}).get("code", "agent_failed"),
                              details=message.get("error"), expected_connection=connection, expected_job=job)

    def _watch(self):
        last_scan = 0.0
        while not self._closed:
            with self._lock:
                process = self._process
                job, connection = self._job, self._connection
                timeout = job is not None and time.monotonic() >= self._deadline
                recycling = self._recycling
            if recycling:
                time.sleep(0.025)
                continue
            if timeout:
                self._recycle("run_timeout", expected_connection=connection, expected_job=job)
            elif process and not process.is_alive():
                self._recycle("worker_died", expected_connection=connection, expected_job=job)
            elif process and time.monotonic() - last_scan > 0.5:
                children = _descendants(process.pid)
                with self._lock:
                    if process is self._process:
                        self._children.update(children)
                last_scan = time.monotonic()
            time.sleep(0.025)

    def _recycle(self, code, *, details=None, restart=True,
                 expected_connection=_UNSET, expected_job=_UNSET):
        with self._lock:
            if expected_connection is not _UNSET and self._connection is not expected_connection:
                return
            if expected_job is not _UNSET and self._job is not expected_job:
                return
            if self._recycling:
                return
            self._recycling = True
            self._ready = False
            process, connection, job = self._process, self._connection, self._job
            sender = self._sender
            children = set(self._children)
            self._job = None
        stop_sender = None
        try:
            if process:
                if not restart and job is None and process.is_alive() and connection:
                    # 正常退出也不能被IPC写卡住；超时仍由本线程回收worker。
                    stop_sender = threading.Thread(target=self._send_stop, args=(connection,), daemon=True,
                                                   name="delivery-stop")
                    stop_sender.start()
                    process.join(timeout=3)
                children.update(_descendants(process.pid))
                # 先停工具，再停worker；独立MCP session也须回收。
                _signal_owned(children, signal.SIGTERM)
                _signal_owned({process.pid}, signal.SIGTERM)
                process.join(timeout=0.2)
                _signal_owned(children, signal.SIGKILL)
                _signal_owned({process.pid}, signal.SIGKILL)
                process.join(timeout=1)
            if connection:
                connection.close()
            for thread in (sender, stop_sender):
                if thread and thread is not threading.current_thread():
                    thread.join(timeout=1)
            if job:
                try:
                    self.on_failure(job, {"code": code, **(details or {})})
                except Exception:
                    _LOG.exception("Could not persist delivery failure for run %s", job["run_id"])
        finally:
            with self._lock:
                self._process, self._connection = None, None
                if self._sender is sender:
                    self._sender = None
                self._children = set()
                if restart and not self._closed:
                    self._spawn_locked()
                self._recycling = False

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # A watchdog recycle may already be in progress; wait for its cleanup.
        while self._recycling:
            time.sleep(0.01)
        self._recycle("server_restarted", restart=False)
        for thread in (self._monitor, self._watchdog):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=2)
