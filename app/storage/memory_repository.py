"""Raw SQL repository for the canonical Memory ledger.

This layer intentionally owns transaction ordering and idempotency.  Mem0 (or
pgvector retrieval) is only an index; an indexing failure must never discard a
canonical event or fact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg

from app.memory.policy import CanonicalFact, MemoryCandidate, gate_candidate, resolved_fact_type
from app.memory.retriever import RetrievedMemory


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
                 (event_id, run_id, merchant_id, event_kind, subject, predicate, value_json, source_type, source_ref,
                  thread_id, occurred_at, evidence_refs, schema_version, effective_from, effective_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, COALESCE(%s, now()), %s::jsonb, %s, %s, %s)
               ON CONFLICT (run_id, source_ref) DO UPDATE SET source_ref = EXCLUDED.source_ref
               RETURNING event_id""",
            (event_id, run_id, merchant_id, candidate.kind, candidate.subject, candidate.predicate,
             json.dumps(candidate.value), candidate.source_type, source_ref, candidate.thread_id,
             candidate.observed_at, json.dumps(list(candidate.evidence_refs), ensure_ascii=False), candidate.schema_version,
             candidate.effective_from, candidate.effective_to),
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
            # 行锁无法覆盖“首条事实尚不存在”的竞态；以语义键序列化同一
            # merchant/subject/predicate 的替换，再由 003 的部分唯一索引兜底。
            semantic_key = (
                f"{merchant_id}\x1f{candidate.subject}\x1f{candidate.predicate}\x1f"
                f"{candidate.effective_from}\x1f{candidate.effective_to}"
            )
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (semantic_key,))
            if candidate.effective_from is None:
                cur.execute(
                    """UPDATE memory_facts SET status = 'superseded', valid_to = %s
                       WHERE merchant_id = %s AND subject = %s AND predicate = %s
                         AND status = 'active' AND valid_to IS NULL
                         AND effective_from IS NULL AND effective_to IS NULL""",
                    (now, merchant_id, candidate.subject, candidate.predicate),
                )
            else:
                cur.execute(
                    """UPDATE memory_facts SET status = 'superseded', valid_to = %s
                       WHERE merchant_id = %s AND subject = %s AND predicate = %s
                         AND status = 'active' AND valid_to IS NULL
                         AND effective_from IS NOT NULL AND effective_to IS NOT NULL
                         AND tstzrange(effective_from, effective_to, '[)')
                             && tstzrange(%s, %s, '[)')""",
                    (now, merchant_id, candidate.subject, candidate.predicate,
                     candidate.effective_from, candidate.effective_to),
                )
        fact_type = resolved_fact_type(candidate)
        decision_ids: list[str] = []
        if fact_type == "outcome":
            if not isinstance(candidate.value, dict):
                raise ValueError("outcome value must contain decision_memory_ids")
            decision_ids = [str(item) for item in candidate.value.get("decision_memory_ids", [])]
            if not decision_ids:
                raise ValueError("outcome must link at least one executed decision")
            cur.execute(
                """SELECT memory_id FROM memory_facts
                    WHERE memory_id = ANY(%s::uuid[]) AND fact_type = 'decision' AND status = 'active'
                      AND value_json->>'execution_status' = 'executed'""",
                (decision_ids,),
            )
            if {str(row[0]) for row in cur.fetchall()} != set(decision_ids):
                raise ValueError("outcome cannot claim an unexecuted decision")
        cur.execute(
            """INSERT INTO memory_facts
                 (memory_id, source_event_id, merchant_id, memory_kind, subject, predicate, value_json, content,
                  status, valid_from, fact_type, scope_type, scope_id, observed_at, truth_confidence,
                  utility_score, contradiction_group_id, approval_reason, effective_from, effective_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, COALESCE(%s, %s), %s, %s, %s, %s, %s, %s)""",
            (memory_id, source_event_id, merchant_id, candidate.kind, candidate.subject, candidate.predicate,
             json.dumps(candidate.value), content, status, now, fact_type, candidate.scope_type,
             candidate.scope_id or merchant_id, candidate.observed_at, now, candidate.truth_confidence,
             candidate.utility_score, candidate.contradiction_group_id, candidate.approval_reason,
             candidate.effective_from, candidate.effective_to),
        )
        for decision_id in decision_ids:
            cur.execute(
                """INSERT INTO memory_links (link_id, from_memory_id, to_memory_id, relation)
                   VALUES (%s, %s, %s, 'decision_outcome')
                   ON CONFLICT (from_memory_id, to_memory_id, relation) DO NOTHING""",
                (uuid4(), UUID(decision_id), memory_id),
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


def compensate_pending_indexes(
    conn: psycopg.Connection,
    *,
    merchant_id: str,
    encode: Callable[[str], list[float]],
    limit: int = 20,
) -> dict[str, int]:
    """Retry canonical facts whose vector indexing previously failed.

    The canonical event/fact is deliberately committed before this work.  A retry
    failure therefore leaves `index_status=pending` for a later request instead
    of losing the auditable fact.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT event_id, memory_id, content
                 FROM memory_events AS event
                 JOIN memory_facts AS fact ON fact.source_event_id = event.event_id
                WHERE event.merchant_id = %s
                  AND event.index_status = 'pending'
                  AND fact.status = 'active'
                  AND fact.embedding IS NULL
                ORDER BY event.created_at
                LIMIT %s""",
            (merchant_id, limit),
        )
        pending = cur.fetchall()

    indexed = 0
    for event_id, memory_id, content in pending:
        try:
            embedding = encode(content)
            if len(embedding) != 1024:
                raise ValueError("Memory embedding must have 1024 dimensions")
            mark_index_result(conn, event_id, memory_id, embedding)
            indexed += 1
        except Exception:
            # Keep the pending marker: retries are safe and canonical data survives.
            continue
    return {"attempted": len(pending), "indexed": indexed, "pending": len(pending) - indexed}


def fetch_active_memories(
    conn: psycopg.Connection, *, merchant_id: str, query_embedding: list[float], candidate_limit: int = 20,
    fact_types: list[str] | None = None, thread_id: str | None = None,
    effective_from: datetime | None = None, effective_to: datetime | None = None,
) -> list[RetrievedMemory]:
    """Fetch only current canonical facts; caller applies the fixed context budgets."""
    vector = "[" + ",".join(str(value) for value in query_embedding) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """SELECT memory_id, source_event_id, memory_kind, content, subject, predicate,
                      1 - (embedding <=> %s::vector) AS semantic, importance, confidence, valid_from, valid_to, status,
                      fact_type, scope_type, scope_id, truth_confidence, utility_score, observed_at,
                      effective_from, effective_to
                 FROM memory_facts
                WHERE merchant_id = %s AND status = 'active' AND valid_to IS NULL AND embedding IS NOT NULL
                  AND (%s::text[] IS NULL OR fact_type = ANY(%s::text[]))
                  AND (scope_type = 'merchant' OR (scope_type = 'thread' AND scope_id = %s))
                  AND (%s::timestamptz IS NULL OR effective_from IS NULL
                       OR tstzrange(effective_from, effective_to, '[)')
                          && tstzrange(%s::timestamptz, %s::timestamptz, '[)'))
                ORDER BY embedding <=> %s::vector
                LIMIT %s""",
            (vector, merchant_id, fact_types, fact_types, thread_id,
             effective_from, effective_from, effective_to, vector, candidate_limit),
        )
        rows = cur.fetchall()
    memories = []
    for row in rows:
        memories.append(RetrievedMemory(
            memory_id=str(row[0]), source_event_id=str(row[1]), kind=row[2], content=row[3],
            subject=row[4], predicate=row[5], semantic=float(row[6]),
            importance=float(row[7]), confidence=float(row[8]),
            valid_from=row[9], valid_to=row[10], status=row[11],
            fact_type=row[12] if len(row) > 12 else "observation",
            scope_type=row[13] if len(row) > 13 else "merchant",
            scope_id=(row[14] or "") if len(row) > 14 else merchant_id,
            truth_confidence=float(row[15]) if len(row) > 15 else float(row[8]),
            utility_score=float(row[16]) if len(row) > 16 else 0.0,
            observed_at=row[17] if len(row) > 17 else row[9],
            effective_from=row[18] if len(row) > 18 else None,
            effective_to=row[19] if len(row) > 19 else None,
        ))
    return memories


def link_memories(
    conn: psycopg.Connection, *, from_memory_id: UUID, to_memory_id: UUID,
    relation: str, link_id: UUID | None = None,
) -> UUID:
    if relation not in {"supersedes", "contradicts", "derived_from", "decision_outcome"}:
        raise ValueError("unsupported memory relation")
    link_id = link_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO memory_links (link_id, from_memory_id, to_memory_id, relation)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (from_memory_id, to_memory_id, relation)
               DO UPDATE SET relation = EXCLUDED.relation
               RETURNING link_id""",
            (link_id, from_memory_id, to_memory_id, relation),
        )
        return cur.fetchone()[0]
