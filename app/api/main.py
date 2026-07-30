"""Small, authenticated HTTP boundary for the v2 demo.

Persistence is deliberately injected here: before S1's Postgres acceptance the
default runtime is process-local, which keeps the HTTP contract testable without
claiming that threads or approvals already survive a restart.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


class ThreadRequest(BaseModel):
    merchant_id: str = Field(min_length=1)


class RunRequest(BaseModel):
    query: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = ""


@dataclass
class DemoRuntime:
    """Replaceable in tests; production wiring is added only after S1 passes."""

    threads: dict[str, dict[str, Any]] = field(default_factory=dict)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    memories: dict[str, dict[str, Any]] = field(default_factory=dict)
    graph: Any = None
    lock: RLock = field(default_factory=RLock)

    def execute(self, query: str, thread_id: str) -> dict[str, Any]:
        from langgraph.checkpoint.memory import MemorySaver

        from app.agent.graph_v2 import build_graph_v2

        if self.graph is None:
            self.graph = build_graph_v2(checkpointer=MemorySaver())
        return self.graph.invoke({"user_query": query, "steps": []}, config={"configurable": {"thread_id": thread_id}})


@asynccontextmanager
async def _lifespan(application: FastAPI):
    application.state.runtime = DemoRuntime()
    yield


app = FastAPI(
    title="MerchantCopilot v2", version="2.0.0", lifespan=_lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)

# The mobile client is intentionally constrained to this stable event vocabulary.
SSE_EVENT_TYPES = frozenset({
    "meta", "node_started", "node_completed", "tool_call", "evidence",
    "memory_recalled", "memory_candidate", "token", "final", "error", "done",
})


def _runtime(request: Request) -> DemoRuntime:
    return request.app.state.runtime


def require_demo_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DEMO_ACCESS_TOKEN", "").strip()
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail={"code": "auth", "message": "invalid demo token"})


def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    try:
        return str(UUID(idempotency_key or ""))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail={"code": "idempotency", "message": "Idempotency-Key is required"})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/v1/threads", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_demo_token)])
def create_thread(
    body: ThreadRequest,
    key: str = Depends(require_idempotency_key),
    runtime: DemoRuntime = Depends(_runtime),
) -> dict[str, Any]:
    scoped_key = ("create_thread", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        thread = {"thread_id": str(uuid4()), "merchant_id": body.merchant_id}
        runtime.threads[thread["thread_id"]] = thread
        runtime.idempotency[scoped_key] = thread
        return thread


@app.post("/v1/threads/{thread_id}/runs:stream", dependencies=[Depends(require_demo_token)])
def stream_run(
    thread_id: str,
    body: RunRequest,
    key: str = Depends(require_idempotency_key),
    runtime: DemoRuntime = Depends(_runtime),
) -> StreamingResponse:
    scoped_key = (f"run:{thread_id}", key)
    with runtime.lock:
        if thread_id not in runtime.threads:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "thread not found"})
        run = runtime.idempotency.get(scoped_key)
        if run is None:
            run = {"run_id": str(uuid4()), "thread_id": thread_id, "status": "queued", "query": body.query}
            runtime.runs[run["run_id"]] = run
            runtime.idempotency[scoped_key] = run

    def events():
        yield _sse("meta", {"run_id": run["run_id"], "thread_id": thread_id})
        with runtime.lock:
            should_execute = run["status"] == "queued"
            if should_execute:
                run["status"] = "running"
        if should_execute:
            yield _sse("node_started", {"run_id": run["run_id"], "node": "agent"})
            if len(runtime.runs) > int(os.environ.get("DEMO_MONTHLY_RUN_CAP", "1000")):
                run.update({"status": "failed", "error": {"code": "quota", "message": "demo run cap reached"}})
                yield _sse("error", run["error"])
            else:
                try:
                    result = runtime.execute(body.query, thread_id)
                    run.update({"status": "completed", "result": result.get("final_answer", "")})
                    yield _sse("node_completed", {"run_id": run["run_id"], "node": "agent"})
                    yield _sse("evidence", {"run_id": run["run_id"], "items": result.get("node_result", {}).get("evidence", [])})
                    yield _sse("final", {"run_id": run["run_id"], "answer": run["result"]})
                except Exception as exc:  # boundary must expose a stable demo error
                    error = _classify_error(exc)
                    run.update({"status": "failed", "error": error})
                    yield _sse("error", error)
        elif run["status"] == "completed":
            yield _sse("final", {"run_id": run["run_id"], "answer": run.get("result", "")})
        elif run["status"] == "failed":
            yield _sse("error", run.get("error", {"code": "agent_failure"}))
        yield _sse("done", {"run_id": run["run_id"], "status": run["status"]})

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/v1/runs/{run_id}", dependencies=[Depends(require_demo_token)])
def get_run(run_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    return _get_or_404(runtime.runs, run_id, "run")


@app.get("/v1/threads/{thread_id}/memories", dependencies=[Depends(require_demo_token)])
def get_memories(thread_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    _get_or_404(runtime.threads, thread_id, "thread")
    return {"items": [m for m in runtime.memories.values() if m.get("thread_id") == thread_id]}


@app.post("/v1/memories/{memory_id}/approve", dependencies=[Depends(require_demo_token)])
def approve_memory(memory_id: str, key: str = Depends(require_idempotency_key), runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    scoped_key = (f"approve:{memory_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        memory = _get_or_404(runtime.memories, memory_id, "memory")
        memory["status"] = "approved"
        runtime.idempotency[scoped_key] = memory
        return memory


@app.post("/v1/memories/{memory_id}/reject", dependencies=[Depends(require_demo_token)])
def reject_memory(memory_id: str, key: str = Depends(require_idempotency_key), runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    scoped_key = (f"reject:{memory_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        memory = _get_or_404(runtime.memories, memory_id, "memory")
        memory["status"] = "rejected"
        runtime.idempotency[scoped_key] = memory
        return memory


@app.post("/v1/runs/{run_id}/feedback", dependencies=[Depends(require_demo_token)])
def record_feedback(run_id: str, body: FeedbackRequest, key: str = Depends(require_idempotency_key), runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    scoped_key = (f"feedback:{run_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        run = _get_or_404(runtime.runs, run_id, "run")
        run["feedback"] = body.model_dump()
        response = {"run_id": run_id, "accepted": True}
        runtime.idempotency[scoped_key] = response
        return response


def _get_or_404(rows: dict[str, dict[str, Any]], key: str, label: str) -> dict[str, Any]:
    if key not in rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"{label} not found"})
    return rows[key]


def _sse(event: str, payload: dict[str, Any]) -> str:
    assert event in SSE_EVENT_TYPES
    return f"event: {event}\\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\\n\\n"


def _classify_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, TimeoutError):
        return {"code": "llm_timeout", "message": "model request timed out"}
    if isinstance(exc, ConnectionError):
        return {"code": "database_unavailable", "message": "database unavailable"}
    return {"code": "agent_failure", "message": str(exc)}
