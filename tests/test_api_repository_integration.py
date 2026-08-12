"""Real-Postgres persistence checks for the fixed HTTP API state."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.main import PostgresRuntime, app
from app.memory.policy import MemoryCandidate
from app.storage.api_repository import (
    create_or_get_thread,
    decide_memory,
    finish_run,
    get_run,
    get_thread,
    list_thread_memories,
    record_feedback,
)
from app.storage.database import apply_migrations
from app.storage.memory_repository import append_event, create_or_get_run, materialize_fact

DSN = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="requires local pgvector DATABASE_URL")


def test_api_state_is_persistent_and_idempotent():
    apply_migrations()
    key = uuid4()

    def create(_: int) -> dict[str, str]:
        with psycopg.connect(DSN) as conn:
            row = create_or_get_thread(conn, merchant_id="api-merchant", idempotency_key=key)
            conn.commit()
            return row

    with ThreadPoolExecutor(max_workers=10) as pool:
        threads = list(pool.map(create, range(10)))
    assert len({row["thread_id"] for row in threads}) == 1
    thread = threads[0]
    with psycopg.connect(DSN) as conn:
        assert get_thread(conn, thread["thread_id"]) == thread
        run = create_or_get_run(conn, thread_id=thread["thread_id"], merchant_id=thread["merchant_id"],
                                idempotency_key=uuid4(), request={"query": "GMV"})
        run_id = UUID(run["run_id"])
        finish_run(conn, run_id, status="completed", result={"final_answer": "done", "node_result": {"gmv": 1}})
        assert record_feedback(conn, run["run_id"], {"score": 5, "comment": "useful"})
        candidate = MemoryCandidate(f"api-{uuid4()}", "merchant", "constraint", "value", "mcp")
        event = append_event(conn, run_id=run_id, merchant_id=thread["merchant_id"], candidate=candidate, source_ref=candidate.candidate_id)
        fact = materialize_fact(conn, source_event_id=event, merchant_id=thread["merchant_id"], candidate=candidate, content="value")
        assert decide_memory(conn, fact.memory_id, approved=False) == {"memory_id": fact.memory_id, "status": "rejected"}
        conn.commit()

    with psycopg.connect(DSN) as reopened:
        restored = get_run(reopened, run["run_id"])
        assert restored["result"] == "done"
        assert restored["feedback"] == {"score": 5, "comment": "useful"}
        assert list_thread_memories(reopened, thread["thread_id"])[-1]["status"] == "rejected"


def test_fixed_api_uses_persistent_runtime(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "demo")
    runtime = PostgresRuntime(DSN)
    runtime.execute = lambda query, thread_id: {"final_answer": "persisted", "node_result": {"evidence": ["fact"]}}
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo", "Idempotency-Key": str(uuid4())}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "api-http"}).json()
    headers["Idempotency-Key"] = str(uuid4())
    stream = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=headers, json={"query": "GMV"})
    assert '"status": "completed"' in stream.text
    meta = next(line for line in stream.text.splitlines() if line.startswith("data: "))
    run_id = __import__("json").loads(meta.removeprefix("data: "))["run_id"]
    recovered = client.get(f"/v1/runs/{run_id}", headers={"Authorization": "Bearer demo"})
    assert recovered.json()["result"] == "persisted"
