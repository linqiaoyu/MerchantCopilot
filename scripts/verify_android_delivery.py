"""Real HTTP/spawn fault verification against disposable native PostgreSQL.

Only the Agent worker is replaced by a deterministic stub. Uvicorn, REST/SSE,
parent lifecycle management, PostgreSQL transactions and process cleanup are real.
No LLM, embedding model, frozen evaluation runner, or production database is used.
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager, contextmanager
from functools import partial
import hashlib
from importlib.metadata import version
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def controlled_worker(channel, _dsn, _warmup, *, state_dir: str):
    """Module-level spawn target. The candidate after a hang must never commit."""
    directory = Path(state_dir)
    _write_json(directory / f"worker-{os.getpid()}.json", {"pid": os.getpid()})
    channel.ready()
    while (job := channel.receive()) is not None:
        marker = {"run_id": job["run_id"], "worker_pid": os.getpid(), "query": job["query"],
                  "completed_context": job.get("completed_context", []), "started": True}
        _write_json(directory / f"run-{job['run_id']}.json", marker)
        channel.event(job, "controlled_private_trace", {"input": "PRIVATE_CONTROLLED_TRACE"}, model_visible=True)
        channel.event(job, "node_started", {"node": "agent"})
        if job["query"] in {"CONTROLLED:timeout", "CONTROLLED:restart"}:
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                      f"delivery-verify-{job['run_id']}"], start_new_session=True)
            marker["child_pid"] = child.pid
            _write_json(directory / f"run-{job['run_id']}.json", marker)
            # 此ACK同时把真实独立session子进程登记给执行器，不暴露PID到产品API。
            channel.event(job, "tool_call", {"tool": "controlled_metric", "action": "metric"})
            time.sleep(8)
            channel.result(job, {"final_answer": "late result must be discarded", "memory_candidates": [{
                "candidate_id": f"late-{job['run_id']}", "subject": "merchant", "predicate": "late_stub",
                "value": "must not commit", "source_type": "user", "fact_type": "user_fact",
            }]})
            continue
        if job["query"] == "CONTROLLED:recovery":
            time.sleep(0.8)
        channel.event(job, "tool_call", {"tool": "controlled_metric", "action": "metric"})
        channel.result(job, {
            "final_answer": "controlled deterministic result", "node_result": {
                "task": "metric", "headline": "受控确定性结果", "data": {"gmv": 12},
                "evidence": ["sql:controlled:no-model"],
            }, "memory_candidates": [], "model_traces": [], "llm_usage": [],
        })
        marker["returned"] = True
        _write_json(directory / f"run-{job['run_id']}.json", marker)


def _serve(listener, dsn: str, token: str, state_dir: str, max_seconds: float):
    # 清空凭据，且只装配controlled_worker；dotenv不会覆盖已设置的空值。
    os.environ.update({"DATABASE_URL": dsn, "DEMO_ACCESS_TOKEN": token,
                       "DEMO_MERCHANT_ID": "xiaozhang_women", "DEMO_MONTHLY_RUN_CAP": "10000",
                       "DEEPSEEK_API_KEY": "", "QWEN_API_KEY": "", "OPENAI_API_KEY": "",
                       "LANGSMITH_API_KEY": "", "LANGSMITH_TRACING": "false"})
    import uvicorn
    from app.api.delivery_service import DeliveryService
    from app.api.main import app, PostgresRuntime
    from app.delivery.executor import SpawnExecutor

    @asynccontextmanager
    async def lifespan(application):
        service = DeliveryService(
            dsn, max_seconds=max_seconds,
            executor_factory=partial(SpawnExecutor, worker_target=partial(controlled_worker, state_dir=state_dir), warmup=False),
            budget_path=Path(state_dir) / "controlled-budget.json",
        )
        runtime = PostgresRuntime(dsn)
        runtime.delivery = service
        application.state.runtime = runtime
        service.start()
        try:
            yield
        finally:
            service.close()

    app.router.lifespan_context = lifespan
    uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False)).run(sockets=[listener])


def wait_until(predicate, *, timeout: float = 12, description: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.025)
    raise AssertionError(f"timed out waiting for {description}")


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout.strip()
    return bool(state) and not state.startswith("Z")


class LiveServer:
    def __init__(self, dsn: str, directory: Path, *, max_seconds: float = 2.0):
        self.dsn, self.directory, self.max_seconds = dsn, directory, max_seconds
        self.token = uuid4().hex
        self.process = None
        self.client = None
        self.port = None

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        self.port = listener.getsockname()[1]
        self.process = mp.get_context("spawn").Process(
            target=_serve, args=(listener, self.dsn, self.token, str(self.directory), self.max_seconds),
            name="controlled-delivery-uvicorn", daemon=False,
        )
        self.process.start()
        listener.close()
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", headers=self.headers, timeout=12,
                                   trust_env=False)

        def ready():
            if not self.process.is_alive():
                raise AssertionError("controlled Uvicorn exited during startup")
            try:
                return self.client.get("/readyz").status_code == 200
            except httpx.TransportError:
                return False

        try:
            wait_until(ready, timeout=20, description="Uvicorn and spawn worker readiness")
        except BaseException:
            self.stop()
            raise
        return self

    def stop(self, *, crash=False):
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.kill() if crash else self.process.terminate()
                self.process.join(timeout=8)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=3)
            self.process.close()
            self.process = None

    def thread(self):
        response = self.client.post("/v1/threads", json={"merchant_id": "xiaozhang_women"},
                                    headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 201, "thread creation failed"
        return response.json()["thread_id"]

    def submit(self, thread_id, query="CONTROLLED:fast", *, key=None):
        return self.client.post(f"/v1/threads/{thread_id}/runs", json={"query": query},
                                headers={"Idempotency-Key": key or str(uuid4())})

    def run(self, run_id):
        response = self.client.get(f"/v1/runs/{run_id}")
        assert response.status_code == 200, "run snapshot lookup failed"
        return response.json()

    def terminal(self, run_id):
        def snapshot():
            row = self.run(run_id)
            return row if row["status"] in {"completed", "failed"} else None
        return wait_until(snapshot, description="persisted terminal state")


@contextmanager
def isolated_database(source: str | None = None, *, keep=False):
    from app.storage.database import apply_migrations
    admin_dsn = source or os.environ.get("DATABASE_URL") or "dbname=postgres"
    name = "delivery_verify_" + uuid4().hex
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        postgres_version = admin.execute("SELECT version()").fetchone()[0]
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        dsn = make_conninfo(admin_dsn, dbname=name)
        try:
            apply_migrations(dsn)
            yield dsn, name, postgres_version
        finally:
            if not keep:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def sse_frames(lines):
    """Decode actual HTTP SSE framing; a closed connection is not a run state."""
    frame, data = {}, []
    for line in lines:
        if not line:
            if frame.get("event"):
                yield {"id": int(frame["id"]), "event": frame["event"], "data": json.loads("\n".join(data))}
            frame, data = {}, []
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            if field == "data":
                data.append(value.lstrip(" "))
            elif field in {"id", "event"}:
                frame[field] = value.lstrip(" ")


def read_marker(directory: Path, run_id: str, *, require_child=False):
    path = directory / f"run-{run_id}.json"
    if not path.exists():
        return None
    marker = json.loads(path.read_text())
    return marker if not require_child or "child_pid" in marker else None


def registered_processes(directory: Path) -> set[int]:
    pids = {json.loads(path.read_text())["pid"] for path in directory.glob("worker-*.json")}
    for path in directory.glob("run-*.json"):
        marker = json.loads(path.read_text())
        if "child_pid" in marker:
            pids.add(marker["child_pid"])
    return pids


def cleanup_registered_processes(directory: Path) -> None:
    """Even a failed verifier must reap only the PIDs its controlled worker recorded."""
    for pid in registered_processes(directory):
        if pid > 1 and pid != os.getpid() and process_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _passed(report, name, *, details=None):
    report["passed"].append(name)
    report["checks"].append({"name": name, "passed": True, **({"details": details} if details else {})})


def verify_response_loss_and_sse(server: LiveServer, dsn: str, report: dict):
    from app.storage.delivery_repository import DeliveryRepository
    thread_id, key = server.thread(), str(uuid4())
    body = json.dumps({"query": "CONTROLLED:recovery"}).encode()
    request = (f"POST /v1/threads/{thread_id}/runs HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
               f"Authorization: Bearer {server.token}\r\nIdempotency-Key: {key}\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body
    # 故障点：请求完整发出，数据库已接受，但客户端从不读取首次HTTP响应。
    with socket.create_connection(("127.0.0.1", server.port), timeout=3) as connection:
        connection.sendall(request)

        def accepted_id():
            with psycopg.connect(dsn) as conn:
                row = conn.execute("SELECT run_id FROM run_records WHERE idempotency_key = %s", (key,)).fetchone()
            return str(row[0]) if row else None

        observed_id = wait_until(accepted_id, description="accepted operation with discarded HTTP response")
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Connection: close 允许服务端先关TCP；客户端仍未消费任何响应字节。
            pass
    replay = server.submit(thread_id, "CONTROLLED:recovery", key=key)
    assert replay.status_code == 200 and replay.json()["run_id"] == observed_id, "lost response retry created a different task"
    _passed(report, "first_response_discarded_same_key_recovers_same_run")
    conflict = server.submit(thread_id, "CONTROLLED:changed", key=key)
    assert conflict.status_code == 409, "changed request reused an idempotency key"
    _passed(report, "same_key_changed_body_is_409")
    prefix = []
    with server.client.stream("GET", f"/v1/runs/{observed_id}/events") as stream:
        assert stream.status_code == 200
        for frame in sse_frames(stream.iter_lines()):
            prefix.append(frame)
            if frame["event"] == "node_started":
                break
    assert prefix[-1]["event"] == "node_started"
    assert server.run(observed_id)["status"] == "running", "fault injection missed the live SSE interval"
    with server.client.stream("GET", f"/v1/runs/{observed_id}/events",
                              headers={"Last-Event-ID": str(prefix[-1]["id"])}) as stream:
        suffix = list(sse_frames(stream.iter_lines()))
    frames = prefix + suffix
    assert frames[-1]["event"] == "done" and frames[-1]["data"]["status"] == "completed"
    expected = DeliveryRepository(dsn).list_events(observed_id, limit=500)
    assert [frame["id"] for frame in frames] == [event["sequence_no"] for event in expected], "SSE reconnect lost or duplicated a public event"
    assert len({frame["id"] for frame in frames}) == len(frames)
    assert all("PRIVATE_CONTROLLED_TRACE" not in json.dumps(frame) for frame in frames)
    assert sum(frame["event"] == "final" for frame in frames) == 1
    assert server.terminal(observed_id)["status"] == "completed"
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM run_records WHERE idempotency_key = %s", (key,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM run_events WHERE run_id = %s AND event_type = 'controlled_private_trace'", (observed_id,)).fetchone()[0] == 1
    _passed(report, "live_sse_disconnect_reconnect_replays_all_committed_events", details={"public_event_count": len(frames)})
    _passed(report, "private_trace_is_durable_but_absent_from_public_sse")
    _passed(report, "one_execution_and_one_final_after_response_and_stream_loss")
    return thread_id


def _assert_no_run_memories(dsn, run_id):
    with psycopg.connect(dsn) as conn:
        assert conn.execute("""SELECT count(*) FROM memory_facts AS fact
            JOIN memory_events AS event ON fact.source_event_id = event.event_id WHERE event.run_id = %s""", (run_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM run_events WHERE run_id = %s AND event_type IN ('public_final','final')", (run_id,)).fetchone()[0] == 0


def verify_timeout(server: LiveServer, dsn: str, report: dict, thread_id: str):
    from app.storage.delivery_repository import DeliveryRepository
    response = server.submit(thread_id, "CONTROLLED:timeout")
    assert response.status_code == 202
    run = response.json()
    marker = wait_until(lambda: read_marker(server.directory, run["run_id"], require_child=True), description="timeout worker and detached child")
    report.setdefault("fault_evidence", {})["timeout"] = marker
    failed = server.terminal(run["run_id"])
    assert failed["status"] == "failed" and failed["error"]["code"] == "run_timeout"
    for pid in (marker["worker_pid"], marker["child_pid"]):
        wait_until(lambda pid=pid: not process_alive(pid), description="timeout descendant cleanup")
    repo = DeliveryRepository(dsn)
    late = repo.finish(run["run_id"], run["owner"], result={"final_answer": "late", "memory_candidates": [{
        "candidate_id": f"late-direct-{run['run_id']}", "subject": "merchant", "predicate": "late", "value": "forbidden", "source_type": "user",
    }]})
    assert late is None
    _assert_no_run_memories(dsn, run["run_id"])
    events = repo.list_events(run["run_id"], limit=500)
    assert events[-1]["event_type"] == "done" and events[-1]["payload"]["status"] == "failed"
    assert sum(event["event_type"] == "error" for event in events) == 1
    wait_until(lambda: server.client.get("/readyz").status_code == 200, description="replacement worker readiness")
    _passed(report, "deadline_fails_run_and_reaps_worker_and_detached_tool", details={"configured_deadline_seconds": server.max_seconds})
    _passed(report, "timeout_rejects_late_result_and_canonical_memory")


def verify_restart(server: LiveServer, dsn: str, report: dict, thread_id: str):
    from app.storage.delivery_repository import DeliveryRepository
    key = str(uuid4())
    response = server.submit(thread_id, "CONTROLLED:restart", key=key)
    assert response.status_code == 202
    run = response.json()
    marker = wait_until(lambda: read_marker(server.directory, run["run_id"], require_child=True), description="restart worker and detached child")
    report.setdefault("fault_evidence", {})["restart"] = marker
    server.stop(crash=True)
    for pid in (marker["worker_pid"], marker["child_pid"]):
        wait_until(lambda pid=pid: not process_alive(pid), description=f"parent-death cleanup for PID {pid}")
    server.start()
    recovered = server.run(run["run_id"])
    assert recovered["status"] == "failed" and recovered["error"]["code"] == "server_restarted"
    replay = server.submit(thread_id, "CONTROLLED:restart", key=key)
    assert replay.status_code == 200 and replay.json()["run_id"] == run["run_id"]
    assert replay.json()["status"] == "failed"
    events = server.client.get(f"/v1/runs/{run['run_id']}/events")
    frames = list(sse_frames(events.text.splitlines()))
    assert frames[-1]["event"] == "done" and frames[-1]["data"]["status"] == "failed"
    repo = DeliveryRepository(dsn)
    assert repo.finish(run["run_id"], run["owner"], result={"final_answer": "old owner"}) is None
    _assert_no_run_memories(dsn, run["run_id"])
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM run_events WHERE run_id = %s AND event_type = 'controlled_private_trace'", (run["run_id"],)).fetchone()[0] == 1
    followup = server.submit(thread_id).json()
    assert server.terminal(followup["run_id"])["status"] == "completed"
    next_marker = read_marker(server.directory, followup["run_id"])
    assert all(item["query"] not in {"CONTROLLED:timeout", "CONTROLLED:restart"} for item in next_marker["completed_context"])
    _passed(report, "sigkill_api_recovers_prior_run_as_failed_without_reexecution")
    _passed(report, "api_parent_death_leaves_no_live_worker_or_detached_tool")
    _passed(report, "restart_rejects_old_owner_and_failed_context_and_accepts_next_run")


def latency_summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {"samples": len(samples), "unit": "milliseconds", "p50": ordered[math.ceil(len(ordered) * 0.5) - 1],
            "p95": ordered[math.ceil(len(ordered) * 0.95) - 1], "max": max(samples),
            "mean": sum(samples) / len(samples), "raw": samples}


def measure_http(server: LiveServer, report: dict, *, samples: int):
    if samples <= 0:
        report["measurements"] = {"skipped": True, "reason": "samples=0; lifecycle verification only"}
        return
    progress = {"stage": "overview_warmup", "index": 0, "overview_raw_ms": [], "accept_raw_ms": []}
    report["measurement_progress"] = progress
    for index in range(3):
        progress["index"] = index + 1
        assert server.client.get("/v1/overview").status_code == 200
    progress["stage"] = "create_measurement_thread"
    thread_id = server.thread()
    measurements = {"overview": progress["overview_raw_ms"], "accept": progress["accept_raw_ms"]}
    for index in range(samples):
        progress.update(stage="overview", index=index + 1)
        start = time.perf_counter()
        overview_response = server.client.get("/v1/overview")
        measurements["overview"].append((time.perf_counter() - start) * 1000)
        assert overview_response.status_code == 200 and overview_response.json()["synthetic"] is True
        progress["stage"] = "accept"
        start = time.perf_counter()
        accepted = server.submit(thread_id)
        measurements["accept"].append((time.perf_counter() - start) * 1000)
        assert accepted.status_code == 202, "performance sample was not a newly accepted task"
        progress["stage"] = "terminal_snapshot"
        assert server.terminal(accepted.json()["run_id"])["status"] == "completed"
    report["measurements"] = {"mode": "sequential_loopback_controlled_worker", "overview_warmups": 3,
                              "percentile_method": "nearest_rank", "includes_model_latency": False,
                              "overview": latency_summary(measurements["overview"]), "accept": latency_summary(measurements["accept"])}
    report["measurement_progress"] = {"stage": "complete", "samples_per_endpoint": samples}
    _passed(report, "sequential_http_measurements_are_successful_and_use_no_model", details={"samples_per_endpoint": samples})


def environment_evidence():
    dataset = ROOT / "data/merchant.duckdb"
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    source_paths = ("scripts/verify_android_delivery.py", "app/api/main.py", "app/api/delivery_service.py",
                    "app/api/delivery_routes.py", "app/api/delivery_presentation.py", "app/api/delivery_contracts.py",
                    "app/delivery/executor.py", "app/storage/delivery_repository.py", "migrations/006_android_delivery.sql")
    return {"machine": {"platform": platform.platform(), "architecture": platform.machine(), "logical_cpus": os.cpu_count()},
            "versions": {"python": platform.python_version(), **{name: version(name) for name in ("fastapi", "uvicorn", "psycopg", "httpx", "duckdb")}},
            "git_base_revision": revision, "working_tree_changes_included": True,
            "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths},
            "synthetic_dataset": {"path": "data/merchant.duckdb", "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(), "bytes": dataset.stat().st_size}}


def verify(output: Path, *, samples: int = 100, admin_dsn: str | None = None, keep_db: bool = False) -> dict:
    report = {"schema_version": 1, "status": "running", "stub": True, "paid_model_calls": 0,
              "scope": "real loopback HTTP, native PostgreSQL, Uvicorn and spawn lifecycle; controlled worker only",
              "started_at_unix": time.time(), "passed": [], "checks": [], "environment": environment_evidence()}
    server = None
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="merchant-delivery-verify-") as temporary:
            directory = Path(temporary)
            try:
                with isolated_database(admin_dsn, keep=keep_db) as (dsn, name, postgres_version):
                    report["database"] = {"name": name, "isolated": True, "kept": keep_db}
                    report["environment"]["versions"]["postgresql"] = postgres_version
                    server = LiveServer(dsn, directory).start()
                    try:
                        thread_id = verify_response_loss_and_sse(server, dsn, report)
                        verify_timeout(server, dsn, report, thread_id)
                        verify_restart(server, dsn, report, thread_id)
                        measure_http(server, report, samples=samples)
                    finally:
                        server.stop()
                    pids = registered_processes(directory)
                    for pid in pids:
                        wait_until(lambda pid=pid: not process_alive(pid), description="final process cleanup")
                    _passed(report, "verification_shutdown_leaves_no_live_owned_processes", details={"checked_processes": len(pids)})
                    budget = json.loads((directory / "controlled-budget.json").read_text()) if (directory / "controlled-budget.json").exists() else {}
                    report["controlled_budget"] = budget
            finally:
                if server is not None:
                    server.stop()
                cleanup_registered_processes(directory)
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc) if isinstance(exc, (AssertionError, RuntimeError)) else "verification failed; connection details omitted"}
        raise
    finally:
        if server is not None:
            server.stop()
        report["elapsed_seconds"] = time.monotonic() - started
        _write_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--keep-db", action="store_true", help="retain only the newly created isolated database")
    arguments = parser.parse_args()
    if not 0 <= arguments.samples <= 1000:
        parser.error("samples must be 0 to 1000")
    try:
        report = verify(arguments.output, samples=arguments.samples, keep_db=arguments.keep_db)
    except Exception:
        print(json.dumps({"status": "failed", "report": str(arguments.output.resolve())}))
        return 1
    print(json.dumps({"status": report["status"], "passed_checks": len(report["passed"]),
                      "report": str(arguments.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
