"""Small authenticated HTTP boundary; the v3 internals retain the v1 API contract.

Persistence is deliberately injected here: before S1's Postgres acceptance the
default runtime is process-local, which keeps the HTTP contract testable without
claiming that threads or approvals already survive a restart.
"""
from __future__ import annotations

import json
import inspect
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

import psycopg

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.agent.context import RunContext

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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

    def execute(self, query: str, thread_id: str, run_context: RunContext | None = None) -> dict[str, Any]:
        from langgraph.checkpoint.memory import MemorySaver
        from app.agent.runtime import run_query

        if self.graph is None:
            from app.agent.graph_v2 import build_graph_v2
            self.graph = build_graph_v2(checkpointer=MemorySaver())
        return run_query(query, graph=self.graph, thread_id=thread_id, run_context=run_context)


@dataclass
class PostgresRuntime:
    """Persistent implementation selected only when the runtime DSN is configured.

    A PostgresSaver owns a synchronous connection.  FastAPI can invoke separate
    SSE generators on different worker threads, so a saver/compiled graph must
    be scoped to one execution instead of being shared by the application.
    """

    dsn: str

    def execute(self, query: str, thread_id: str, run_context: RunContext | None = None) -> dict[str, Any]:
        from app.agent.runtime import run_query
        from app.agent.graph_v2 import build_graph_v2
        from app.storage.database import checkpointer_context

        # Do not share a PostgresSaver connection across concurrent SSE runs.
        # Graph construction is negligible next to model/tool execution and
        # preserves a separate durable checkpointer session per request.
        context = run_context or RunContext(thread_id=thread_id)
        if run_context is not None:
            from app.storage.run_event_repository import append_run_event

            with psycopg.connect(self.dsn) as conn:
                append_run_event(
                    conn, run_id=UUID(context.run_id), event_type="query_ingested",
                    payload={"query": query, "thread_id": thread_id, "merchant_id": context.merchant_id},
                    model_visible=True,
                )
                conn.commit()
        from app.llm.client import capture_llm_trace

        with capture_llm_trace() as model_traces:
            with checkpointer_context(self.dsn) as checkpointer:
                graph = build_graph_v2(checkpointer=checkpointer)
                if run_context is None:
                    result = run_query(query, graph=graph, thread_id=thread_id)
                else:
                    result = run_query(query, graph=graph, thread_id=thread_id, run_context=context)
        if run_context is not None:
            self._persist_learning(context, result, model_traces=model_traces)
        return result

    def _persist_learning(
        self, context: RunContext, result: dict[str, Any], *,
        model_traces: list[dict[str, object]] | None = None,
    ) -> None:
        """Commit graph candidates and replay events before the HTTP final event."""
        from app.memory.policy import candidate_from_dict
        from app.storage.memory_repository import append_event, mark_index_result, materialize_fact
        from app.storage.run_event_repository import append_run_event

        run_id = UUID(context.run_id)
        with psycopg.connect(self.dsn) as conn:
            for trace in model_traces or []:
                append_run_event(
                    conn, run_id=run_id, event_type="model_interaction",
                    payload=trace, model_visible=True,
                )
            recalled = result.get("recalled_memories", [])
            append_run_event(
                conn, run_id=run_id, event_type="memory_context",
                payload={"items": recalled, "usage": result.get("memory_usage_trace", {})},
                model_visible=True,
            )
            selected_skill = result.get("selected_skill", {})
            append_run_event(
                conn, run_id=run_id, event_type="skill_selection",
                payload={
                    "selected": {
                        key: selected_skill.get(key)
                        for key in ("id", "version", "content_hash") if selected_skill.get(key)
                    },
                    "trace": result.get("skill_selection_trace", {}),
                },
            )
            append_run_event(
                conn, run_id=run_id, event_type="compiled_plan",
                payload={"actions": result.get("action_sequence", [])},
            )
            for index, action_result in enumerate(result.get("action_results", [])):
                append_run_event(
                    conn, run_id=run_id, event_type="tool_execution",
                    payload={"action_index": index, **action_result},
                )
            append_run_event(
                conn, run_id=run_id, event_type="evidence_verified",
                payload={"verification": result.get("evidence_verification", {}),
                         "evidence": result.get("node_result", {}).get("evidence", [])},
            )
            decision = result.get("node_result", {}).get("data", {}).get("decision")
            if decision:
                append_run_event(
                    conn, run_id=run_id, event_type="structured_decision",
                    payload=decision,
                )
            for payload in result.get("memory_candidates", []):
                try:
                    candidate = candidate_from_dict(payload)
                    event_id = append_event(
                        conn, run_id=run_id, merchant_id=context.merchant_id,
                        candidate=candidate, source_ref=candidate.candidate_id,
                    )
                    content = candidate.value if isinstance(candidate.value, str) else json.dumps(candidate.value, ensure_ascii=False)
                    fact = materialize_fact(
                        conn, source_event_id=event_id, merchant_id=context.merchant_id,
                        candidate=candidate, content=content,
                    )
                    if fact.status == "active":
                        try:
                            from app.rag.indexer import encode_with_shared_embedder

                            embedding = encode_with_shared_embedder(content, normalize_embeddings=True).tolist()
                        except Exception:
                            embedding = None
                        mark_index_result(conn, event_id, UUID(fact.memory_id), embedding)
                    append_run_event(
                        conn, run_id=run_id, event_type="memory_candidate_committed",
                        payload={"candidate_id": candidate.candidate_id, "memory_id": fact.memory_id,
                                 "status": fact.status},
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    append_run_event(
                        conn, run_id=run_id, event_type="memory_candidate_rejected",
                        payload={"candidate_id": payload.get("candidate_id"), "reason": type(exc).__name__},
                    )
            append_run_event(
                conn, run_id=run_id, event_type="final",
                payload={"answer": result.get("final_answer", ""), "node_result": result.get("node_result", {})},
            )
            conn.commit()

    def close(self) -> None:
        """Per-execution checkpointer contexts are already closed."""


@asynccontextmanager
async def _lifespan(application: FastAPI):
    dsn = os.environ.get("DATABASE_URL", "").strip()
    runtime: DemoRuntime | PostgresRuntime = PostgresRuntime(dsn) if dsn else DemoRuntime()
    application.state.runtime = runtime
    try:
        yield
    finally:
        if isinstance(runtime, PostgresRuntime):
            runtime.close()


app = FastAPI(
    title="MerchantCopilot v3", version="3.0.0", lifespan=_lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)

# The mobile client is intentionally constrained to this stable event vocabulary.
SSE_EVENT_TYPES = frozenset({
    "meta", "node_started", "node_completed", "tool_call", "evidence",
    "memory_recalled", "memory_candidate", "token", "final", "error", "done",
})


def _runtime(request: Request) -> DemoRuntime | PostgresRuntime:
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
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        from app.storage.database import database_ready

        if not database_ready(dsn):
            raise HTTPException(status_code=503, detail={"code": "database_unavailable", "message": "database not ready"})
    return {"status": "ready"}


@app.post("/v1/threads", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_demo_token)])
def create_thread(
    body: ThreadRequest,
    key: str = Depends(require_idempotency_key),
    runtime: DemoRuntime | PostgresRuntime = Depends(_runtime),
) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        from app.storage.api_repository import create_or_get_thread

        with psycopg.connect(runtime.dsn) as conn:
            response = create_or_get_thread(conn, merchant_id=body.merchant_id, idempotency_key=UUID(key))
            conn.commit()
            return response
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
    runtime: DemoRuntime | PostgresRuntime = Depends(_runtime),
) -> StreamingResponse:
    if isinstance(runtime, PostgresRuntime):
        return _stream_postgres_run(runtime, thread_id=thread_id, query=body.query, key=key)
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
                    run.update({"status": "completed", "result": result.get("final_answer", ""),
                                "node_result": result.get("node_result", {})})
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
def get_run(run_id: str, runtime: DemoRuntime | PostgresRuntime = Depends(_runtime)) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        from app.storage.api_repository import get_run as get_persisted_run

        with psycopg.connect(runtime.dsn) as conn:
            row = get_persisted_run(conn, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "run not found"})
        return row
    return _get_or_404(runtime.runs, run_id, "run")


@app.get("/v1/threads/{thread_id}/memories", dependencies=[Depends(require_demo_token)])
def get_memories(thread_id: str, runtime: DemoRuntime | PostgresRuntime = Depends(_runtime)) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        from app.storage.api_repository import get_thread, list_thread_memories

        with psycopg.connect(runtime.dsn) as conn:
            if get_thread(conn, thread_id) is None:
                raise HTTPException(status_code=404, detail={"code": "not_found", "message": "thread not found"})
            return {"items": list_thread_memories(conn, thread_id)}
    _get_or_404(runtime.threads, thread_id, "thread")
    return {"items": [m for m in runtime.memories.values() if m.get("thread_id") == thread_id]}


@app.post("/v1/memories/{memory_id}/approve", dependencies=[Depends(require_demo_token)])
def approve_memory(memory_id: str, key: str = Depends(require_idempotency_key), runtime: DemoRuntime | PostgresRuntime = Depends(_runtime)) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        return _decide_postgres_memory(runtime, memory_id, approved=True)
    scoped_key = (f"approve:{memory_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        memory = _get_or_404(runtime.memories, memory_id, "memory")
        memory["status"] = "approved"
        runtime.idempotency[scoped_key] = memory
        return memory


@app.post("/v1/memories/{memory_id}/reject", dependencies=[Depends(require_demo_token)])
def reject_memory(memory_id: str, key: str = Depends(require_idempotency_key), runtime: DemoRuntime | PostgresRuntime = Depends(_runtime)) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        return _decide_postgres_memory(runtime, memory_id, approved=False)
    scoped_key = (f"reject:{memory_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        memory = _get_or_404(runtime.memories, memory_id, "memory")
        memory["status"] = "rejected"
        runtime.idempotency[scoped_key] = memory
        return memory


@app.post("/v1/runs/{run_id}/feedback", dependencies=[Depends(require_demo_token)])
def record_feedback(run_id: str, body: FeedbackRequest, key: str = Depends(require_idempotency_key), runtime: DemoRuntime | PostgresRuntime = Depends(_runtime)) -> dict[str, Any]:
    if isinstance(runtime, PostgresRuntime):
        from app.storage.api_repository import record_feedback as persist_feedback

        with psycopg.connect(runtime.dsn) as conn:
            if not persist_feedback(conn, run_id, body.model_dump()):
                raise HTTPException(status_code=404, detail={"code": "not_found", "message": "run not found"})
            conn.commit()
        return {"run_id": run_id, "accepted": True}
    scoped_key = (f"feedback:{run_id}", key)
    with runtime.lock:
        if scoped_key in runtime.idempotency:
            return runtime.idempotency[scoped_key]
        run = _get_or_404(runtime.runs, run_id, "run")
        run["feedback"] = body.model_dump()
        response = {"run_id": run_id, "accepted": True}
        runtime.idempotency[scoped_key] = response
        return response


def _decide_postgres_memory(runtime: PostgresRuntime, memory_id: str, *, approved: bool) -> dict[str, Any]:
    from app.storage.api_repository import decide_memory

    with psycopg.connect(runtime.dsn) as conn:
        memory = decide_memory(conn, memory_id, approved=approved)
        if memory is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "memory not found"})
        conn.commit()
        return memory


def _stream_postgres_run(runtime: PostgresRuntime, *, thread_id: str, query: str, key: str) -> StreamingResponse:
    """Persistent SSE execution: only the atomic queued→running claimant executes."""
    from app.storage.api_repository import claim_monthly_run, claim_queued_run, finish_run, get_run as get_persisted_run, get_thread
    from app.storage.memory_repository import create_or_get_run

    with psycopg.connect(runtime.dsn) as conn:
        thread = get_thread(conn, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "thread not found"})
        run = create_or_get_run(conn, thread_id=thread_id, merchant_id=thread["merchant_id"],
                                idempotency_key=UUID(key), request={"query": query})
        conn.commit()

    def events():
        yield _sse("meta", {"run_id": run["run_id"], "thread_id": thread_id})
        with psycopg.connect(runtime.dsn) as conn:
            execute = claim_queued_run(conn, run["run_id"])
            conn.commit()
        if execute:
            yield _sse("node_started", {"run_id": run["run_id"], "node": "agent"})
            with psycopg.connect(runtime.dsn) as conn:
                within_cap = claim_monthly_run(
                    conn,
                    merchant_id=thread["merchant_id"],
                    cap=int(os.environ.get("DEMO_MONTHLY_RUN_CAP", "1000")),
                )
                conn.commit()
            if not within_cap:
                error = {"code": "quota", "message": "demo run cap reached"}
                with psycopg.connect(runtime.dsn) as conn:
                    finish_run(conn, UUID(run["run_id"]), status="failed", error=error)
                    conn.commit()
                yield _sse("error", error)
            else:
                try:
                    context = RunContext(
                        run_id=run["run_id"], thread_id=thread_id, merchant_id=thread["merchant_id"],
                    )
                    parameters = inspect.signature(runtime.execute).parameters
                    if "run_context" in parameters:
                        result = runtime.execute(query, thread_id, run_context=context)
                    else:
                        # Compatibility seam for injected v2 runtimes used by
                        # callers/tests; the production runtime always accepts
                        # and persists the explicit v3 RunContext.
                        result = runtime.execute(query, thread_id)
                    persisted = {
                        "final_answer": result.get("final_answer", ""),
                        "node_result": result.get("node_result", {}),
                        "selected_skill": result.get("selected_skill", {}),
                    }
                    with psycopg.connect(runtime.dsn) as conn:
                        finish_run(conn, UUID(run["run_id"]), status="completed", result=persisted)
                        conn.commit()
                    yield _sse("node_completed", {"run_id": run["run_id"], "node": "agent"})
                    yield _sse("evidence", {"run_id": run["run_id"], "items": persisted["node_result"].get("evidence", [])})
                    yield _sse("final", {"run_id": run["run_id"], "answer": persisted["final_answer"]})
                except Exception as exc:
                    error = _classify_error(exc)
                    with psycopg.connect(runtime.dsn) as conn:
                        finish_run(conn, UUID(run["run_id"]), status="failed", error=error)
                        conn.commit()
                    yield _sse("error", error)
        else:
            with psycopg.connect(runtime.dsn) as conn:
                persisted = get_persisted_run(conn, run["run_id"])
            if persisted and persisted["status"] == "completed":
                yield _sse("final", {"run_id": run["run_id"], "answer": persisted.get("result", "")})
            elif persisted and persisted["status"] == "failed":
                yield _sse("error", persisted.get("error", {"code": "agent_failure"}))
        with psycopg.connect(runtime.dsn) as conn:
            persisted = get_persisted_run(conn, run["run_id"])
        yield _sse("done", {"run_id": run["run_id"], "status": persisted["status"] if persisted else "failed"})

    return StreamingResponse(events(), media_type="text/event-stream")


def _get_or_404(rows: dict[str, dict[str, Any]], key: str, label: str) -> dict[str, Any]:
    if key not in rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"{label} not found"})
    return rows[key]


def _sse(event: str, payload: dict[str, Any]) -> str:
    assert event in SSE_EVENT_TYPES
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _classify_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, TimeoutError):
        return {"code": "llm_timeout", "message": "model request timed out"}
    if isinstance(exc, ConnectionError):
        return {"code": "database_unavailable", "message": "database unavailable"}
    return {"code": "agent_failure", "message": str(exc)}
