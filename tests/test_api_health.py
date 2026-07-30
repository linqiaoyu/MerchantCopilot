from fastapi.testclient import TestClient

from app.api.main import DemoRuntime, SSE_EVENT_TYPES, app, require_demo_token


def test_health_and_ready_are_public():
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


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


def test_business_contract_requires_auth_and_idempotency(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    app.state.runtime = DemoRuntime()
    client = TestClient(app)
    assert client.post("/v1/threads", json={"merchant_id": "m1"}).status_code == 401
    headers = {"Authorization": "Bearer demo"}
    assert client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).status_code == 400
    headers["Idempotency-Key"] = "create-m1"
    created = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"})
    assert created.status_code == 201
    assert client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json() == created.json()
    assert client.post("/v1/runs/no-run/feedback", headers={"Authorization": "Bearer demo"}, json={"score": 5}).status_code == 400


def test_stream_endpoint_emits_lifecycle_without_real_llm(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: {"final_answer": "已完成"}
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": "t1"}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
    headers["Idempotency-Key"] = "r1"
    response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: node_started" in response.text
    assert "event: node_completed" in response.text
    assert "event: evidence" in response.text
    assert "event: final" in response.text
    assert "event: done" in response.text
    assert '"status": "completed"' in response.text


def test_sse_failure_is_ordered_and_classified(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: (_ for _ in ()).throw(TimeoutError())
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": "t2"}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "m1"}).json()
    headers["Idempotency-Key"] = "r2"
    response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert response.text.index("event: meta") < response.text.index("event: error") < response.text.index("event: done")
    assert '"code": "llm_timeout"' in response.text


def test_sse_event_vocabulary_has_exactly_eleven_types():
    assert SSE_EVENT_TYPES == {
        "meta", "node_started", "node_completed", "tool_call", "evidence",
        "memory_recalled", "memory_candidate", "token", "final", "error", "done",
    }
