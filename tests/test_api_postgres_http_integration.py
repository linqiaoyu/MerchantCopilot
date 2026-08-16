"""HTTP/SSE acceptance against the local pgvector Postgres runtime."""
from __future__ import annotations

import json
import re
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.main import PostgresRuntime, app


@pytest.fixture
def postgres_http(monkeypatch):
    dsn = "postgresql://merchantcopilot:merchantcopilot@127.0.0.1:55432/merchantcopilot"
    merchant_id = f"http-test-{uuid4()}"
    calls: list[tuple[str, str]] = []

    def fake_execute(self, query: str, thread_id: str) -> dict:
        calls.append((query, thread_id))
        return {"final_answer": "持久化验收完成", "node_result": {"evidence": ["controlled-source"]}}

    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "postgres-demo")
    monkeypatch.setattr(PostgresRuntime, "execute", fake_execute)
    with TestClient(app) as client:
        yield client, merchant_id, calls
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM run_records WHERE merchant_id = %s", (merchant_id,))
            cur.execute("DELETE FROM usage_counters WHERE merchant_id = %s", (merchant_id,))
            cur.execute("DELETE FROM threads WHERE merchant_id = %s", (merchant_id,))
        conn.commit()


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Authorization": "Bearer postgres-demo", "Idempotency-Key": key or str(uuid4())}


def test_postgres_runtime_persists_sse_run_idempotently(postgres_http):
    client, merchant_id, calls = postgres_http
    create_headers = _headers()
    created = client.post("/v1/threads", headers=create_headers, json={"merchant_id": merchant_id})
    assert created.status_code == 201
    assert client.post("/v1/threads", headers=create_headers, json={"merchant_id": merchant_id}).json() == created.json()

    thread_id = created.json()["thread_id"]
    run_headers = _headers()
    first = client.post(f"/v1/threads/{thread_id}/runs:stream", headers=run_headers, json={"query": "GMV"})
    second = client.post(f"/v1/threads/{thread_id}/runs:stream", headers=run_headers, json={"query": "GMV"})
    assert first.status_code == second.status_code == 200
    assert [event for event in ("meta", "node_started", "node_completed", "evidence", "final", "done") if f"event: {event}" in first.text] == ["meta", "node_started", "node_completed", "evidence", "final", "done"]
    assert "event: node_started" not in second.text
    assert calls == [("GMV", thread_id)]

    run_id = json.loads(re.search(r"data: (\{.*?\})", first.text).group(1))["run_id"]
    persisted = client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer postgres-demo"})
    assert persisted.json()["status"] == "completed"
    assert persisted.json()["result"] == "持久化验收完成"
    feedback = client.post(f"/v1/runs/{run_id}/feedback", headers=_headers(), json={"score": 5, "comment": "可复现"})
    assert feedback.json() == {"run_id": run_id, "accepted": True}
    assert client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer postgres-demo"}).json()["feedback"] == {"score": 5, "comment": "可复现"}


def test_postgres_runtime_quota_failure_does_not_execute_agent(postgres_http, monkeypatch):
    client, merchant_id, calls = postgres_http
    monkeypatch.setenv("DEMO_MONTHLY_RUN_CAP", "0")
    thread = client.post("/v1/threads", headers=_headers(), json={"merchant_id": merchant_id}).json()

    response = client.post(
        f"/v1/threads/{thread['thread_id']}/runs:stream",
        headers=_headers(),
        json={"query": "GMV"},
    )
    assert response.status_code == 200
    assert response.text.index("event: meta") < response.text.index("event: node_started") < response.text.index("event: error") < response.text.index("event: done")
    assert '"code": "quota"' in response.text
    assert calls == []

    run_id = json.loads(re.search(r"data: (\{.*?\})", response.text).group(1))["run_id"]
    recovered = client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer postgres-demo"})
    assert recovered.json()["status"] == "failed"
    assert recovered.json()["error"] == {"code": "quota", "message": "demo run cap reached"}


def test_postgres_runtime_classifies_agent_connection_error(postgres_http, monkeypatch):
    client, merchant_id, _ = postgres_http
    monkeypatch.setattr(
        PostgresRuntime,
        "execute",
        lambda *_: (_ for _ in ()).throw(ConnectionError("database connection lost")),
    )
    thread = client.post("/v1/threads", headers=_headers(), json={"merchant_id": merchant_id}).json()

    response = client.post(
        f"/v1/threads/{thread['thread_id']}/runs:stream",
        headers=_headers(),
        json={"query": "GMV"},
    )
    assert response.status_code == 200
    assert response.text.index("event: meta") < response.text.index("event: error") < response.text.index("event: done")
    assert '"code": "database_unavailable"' in response.text

    run_id = json.loads(re.search(r"data: (\{.*?\})", response.text).group(1))["run_id"]
    recovered = client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer postgres-demo"})
    assert recovered.json()["status"] == "failed"
    assert recovered.json()["error"] == {"code": "database_unavailable", "message": "database unavailable"}
