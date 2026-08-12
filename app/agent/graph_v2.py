"""Bounded v2 graph: recall → plan → executor → verifier → synthesis."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

import psycopg
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.insight import insight
from app.agent.nodes.router import router
from app.agent.state import AgentState
from app.agent.planning import Action, Plan, next_plan, verify_evidence
from app.memory.extractor import extract_candidates
from app.memory.policy import gate_candidate
from app.memory.retriever import assemble_context
from app.storage.memory_repository import compensate_pending_indexes, fetch_active_memories

MAX_RUN_SECONDS = 120


def metric_query(state: dict) -> dict:
    """Delay tool-node imports until their bounded action is actually chosen."""
    from app.agent.nodes.metric_query import metric_query as implementation

    return implementation(state)


def attribution(state: dict) -> dict:
    from app.agent.nodes.attribution import attribution as implementation

    return implementation(state)


def strategy(state: dict) -> dict:
    # Strategy imports Mem0/RAG; metric-only API requests must not pay that cost.
    from app.agent.nodes.strategy import strategy as implementation

    return implementation(state)


def _recall(state: dict) -> dict:
    if state.get("disable_memory_recall"):
        return {"recalled_memories": [],
                "steps": [{"node": "MemoryRecall", "summary": "disabled for component ablation"}]}
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        return {"recalled_memories": [], "steps": [{"node": "MemoryRecall", "summary": "database unavailable; no recall"}]}
    try:
        from app.rag.indexer import encode_with_shared_embedder

        vector = encode_with_shared_embedder(state["user_query"], normalize_embeddings=True).tolist()
        with psycopg.connect(dsn) as conn:
            compensate_pending_indexes(
                conn,
                merchant_id=state.get("merchant_id", "xiaozhang_women"),
                encode=lambda content: encode_with_shared_embedder(content, normalize_embeddings=True).tolist(),
            )
            conn.commit()
            memories = fetch_active_memories(conn, merchant_id=state.get("merchant_id", "xiaozhang_women"), query_embedding=vector)
        selected = assemble_context(memories, datetime.now(timezone.utc), state["user_query"])
        return {"recalled_memories": selected,
                "steps": [{"node": "MemoryRecall", "summary": f"recalled={len(selected)}"}]}
    except Exception as exc:
        return {"recalled_memories": [],
                "steps": [{"node": "MemoryRecall", "summary": f"recall unavailable: {type(exc).__name__}"}]}


def _plan(state: dict) -> dict:
    intent = state["intent"]
    replan_count = state.get("verification", {}).get("replan_count", 0)
    dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", state["user_query"])
    # 跨 case 归因是唯一允许的多 action 产品路径；固定最多两次工具调用。
    actions = (
        tuple(Action("attribution", {"anomaly_date": date}) for date in dates[:2])
        if intent == "attribution" and len(dates) >= 2
        else (Action(intent, {}),)
    )
    return {"plan": Plan(actions, replan_count=replan_count), "action_cursor": 0,
            "steps": [{"node": "Planner", "summary": f"planned {intent}, replan={replan_count}"}]}


def _execute_action(state: dict, action: Action) -> dict:
    if action.name == "attribution" and action.arguments.get("anomaly_date"):
        scoped = dict(state)
        date = action.arguments["anomaly_date"]
        scoped["time_window"] = {"start": date, "end": date}
        return attribution(scoped)
    return {"metric": metric_query, "attribution": attribution, "strategy": strategy}[action.name](state)


def _insufficient_result(intent: str, reason: str) -> dict:
    return {
        "task": intent,
        "headline": "证据不足，已停止继续尝试",
        "data": {"status": "evidence_insufficient", "reason": reason},
        "evidence": [reason],
    }


def _execute(state: dict) -> dict:
    """Run the immutable bounded plan and convert failures into visible evidence."""
    started = state.get("run_started_monotonic", time.monotonic())
    outcomes: list[dict] = []
    step_rows: list[dict] = []
    for cursor, action in enumerate(state["plan"].actions):
        if time.monotonic() - started >= MAX_RUN_SECONDS:
            outcomes.append({"status": "error", "evidence": [], "reason": "agent_timeout"})
            step_rows.append({"node": "ActionExecutor", "summary": f"{action.name}: agent_timeout"})
            break
        try:
            response = _execute_action(state, action)
            result = response["node_result"]
            outcomes.append({"status": "ok" if result.get("evidence") else "error", "evidence": result.get("evidence", []), "result": result})
            step_rows.extend(response.get("steps", []))
        except Exception as exc:
            reason = f"tool_failure:{type(exc).__name__}"
            outcomes.append({"status": "error", "evidence": [], "reason": reason})
            step_rows.append({"node": "ActionExecutor", "summary": f"{action.name}: {reason}"})

    successful = [item["result"] for item in outcomes if item["status"] == "ok"]
    if len(successful) == 1 and len(outcomes) == 1:
        result = successful[0]
    elif successful and len(successful) == len(outcomes):
        result = {
            "task": "attribution_comparison",
            "headline": f"跨 case 归因对比：{len(successful)} 个窗口",
            "data": {"comparisons": [item["data"] for item in successful]},
            "evidence": [evidence for item in successful for evidence in item["evidence"]],
        }
    else:
        result = _insufficient_result(state["intent"], outcomes[-1].get("reason", "empty_evidence"))
    return {"node_result": result, "action_results": outcomes, "action_cursor": len(outcomes), "steps": step_rows}


def _verify(state: dict) -> dict:
    results = state.get("action_results") or []
    ok = verify_evidence(results)
    follow_up = next_plan(state["plan"], ok)
    replan_count = follow_up.replan_count if follow_up else state["plan"].replan_count
    return {"verification": {"sufficient": ok, "replan_count": replan_count,
                             "will_replan": follow_up is not None},
            "steps": [{"node": "EvidenceVerifier", "summary": "sufficient" if ok else "insufficient"}]}


def _after_verify(state: dict) -> str:
    return "planner" if state["verification"].get("will_replan") else "insight"


def _memory_candidate(state: dict) -> dict:
    if state.get("disable_memory_candidates"):
        return {"memory_candidates": [],
                "steps": [{"node": "MemoryPolicyGate", "summary": "disabled for no-memory evaluation"}]}
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
