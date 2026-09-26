"""Delivery-only instrumentation preserves old invocation semantics."""
import json

import pytest

from app.agent.context import RunContext
from app.agent.runtime import run_query
from app.llm.client import LLMClient, observe_llm


def test_default_invocation_uses_legacy_invoke_and_business_thread():
    class Graph:
        def invoke(self, initial, config):
            assert config["configurable"]["thread_id"] == "business"
            return {"final_answer": "legacy"}
    assert run_query("q", graph=Graph(), thread_id="business")["final_answer"] == "legacy"


def test_delivery_stream_uses_run_checkpoint_with_business_thread_in_state():
    class Graph:
        def stream(self, initial, config, stream_mode):
            assert stream_mode == "updates"
            assert config["configurable"]["thread_id"] == "run-isolated"
            assert initial["thread_id"] == "business"
            yield {"router": {"steps": [{"node": "Router"}]}}
            yield {"insight": {"steps": [{"node": "Insight"}], "final_answer": "ok"}}
    result = run_query("q", graph=Graph(), run_context=RunContext(thread_id="business"),
                       checkpoint_id="run-isolated", event_callback=lambda *a: None)
    assert len(result["steps"]) == 2
    assert result["final_answer"] == "ok"


def test_llm_ack_precedes_network_and_usage_has_same_call_id(monkeypatch):
    order, events = [], []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}],
                               "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}).encode()
    def network(request, timeout):
        order.append("network")
        assert json.loads(request.data)["max_tokens"] == 99
        return Response()
    def emit(kind, payload, model_visible=False):
        order.append(kind)
        events.append((kind, payload, model_visible))
    monkeypatch.setattr("app.llm.client._urlopen", network)
    with observe_llm(emit, max_tokens=99):
        LLMClient("deepseek", "not-real", "https://example.test", "deepseek-v4-flash").complete("sys", "你好")
    assert order == ["before_llm", "network", "after_llm"]
    assert events[0][1]["call_id"] == events[1][1]["call_id"]
    assert events[0][1]["system"] == "sys" and events[0][2]
    assert events[1][1]["usage"]["total_tokens"] == 5


def test_rejected_llm_event_cannot_make_network_request(monkeypatch):
    def reject(*args, **kwargs): raise RuntimeError("budget denied")
    def network(*args, **kwargs): pytest.fail("network must follow durable ACK")
    monkeypatch.setattr("app.llm.client._urlopen", network)
    with observe_llm(reject), pytest.raises(RuntimeError, match="budget denied"):
        LLMClient("deepseek", "fake", "https://example.test", "deepseek-v4-flash").complete("sys", "q")


def test_llm_network_failure_is_recorded_for_reserved_budget(monkeypatch):
    events = []
    def network(*args, **kwargs): raise OSError("offline")
    monkeypatch.setattr("app.llm.client._urlopen", network)
    with observe_llm(lambda kind, payload, **k: events.append((kind, payload))), pytest.raises(OSError):
        LLMClient("deepseek", "fake", "https://example.test", "deepseek-v4-flash").complete("sys", "q")
    assert events[-1][0] == "after_llm"
    assert events[-1][1]["error"] == "OSError"


def test_delivery_action_limit_applies_across_replans(monkeypatch):
    import app.agent.graph_v2 as graph
    from app.agent.planning import Action, Plan
    calls, events = [], []
    def fail(state):
        calls.append(state)
        return {"node_result": {"task": "metric", "evidence": []}, "steps": []}
    monkeypatch.setattr(graph, "metric_query", fail)
    state = {"plan": Plan((Action("metric", {}), Action("metric", {}))), "intent": "metric"}
    with graph.observe_graph(lambda kind, payload, **k: events.append(kind), max_actions=3):
        graph._execute(state)
        result = graph._execute(state)
    assert len(calls) == 3
    assert result["action_results"][-1]["reason"] == "action_budget_exhausted"
    assert events.count("tool_call") == 3


def test_delivery_context_controls_planner_dates_without_duplicates():
    import app.agent.graph_v2 as graph
    events = []
    state = {"user_query": "对比2026-04-17和2026-04-17暴跌原因", "intent": "attribution"}
    with graph.observe_graph(lambda *a, **k: events.append(a), analysis_context={
        "metric": "gmv", "start_date": "2026-04-02", "end_date": "2026-04-02",
    }):
        result = graph._observed_node("planner", graph._plan)(state)
    assert len(result["plan"].actions) == 1
    assert state["user_query"] == "对比2026-04-17和2026-04-17暴跌原因"


def test_delivery_metric_uses_explicit_window_and_metric(monkeypatch):
    import app.agent.graph_v2 as graph
    import app.agent.nodes.metric_query  # Bind the existing node import before patching the shared service.
    observed = []
    def tool(name, **args):
        observed.append((name, args))
        return {"headline": "gmv", "data": {}, "evidence": ["sql"]}
    monkeypatch.setattr("app.tools.client.call_tool", tool)
    with graph.observe_graph(lambda *a, **k: None, analysis_context={
        "metric": "gmv", "start_date": "2026-04-02", "end_date": "2026-04-02",
    }):
        graph.metric_query({"user_query": "对比2026-03月和2026-04月退款率", "time_window": {
            "start": "2026-04-02", "end": "2026-04-02",
        }})
    assert len(observed) == 1
    assert observed[0][1]["metric"] == "gmv"
    assert observed[0][1]["start_date"] == "2026-04-02"


def test_real_graph_reports_node_start_before_tool_and_checkpoint_isolated(monkeypatch):
    import app.agent.graph_v2 as graph
    from langgraph.checkpoint.memory import MemorySaver
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    observed = []
    def metric(state):
        observed.append("actual_tool")
        return {"node_result": {"task": "metric", "headline": "ok", "data": {}, "evidence": ["sql"]},
                "steps": [{"node": "MetricQuery"}]}
    monkeypatch.setattr(graph, "metric_query", metric)
    saver = MemorySaver()
    compiled = graph.build_graph_v2(saver)
    common = {"disable_skill": True, "disable_memory_recall": True, "disable_memory_candidates": True}
    result = run_query("GMV", graph=compiled, run_context=RunContext(thread_id="business"),
                       checkpoint_id="isolated-A", event_callback=lambda kind, p, **k: observed.append(kind),
                       state_overrides=common, max_actions=3)
    assert observed.index("node_started") < observed.index("tool_call") < observed.index("actual_tool")
    assert compiled.get_state({"configurable": {"thread_id": "business"}}).values == {}
    assert compiled.get_state({"configurable": {"thread_id": "isolated-B"}}).values == {}
    assert result["final_answer"]


def test_model_history_only_accepts_completed_context_and_preserves_current_query(monkeypatch):
    observed = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1}}'
    def network(request, timeout):
        observed.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr("app.llm.client._urlopen", network)
    history = [{"run_id": "bad", "status": "failed", "result": "never-use-this"},
               {"run_id": "ok", "status": "completed", "query": "prior", "result": "verified"}]
    with observe_llm(lambda *a, **k: None, completed_context=history):
        LLMClient("deepseek", "fake", "https://example.test", "deepseek-v4-flash").complete("sys", "current")
    assert observed[0]["messages"][-1]["content"] == "current"
    assert "verified" in observed[0]["messages"][1]["content"]
    assert "never-use-this" not in json.dumps(observed)


def test_delivery_extraction_schema_uses_existing_memory_partitions(monkeypatch):
    import app.memory.extractor as extractor
    import app.agent.graph_v2 as graph
    observed = []
    class FakeLLM:
        is_stub = False
        def complete_json(self, system, user, schema, **kwargs):
            observed.append(schema)
            return {"candidates": []}, None
    monkeypatch.setattr(extractor, "get_llm", lambda: FakeLLM())
    state = {"run_id": "delivery", "user_query": "不增加预算", "thread_id": "t", "merchant_id": "m"}
    with graph.observe_graph(lambda *a, **k: None, max_actions=3):
        graph._memory_candidate(state)
    assert observed[-1]["properties"]["candidates"]["items"]["properties"]["kind"]["enum"] == [
        "core", "episodic", "decision", "outcome"]
    graph._memory_candidate(state)
    assert "enum" not in observed[-1]["properties"]["candidates"]["items"]["properties"]["kind"]


def test_delivery_gate_rejects_unsupported_partition_without_changing_legacy(monkeypatch):
    import app.agent.graph_v2 as graph
    from app.memory.policy import MemoryCandidate
    candidate = MemoryCandidate("bad-kind", "merchant", "budget", "不增加预算", "user",
                                kind="semantic", fact_type="user_fact", schema_version=3)
    monkeypatch.setattr(graph, "extract_candidates", lambda *a, **k: [candidate])
    events = []
    with graph.observe_graph(lambda kind, payload, **k: events.append((kind, payload)), max_actions=3):
        result = graph._memory_candidate({"run_id": "r", "user_query": "不增加预算"})
    assert result["memory_candidates"] == []
    assert events == [("memory_candidate_rejected", {"candidate_id": "bad-kind", "reason": "unsupported_memory_kind"})]
    assert graph._memory_candidate({"run_id": "r", "user_query": "不增加预算"})["memory_candidates"][0]["kind"] == "semantic"
