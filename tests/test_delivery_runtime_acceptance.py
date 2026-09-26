"""Cross-boundary runtime acceptance in a disposable DB, without paid models.

Uses the existing HTTP fixture's separately created PostgreSQL database; never
connects to the running demonstration API or modifies its merchant records.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import psycopg
import pytest

from app.agent.context import RunContext
from app.agent.runtime import run_query
from app.llm.client import LLMClient, observe_llm
from app.storage.database import checkpointer_context
from app.storage.run_event_repository import replay_model_context
from test_delivery_api import api, api_dsn, headers, thread  # noqa: F401 -- fixture reuse


class Vector(list):
    def tolist(self):
        return list(self)


def test_http_approval_retries_index_and_next_recall_injects_original_fact(api, monkeypatch):
    import app.agent.graph_v2 as graph
    client, service = api
    tid = thread(client)
    run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "GMV"}).json()
    service.executor.finish({"final_answer": "pending", "node_result": {}, "memory_candidates": [{
        "candidate_id": str(uuid4()), "subject": "merchant", "predicate": "delivery-budget-" + uuid4().hex,
        "value": "预算不得增加；单场上限1000元", "source_type": "llm", "fact_type": "user_fact",
        "kind": "core", "schema_version": 3, "scope_type": "merchant", "thread_id": tid,
    }]})
    pending = client.get("/v1/memories?status=pending", headers=headers()).json()["items"][0]
    response = client.post(f"/v1/memories/{pending['memory_id']}/approve", headers=headers(),
                           json={"expected_version": pending["version"]})
    assert response.status_code == 200
    approved = response.json()
    assert approved["status"] == "active" and approved["index_status"] == "pending"
    assert approved["source_type"] == "llm" and approved["fact_type"] == "user_fact"
    monkeypatch.setenv("DATABASE_URL", service.dsn)
    fault = {"enabled": True}
    def encode(text, **kwargs):
        if fault["enabled"] and "预算不得增加" in text:
            raise RuntimeError("injected indexing outage")
        return Vector([1.0] + [0.0] * 1023)
    monkeypatch.setattr("app.rag.indexer.encode_with_shared_embedder", encode)
    state = {"user_query": "给出GMV经营策略建议", "intent": "strategy", "merchant_id": service.merchant_id,
             "thread_id": tid}
    failed_index_recall = graph._recall(state)
    assert approved["memory_id"] not in failed_index_recall["memory_usage_trace"]["injected"]
    preserved = service.repo.get_memory(approved["memory_id"])
    assert preserved["status"] == "active" and preserved["index_status"] == "pending"
    assert preserved["source_event_id"] == pending["source_event_id"]
    fault["enabled"] = False
    recalled = graph._recall(state)
    assert approved["memory_id"] in recalled["memory_usage_trace"]["injected"]
    row = next(item for item in recalled["recalled_memories"] if item["memory_id"] == approved["memory_id"])
    assert row["source_event_id"] == pending["source_event_id"]
    indexed = service.repo.get_memory(approved["memory_id"])
    assert indexed["index_status"] == "indexed" and indexed["version"] == approved["version"]
    with psycopg.connect(service.dsn) as conn:
        assert conn.execute("SELECT count(*) FROM memory_events WHERE run_id = %s AND event_kind = 'confirmation'",
                            (run["run_id"],)).fetchone()[0] == 1


def test_failed_postgres_checkpoint_does_not_seed_next_run_of_same_thread(api, monkeypatch):
    import app.agent.graph_v2 as graph
    client, service = api
    tid = thread(client)
    owner = "checkpoint-acceptance"
    first, _ = service.repo.admit_run(thread_id=tid, request={"query": "first"},
                                      idempotency_key=str(uuid4()), owner=owner)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    incoming = []
    def recall(state):
        incoming.append(dict(state))
        return {"recalled_memories": [{"memory_id": "uncommitted-poison"}] if state["user_query"] == "first" else []}
    def execute(state):
        if state["user_query"] == "first":
            raise RuntimeError("injected failure after checkpoint")
        return {"node_result": {"task": "metric", "headline": "clean", "data": {}, "evidence": ["sql:clean"]},
                "action_results": [{"status": "ok", "evidence": ["sql:clean"]}]}
    monkeypatch.setattr(graph, "_recall", recall)
    monkeypatch.setattr(graph, "_execute", execute)
    overrides = {"disable_skill": True, "disable_memory_candidates": True}
    with checkpointer_context(service.dsn) as saver:
        compiled = graph.build_graph_v2(saver)
        with pytest.raises(RuntimeError, match="injected failure"):
            run_query("first", graph=compiled, checkpoint_id=first["run_id"],
                      run_context=RunContext(run_id=first["run_id"], thread_id=tid),
                      state_overrides=overrides, event_callback=lambda *a, **k: None, max_actions=3)
        partial = compiled.get_state({"configurable": {"thread_id": first["run_id"]}}).values
        assert partial["recalled_memories"] == [{"memory_id": "uncommitted-poison"}]
        service.repo.finish(first["run_id"], owner, error={"code": "agent_failure"})
        second, _ = service.repo.admit_run(thread_id=tid, request={"query": "second"},
                                          idempotency_key=str(uuid4()), owner=owner)
        result = run_query("second", graph=compiled, checkpoint_id=second["run_id"],
                           run_context=RunContext(run_id=second["run_id"], thread_id=tid),
                           state_overrides=overrides, event_callback=lambda *a, **k: None, max_actions=3)
        assert "uncommitted-poison" not in json.dumps(incoming[-1])
        assert compiled.get_state({"configurable": {"thread_id": tid}}).values == {}
        service.repo.finish(second["run_id"], owner, result=result)
    assert service.repo.get_run(first["run_id"])["status"] == "failed"
    assert service.repo.get_run(second["run_id"])["status"] == "completed"


def test_actual_model_wire_input_is_durable_before_network_and_rebuilds_after_failure(api, monkeypatch):
    client, service = api
    tid = thread(client)
    run = client.post(f"/v1/threads/{tid}/runs", headers=headers(), json={"query": "current"}).json()
    job = service.executor.jobs[-1]
    actual_payloads = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}'
    def fake_network(request, timeout):
        actual = json.loads(request.data)
        # Independent connection proves the callback committed before networking.
        with psycopg.connect(service.dsn) as conn:
            before = [item for item in replay_model_context(conn, UUID(run["run_id"]))
                      if item["event_type"] == "before_llm"]
        assert len(before) == 1
        payload = before[0]["payload"]
        rebuilt = {"model": payload["model"], "messages": payload["messages"],
                   "temperature": payload["temperature"], "max_tokens": payload["max_tokens"],
                   "thinking": {"type": "enabled" if payload["thinking"] else "disabled"},
                   "response_format": {"type": "json_object"}}
        assert rebuilt == actual
        actual_payloads.append(actual)
        return Response()
    monkeypatch.setattr("app.llm.client._urlopen", fake_network)
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    with observe_llm(lambda kind, payload, **kwargs: service.on_event(job, kind, payload, **kwargs),
                     max_tokens=128, completed_context=[{"run_id": "previous", "status": "completed",
                                                        "query": "last", "result": "reference-only"}]):
        LLMClient("deepseek", "fake-secret-not-written", "https://example.test", "deepseek-v4-flash").complete(
            "system-boundary", "current-query", thinking=False, json_schema=schema)
    service.on_failure(job, {"code": "agent_failure"})
    with psycopg.connect(service.dsn) as conn:
        events = replay_model_context(conn, UUID(run["run_id"]))
    before = next(item["payload"] for item in events if item["event_type"] == "before_llm")
    after = next(item["payload"] for item in events if item["event_type"] == "after_llm")
    assert before["messages"] == actual_payloads[0]["messages"]
    assert before["call_id"] == after["call_id"]
    assert after["output"] == "ok" and after["usage"]["total_tokens"] == 5
    assert "fake-secret-not-written" not in json.dumps(events, default=str)
    assert service.repo.get_run(run["run_id"])["status"] == "failed"


def test_real_graph_replan_counts_all_actions_and_stops_at_three(monkeypatch):
    import app.agent.graph_v2 as graph
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    calls, events = [], []
    def attribution(state):
        calls.append(state["time_window"])
        return {"node_result": {"task": "attribution", "headline": "no evidence", "data": {}, "evidence": []}}
    monkeypatch.setattr(graph, "attribution", attribution)
    result = run_query("对比2026-04-02和2026-04-17 GMV暴跌原因", graph=graph.build_graph_v2(),
                       run_context=RunContext(thread_id="replan-check"), checkpoint_id=str(uuid4()),
                       state_overrides={"disable_memory_recall": True, "disable_skill": True,
                                        "disable_memory_candidates": True},
                       event_callback=lambda kind, payload, **kwargs: events.append((kind, payload)), max_actions=3)
    assert len(calls) == 3
    assert [payload["action_index"] for kind, payload in events if kind == "tool_call"] == [0, 1, 2]
    assert [payload["replan_count"] for kind, payload in events if kind == "compiled_plan"] == [0, 1]
    assert result["evidence_verification"]["replan_count"] == 1
    assert not result["evidence_verification"]["will_replan"]
    assert result["action_results"][-1]["reason"] == "action_budget_exhausted"
