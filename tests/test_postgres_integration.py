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
from app.storage.memory_repository import append_event, create_or_get_run, mark_index_result, materialize_fact

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
