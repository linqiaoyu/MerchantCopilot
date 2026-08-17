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
from app.memory.policy import MemoryCandidate, candidate_to_dict, gate_candidate
from app.memory.retriever import assemble_context, build_query_plan
from app.storage.memory_repository import compensate_pending_indexes, fetch_active_memories
from app.skills.compiler import compile_skill, diagnose_preconditions
from app.skills.models import SkillContract
from app.skills.registry import runtime_registry
from app.skills.selector import rank_skills, select_skill
from app.skills.verifier import verify_skill_evidence

MAX_RUN_SECONDS = 120


def _skill_discovery(state: dict) -> dict:
    if state.get("disable_skill"):
        return {"skill_candidates": [], "steps": []}
    metadata = runtime_registry(state.get("skill_registry_mode", "runtime")).discover()
    ranked = rank_skills(state["user_query"], state.get("intent", ""), metadata)
    # Discovery remains observable through state/run_events, but it is not
    # surfaced as a user-facing execution step until a Skill is selected.  This
    # preserves the public v2 trace for requests that do not use a Skill.
    return {"skill_candidates": ranked, "steps": []}


def _skill_selection(state: dict) -> dict:
    selected = select_skill(state["user_query"], state.get("intent", ""), state.get("skill_candidates", []))
    if not selected:
        return {"selected_skill": {}, "skill_version": "",
                "skill_selection_trace": {"status": "no_metadata_match"}, "steps": []}
    loaded = runtime_registry(state.get("skill_registry_mode", "runtime")).load(selected["id"])
    preconditions = diagnose_preconditions(loaded.contract, state)
    if any(not row["passed"] for row in preconditions):
        return {
            "selected_skill": {}, "skill_version": "",
            "skill_selection_trace": {
                "status": "precondition_failed", "skill_id": loaded.contract.id,
                "preconditions": preconditions,
            },
            "steps": [],
        }
    runtime_skill = {
        **selected,
        "contract": loaded.contract.to_dict(),
        "instructions": loaded.instructions,
        "content_hash": loaded.content_hash,
    }
    return {"selected_skill": runtime_skill, "skill_version": loaded.contract.version,
            "skill_selection_trace": {"status": "selected", "skill_id": loaded.contract.id,
                                      "preconditions": preconditions},
            "steps": [{"node": "SkillDiscovery",
                       "summary": f"metadata_candidates={len(state.get('skill_candidates', []))}"},
                      {"node": "SkillSelection",
                       "summary": f"selected={loaded.contract.id}@{loaded.contract.version}"}]}


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
    query = state.get("user_query", "")
    query_plan = build_query_plan(query, state.get("intent", ""))
    if state.get("dataset_partition") in {"dev", "regression", "test"} \
            and "evaluation_memory_context" in state:
        rows = state.get("evaluation_memory_context", [])
        ids = [str(item["memory_id"]) for item in rows]
        return {"recalled_memories": rows, "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": ids, "injected": ids, "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": f"frozen_canonical={len(rows)}"}]}
    if state.get("memory_mode") == "raw_history":
        raw = []
        for index, item in enumerate(state.get("raw_history", [])):
            raw.append({
                "memory_id": str(item.get("event_id", f"raw-{index}")),
                "source_event_id": str(item.get("event_id", f"raw-{index}")),
                "kind": item.get("kind", "episodic"), "fact_type": item.get("fact_type", "observation"),
                "subject": item.get("subject", "merchant"), "predicate": item.get("predicate", "raw_history"),
                "scope_type": item.get("scope_type", "thread"), "scope_id": item.get("thread_id", state.get("thread_id", "")),
                "content": str(item.get("value", item)),
            })
        ids = [item["memory_id"] for item in raw]
        return {"recalled_memories": raw, "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": ids, "injected": ids, "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": f"raw_history={len(raw)}"}]}
    if state.get("disable_memory_recall"):
        return {"recalled_memories": [],
                "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": [], "injected": [], "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": "disabled for component ablation"}]}
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        return {"recalled_memories": [], "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": [], "injected": [], "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": "database unavailable; no recall"}]}
    try:
        from app.rag.indexer import encode_with_shared_embedder

        vector = encode_with_shared_embedder(query, normalize_embeddings=True).tolist()
        with psycopg.connect(dsn) as conn:
            compensate_pending_indexes(
                conn,
                merchant_id=state.get("merchant_id", "xiaozhang_women"),
                encode=lambda content: encode_with_shared_embedder(content, normalize_embeddings=True).tolist(),
            )
            conn.commit()
            effective_window = query_plan.get("effective_window")
            memories = fetch_active_memories(
                conn, merchant_id=state.get("merchant_id", "xiaozhang_women"), query_embedding=vector,
                fact_types=query_plan["fact_types"] or None, thread_id=state.get("thread_id"),
                effective_from=datetime.fromisoformat(effective_window["start"]) if effective_window else None,
                effective_to=datetime.fromisoformat(effective_window["end"]) if effective_window else None,
            )
        selected = assemble_context(memories, datetime.now(timezone.utc), query)
        selected_ids = [row["memory_id"] for row in selected]
        return {"recalled_memories": selected,
                "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": [memory.memory_id for memory in memories],
                                       "injected": selected_ids, "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": f"recalled={len(selected)}"}]}
    except Exception as exc:
        return {"recalled_memories": [], "memory_query_plan": query_plan,
                "memory_usage_trace": {"recalled": [], "injected": [], "cited": [], "used": []},
                "steps": [{"node": "MemoryRecall", "summary": f"recall unavailable: {type(exc).__name__}"}]}


def _plan(state: dict) -> dict:
    intent = state["intent"]
    replan_count = state.get("verification", {}).get("replan_count", 0)
    selected = state.get("selected_skill") or {}
    if selected.get("contract"):
        contract = SkillContract.from_dict(selected["contract"])
        plan = compile_skill(contract, state, replan_count=replan_count)
        return {"plan": plan, "compiled_skill_plan": plan,
                "steps": [{"node": "Planner",
                           "summary": f"compiled {contract.id}@{contract.version}, replan={replan_count}"}]}
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
    if action.arguments:
        scoped = dict(state)
        if action.arguments.get("anomaly_date"):
            date = action.arguments["anomaly_date"]
            scoped["time_window"] = {"start": date, "end": date}
        elif action.arguments.get("start") and action.arguments.get("end"):
            scoped["time_window"] = {
                "start": action.arguments["start"], "end": action.arguments["end"],
            }
        return {"metric": metric_query, "attribution": attribution, "strategy": strategy}[action.name](scoped)
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
            scoped_state = dict(state)
            scoped_state["prior_action_results"] = [item.get("result", {}) for item in outcomes]
            response = _execute_action(scoped_state, action)
            result = response["node_result"]
            outcomes.append({"status": "ok" if result.get("evidence") else "error", "evidence": result.get("evidence", []), "result": result})
            step_rows.extend(response.get("steps", []))
        except Exception as exc:
            reason = f"tool_failure:{type(exc).__name__}"
            outcomes.append({"status": "error", "evidence": [], "reason": reason})
            step_rows.append({"node": "ActionExecutor", "summary": f"{action.name}: {reason}"})

    successful = [item["result"] for item in outcomes if item["status"] == "ok"]
    selected_id = (state.get("selected_skill") or {}).get("id")
    if len(successful) == 1 and len(outcomes) == 1:
        result = successful[0]
    elif successful and len(successful) == len(outcomes):
        combined_evidence = [evidence for item in successful for evidence in item["evidence"]]
        if selected_id in {"anomaly-root-cause", "outcome-driven-experiment"}:
            # The final typed result remains the terminal analytical/strategy
            # action; prior metric results are attached as deterministic
            # baselines instead of being flattened into an attribution result.
            result = dict(successful[-1])
            result["data"] = {**result.get("data", {}), "baseline_result": successful[0].get("data", {})}
            result["evidence"] = combined_evidence
        else:
            comparison_task = (
                "cross_period_comparison" if selected_id == "cross-period-comparison"
                else "attribution_comparison"
            )
            result = {
                "task": comparison_task,
                "headline": f"跨周期对比：{len(successful)} 个窗口" if selected_id == "cross-period-comparison"
                else f"跨 case 归因对比：{len(successful)} 个窗口",
                "data": {"comparisons": [item["data"] for item in successful]},
                "evidence": combined_evidence,
            }
    else:
        result = _insufficient_result(state["intent"], outcomes[-1].get("reason", "empty_evidence"))
    selected = state.get("selected_skill") or {}
    skill_steps = selected.get("contract", {}).get("steps", [])
    trace = []
    for index, outcome in enumerate(outcomes):
        step = skill_steps[index] if index < len(skill_steps) else {"id": f"action_{index}"}
        trace.append({"step_id": step["id"], "status": outcome["status"],
                      "evidence_count": len(outcome.get("evidence", []))})
    usage_trace = dict(state.get("memory_usage_trace", {}))
    decision_refs = result.get("data", {}).get("decision", {}).get("evidence_refs", [])
    cited_ids = [ref.removeprefix("memory:") for ref in decision_refs if str(ref).startswith("memory:")]
    usage_trace["cited"] = cited_ids
    usage_trace["used"] = cited_ids
    return {"node_result": result, "action_results": outcomes, "action_cursor": len(outcomes),
            "skill_execution_trace": trace, "memory_usage_trace": usage_trace, "steps": step_rows}


def _verify(state: dict) -> dict:
    results = state.get("action_results") or []
    ok = verify_evidence(results)
    follow_up = next_plan(state["plan"], ok)
    replan_count = follow_up.replan_count if follow_up else state["plan"].replan_count
    selected = state.get("selected_skill") or {}
    skill_verification = None
    if selected.get("contract"):
        contract = SkillContract.from_dict(selected["contract"])
        skill_verification = verify_skill_evidence(contract, results)
        ok = ok and skill_verification["sufficient"]
        follow_up = next_plan(state["plan"], ok)
        replan_count = follow_up.replan_count if follow_up else state["plan"].replan_count
    verification = {"sufficient": ok, "replan_count": replan_count,
                    "will_replan": follow_up is not None}
    if skill_verification is not None:
        verification["skill_contract"] = skill_verification
    return {"verification": verification, "evidence_verification": verification,
            "steps": [{"node": "EvidenceVerifier", "summary": "sufficient" if ok else "insufficient"}]}


def _after_verify(state: dict) -> str:
    return "planner" if state["verification"].get("will_replan") else "insight"


def _memory_candidate(state: dict) -> dict:
    if state.get("disable_memory_candidates"):
        return {"memory_candidates": [],
                "steps": [{"node": "MemoryPolicyGate", "summary": "disabled for no-memory evaluation"}]}
    evidence_refs = [f"{state.get('run_id', 'local-run')}:evidence:{index}"
                     for index, _ in enumerate(state.get("node_result", {}).get("evidence", []))]
    run_id = state.get("run_id", "local-run")
    thread_id = state.get("thread_id")
    merchant_id = state.get("merchant_id")
    candidates = extract_candidates(
        f"{run_id}:user", state.get("user_query", ""), "user", thread_id, merchant_id,
        (f"user:{run_id}:query",), ("user_fact",),
    )
    node_result = state.get("node_result", {})
    if node_result.get("task") in {"metric", "attribution", "attribution_comparison", "cross_period_comparison"} and evidence_refs:
        candidates.append(MemoryCandidate(
            candidate_id=f"{run_id}:tool-observation", subject="merchant",
            predicate=f"{node_result['task']}_result", value=node_result.get("data", {}),
            source_type="mcp", kind="episodic", fact_type="observation",
            thread_id=thread_id, scope_type="thread", scope_id=thread_id,
            evidence_refs=tuple(evidence_refs), schema_version=3,
        ))
    decision = node_result.get("data", {}).get("decision")
    if decision:
        candidates.append(MemoryCandidate(
            candidate_id=f"{run_id}:decision", subject="merchant", predicate="strategy_decision",
            value=decision, source_type="agent", kind="decision", fact_type="decision",
            thread_id=thread_id, scope_type="merchant", scope_id=merchant_id,
            evidence_refs=tuple(decision.get("evidence_refs", [])), schema_version=3,
        ))
    rows = []
    for candidate in candidates:
        payload = candidate_to_dict(candidate) if hasattr(candidate, "source_type") else {
            "candidate_id": candidate.candidate_id, "subject": candidate.subject,
            "predicate": candidate.predicate, "value": candidate.value,
        }
        payload["status"] = gate_candidate(candidate)
        rows.append(payload)
    return {"memory_candidates": rows,
            "steps": [{"node": "MemoryPolicyGate", "summary": f"candidates={len(rows)}"}]}


def build_graph_v2(checkpointer=None):
    """Build the bounded graph; callers may supply MemorySaver or PostgresSaver."""
    graph = StateGraph(AgentState)
    graph.add_node("router", router)
    graph.add_node("recall", _recall)
    graph.add_node("skill_discovery", _skill_discovery)
    graph.add_node("skill_selection", _skill_selection)
    graph.add_node("planner", _plan)
    graph.add_node("executor", _execute)
    graph.add_node("verifier", _verify)
    graph.add_node("insight", insight)
    graph.add_node("memory_candidate", _memory_candidate)
    graph.add_edge(START, "router")
    graph.add_edge("router", "recall")
    graph.add_edge("recall", "skill_discovery")
    graph.add_edge("skill_discovery", "skill_selection")
    graph.add_edge("skill_selection", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "verifier")
    graph.add_conditional_edges("verifier", _after_verify, {"planner": "planner", "insight": "insight"})
    graph.add_edge("insight", "memory_candidate")
    graph.add_edge("memory_candidate", END)
    return graph.compile(checkpointer=checkpointer)
