from langgraph.checkpoint.memory import MemorySaver

import time

import app.agent.graph_v2 as graph_v2
from app.agent.graph_v2 import _after_verify, _execute, _execute_action, _memory_candidate, _plan, _verify, build_graph_v2
from app.agent.nodes.router import _rule_intent
from app.agent.planning import Action, Plan


def test_v2_graph_runs_bounded_metric_path(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    state = build_graph_v2().invoke({"user_query": "2026-04-02 GMV 怎么样"})
    assert [step["node"] for step in state["steps"]] == [
        "Router", "MemoryRecall", "Planner", "MetricQuery", "EvidenceVerifier", "Insight", "MemoryPolicyGate"
    ]
    assert len(state["plan"].actions) == 1
    assert state["verification"]["sufficient"]


def test_router_rule_covers_strategy_phrasings_when_llm_is_unavailable():
    assert _rule_intent("午场和晚场的排播节奏要怎么差异化?") == "strategy"
    assert _rule_intent("付费投流和自然流量在新品场上要怎么承接配比?") == "strategy"
    assert _rule_intent("直播里的话术节奏,怎么排?") == "strategy"
    assert _rule_intent("主推位选品上要避开哪些坑?") == "strategy"


def test_v2_graph_accepts_in_memory_checkpointer(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    graph = build_graph_v2(checkpointer=MemorySaver())
    result = graph.invoke({"user_query": "2026-04-02 GMV 怎么样"}, config={"configurable": {"thread_id": "t1"}})
    assert result["node_result"]["task"] == "metric"


def test_evidence_verifier_allows_exactly_one_replan():
    plan = Plan((Action("metric", {}),))
    first = _verify({"plan": plan, "node_result": {}})["verification"]
    assert first == {"sufficient": False, "replan_count": 1, "will_replan": True}
    assert _after_verify({"verification": first}) == "planner"
    second = _verify({"plan": Plan(plan.actions, replan_count=1), "node_result": {}})["verification"]
    assert second == {"sufficient": False, "replan_count": 1, "will_replan": False}
    assert _after_verify({"verification": second}) == "insight"


def test_cross_case_attribution_plan_has_two_bounded_actions():
    plan = _plan({
        "intent": "attribution",
        "user_query": "比较 2026-04-02 和 2026-04-17 的 GMV 暴跌原因",
    })["plan"]
    assert [action.arguments["anomaly_date"] for action in plan.actions] == ["2026-04-02", "2026-04-17"]
    assert len(plan.actions) == 2


def test_cross_case_attribution_plan_discards_a_third_date():
    plan = _plan({
        "intent": "attribution",
        "user_query": "比较 2026-04-02、2026-04-17 和 2026-04-20 的 GMV",
    })["plan"]
    assert len(plan.actions) == 2
    assert [action.arguments["anomaly_date"] for action in plan.actions] == ["2026-04-02", "2026-04-17"]


def test_attribution_action_scopes_its_time_window(monkeypatch):
    observed = {}

    def fake_attribution(state):
        observed.update(state["time_window"])
        return {"node_result": {"evidence": ["ok"]}}

    monkeypatch.setattr(graph_v2, "attribution", fake_attribution)
    _execute_action({}, Action("attribution", {"anomaly_date": "2026-04-02"}))
    assert observed == {"start": "2026-04-02", "end": "2026-04-02"}


def test_executor_returns_distinguishable_tool_failure(monkeypatch):
    monkeypatch.setattr(graph_v2, "metric_query", lambda _: (_ for _ in ()).throw(RuntimeError("broken")))
    state = {"intent": "metric", "plan": _plan({"intent": "metric", "user_query": "GMV"})["plan"],
             "run_started_monotonic": time.monotonic(), "user_query": "GMV"}
    result = _execute(state)
    assert result["action_results"][0]["reason"] == "tool_failure:RuntimeError"
    assert result["node_result"]["data"]["reason"] == "tool_failure:RuntimeError"


def test_executor_times_out_without_invoking_action(monkeypatch):
    invoked = []
    monkeypatch.setattr(graph_v2, "metric_query", lambda _: invoked.append(True))
    state = {"intent": "metric", "plan": _plan({"intent": "metric", "user_query": "GMV"})["plan"],
             "run_started_monotonic": time.monotonic() - graph_v2.MAX_RUN_SECONDS, "user_query": "GMV"}
    result = _execute(state)
    assert invoked == []
    assert result["node_result"]["data"]["reason"] == "agent_timeout"
    assert result["action_cursor"] == 1


def test_executor_combines_two_attribution_results(monkeypatch):
    def fake_attribution(state):
        date = state["time_window"]["end"]
        return {"node_result": {"task": "attribution", "headline": date,
                                "data": {"date": date}, "evidence": [date]}, "steps": []}

    monkeypatch.setattr(graph_v2, "attribution", fake_attribution)
    state = {"intent": "attribution", "user_query": "比较 2026-04-02 和 2026-04-17 的 GMV 暴跌原因",
             "run_started_monotonic": time.monotonic()}
    state["plan"] = _plan(state)["plan"]
    result = _execute(state)
    assert result["node_result"]["task"] == "attribution_comparison"
    assert [item["date"] for item in result["node_result"]["data"]["comparisons"]] == ["2026-04-02", "2026-04-17"]


def test_executor_rejects_an_action_without_evidence(monkeypatch):
    monkeypatch.setattr(graph_v2, "metric_query", lambda _: {"node_result": {"task": "metric", "evidence": []}, "steps": []})
    state = {"intent": "metric", "plan": Plan((Action("metric", {}),)),
             "run_started_monotonic": time.monotonic(), "user_query": "GMV"}
    result = _execute(state)
    assert result["action_results"][0]["status"] == "error"
    assert result["node_result"]["data"] == {"status": "evidence_insufficient", "reason": "empty_evidence"}


def test_evidence_verifier_accepts_a_successful_action_without_replan():
    verification = _verify({"plan": Plan((Action("metric", {}),)),
                            "action_results": [{"status": "ok", "evidence": ["source"]}]})["verification"]
    assert verification == {"sufficient": True, "replan_count": 0, "will_replan": False}
    assert _after_verify({"verification": verification}) == "insight"


def test_memory_candidate_records_policy_gate_result(monkeypatch):
    candidate = type("Candidate", (), {"candidate_id": "candidate-1", "subject": "merchant", "predicate": "policy", "value": "x"})()
    monkeypatch.setattr(graph_v2, "extract_candidates", lambda *_: [candidate])
    monkeypatch.setattr(graph_v2, "gate_candidate", lambda _: "approved")
    result = _memory_candidate({"final_answer": "结论"})
    assert result["memory_candidates"] == [{"candidate_id": "candidate-1", "status": "approved", "subject": "merchant", "predicate": "policy", "value": "x"}]


def test_no_memory_evaluation_skips_candidate_extraction(monkeypatch):
    monkeypatch.setattr(graph_v2, "extract_candidates", lambda *_: (_ for _ in ()).throw(AssertionError("must not extract")))
    assert graph_v2._memory_candidate({"disable_memory_candidates": True})["memory_candidates"] == []


def test_recall_can_be_disabled_for_component_ablation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://should-not-be-opened")
    result = graph_v2._recall({"disable_memory_recall": True})
    assert result["recalled_memories"] == []
    assert result["steps"][0]["summary"] == "disabled for component ablation"
