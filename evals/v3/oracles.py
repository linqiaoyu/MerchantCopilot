"""Independent scorers: they consume public traces, never runtime scoring helpers."""
from __future__ import annotations


def score_skill_case(case: dict, result: dict) -> dict[str, float | int | bool]:
    oracle = case["oracle"]
    selected = result.get("selected_skill_id")
    action_sequence = result.get("action_sequence", [])
    evidence_pass = bool(result.get("evidence_contract_pass", False))
    evidence_sufficient = bool(result.get("evidence_sufficient", False))
    policy_violations = int(result.get("policy_violations", 0))
    top1 = selected == oracle["selected_skill"]
    wrong_injection = selected is not None and not top1
    tools_ok = action_sequence == oracle["action_sequence"]
    calls = len(action_sequence)
    call_budget_ok = oracle["min_tool_calls"] <= calls <= oracle["max_tool_calls"]
    semantic_contract = (
        bool(result.get("structured_experiment_pass", False))
        if oracle["selected_skill"] == "outcome-driven-experiment" else True
    )
    # Task success is independent from Skill selection: a bare planner may solve
    # a case, and that outcome must be counted.  Skill-specific evidence rules
    # apply only when a Skill was actually injected.
    evidence_ok = evidence_pass if selected is not None else evidence_sufficient
    success = tools_ok and call_budget_ok and evidence_ok and semantic_contract and policy_violations == 0
    return {"task_success": success, "skill_top1": top1,
            "wrong_skill_injection": wrong_injection, "evidence_contract_pass": evidence_pass,
            "tool_call_accuracy": tools_ok, "tool_calls": calls,
            "structured_contract_pass": semantic_contract,
            "replan": bool(result.get("replan", False)), "policy_violations": policy_violations}


def score_memory_case(case: dict, result: dict) -> dict[str, float | int]:
    oracle = case["oracle"]
    recalled = set(result.get("recalled_ids", []))
    cited = set(result.get("cited_provenance_ids", []))
    expected = set(oracle["active_fact_ids"])
    forbidden = set(oracle["forbidden_recall_ids"])
    required_provenance = set(oracle["required_provenance_ids"])
    tp = len(recalled & expected)
    precision = tp / len(recalled) if recalled else float(not expected)
    recall = tp / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    forbidden_hits = recalled & forbidden
    exact_current = recalled == expected
    category = case["category"]
    stale = len(forbidden_hits) / max(len(recalled), 1) if category == "temporal_conflict_correction" else 0.0
    irrelevant = len(forbidden_hits) / max(len(recalled), 1) if category in {
        "cross_thread_irrelevant_injection", "contradiction_memory_poisoning",
        "evidence_bound_extraction",
    } else 0.0
    provenance = len(cited & required_provenance) / max(len(required_provenance), 1)
    links_ok = float(result.get("decision_outcome_links", []) == oracle["decision_outcome_links"])
    task_success = exact_current and not forbidden_hits and provenance == 1.0 and links_ok == 1.0
    return {"extraction_precision": precision, "extraction_recall": recall, "extraction_f1": f1,
            "temporal_fact_accuracy": float(exact_current),
            "stale_memory": stale, "irrelevant_injection": irrelevant,
            "cross_thread_leaks": int(any(item.endswith("-other") for item in recalled)),
            "answer_provenance": provenance,
            "decision_outcome_link_accuracy": links_ok,
            "task_success": task_success}
