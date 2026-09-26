"""New and legacy HTTP routes share a durable operation; no paid model calls."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.api.main import app, PostgresRuntime, _runtime
from app.api.delivery_service import DeliveryService
from app.storage.database import apply_migrations


class ControlledExecutor:
    def __init__(self, _dsn, **callbacks):
        self.callbacks = callbacks
        self.ready = False
        self.busy = False
        self.jobs = []

    def start(self):
        self.ready = True

    def submit(self, job):
        assert not self.busy
        self.busy = True
        self.jobs.append(job)

    def finish(self, result=None):
        self.callbacks["on_result"](self.jobs[-1], result or {
            "final_answer": "已完成", "node_result": {"task": "metric", "data": {"gmv": 12}, "evidence": ["sql:controlled"]}})
        self.busy = False

    def close(self):
        self.ready = False


@pytest.fixture(scope="module")
def api_dsn():
    name = "delivery_api_" + uuid4().hex[:12]
    try:
        admin = psycopg.connect("dbname=postgres", autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("native PostgreSQL required")
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = f"dbname={name}"
    apply_migrations(dsn)
    yield dsn
    admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    admin.close()


@pytest.fixture
def api(api_dsn, tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "delivery-test")
    service = DeliveryService(api_dsn, executor_factory=ControlledExecutor, budget_path=tmp_path / "budget.json")
    service.start()
    runtime = PostgresRuntime(api_dsn)
    runtime.delivery = service
    app.dependency_overrides[_runtime] = lambda: runtime
    client = TestClient(app)
    yield client, service
    app.dependency_overrides.clear()
    service.close()


def headers(key=None):
    return {"Authorization": "Bearer delivery-test", "Idempotency-Key": key or str(uuid4())}


def thread(client):
    response = client.post("/v1/threads", headers=headers(), json={"merchant_id": "xiaozhang_women"})
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


def test_new_routes_require_auth_and_overview_is_deterministic(api):
    client, _ = api
    for path in ("/v1/overview", "/v1/runs", "/v1/memories", "/v1/runs/missing/events"):
        assert client.get(path).status_code == 401
    overview = client.get("/v1/overview", headers=headers()).json()
    assert overview["synthetic"] and len(overview["metrics"]) == 5
    assert client.get("/v1/overview?start_date=1900-01-01&end_date=1900-01-02", headers=headers()).status_code == 422
    assert client.post("/v1/threads", headers=headers(), json={"merchant_id": "another"}).status_code in (403, 404)


def test_concurrent_idempotency_busy_retry_and_request_conflict(api):
    client, service = api
    tid, key = thread(client), str(uuid4())
    path = f"/v1/threads/{tid}/runs"
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: client.post(path, headers=headers(key), json={"query": "GMV"}), range(10)))
    assert sorted(r.status_code for r in responses) == [200] * 9 + [202]
    assert len({r.json()["run_id"] for r in responses}) == 1
    assert len(service.executor.jobs) == 1
    assert client.post(path, headers=headers(), json={"query": "other"}).status_code == 429
    assert client.post(path, headers=headers(key), json={"query": "different"}).status_code == 409
    service.executor.finish()
    replay = client.post(f"/v1/threads/{tid}/runs:stream", headers=headers(key), json={"query": "GMV"})
    assert replay.status_code == 200 and "event: final" in replay.text and "event: done" in replay.text
    assert len(service.executor.jobs) == 1


def test_public_events_replay_cursor_and_structured_result(api):
    client, service = api
    tid = thread(client)
    run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "GMV"}).json()
    job = service.executor.jobs[-1]
    service.repo.record_event(run["run_id"], job["owner"], "model_input", {"system": "private-test-input"}, public=False, model_visible=True)
    event = service.repo.record_event(run["run_id"], job["owner"], "node_started", {"node": "metric"})
    service.executor.finish()
    response = client.get(f"/v1/runs/{run['run_id']}/events", headers=headers())
    assert "private-test-input" not in response.text
    assert "event: node_started" in response.text
    replay = client.get(f"/v1/runs/{run['run_id']}/events", headers={**headers(), "Last-Event-ID": str(event["sequence_no"])})
    assert "event: node_started" not in replay.text and "event: final" in replay.text
    assert client.get(f"/v1/runs/{run['run_id']}/events", headers={**headers(), "Last-Event-ID": "999999"}).status_code == 400
    recovered = client.get(f"/v1/runs/{run['run_id']}", headers=headers()).json()
    assert recovered["result"] == "已完成"
    assert recovered["structured_result"]["metrics"][0]["value"] == 12
    assert recovered["last_event_id"] > 0


def test_memory_approval_and_feedback_are_real_transactions(api):
    client, service = api
    tid = thread(client)
    run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "GMV"}).json()
    service.executor.finish({"final_answer": "候选待确认", "node_result": {}, "memory_candidates": [{
        "candidate_id": str(uuid4()), "subject": "merchant", "predicate": "budget", "value": "不增加预算",
        "source_type": "llm", "fact_type": "user_fact", "schema_version": 3,
        "thread_id": tid, "scope_type": "merchant", "scope_id": "xiaozhang_women"}]})
    pending = client.get("/v1/memories?status=pending", headers=headers()).json()["items"]
    memory = pending[-1]
    key = str(uuid4())
    path = f"/v1/memories/{memory['memory_id']}/approve"
    first = client.post(path, headers=headers(key), json={"expected_version": memory["version"]})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "active"
    assert client.post(path, headers=headers(key), json={"expected_version": memory["version"]}).json() == first.json()
    assert client.post(f"/v1/memories/{memory['memory_id']}/reject", headers=headers(), json={"expected_version": memory["version"]}).status_code == 409
    feedback = client.post(f"/v1/runs/{run['run_id']}/feedback", headers=headers(), json={"score": 4, "comment": "controlled"})
    assert feedback.status_code == 200 and feedback.json()["accepted"]


def _admission_counts(service, thread_id, key):
    with psycopg.connect(service.dsn) as conn:
        return (
            conn.execute("SELECT count(*) FROM run_records WHERE thread_id = %s", (thread_id,)).fetchone()[0],
            conn.execute("SELECT COALESCE(SUM(run_count),0) FROM usage_counters WHERE merchant_id = %s", (service.merchant_id,)).fetchone()[0],
            conn.execute("SELECT count(*) FROM delivery_operations WHERE idempotency_key = %s", (key,)).fetchone()[0],
        )


def test_history_lookup_failure_before_admission_does_not_charge_or_bind_key(api, monkeypatch):
    client, service = api
    tid, key = thread(client), str(uuid4())
    original = service.repo.list_runs
    before = _admission_counts(service, tid, key)

    def fail_history(**_kwargs):
        raise ConnectionError("controlled history read failure before admission")

    monkeypatch.setattr(service.repo, "list_runs", fail_history)
    response = client.post(f"/v1/threads/{tid}/runs", headers=headers(key), json={"query": "GMV"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "dispatch_failed"
    assert _admission_counts(service, tid, key) == before
    assert service.executor.jobs == [] and not service.executor.busy
    monkeypatch.setattr(service.repo, "list_runs", original)
    replay = client.post(f"/v1/threads/{tid}/runs", headers=headers(key), json={"query": "GMV"})
    assert replay.status_code == 202 and len(service.executor.jobs) == 1
    service.executor.finish()


def test_blocked_history_read_has_not_admitted_or_started_deadline(api, monkeypatch):
    client, service = api
    tid, key = thread(client), str(uuid4())
    before = _admission_counts(service, tid, key)
    original = service.repo.list_runs
    entered, release = threading.Event(), threading.Event()

    def blocked_history(**kwargs):
        entered.set()
        assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(service.repo, "list_runs", blocked_history)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: client.post(f"/v1/threads/{tid}/runs", headers=headers(key), json={"query": "GMV"}))
        try:
            assert entered.wait(3)
            assert not future.done()
            assert _admission_counts(service, tid, key) == before
            assert service.executor.jobs == [] and not service.executor.busy
        finally:
            release.set()
        response = future.result(timeout=5)
    assert response.status_code == 202 and response.json()["status"] == "running"
    service.executor.finish()


def test_submit_failure_after_admission_terminalizes_and_replays_same_run(api, monkeypatch):
    client, service = api
    tid, key = thread(client), str(uuid4())
    original = service.executor.submit

    def fail_submit(_job):
        raise RuntimeError("controlled dispatch failure after admission")

    monkeypatch.setattr(service.executor, "submit", fail_submit)
    response = client.post(f"/v1/threads/{tid}/runs", headers=headers(key), json={"query": "GMV"})
    assert response.status_code == 202
    run = response.json()
    assert run["status"] == "failed" and run["error"]["code"] == "dispatch_failed"
    assert service.repo.list_events(run["run_id"])[-1]["payload"]["status"] == "failed"
    assert service.executor.jobs == [] and not service.executor.busy
    monkeypatch.setattr(service.executor, "submit", original)
    replay = client.post(f"/v1/threads/{tid}/runs", headers=headers(key), json={"query": "GMV"})
    assert replay.status_code == 200 and replay.json()["run_id"] == run["run_id"]
    next_run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "GMV"})
    assert next_run.status_code == 202 and len(service.executor.jobs) == 1
    service.executor.finish()


def test_pre_delivery_terminal_run_replays_without_rewriting_history(api):
    client, service = api
    tid, key, run_id = thread(client), str(uuid4()), str(uuid4())
    with psycopg.connect(service.dsn) as conn:
        conn.execute("""INSERT INTO run_records(run_id,thread_id,merchant_id,idempotency_key,status,request_json,result_json)
                     VALUES (%s,%s,'xiaozhang_women',%s,'completed',%s::jsonb,%s::jsonb)""",
                     (run_id, tid, key, json.dumps({"query": "历史查询"}),
                      json.dumps({"final_answer": "历史答案", "node_result": {"evidence": ["historical-sql"]}})))
    replay = client.post(f"/v1/threads/{tid}/runs:stream", headers=headers(key), json={"query": "历史查询"})
    assert replay.status_code == 200
    assert all(f"event: {name}" in replay.text for name in ("meta", "evidence", "final", "done"))
    assert "历史答案" in replay.text and "historical-sql" in replay.text
    assert service.executor.jobs == []
    with psycopg.connect(service.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM run_events WHERE run_id=%s", (run_id,)).fetchone()[0] == 0


def test_thread_memories_keep_all_legacy_items_and_support_explicit_pagination(api):
    client, service = api
    tid = thread(client)
    run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "GMV"}).json()
    service.executor.finish({"final_answer": "controlled memory fixture", "node_result": {}, "memory_candidates": [
        {"candidate_id": str(uuid4()), "subject": "merchant", "predicate": f"pending_{index}", "value": str(index),
         "source_type": "llm", "fact_type": "inference", "kind": "core"} for index in range(55)
    ]})
    path = f"/v1/threads/{tid}/memories"
    legacy = client.get(path, headers=headers()).json()
    assert len(legacy["items"]) == 55, "legacy unpaged route must not silently stop at 50"
    assert not legacy.get("next_cursor")
    first = client.get(path, params={"status": "pending", "limit": 30}, headers=headers()).json()
    assert len(first["items"]) == 30 and first["next_cursor"]
    second = client.get(path, params={"status": "pending", "limit": 30, "cursor": first["next_cursor"]}, headers=headers()).json()
    assert len(second["items"]) == 25 and second["next_cursor"] is None
    assert len({item["memory_id"] for item in first["items"] + second["items"]}) == 55
    assert client.get(path, params={"status": "active"}, headers=headers()).json()["items"] == []
    assert client.get(path, params={"status": "unknown"}, headers=headers()).status_code == 400
    assert client.get(path, params={"limit": 101}, headers=headers()).status_code == 400
    assert client.get(path).status_code == 401
