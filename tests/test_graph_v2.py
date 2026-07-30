from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph_v2 import _after_verify, _verify, build_graph_v2
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
