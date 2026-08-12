from langgraph.checkpoint.memory import MemorySaver

import time

import app.agent.graph_v2 as graph_v2
from app.agent.graph_v2 import _after_verify, _execute, _plan, _verify, build_graph_v2
from app.agent.planning import Action, Plan


def test_v2_graph_runs_bounded_metric_path(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    state = build_graph_v2().invoke({"user_query": "2026-04-02 GMV 怎么样"})
    assert [step["node"] for step in state["steps"]] == [
        "Router", "MemoryRecall", "Planner", "MetricQuery", "EvidenceVerifier", "Insight", "MemoryPolicyGate"
    ]
    assert len(state["plan"].actions) == 1
    assert state["verification"]["sufficient"]


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
