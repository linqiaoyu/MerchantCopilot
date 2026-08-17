"""Postgres operations consumed by the fixed FastAPI v2 contract."""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import psycopg


def create_or_get_thread(
    conn: psycopg.Connection, *, merchant_id: str, idempotency_key: UUID, thread_id: UUID | None = None,
) -> dict[str, str]:
    thread_id = thread_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO threads (thread_id, merchant_id, idempotency_key)
                 VALUES (%s, %s, %s)
                 ON CONFLICT (idempotency_key) DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
                 RETURNING thread_id, merchant_id""",
            (thread_id, merchant_id, idempotency_key),
        )
        row = cur.fetchone()
    return {"thread_id": str(row[0]), "merchant_id": row[1]}


def get_thread(conn: psycopg.Connection, thread_id: str) -> dict[str, str] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT thread_id, merchant_id FROM threads WHERE thread_id = %s", (thread_id,))
        row = cur.fetchone()
    return {"thread_id": str(row[0]), "merchant_id": row[1]} if row else None


def finish_run(conn: psycopg.Connection, run_id: UUID, *, status: str, result: dict[str, Any] | None = None, error: dict[str, str] | None = None) -> None:
    payload = result if result is not None else {"error": error or {}}
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE run_records SET status = %s, result_json = %s::jsonb, completed_at = now()
                 WHERE run_id = %s""",
            (status, json.dumps(payload), run_id),
        )


def claim_queued_run(conn: psycopg.Connection, run_id: str) -> bool:
    """Atomically elect one concurrent SSE request to execute an idempotent run."""
    with conn.cursor() as cur:
        cur.execute("UPDATE run_records SET status = 'running' WHERE run_id = %s AND status = 'queued'", (run_id,))
        return cur.rowcount == 1


def claim_monthly_run(conn: psycopg.Connection, *, merchant_id: str, cap: int) -> bool:
    """Atomically reserve one demo run without exceeding the configured cap."""
    if cap <= 0:
        return False
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO usage_counters (counter_month, merchant_id, run_count)
                 VALUES (%s, %s, 1)
                 ON CONFLICT (counter_month, merchant_id) DO UPDATE
                    SET run_count = usage_counters.run_count + 1, updated_at = now()
                  WHERE usage_counters.run_count < %s
                 RETURNING run_count""",
            (date.today().replace(day=1), merchant_id, cap),
        )
        return cur.fetchone() is not None


def get_run(conn: psycopg.Connection, run_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT run_id, thread_id, merchant_id, status, request_json, result_json, feedback_json
                 FROM run_records WHERE run_id = %s""",
            (run_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    result = row[5] or {}
    response = {"run_id": str(row[0]), "thread_id": row[1], "merchant_id": row[2], "status": row[3],
                "query": (row[4] or {}).get("query", "")}
    if row[3] == "completed":
        response.update({"result": result.get("final_answer", ""), "node_result": result.get("node_result", {})})
    elif row[3] == "failed":
        response["error"] = result.get("error", {})
    if row[6] is not None:
        response["feedback"] = row[6]
    return response


def list_thread_memories(conn: psycopg.Connection, thread_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT fact.memory_id, fact.memory_kind, fact.content, fact.status, fact.source_event_id
                 FROM memory_facts AS fact
                 JOIN memory_events AS event ON event.event_id = fact.source_event_id
                 JOIN run_records AS run ON run.run_id = event.run_id
                WHERE run.thread_id = %s
                ORDER BY fact.created_at""",
            (thread_id,),
        )
        rows = cur.fetchall()
    return [{"memory_id": str(row[0]), "kind": row[1], "content": row[2], "status": row[3],
             "source_event_id": str(row[4])} for row in rows]


def decide_memory(
    conn: psycopg.Connection, memory_id: str, *, approved: bool,
    reason: str = "explicit_api_decision",
) -> dict[str, Any] | None:
    status = "active" if approved else "rejected"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE memory_facts SET status = %s, approval_reason = %s WHERE memory_id = %s
                 RETURNING memory_id, status""",
            (status, reason, memory_id),
        )
        row = cur.fetchone()
    return {"memory_id": str(row[0]), "status": row[1]} if row else None


def record_feedback(conn: psycopg.Connection, run_id: str, feedback: dict[str, Any]) -> bool:
    with conn.cursor() as cur:
        cur.execute("UPDATE run_records SET feedback_json = %s::jsonb WHERE run_id = %s", (json.dumps(feedback), run_id))
        return cur.rowcount == 1
