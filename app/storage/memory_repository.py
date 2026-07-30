"""Raw SQL repository for the canonical Memory ledger.

This layer intentionally owns transaction ordering and idempotency.  Mem0 (or
pgvector retrieval) is only an index; an indexing failure must never discard a
canonical event or fact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import psycopg

from app.memory.policy import CanonicalFact, MemoryCandidate, gate_candidate


def create_or_get_run(
    conn: psycopg.Connection, *, thread_id: str, merchant_id: str,
    idempotency_key: UUID, request: dict[str, Any], run_id: UUID | None = None,
) -> dict[str, Any]:
    """Atomically return one run for a request key, including concurrent retries."""
    run_id = run_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO run_records (run_id, thread_id, merchant_id, idempotency_key, status, request_json)
               VALUES (%s, %s, %s, %s, 'queued', %s::jsonb)
               ON CONFLICT (idempotency_key) DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key
               RETURNING run_id, thread_id, merchant_id, status, request_json""",
            (run_id, thread_id, merchant_id, idempotency_key, json.dumps(request)),
        )
        row = cur.fetchone()
    return {"run_id": str(row[0]), "thread_id": row[1], "merchant_id": row[2], "status": row[3], "request": row[4]}


def append_event(
    conn: psycopg.Connection, *, run_id: UUID, merchant_id: str, candidate: MemoryCandidate,
    source_ref: str, event_id: UUID | None = None,
) -> UUID:
    """Append once per run/source; duplicate delivery returns the original event id."""
    event_id = event_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO memory_events
                 (event_id, run_id, merchant_id, event_kind, subject, predicate, value_json, source_type, source_ref)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
               ON CONFLICT (run_id, source_ref) DO UPDATE SET source_ref = EXCLUDED.source_ref
               RETURNING event_id""",
            (event_id, run_id, merchant_id, candidate.kind, candidate.subject, candidate.predicate,
             json.dumps(candidate.value), candidate.source_type, source_ref),
        )
        return cur.fetchone()[0]


def materialize_fact(
    conn: psycopg.Connection, *, source_event_id: UUID, merchant_id: str,
    candidate: MemoryCandidate, content: str, memory_id: UUID | None = None,
) -> CanonicalFact:
    """Create a fact and supersede prior active fact with the same semantic key."""
    status = gate_candidate(candidate)
    memory_id = memory_id or uuid4()
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        if status == "active":
            cur.execute(
                """UPDATE memory_facts SET status = 'superseded', valid_to = %s
                   WHERE merchant_id = %s AND subject = %s AND predicate = %s
                     AND status = 'active' AND valid_to IS NULL""",
                (now, merchant_id, candidate.subject, candidate.predicate),
            )
        cur.execute(
            """INSERT INTO memory_facts
                 (memory_id, source_event_id, merchant_id, memory_kind, subject, predicate, value_json, content, status, valid_from)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)""",
            (memory_id, source_event_id, merchant_id, candidate.kind, candidate.subject, candidate.predicate,
             json.dumps(candidate.value), content, status, now),
        )
    return CanonicalFact(memory_id=str(memory_id), subject=candidate.subject, predicate=candidate.predicate,
                         value=candidate.value, status=status, source_event_id=str(source_event_id))


def mark_index_result(conn: psycopg.Connection, event_id: UUID, memory_id: UUID, embedding: list[float] | None) -> None:
    """Index outcome is compensatable metadata, never a reason to roll back facts."""
    with conn.cursor() as cur:
        if embedding is None:
            cur.execute("UPDATE memory_events SET index_status = 'pending' WHERE event_id = %s", (event_id,))
            return
        vector = "[" + ",".join(str(value) for value in embedding) + "]"
        cur.execute("UPDATE memory_facts SET embedding = %s::vector WHERE memory_id = %s", (vector, memory_id))
        cur.execute("UPDATE memory_events SET index_status = 'indexed' WHERE event_id = %s", (event_id,))
