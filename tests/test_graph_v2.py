from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph_v2 import build_graph_v2


def test_v2_graph_runs_bounded_metric_path(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    state = build_graph_v2().invoke({"user_query": "2026-04-02 GMV 怎么样"})
    assert [step["node"] for step in state["steps"]] == [
        "Router", "MemoryRecall", "Planner", "MetricQuery", "EvidenceVerifier", "Insight"
    ]
    assert len(state["plan"].actions) == 1
    assert state["verification"]["sufficient"]


def test_v2_graph_accepts_in_memory_checkpointer(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    graph = build_graph_v2(checkpointer=MemorySaver())
    result = graph.invoke({"user_query": "2026-04-02 GMV 怎么样"}, config={"configurable": {"thread_id": "t1"}})
    assert result["node_result"]["task"] == "metric"
