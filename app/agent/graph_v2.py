"""Bounded v2 graph: recall → plan → executor → verifier → synthesis."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.attribution import attribution
from app.agent.nodes.insight import insight
from app.agent.nodes.metric_query import metric_query
from app.agent.nodes.router import router
from app.agent.nodes.strategy import strategy
from app.agent.state import AgentState
from app.agent.planning import Action, Plan, verify_evidence


def _recall(state: dict) -> dict:
    return {"recalled_memories": [], "steps": [{"node": "MemoryRecall", "summary": "no persistent backend configured"}]}


def _plan(state: dict) -> dict:
    intent = state["intent"]
    return {"plan": Plan((Action(intent, {}),)), "action_cursor": 0,
            "steps": [{"node": "Planner", "summary": f"planned {intent}"}]}


def _execute(state: dict) -> dict:
    node = {"metric": metric_query, "attribution": attribution, "strategy": strategy}[state["intent"]]
    return node(state)


def _verify(state: dict) -> dict:
    result = state.get("node_result", {})
    ok = verify_evidence([{"status": "ok" if result else "error", "evidence": result.get("evidence", [])}])
    return {"verification": {"sufficient": ok, "replan_count": 0},
            "steps": [{"node": "EvidenceVerifier", "summary": "sufficient" if ok else "insufficient"}]}


def build_graph_v2(checkpointer=None):
    """Build the bounded graph; callers may supply MemorySaver or PostgresSaver."""
    graph = StateGraph(AgentState)
    graph.add_node("router", router)
    graph.add_node("recall", _recall)
    graph.add_node("planner", _plan)
    graph.add_node("executor", _execute)
    graph.add_node("verifier", _verify)
    graph.add_node("insight", insight)
    graph.add_edge(START, "router")
    graph.add_edge("router", "recall")
    graph.add_edge("recall", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "verifier")
    graph.add_edge("verifier", "insight")
    graph.add_edge("insight", END)
    return graph.compile(checkpointer=checkpointer)
