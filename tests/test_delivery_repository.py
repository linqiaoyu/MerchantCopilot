"""Delivery transactions exercised in an isolated, disposable PostgreSQL database.

The configured database supplies connection credentials only. No existing table,
fixture, benchmark artifact, or paid model is changed by these tests.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from importlib import import_module
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.storage.database import apply_migrations


@pytest.fixture(scope="module")
def delivery_dsn():
    source = os.environ.get("DATABASE_URL", "")
    if not source:
        pytest.skip("requires local PostgreSQL DATABASE_URL")
    database_name = f"delivery_test_{uuid4().hex}"
    with psycopg.connect(source, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database_name)))
    target = make_conninfo(source, dbname=database_name)
    try:
        apply_migrations(target)
        yield target
    finally:
        with psycopg.connect(source, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name)))


@pytest.fixture
def repo(delivery_dsn):
    module = import_module("app.storage.delivery_repository")
    repository = module.DeliveryRepository(delivery_dsn, merchant_id=f"delivery-{uuid4()}")
    yield repository
    repository.recover_interrupted(f"cleanup-{uuid4()}")


def thread(repo):
    return repo.create_thread(idempotency_key=str(uuid4()))["thread_id"]


def admit(repo, thread_id=None, key=None, **kwargs):
    return repo.admit_run(
        thread_id=thread_id or thread(repo), request={"query": "GMV"},
        idempotency_key=key or str(uuid4()), owner="test-owner", **kwargs,
    )


def assert_code(code, operation):
    module = import_module("app.storage.delivery_repository")
    with pytest.raises(module.DeliveryRepositoryError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


def candidate(**overrides):
    return {
        "candidate_id": str(uuid4()), "subject": "merchant", "predicate": "budget",
        "value": "1000", "source_type": "llm", "fact_type": "inference",
        "scope_type": "merchant", "schema_version": 3, **overrides,
    }


def finish_with_memory(repo, **overrides):
    run, _ = admit(repo)
    result = {"final_answer": "done", "node_result": {"evidence": ["sql:metric"]},
              "memory_candidates": [candidate(**overrides)]}
    repo.finish(run["run_id"], "test-owner", result=result)
    return run, repo.list_memories()["items"][0]


def test_atomic_same_key_retries_execute_and_charge_once(repo, delivery_dsn):
    thread_id, key = thread(repo), str(uuid4())
    with ThreadPoolExecutor(max_workers=10) as pool:
        rows = list(pool.map(lambda _: admit(repo, thread_id, key), range(10)))
    assert sum(created for _, created in rows) == 1
    assert len({row["run_id"] for row, _ in rows}) == 1
    with psycopg.connect(delivery_dsn) as conn:
        assert conn.execute("SELECT run_count FROM usage_counters WHERE merchant_id = %s", (repo.merchant_id,)).fetchone() == (1,)
    assert_code("idempotency_conflict", lambda: repo.admit_run(
        thread_id=thread_id, request={"query": "changed"}, idempotency_key=key, owner="test-owner"))
    other_thread = thread(repo)
    assert_code("idempotency_conflict", lambda: admit(repo, other_thread, key))


def test_busy_and_quota_do_not_consume_key_or_counter_and_replay_precedes_busy(repo):
    thread_id, first_key, rejected_key = thread(repo), str(uuid4()), str(uuid4())
    first, _ = admit(repo, thread_id, first_key, monthly_cap=2)
    assert_code("busy", lambda: admit(repo, thread_id, rejected_key, monthly_cap=2))
    replay, created = admit(repo, thread_id, first_key, monthly_cap=0)
    assert not created and replay["run_id"] == first["run_id"]
    repo.finish(first["run_id"], "test-owner", result={"final_answer": "done"})
    second, created = admit(repo, thread_id, rejected_key, monthly_cap=2)
    assert created
    repo.finish(second["run_id"], "test-owner", result={"final_answer": "done"})
    assert_code("quota", lambda: admit(repo, thread_id, str(uuid4()), monthly_cap=2))
    assert len(repo.list_runs()["items"]) == 2


def test_public_events_are_ordered_filtered_and_owner_guarded(repo):
    run, _ = admit(repo)
    run_id = run["run_id"]
    assert repo.record_event(run_id, "wrong-owner", "node_started", {"node": "agent"}) is None
    private = repo.record_event(run_id, "test-owner", "model_interaction", {"input": "secret"}, public=False, model_visible=True)
    started = repo.record_event(run_id, "test-owner", "node_started", {"node": "agent", "model_trace": "secret"})
    events = repo.list_events(run_id)
    assert private["sequence_no"] not in [event["sequence_no"] for event in events]
    assert events[-1]["payload"] == {"run_id": run_id, "node": "agent"}
    assert [event["sequence_no"] for event in events] == sorted(event["sequence_no"] for event in events)
    assert repo.list_events(run_id, after=started["sequence_no"] - 1) == [events[-1]]
    assert_code("invalid_event", lambda: repo.record_event(run_id, "test-owner", "model_interaction", {"input": "secret"}))


def test_nested_private_audit_is_excluded_from_public_stream_and_snapshot(repo, delivery_dsn):
    run, _ = admit(repo)
    run_id = run["run_id"]
    business = {"gmv": 42.5, "rows": [{"sku": "SKU-1", "amount": 42.5}], "sql": "SELECT " + "business_column," * 5000}
    audit = {"messages": [{"role": "system", "content": "private"}], "system": "private",
             "user": "private", "output": "private",
             "model_input": {"user": "private"}, "model_traces": [{"input": "private"}],
             "api_key": "private", "accessToken": "private"}
    evidence = repo.record_event(run_id, "test-owner", "evidence", {"items": [
        {"id": "sql:1", "text": "SQL verified", **audit},
        {"sql": business["sql"], "data": {"gmv": 42.5, **audit}},
    ]})
    # 升级前已经持久化的公开事件也必须在回放时投影，不修改 append-only 历史。
    with psycopg.connect(delivery_dsn) as conn:
        import_module("app.storage.delivery_repository").append_run_event(
            conn, run_id=UUID(run_id), event_type="public_evidence",
            payload={"items": [{"text": "historical evidence", **audit}]})
    result = {"final_answer": "done", "node_result": {"task": "metric", "data": {**business, "nested": audit},
                                                          "evidence": [{"id": "sql:1", "text": "SQL verified", **audit}], **audit},
              "structured_result": {"schema_version": 1, "summary": "done", "kind": "metric", **audit,
                                    "metrics": [{"key": "gmv", "value": 42.5, "label": "GMV", "unit": "CNY", **audit}],
                                    "evidence": [{"id": "sql:1", "text": "SQL verified", **audit}],
                                    "experiment": {"success_threshold": 1.5, **audit}}}
    finished = repo.finish(run_id, "test-owner", result=result)
    public = {"event": evidence, "finished": finished, "replayed": repo.list_events(run_id), "snapshot": repo.get_run(run_id)}
    import json
    assert "private" not in json.dumps(public)
    assert evidence["payload"]["items"][0] == {"id": "sql:1", "text": "SQL verified"}
    assert isinstance(evidence["payload"]["items"][1], str)
    assert finished["node_result"]["data"]["rows"] == business["rows"]
    assert finished["node_result"]["data"]["sql"] == business["sql"]
    assert finished["node_result"]["evidence"] == [{"id": "sql:1", "text": "SQL verified"}]
    assert finished["structured_result"]["metrics"] == [{"key": "gmv", "value": 42.5, "label": "GMV", "unit": "CNY"}]
    with psycopg.connect(delivery_dsn) as conn:
        stored = conn.execute("SELECT result_json FROM run_records WHERE run_id = %s", (run_id,)).fetchone()[0]
        assert stored["node_result"]["model_input"] == {"user": "private"}, "private canonical evidence must remain auditable"


def test_deadline_recovery_and_late_results_cannot_create_memory(repo, delivery_dsn):
    run, _ = admit(repo)
    with psycopg.connect(delivery_dsn) as conn:
        conn.execute("UPDATE run_records SET deadline_at = clock_timestamp() - interval '1 second' WHERE run_id = %s", (run["run_id"],))
    result = {"final_answer": "late", "memory_candidates": [candidate()]}
    assert repo.finish(run["run_id"], "test-owner", result=result) is None
    assert repo.record_event(run["run_id"], "test-owner", "node_completed", {"node": "agent"}) is None
    failed = repo.finish(run["run_id"], "test-owner", error={"code": "run_timeout", "message": "deadline"})
    assert failed["status"] == "failed"
    assert not repo.list_memories()["items"]
    next_run, _ = admit(repo)
    assert repo.recover_interrupted("replacement-owner") == 1
    assert repo.get_run(next_run["run_id"])["error"]["code"] == "server_restarted"
    assert repo.finish(next_run["run_id"], "test-owner", result=result) is None
    assert repo.recover_interrupted("replacement-owner") == 0


def test_restart_recovers_unowned_legacy_nonterminal_only_in_current_merchant(repo, delivery_dsn):
    tid = thread(repo)
    owned, _ = admit(repo, thread_id=tid)
    historical = {status: (str(uuid4()), str(uuid4())) for status in ("queued", "running", "completed", "failed")}
    other = import_module("app.storage.delivery_repository").DeliveryRepository(delivery_dsn, merchant_id=f"other-{uuid4()}")
    other_tid, other_run = thread(other), str(uuid4())
    with psycopg.connect(delivery_dsn) as conn:
        for status, (run_id, key) in historical.items():
            conn.execute("""INSERT INTO run_records (run_id,thread_id,merchant_id,idempotency_key,status,request_json,result_json)
                         VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                         (run_id, tid, repo.merchant_id, key, status, '{"query":"legacy"}', '{"final_answer":"historical result"}'))
        conn.execute("""INSERT INTO run_records (run_id,thread_id,merchant_id,idempotency_key,status,request_json)
                     VALUES (%s,%s,%s,%s,'running','{"query":"other"}'::jsonb)""",
                     (other_run, other_tid, other.merchant_id, str(uuid4())))
    assert repo.recover_interrupted("test-owner") == 2
    for status in ("queued", "running"):
        run_id, key = historical[status]
        recovered = repo.lookup_run(idempotency_key=key, thread_id=tid, request={"query": "legacy"})
        assert recovered["status"] == "failed" and recovered["error"]["code"] == "server_restarted"
        assert [event["event_type"] for event in repo.list_events(run_id)] == ["error", "done"]
    assert repo.get_run(owned["run_id"])["status"] == "running"
    assert other.get_run(other_run)["status"] == "running"
    with psycopg.connect(delivery_dsn) as conn:
        for status in ("completed", "failed"):
            run_id, _ = historical[status]
            assert conn.execute("SELECT status,result_json FROM run_records WHERE run_id=%s", (run_id,)).fetchone() == (
                status, {"final_answer": "historical result"})
            assert conn.execute("SELECT count(*) FROM run_events WHERE run_id=%s", (run_id,)).fetchone()[0] == 0
    assert repo.recover_interrupted("test-owner") == 0


def test_terminal_event_failure_rolls_back_memory_and_result(repo, delivery_dsn, monkeypatch):
    run, _ = admit(repo)
    original = repo._append_public

    def fail_done(conn, run_id, event_type, payload):
        if event_type == "done":
            raise RuntimeError("injected transaction interruption")
        return original(conn, run_id, event_type, payload)

    monkeypatch.setattr(repo, "_append_public", fail_done)
    with pytest.raises(RuntimeError, match="interruption"):
        repo.finish(run["run_id"], "test-owner", result={"final_answer": "done", "memory_candidates": [candidate()]})
    assert repo.get_run(run["run_id"])["status"] == "running"
    assert not repo.list_memories()["items"]
    assert not any(event["event_type"] == "final" for event in repo.list_events(run["run_id"]))
    monkeypatch.setattr(repo, "_append_public", original)


def test_memory_confirmation_is_versioned_idempotent_and_audited(repo, delivery_dsn):
    _, memory = finish_with_memory(repo)
    assert memory["status"] == "pending" and memory["index_status"] == "pending"
    key = str(uuid4())
    confirmed = repo.decide_memory(memory["memory_id"], approved=True, expected_version=1, idempotency_key=key)
    assert confirmed["status"] == "active" and confirmed["version"] == 2
    assert confirmed["fact_type"] == "inference" and confirmed["source_type"] == "llm"
    assert confirmed["index_status"] == "pending"
    assert repo.decide_memory(memory["memory_id"], approved=True, expected_version=1, idempotency_key=key) == confirmed
    assert_code("version_conflict", lambda: repo.decide_memory(memory["memory_id"], approved=False, expected_version=1, idempotency_key=str(uuid4())))
    with psycopg.connect(delivery_dsn) as conn:
        events = conn.execute("SELECT event_kind, source_type FROM memory_events WHERE merchant_id = %s ORDER BY created_at", (repo.merchant_id,)).fetchall()
        assert events == [("episodic", "llm"), ("confirmation", "user_approved")]
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("UPDATE memory_events SET value_json = '{}' WHERE merchant_id = %s", (repo.merchant_id,))


def test_confirmation_supersedes_conflicting_fact_and_keeps_decision_unexecuted(repo):
    _, first = finish_with_memory(repo, source_type="user", fact_type="user_fact")
    _, second = finish_with_memory(repo)
    repo.decide_memory(second["memory_id"], approved=True, expected_version=1, idempotency_key=str(uuid4()))
    assert repo.get_memory(first["memory_id"])["status"] == "superseded"
    assert_code("invalid_memory_state", lambda: repo.decide_memory(first["memory_id"], approved=True, expected_version=2, idempotency_key=str(uuid4())))
    _, decision = finish_with_memory(repo, predicate="experiment", kind="decision", fact_type="decision", value={"execution_status": "proposed"})
    confirmed = repo.decide_memory(decision["memory_id"], approved=True, expected_version=1, idempotency_key=str(uuid4()))
    assert confirmed["fact_type"] == "decision" and confirmed["value"]["execution_status"] == "proposed"


def test_expired_memory_and_cross_merchant_access_are_rejected(repo):
    past = datetime.now(timezone.utc) - timedelta(days=2)
    _, memory = finish_with_memory(repo, effective_from=past.isoformat(), effective_to=(past + timedelta(days=1)).isoformat())
    assert_code("invalid_memory_state", lambda: repo.decide_memory(memory["memory_id"], approved=True, expected_version=1, idempotency_key=str(uuid4())))
    module = import_module("app.storage.delivery_repository")
    other = module.DeliveryRepository(repo.dsn, merchant_id="another-merchant")
    assert_code("not_found", lambda: other.get_memory(memory["memory_id"]))
    run = repo.list_runs()["items"][0]
    assert_code("not_found", lambda: other.get_run(run["run_id"]))
    assert_code("not_found", lambda: other.list_events(run["run_id"]))


def test_pagination_has_no_duplicates_and_legacy_idempotency_is_preserved(repo, delivery_dsn):
    legacy_key, legacy_id = uuid4(), uuid4()
    with psycopg.connect(delivery_dsn) as conn:
        conn.execute("INSERT INTO threads(thread_id,merchant_id,idempotency_key) VALUES (%s,%s,%s)", (legacy_id, repo.merchant_id, legacy_key))
    assert repo.create_thread(idempotency_key=str(legacy_key))["thread_id"] == str(legacy_id)
    for _ in range(3):
        run, _ = admit(repo, str(legacy_id))
        repo.finish(run["run_id"], "test-owner", result={"final_answer": "done", "structured_result": {"summary": "typed"}})
    first = repo.list_runs(limit=2)
    second = repo.list_runs(limit=2, cursor=first["next_cursor"])
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert len({item["run_id"] for item in first["items"] + second["items"]}) == 3
    assert all(item["structured_result"] == {"summary": "typed"} for item in first["items"])


def test_feedback_idempotency_rejects_changed_payload(repo):
    run, _ = admit(repo)
    key = str(uuid4())
    assert repo.record_feedback(run["run_id"], feedback={"score": 4}, idempotency_key=key)["accepted"]
    assert_code("idempotency_conflict", lambda: repo.record_feedback(run["run_id"], feedback={"score": 5}, idempotency_key=key))


def test_deadline_expiring_during_terminal_transaction_rolls_back_candidates(repo, monkeypatch):
    run, _ = admit(repo, timeout_seconds=0.15)
    original = repo._commit_learning

    def slow_commit(conn, row, result):
        original(conn, row, result)
        time.sleep(0.2)

    monkeypatch.setattr(repo, "_commit_learning", slow_commit)
    response = repo.finish(run["run_id"], "test-owner", result={"final_answer": "late", "memory_candidates": [candidate()]})
    assert response is None
    assert repo.get_run(run["run_id"])["status"] == "running"
    assert not repo.list_memories()["items"]
    assert not any(event["event_type"] in {"final", "done"} for event in repo.list_events(run["run_id"]))


def test_outcome_cannot_link_another_merchant_decision(repo):
    module = import_module("app.storage.delivery_repository")
    other = module.DeliveryRepository(repo.dsn, merchant_id=f"outcome-other-{uuid4()}")
    _, decision = finish_with_memory(other, predicate="executed", source_type="user_approved", kind="decision",
                                     fact_type="decision", value={"execution_status": "executed"})
    run, _ = admit(repo)
    outcome = candidate(kind="outcome", fact_type="outcome", source_type="sql", evidence_refs=["sql:outcome"],
                        value={"decision_memory_ids": [decision["memory_id"]], "metric": "gmv"})
    repo.finish(run["run_id"], "test-owner", result={"final_answer": "done", "memory_candidates": [outcome]})
    assert not repo.list_memories()["items"]


def test_malformed_candidate_is_retained_as_rejection_without_losing_good_candidate(repo):
    run, _ = admit(repo)
    repo.finish(run["run_id"], "test-owner", result={"final_answer": "done", "memory_candidates": [None, candidate()]})
    assert repo.get_run(run["run_id"])["status"] == "completed"
    assert len(repo.list_memories()["items"]) == 1


def test_unknown_memory_kind_is_audited_and_never_materialized(repo, delivery_dsn):
    run, _ = admit(repo)
    invalid = candidate(kind="semantic", source_type="user", fact_type="user_fact")
    valid = candidate(kind="core", predicate="valid_core", source_type="user", fact_type="user_fact")
    repo.finish(run["run_id"], "test-owner", result={"final_answer": "done", "memory_candidates": [invalid, valid]})
    memories = repo.list_memories()["items"]
    assert [memory["kind"] for memory in memories] == ["core"]
    with psycopg.connect(delivery_dsn) as conn:
        rejected = conn.execute("""SELECT payload_json FROM run_events
            WHERE run_id = %s AND event_type = 'memory_candidate_rejected'""", (run["run_id"],)).fetchall()
        assert any(row[0]["candidate_id"] == invalid["candidate_id"] for row in rejected)
        assert conn.execute("SELECT count(*) FROM memory_events WHERE run_id = %s AND source_ref = %s", (run["run_id"], invalid["candidate_id"])).fetchone()[0] == 0


def test_pending_approval_race_produces_one_receipt_and_one_event(repo, delivery_dsn):
    _, memory = finish_with_memory(repo)

    def decide(approved):
        try:
            return repo.decide_memory(memory["memory_id"], approved=approved, expected_version=1, idempotency_key=str(uuid4()))
        except import_module("app.storage.delivery_repository").DeliveryRepositoryError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(decide, [True, False]))
    assert sum(isinstance(value, dict) for value in responses) == 1
    assert "version_conflict" in responses
    with psycopg.connect(delivery_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM memory_events WHERE merchant_id = %s AND event_kind IN ('confirmation','rejection')", (repo.merchant_id,)).fetchone() == (1,)


def test_legacy_run_replays_exact_request_before_new_worker_admission(repo, delivery_dsn):
    thread_id, key, run_id = thread(repo), uuid4(), uuid4()
    with psycopg.connect(delivery_dsn) as conn:
        conn.execute("""INSERT INTO run_records(run_id,thread_id,merchant_id,idempotency_key,status,request_json,result_json)
            VALUES (%s,%s,%s,%s,'completed','{"query":"GMV"}','{"final_answer":"legacy"}')""", (run_id, thread_id, repo.merchant_id, key))
    response = repo.lookup_run(idempotency_key=str(key), thread_id=thread_id, request={"query": "GMV"})
    assert response["result"] == "legacy"
    admitted, created = admit(repo, thread_id, str(key), monthly_cap=0)
    assert not created and admitted["run_id"] == str(run_id)
    assert_code("idempotency_conflict", lambda: repo.lookup_run(idempotency_key=str(key), thread_id=thread_id, request={"query": "changed"}))


@pytest.mark.parametrize("read_method", ["get_run", "list_runs", "lookup_run"])
def test_run_snapshot_never_combines_old_status_with_new_terminal_cursor(repo, monkeypatch, read_method):
    key = str(uuid4())
    run, _ = admit(repo, key=key)
    observed_row, allow_cursor_read = threading.Event(), threading.Event()
    original = repo._run_response

    def pause_between_row_and_cursor(conn, row):
        if threading.current_thread().name.startswith("snapshot-reader"):
            observed_row.set()
            assert allow_cursor_read.wait(3), "writer did not release snapshot reader"
        return original(conn, row)

    monkeypatch.setattr(repo, "_run_response", pause_between_row_and_cursor)

    def read():
        if read_method == "list_runs":
            return repo.list_runs()["items"][0]
        if read_method == "lookup_run":
            return repo.lookup_run(idempotency_key=key, thread_id=run["thread_id"], request={"query": "GMV"})
        return repo.get_run(run["run_id"])

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot-reader") as pool:
        future = pool.submit(read)
        try:
            assert observed_row.wait(3), "reader did not observe the initial row"
            finished = repo.finish(run["run_id"], "test-owner", result={"final_answer": "completed concurrently"})
            assert finished["last_event_id"] > run["last_event_id"]
        finally:
            allow_cursor_read.set()
        snapshot = future.result(timeout=3)
    assert snapshot["status"] == "running"
    assert snapshot["last_event_id"] == run["last_event_id"], "old status carried the future done cursor"
