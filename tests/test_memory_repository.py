from uuid import UUID

from app.memory.policy import MemoryCandidate
from app.storage.memory_repository import append_event, create_or_get_run, fetch_active_memories, materialize_fact


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Connection:
    def __init__(self, row):
        self.cursor_instance = _Cursor(row)

    def cursor(self):
        return self.cursor_instance


def test_run_and_event_queries_are_idempotent_by_database_constraints():
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    conn = _Connection((run_id, "t1", "m1", "queued", {}))
    result = create_or_get_run(conn, thread_id="t1", merchant_id="m1", idempotency_key=UUID(int=2), request={})
    assert result["run_id"] == str(run_id)
    assert "ON CONFLICT (idempotency_key)" in conn.cursor_instance.calls[0][0]
    candidate = MemoryCandidate("c1", "merchant", "audience", "new", "mcp")
    conn = _Connection((UUID(int=3),))
    assert append_event(conn, run_id=run_id, merchant_id="m1", candidate=candidate, source_ref="c1") == UUID(int=3)
    assert "ON CONFLICT (run_id, source_ref)" in conn.cursor_instance.calls[0][0]


def test_active_fact_supersedes_before_inserting_new_value():
    candidate = MemoryCandidate("c1", "merchant", "audience", "new", "mcp")
    conn = _Connection(None)
    fact = materialize_fact(conn, source_event_id=UUID(int=3), merchant_id="m1", candidate=candidate, content="new")
    assert fact.status == "active"
    calls = conn.cursor_instance.calls
    assert "pg_advisory_xact_lock" in calls[0][0]
    assert "UPDATE memory_facts SET status = 'superseded'" in calls[1][0]
    assert "INSERT INTO memory_facts" in calls[2][0]


def test_recall_query_filters_stale_facts_and_uses_vector_distance():
    conn = _Connection([])
    assert fetch_active_memories(conn, merchant_id="m1", query_embedding=[0.0, 1.0]) == []
    sql, params = conn.cursor_instance.calls[0]
    assert "status = 'active' AND valid_to IS NULL AND embedding IS NOT NULL" in sql
    assert "embedding <=> %s::vector" in sql
    assert params[-1] == 20


def test_recall_preserves_canonical_predicate_for_downstream_strategy_context():
    from datetime import datetime, timezone

    row = [(UUID(int=4), UUID(int=5), "core", "类目:女装", "merchant", "category",
            .9, .8, .7, datetime.now(timezone.utc), None, "active")]
    memories = fetch_active_memories(_Connection(row), merchant_id="m1", query_embedding=[0.0, 1.0])
    assert memories[0].subject == "merchant"
    assert memories[0].predicate == "category"
