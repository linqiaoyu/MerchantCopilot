import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import DemoRuntime, SSE_EVENT_TYPES, app, require_demo_token


def test_health_and_ready_are_public():
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_public_http_surface_is_exactly_the_nine_fixed_routes():
    paths = {route.path for route in app.routes}
    assert paths == {
        "/healthz", "/readyz", "/v1/threads", "/v1/threads/{thread_id}/runs:stream",
        "/v1/runs/{run_id}", "/v1/threads/{thread_id}/memories",
        "/v1/memories/{memory_id}/approve", "/v1/memories/{memory_id}/reject",
        "/v1/runs/{run_id}/feedback",
    }


def test_demo_token_dependency_rejects_missing_or_wrong(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    assert require_demo_token("Bearer demo") is None
    for value in (None, "Bearer wrong"):
        try:
            require_demo_token(value)
        except Exception as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("missing/wrong token must be rejected")


@pytest.mark.parametrize(("method", "path", "body"), [
    ("POST", "/v1/threads", {"merchant_id": "m1"}),
    ("POST", "/v1/threads/no-thread/runs:stream", {"query": "GMV"}),
    ("GET", "/v1/runs/no-run", None),
    ("GET", "/v1/threads/no-thread/memories", None),
    ("POST", "/v1/memories/no-memory/approve", None),
    ("POST", "/v1/memories/no-memory/reject", None),
    ("POST", "/v1/runs/no-run/feedback", {"score": 5}),
])
def test_every_business_route_rejects_missing_bearer(method, path, body):
    response = TestClient(app).request(method, path, json=body)
    assert response.status_code == 401


def test_business_contract_requires_auth_and_idempotency(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    app.state.runtime = DemoRuntime()
    client = TestClient(app)
    assert client.post("/v1/threads", json={"merchant_id": "m1"}).status_code == 401
    headers = {"Authorization": "Bearer demo"}
    assert client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).status_code == 400
    headers["Idempotency-Key"] = str(uuid4())
    created = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"})
    assert created.status_code == 201
    assert client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json() == created.json()
    assert client.post("/v1/runs/no-run/feedback", headers={"Authorization": "Bearer demo"}, json={"score": 5}).status_code == 400
    assert client.post("/v1/threads", headers={"Authorization": "Bearer demo", "Idempotency-Key": "not-a-uuid"}, json={"merchant_id": "m1"}).status_code == 400


def test_stream_endpoint_emits_lifecycle_without_real_llm(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: {"final_answer": "已完成", "node_result": {"data": {"gmv": 1}}}
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
    headers["Idempotency-Key"] = str(uuid4())
    response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: node_started" in response.text
    assert "event: node_completed" in response.text
    assert "event: evidence" in response.text
    assert "event: final" in response.text
    assert "event: done" in response.text
    assert '"status": "completed"' in response.text
    run_id = json.loads(re.search(r"data: (\{.*?\})", response.text).group(1))["run_id"]
    recovered = client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer demo"})
    assert recovered.json()["status"] == "completed"
    assert recovered.json()["result"] == "已完成"
    assert recovered.json()["node_result"] == {"data": {"gmv": 1}}


def test_sse_failure_is_ordered_and_classified(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: (_ for _ in ()).throw(TimeoutError())
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
    headers["Idempotency-Key"] = str(uuid4())
    response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert response.text.index("event: meta") < response.text.index("event: error") < response.text.index("event: done")
    assert '"code": "llm_timeout"' in response.text


def test_sse_classifies_database_agent_and_quota_failures(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    for error, code in ((ConnectionError(), "database_unavailable"), (RuntimeError("bad agent"), "agent_failure")):
        runtime = DemoRuntime()
        runtime.execute = lambda query, thread_id, failure=error: (_ for _ in ()).throw(failure)
        app.state.runtime = runtime
        client = TestClient(app)
        headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
        thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
        headers["Idempotency-Key"] = str(uuid4())
        response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
        assert f'"code": "{code}"' in response.text

    monkeypatch.setenv("DEMO_MONTHLY_RUN_CAP", "0")
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: (_ for _ in ()).throw(AssertionError("quota must not call agent"))
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
    headers["Idempotency-Key"] = str(uuid4())
    response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert '"code": "quota"' in response.text


def test_sse_event_vocabulary_has_exactly_eleven_types():
    assert SSE_EVENT_TYPES == {
        "meta", "node_started", "node_completed", "tool_call", "evidence",
        "memory_recalled", "memory_candidate", "token", "final", "error", "done",
    }


def test_concurrent_same_run_key_executes_agent_once(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = DemoRuntime()
    calls = []

    def execute(query, thread_id):
        calls.append((query, thread_id))
        time.sleep(0.03)
        return {"final_answer": "已完成"}

    runtime.execute = execute
    app.state.runtime = runtime
    auth = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
    thread = TestClient(app).post("/v1/threads", headers=auth, json={"merchant_id": "m1"}).json()
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}

    def submit(_: int):
        return TestClient(app).post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert len(calls) == 1
    run_ids = {json.loads(re.search(r"data: (\{.*?\})", response.text).group(1))["run_id"] for response in responses}
    assert len(run_ids) == 1
