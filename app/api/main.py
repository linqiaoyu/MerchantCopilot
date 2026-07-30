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
from typing import Any
from uuid import uuid4

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
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)
    memories: dict[str, dict[str, Any]] = field(default_factory=dict)

    def execute(self, query: str, thread_id: str) -> dict[str, Any]:
        from app.agent.graph_v2 import build_graph_v2

        return build_graph_v2().invoke({"user_query": query, "steps": []})


@asynccontextmanager
async def _lifespan(application: FastAPI):
    application.state.runtime = DemoRuntime()
    yield


app = FastAPI(title="MerchantCopilot v2", version="2.0.0", lifespan=_lifespan)


def _runtime(request: Request) -> DemoRuntime:
    return request.app.state.runtime


def require_demo_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DEMO_ACCESS_TOKEN", "").strip()
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail={"code": "auth", "message": "invalid demo token"})


def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail={"code": "idempotency", "message": "Idempotency-Key is required"})
    return idempotency_key


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
    if key in runtime.idempotency:
        return runtime.idempotency[key]
    thread = {"thread_id": str(uuid4()), "merchant_id": body.merchant_id}
    runtime.threads[thread["thread_id"]] = thread
    runtime.idempotency[key] = thread
    return thread


@app.post("/v1/threads/{thread_id}/runs:stream", dependencies=[Depends(require_demo_token)])
def stream_run(
    thread_id: str,
    body: RunRequest,
    key: str = Depends(require_idempotency_key),
    runtime: DemoRuntime = Depends(_runtime),
) -> StreamingResponse:
    if thread_id not in runtime.threads:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "thread not found"})
    run = runtime.idempotency.get(key)
    if run is None:
        run = {"run_id": str(uuid4()), "thread_id": thread_id, "status": "queued", "query": body.query}
        runtime.runs[run["run_id"]] = run
        runtime.idempotency[key] = run

    def events():
        yield _sse("run_started", run)
        if run["status"] == "queued":
            try:
                result = runtime.execute(body.query, thread_id)
                run.update({"status": "completed", "result": result.get("final_answer", "")})
            except Exception as exc:  # boundary must expose a stable demo error
                run.update({"status": "failed", "error": str(exc)})
        yield _sse("run_finished", run)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/v1/runs/{run_id}", dependencies=[Depends(require_demo_token)])
def get_run(run_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    return _get_or_404(runtime.runs, run_id, "run")


@app.get("/v1/threads/{thread_id}/memories", dependencies=[Depends(require_demo_token)])
def get_memories(thread_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    _get_or_404(runtime.threads, thread_id, "thread")
    return {"items": [m for m in runtime.memories.values() if m.get("thread_id") == thread_id]}


@app.post("/v1/memories/{memory_id}/approve", dependencies=[Depends(require_demo_token)])
def approve_memory(memory_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    memory = _get_or_404(runtime.memories, memory_id, "memory")
    memory["status"] = "approved"
    return memory


@app.post("/v1/memories/{memory_id}/reject", dependencies=[Depends(require_demo_token)])
def reject_memory(memory_id: str, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    memory = _get_or_404(runtime.memories, memory_id, "memory")
    memory["status"] = "rejected"
    return memory


@app.post("/v1/runs/{run_id}/feedback", dependencies=[Depends(require_demo_token)])
def record_feedback(run_id: str, body: FeedbackRequest, runtime: DemoRuntime = Depends(_runtime)) -> dict[str, Any]:
    run = _get_or_404(runtime.runs, run_id, "run")
    run["feedback"] = body.model_dump()
    return {"run_id": run_id, "accepted": True}


def _get_or_404(rows: dict[str, dict[str, Any]], key: str, label: str) -> dict[str, Any]:
    if key not in rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"{label} not found"})
    return rows[key]


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\\n\\n"
