from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from app.agent.context import RunContext
from app.api.main import PostgresRuntime
from app.memory.policy import MemoryCandidate
from app.skills.models import SkillContract
from app.skills.evolution import PairedMetrics
from app.skills.evolution_engine import EvolutionEngine
from app.skills.registry import LoadedSkill
from app.storage.database import apply_migrations
from app.storage.memory_repository import append_event, create_or_get_run, materialize_fact
from app.storage.run_event_repository import append_run_event, list_run_events, replay_model_context
from app.storage.skill_repository import register_skill_version, promote_skill, rollback_skill

DSN = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="requires native PostgreSQL 15 + pgvector")


def _run(merchant: str) -> UUID:
    with psycopg.connect(DSN) as conn:
        row = create_or_get_run(
            conn, thread_id=f"thread-{uuid4()}", merchant_id=merchant,
            idempotency_key=uuid4(), request={"test": "v3"},
        )
        conn.commit()
    return UUID(row["run_id"])


def test_run_event_sequence_is_unique_concurrent_and_payload_is_immutable():
    apply_migrations()
    run_id = _run("event-merchant")

    def write(index: int):
        with psycopg.connect(DSN) as conn:
            event_id = append_run_event(
                conn, run_id=run_id, event_type="model_context",
                payload={"index": index}, model_visible=True,
            )
            conn.commit()
            return event_id

    with ThreadPoolExecutor(max_workers=12) as pool:
        event_ids = list(pool.map(write, range(24)))
    with psycopg.connect(DSN) as conn:
        events = list_run_events(conn, run_id)
        assert [event["sequence_no"] for event in events] == list(range(1, 25))
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            with conn.cursor() as cur:
                cur.execute("UPDATE run_events SET payload_json = '{}' WHERE event_id = %s", (event_ids[0]["event_id"],))


def test_runtime_boundary_commits_graph_candidate_and_replays_model_visible_inputs(monkeypatch):
    merchant = f"runtime-boundary-{uuid4()}"
    run_id = _run(merchant)
    context = RunContext(
        run_id=str(run_id), thread_id=f"thread-{uuid4()}", merchant_id=merchant,
        dataset_partition="integration", evaluation_arm="canonical",
    )
    monkeypatch.setattr(
        "app.rag.indexer.encode_with_shared_embedder",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected index outage")),
    )
    result = {
        "recalled_memories": [{"memory_id": "m-visible", "content": "visible context"}],
        "memory_usage_trace": {"recalled_ids": ["m-visible"], "used_ids": ["m-visible"]},
        "selected_skill": {"id": "anomaly-root-cause", "version": "2.0.0-e1"},
        "skill_selection_trace": {"selected_id": "anomaly-root-cause"},
        "action_sequence": ["metric"],
        "action_results": [{"action": "metric", "evidence": ["sql:metric"]}],
        "evidence_verification": {"passed": True},
        "node_result": {"evidence": ["sql:metric"], "data": {}},
        "memory_candidates": [{
            "candidate_id": "graph-candidate-1", "subject": "merchant",
            "predicate": "preferred_window", "value": "evening", "source_type": "user",
            "fact_type": "user_fact", "thread_id": context.thread_id,
            "scope_type": "merchant", "schema_version": 3,
        }],
        "final_answer": "deterministic final",
    }
    model_trace = {
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "input": {"system": "bounded schema", "user": "visible request"},
        "output": {"structured": {"diagnosis": "ok"}},
    }

    PostgresRuntime(DSN)._persist_learning(context, result, model_traces=[model_trace])

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT fact_type, status, value_json #>> '{}'
                     FROM memory_facts WHERE merchant_id = %s AND predicate = 'preferred_window'""",
                (merchant,),
            )
            assert cur.fetchone() == ("user_fact", "active", "evening")
            cur.execute(
                """SELECT index_status FROM memory_events
                     WHERE merchant_id = %s AND source_ref = 'graph-candidate-1'""",
                (merchant,),
            )
            assert cur.fetchone() == ("pending",)
        visible = replay_model_context(conn, run_id)
        assert [event["event_type"] for event in visible] == ["model_interaction", "memory_context"]
        assert visible[0]["payload"]["input"]["user"] == "visible request"
        assert visible[1]["payload"]["items"][0]["memory_id"] == "m-visible"


def test_nonoverlapping_temporal_facts_coexist_and_overlap_supersedes_only_conflict():
    merchant = f"temporal-{uuid4()}"
    run_id = _run(merchant)
    ranges = [
        (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc)),
        (datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 4, 1, tzinfo=timezone.utc)),
        (datetime(2026, 3, 15, tzinfo=timezone.utc), datetime(2026, 3, 20, tzinfo=timezone.utc)),
    ]
    with psycopg.connect(DSN) as conn:
        for index, (start, end) in enumerate(ranges):
            candidate = MemoryCandidate(
                f"temporal-{index}", "merchant", "campaign_gmv", str(index), "sql",
                fact_type="observation", evidence_refs=(f"sql:{index}",), schema_version=3,
                effective_from=start, effective_to=end,
            )
            event = append_event(conn, run_id=run_id, merchant_id=merchant,
                                 candidate=candidate, source_ref=candidate.candidate_id)
            materialize_fact(conn, source_event_id=event, merchant_id=merchant,
                             candidate=candidate, content=str(index))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT value_json #>> '{}', status FROM memory_facts
                    WHERE merchant_id = %s ORDER BY effective_from""", (merchant,),
            )
            assert cur.fetchall() == [("0", "active"), ("1", "superseded"), ("2", "active")]


def test_outcome_requires_and_links_an_executed_decision():
    merchant = f"outcome-{uuid4()}"
    run_id = _run(merchant)
    decision = MemoryCandidate(
        "decision", "merchant", "experiment", {"execution_status": "planned"}, "llm",
        fact_type="decision", schema_version=3,
    )
    with psycopg.connect(DSN) as conn:
        event = append_event(conn, run_id=run_id, merchant_id=merchant,
                             candidate=decision, source_ref=decision.candidate_id)
        decision_fact = materialize_fact(conn, source_event_id=event, merchant_id=merchant,
                                         candidate=decision, content="experiment")
        with conn.cursor() as cur:
            cur.execute("UPDATE memory_facts SET status = 'active' WHERE memory_id = %s", (decision_fact.memory_id,))
        conn.commit()
        bad_outcome = MemoryCandidate(
            "bad-outcome", "merchant", "experiment_result",
            {"decision_memory_ids": [decision_fact.memory_id], "success": True},
            "sql", fact_type="outcome", evidence_refs=("sql:outcome",), schema_version=3,
        )
        bad_event = append_event(conn, run_id=run_id, merchant_id=merchant,
                                 candidate=bad_outcome, source_ref=bad_outcome.candidate_id)
        with pytest.raises(ValueError, match="unexecuted"):
            materialize_fact(conn, source_event_id=bad_event, merchant_id=merchant,
                             candidate=bad_outcome, content="bad")
        conn.rollback()

    # The rejected transaction is replayed with an explicit execution transition.
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE memory_facts SET value_json = jsonb_set(value_json, '{execution_status}', '\"executed\"') "
                "WHERE memory_id = %s", (decision_fact.memory_id,),
            )
        good_outcome = MemoryCandidate(
            "good-outcome", "merchant", "experiment_result",
            {"decision_memory_ids": [decision_fact.memory_id], "success": True},
            "sql", fact_type="outcome", evidence_refs=("sql:outcome",), schema_version=3,
        )
        good_event = append_event(conn, run_id=run_id, merchant_id=merchant,
                                  candidate=good_outcome, source_ref=good_outcome.candidate_id)
        outcome = materialize_fact(conn, source_event_id=good_event, merchant_id=merchant,
                                   candidate=good_outcome, content="success")
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT relation FROM memory_links WHERE from_memory_id = %s AND to_memory_id = %s",
                (decision_fact.memory_id, outcome.memory_id),
            )
            assert cur.fetchone() == ("decision_outcome",)


def test_skill_promotion_and_rollback_switch_active_version_atomically():
    suffix = str(uuid4())
    skill_id = f"test-skill-{suffix}"
    base = {
        "id": skill_id, "version": "1.0.0", "description": "test",
        "task_types": ["metric"], "preconditions": [], "required_memory_types": [],
        "steps": [{"id": "one", "action": "metric", "arguments": {}}],
        "evidence_contract": [{"step": "one", "path": "evidence", "operator": "exists"}],
        "completion_criteria": [], "failure_policy": "stop", "allowed_tools": ["metric"],
        "parent_version": None, "source_trace_ids": [],
    }
    child = {**base, "version": "1.1.0", "parent_version": "1.0.0", "description": "candidate"}
    with psycopg.connect(DSN) as conn:
        register_skill_version(conn, LoadedSkill(SkillContract.from_dict(base), "base", f"hash-{suffix}-1"), status="active")
        register_skill_version(conn, LoadedSkill(SkillContract.from_dict(child), "child", f"hash-{suffix}-2"), status="candidate")
        promote_skill(conn, skill_id=skill_id, version="1.1.0", metrics={"delta": 0.1})
        conn.commit()
        rollback_skill(conn, skill_id=skill_id, bad_version="1.1.0", reason="injected regression")
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM skill_versions WHERE skill_id = %s AND status = 'active'", (skill_id,))
            assert cur.fetchone() == ("1.0.0",)
            cur.execute(
                "UPDATE skill_versions SET status = 'archived' WHERE skill_id = %s AND status = 'active'",
                (skill_id,),
            )
        conn.commit()


def test_offline_evolution_records_rejection_then_automatic_promotion():
    suffix = str(uuid4())
    skill_id = f"evolution-{suffix}"
    payload = {
        "id": skill_id, "version": "1.0.0", "description": "baseline",
        "task_types": ["metric"], "preconditions": [], "required_memory_types": [],
        "steps": [{"id": "one", "action": "metric", "arguments": {}}],
        "evidence_contract": [{"step": "one", "path": "evidence", "operator": "exists"}],
        "completion_criteria": [], "failure_policy": "stop", "allowed_tools": ["metric"],
        "parent_version": None, "source_trace_ids": [],
    }
    active = LoadedSkill(SkillContract.from_dict(payload), "instructions", f"active-{suffix}")
    rounds = {"count": 0}

    def generator(_contract, _failures):
        rounds["count"] += 1
        return ([{"op": "replace", "path": "/description", "value": f"candidate {rounds['count']}"}],
                {"round": rounds["count"]})

    def paired(active_rows, candidate_rows, *, active_calls=3.0, candidate_calls=3.0):
        n = len(active_rows)
        return PairedMetrics(
            tuple(active_rows), tuple(candidate_rows), (active_calls,) * n, (candidate_calls,) * n,
            (100.0,) * n, (100.0,) * n, (1.0,) * n, (1.0,) * n,
            1.0, 1.0, 0.0, 0.0,
        )

    def evaluator(candidate, partition):
        if partition == "regression":
            return paired([True] * 20, [True] * 20)
        if candidate.contract.version.endswith("e1"):
            return paired([False] * 30, [True] + [False] * 29)
        return paired([False] * 30, [True] * 10 + [False] * 20)

    failures = [{"trace_id": f"trace-{index}", "partition": "train"} for index in range(5)]
    with psycopg.connect(DSN) as conn:
        register_skill_version(conn, active, status="active")
        conn.commit()
        result = EvolutionEngine(conn, generator, evaluator).run(active, failures, max_rounds=2)
        assert result["status"] == "promoted"
        assert [row["promote"] for row in result["attempts"]] == [False, True]
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, count(*) FROM skill_events WHERE skill_id = %s GROUP BY event_type",
                (skill_id,),
            )
            counts = dict(cur.fetchall())
        assert counts == {"generated": 2, "promoted": 1, "rejected": 1}
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE skill_versions SET status = 'archived' WHERE skill_id = %s AND status = 'active'",
                (skill_id,),
            )
        conn.commit()
