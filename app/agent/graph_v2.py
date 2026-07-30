"""Bounded v2 graph: recall → plan → executor → verifier → synthesis."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.attribution import attribution
from app.agent.nodes.insight import insight
from app.agent.nodes.metric_query import metric_query
from app.agent.nodes.router import router
from app.agent.nodes.strategy import strategy
from app.agent.state import AgentState
from app.agent.planning import Action, Plan, next_plan, verify_evidence
from app.memory.extractor import extract_candidates
from app.memory.policy import gate_candidate


def _recall(state: dict) -> dict:
    return {"recalled_memories": [], "steps": [{"node": "MemoryRecall", "summary": "no persistent backend configured"}]}


def _plan(state: dict) -> dict:
    intent = state["intent"]
    replan_count = state.get("verification", {}).get("replan_count", 0)
    return {"plan": Plan((Action(intent, {}),), replan_count=replan_count), "action_cursor": 0,
            "steps": [{"node": "Planner", "summary": f"planned {intent}, replan={replan_count}"}]}


def _execute(state: dict) -> dict:
    node = {"metric": metric_query, "attribution": attribution, "strategy": strategy}[state["intent"]]
    return node(state)


def _verify(state: dict) -> dict:
    result = state.get("node_result", {})
    ok = verify_evidence([{"status": "ok" if result else "error", "evidence": result.get("evidence", [])}])
    follow_up = next_plan(state["plan"], ok)
    replan_count = follow_up.replan_count if follow_up else state["plan"].replan_count
    return {"verification": {"sufficient": ok, "replan_count": replan_count,
                             "will_replan": follow_up is not None},
            "steps": [{"node": "EvidenceVerifier", "summary": "sufficient" if ok else "insufficient"}]}


def _after_verify(state: dict) -> str:
    return "planner" if state["verification"].get("will_replan") else "insight"


def _memory_candidate(state: dict) -> dict:
    candidates = extract_candidates("local-run", state.get("final_answer", ""))
    rows = [{"candidate_id": candidate.candidate_id, "status": gate_candidate(candidate),
             "subject": candidate.subject, "predicate": candidate.predicate, "value": candidate.value}
            for candidate in candidates]
    return {"memory_candidates": rows,
            "steps": [{"node": "MemoryPolicyGate", "summary": f"candidates={len(rows)}"}]}


def build_graph_v2(checkpointer=None):
    """Build the bounded graph; callers may supply MemorySaver or PostgresSaver."""
    graph = StateGraph(AgentState)
    graph.add_node("router", router)
    graph.add_node("recall", _recall)
    graph.add_node("planner", _plan)
    graph.add_node("executor", _execute)
    graph.add_node("verifier", _verify)
    graph.add_node("insight", insight)
    graph.add_node("memory_candidate", _memory_candidate)
    graph.add_edge(START, "router")
    graph.add_edge("router", "recall")
    graph.add_edge("recall", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "verifier")
    graph.add_conditional_edges("verifier", _after_verify, {"planner": "planner", "insight": "insight"})
    graph.add_edge("insight", "memory_candidate")
    graph.add_edge("memory_candidate", END)
    return graph.compile(checkpointer=checkpointer)
