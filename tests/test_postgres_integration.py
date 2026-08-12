"""S1 acceptance tests. They are skipped until a real local pgvector DSN is supplied."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from langgraph.checkpoint.base import empty_checkpoint

from app.memory.policy import MemoryCandidate
from app.storage.database import apply_migrations, checkpointer_context
from app.storage.memory_repository import (
    append_event,
    compensate_pending_indexes,
    create_or_get_run,
    mark_index_result,
    materialize_fact,
)

DSN = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="requires local pgvector DATABASE_URL")


def test_migrations_are_idempotent_and_schema_is_present():
    apply_migrations()
    assert apply_migrations() == []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {row[0] for row in cur.fetchall()}
    assert {"run_records", "memory_events", "memory_facts", "memory_links", "usage_counters"} <= tables


def test_concurrent_idempotency_supersession_and_vector_dimension():
    apply_migrations()
    key = uuid4()

    def create_once(_: int) -> str:
        with psycopg.connect(DSN) as conn:
            run = create_or_get_run(conn, thread_id="s1-thread", merchant_id="s1-merchant", idempotency_key=key, request={"test": "s1"})
            conn.commit()
            return run["run_id"]

    with ThreadPoolExecutor(max_workers=20) as pool:
        run_ids = list(pool.map(create_once, range(20)))
    assert len(set(run_ids)) == 1
    run_id = UUID(run_ids[0])
    suffix = str(uuid4())
    first = MemoryCandidate(f"first-{suffix}", "merchant", "audience", "old", "mcp")
    second = MemoryCandidate(f"second-{suffix}", "merchant", "audience", "new", "mcp")
    with psycopg.connect(DSN) as conn:
        first_event = append_event(conn, run_id=run_id, merchant_id="s1-merchant", candidate=first, source_ref=first.candidate_id)
        assert append_event(conn, run_id=run_id, merchant_id="s1-merchant", candidate=first, source_ref=first.candidate_id) == first_event
        materialize_fact(conn, source_event_id=first_event, merchant_id="s1-merchant", candidate=first, content="old")
        second_event = append_event(conn, run_id=run_id, merchant_id="s1-merchant", candidate=second, source_ref=second.candidate_id)
        second_fact = materialize_fact(conn, source_event_id=second_event, merchant_id="s1-merchant", candidate=second, content="new")
        mark_index_result(conn, second_event, UUID(second_fact.memory_id), [0.0] * 1024)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT status, valid_to IS NOT NULL FROM memory_facts WHERE source_event_id = %s", (first_event,))
            assert cur.fetchone() == ("superseded", True)
            cur.execute("SELECT vector_dims(embedding) FROM memory_facts WHERE memory_id = %s", (UUID(second_fact.memory_id),))
            assert cur.fetchone() == (1024,)


def test_concurrent_semantic_fact_writes_leave_exactly_one_active_fact():
    """Concurrent first writes cannot bypass canonical supersession."""
    apply_migrations()
    suffix = str(uuid4())
    merchant_id = f"semantic-race-{suffix}"
    with psycopg.connect(DSN) as conn:
        run = create_or_get_run(
            conn, thread_id=f"thread-{suffix}", merchant_id=merchant_id,
            idempotency_key=uuid4(), request={"query": "race"},
        )
        conn.commit()
    run_id = UUID(run["run_id"])

    def write(index: int) -> str:
        candidate = MemoryCandidate(
            f"race-{suffix}-{index}", "merchant", "operating_constraint",
            {"value": index}, "mcp",
        )
        with psycopg.connect(DSN) as conn:
            event_id = append_event(
                conn, run_id=run_id, merchant_id=merchant_id, candidate=candidate,
                source_ref=candidate.candidate_id,
            )
            fact = materialize_fact(
                conn, source_event_id=event_id, merchant_id=merchant_id,
                candidate=candidate, content=f"concurrent-{index}",
            )
            conn.commit()
        return fact.memory_id

    with ThreadPoolExecutor(max_workers=10) as pool:
        memory_ids = list(pool.map(write, range(10)))
    assert len(set(memory_ids)) == 10

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM memory_facts
                 WHERE merchant_id = %s AND subject = 'merchant'
                   AND predicate = 'operating_constraint'
                   AND status = 'active' AND valid_to IS NULL""",
            (merchant_id,),
        )
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM memory_events WHERE run_id = %s", (run_id,))
        assert cur.fetchone() == (10,)


def test_concurrent_duplicate_event_delivery_appends_one_canonical_event():
    apply_migrations()
    suffix = str(uuid4())
    merchant_id = f"event-race-{suffix}"
    candidate = MemoryCandidate(f"event-{suffix}", "merchant", "constraint", "one", "mcp")
    with psycopg.connect(DSN) as conn:
        run = create_or_get_run(
            conn, thread_id=f"thread-{suffix}", merchant_id=merchant_id,
            idempotency_key=uuid4(), request={"query": "duplicate event"},
        )
        conn.commit()
    run_id = UUID(run["run_id"])

    def deliver(_: int) -> str:
        with psycopg.connect(DSN) as conn:
            event_id = append_event(
                conn, run_id=run_id, merchant_id=merchant_id, candidate=candidate,
                source_ref="duplicate-delivery",
            )
            conn.commit()
        return str(event_id)

    with ThreadPoolExecutor(max_workers=10) as pool:
        event_ids = list(pool.map(deliver, range(10)))
    assert len(set(event_ids)) == 1
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM memory_events WHERE run_id = %s AND source_ref = 'duplicate-delivery'",
            (run_id,),
        )
        assert cur.fetchone() == (1,)


def test_postgres_checkpointer_persists_and_isolates_threads():
    """A reopened saver must recover only the checkpoint for its own thread."""
    thread_id = f"s1-checkpoint-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"]["answer"] = "persisted"

    with checkpointer_context(DSN) as saver:
        saved_config = saver.put(
            config,
            checkpoint,
            {"source": "input", "step": 0, "writes": {"answer": "persisted"}},
            {},
        )
        assert saver.get_tuple(saved_config).checkpoint["channel_values"]["answer"] == "persisted"

    with checkpointer_context(DSN) as reopened:
        restored = reopened.get_tuple(config)
        assert restored is not None
        assert restored.checkpoint["channel_values"]["answer"] == "persisted"
        other_thread = {"configurable": {"thread_id": f"{thread_id}-other", "checkpoint_ns": ""}}
        assert reopened.get_tuple(other_thread) is None


def test_policy_statuses_idempotent_event_retries_and_index_compensation():
    """Exercise the T06 policy and compensation behavior against real Postgres."""
    suffix = str(uuid4())
    merchant_id = f"s1-policy-{suffix}"
    with psycopg.connect(DSN) as conn:
        run = create_or_get_run(
            conn,
            thread_id=f"thread-{suffix}",
            merchant_id=merchant_id,
            idempotency_key=uuid4(),
            request={"test": "policy"},
        )
        run_id = UUID(run["run_id"])

        active = MemoryCandidate(f"active-{suffix}", "merchant", "constraint", "active", "mcp")
        active_event = append_event(conn, run_id=run_id, merchant_id=merchant_id, candidate=active, source_ref="retry-once")
        for _ in range(9):
            assert append_event(conn, run_id=run_id, merchant_id=merchant_id, candidate=active, source_ref="retry-once") == active_event
        active_fact = materialize_fact(conn, source_event_id=active_event, merchant_id=merchant_id, candidate=active, content="retryable")
        mark_index_result(conn, active_event, UUID(active_fact.memory_id), None)

        causal = MemoryCandidate(f"causal-{suffix}", "merchant", "cause", "inferred", "llm", causal_inference=True)
        causal_event = append_event(conn, run_id=run_id, merchant_id=merchant_id, candidate=causal, source_ref=causal.candidate_id)
        assert materialize_fact(conn, source_event_id=causal_event, merchant_id=merchant_id, candidate=causal, content="inferred").status == "pending"

        strategy = MemoryCandidate(f"strategy-{suffix}", "merchant", "strategy", "proposal", "llm", kind="strategy")
        strategy_event = append_event(conn, run_id=run_id, merchant_id=merchant_id, candidate=strategy, source_ref=strategy.candidate_id)
        assert materialize_fact(conn, source_event_id=strategy_event, merchant_id=merchant_id, candidate=strategy, content="proposal").status == "proposed_decision"

        result = compensate_pending_indexes(conn, merchant_id=merchant_id, encode=lambda _: [0.0] * 1024)
        conn.commit()
        assert result == {"attempted": 1, "indexed": 1, "pending": 0}
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM memory_events WHERE run_id = %s AND source_ref = 'retry-once'", (run_id,))
            assert cur.fetchone() == (1,)
            cur.execute("SELECT status FROM memory_facts WHERE source_event_id = %s", (causal_event,))
            assert cur.fetchone() == ("pending",)
            cur.execute("SELECT status FROM memory_facts WHERE source_event_id = %s", (strategy_event,))
            assert cur.fetchone() == ("proposed_decision",)
            cur.execute("SELECT index_status FROM memory_events WHERE event_id = %s", (active_event,))
            assert cur.fetchone() == ("indexed",)
            cur.execute(
                """SELECT count(*) FROM memory_facts AS fact
                     LEFT JOIN memory_events AS event ON event.event_id = fact.source_event_id
                    WHERE fact.merchant_id = %s AND fact.status = 'active' AND event.event_id IS NOT NULL""",
                (merchant_id,),
            )
            assert cur.fetchone() == (1,)
