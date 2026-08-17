"""Resumable six-arm Skill evaluator with a pre-call CNY hard budget."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from app.agent.context import RunContext
from app.agent.runtime import run_query
from app.llm.client import capture_llm_trace, capture_usage
from app.skills.compiler import compile_skill
from app.skills.models import SkillContract
from app.skills.registry import SkillRegistry, runtime_registry
from app.skills.selector import select_skill
from evals.v3.budget import BudgetGuard
from evals.v3.datasets import DATA_ROOT, assert_no_test_contamination, validate_frozen_datasets
from evals.v3.oracles import score_skill_case

ARMS = (
    "bare", "memory_only", "static_skill_only", "canonical_memory_static_skill",
    "canonical_memory_evolved_skill", "raw_history_static_skill",
)
SNAPSHOT = Path(__file__).with_name("price_snapshot_2026-08-17.json")


def _usage_total(rows: list[dict]) -> dict[str, int]:
    return {key: sum(int(row.get("usage", {}).get(key, 0)) for row in rows)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _arm_state(arm: str, case: dict) -> dict[str, Any]:
    common = {"disable_memory_candidates": True, "disable_rag": True}
    canonical = [
        {
            "memory_id": f"{case['case_id']}:memory:{index}",
            "source_event_id": f"{case['case_id']}:event:{index}",
            "kind": row["fact_type"] if row["fact_type"] in {"decision", "outcome"} else "episodic",
            "fact_type": row["fact_type"], "subject": "merchant",
            "predicate": f"seed_{row['fact_type']}", "scope_type": "merchant",
            "scope_id": case["merchant_id"], "content": json.dumps(row["value"], ensure_ascii=False),
        }
        for index, row in enumerate(case.get("memory_seed", [])) if row.get("status") == "active"
    ]
    if arm == "bare":
        return {**common, "disable_memory_recall": True, "disable_skill": True, "disable_rag": True}
    if arm == "memory_only":
        return {**common, "disable_skill": True}
    if arm == "static_skill_only":
        return {**common, "disable_memory_recall": True, "skill_registry_mode": "filesystem"}
    if arm == "canonical_memory_static_skill":
        return {**common, "skill_registry_mode": "filesystem", "evaluation_memory_context": canonical}
    if arm == "canonical_memory_evolved_skill":
        return {**common, "skill_registry_mode": "runtime", "evaluation_memory_context": canonical}
    if arm == "raw_history_static_skill":
        return {**common, "memory_mode": "raw_history", "raw_history": case.get("memory_seed", []),
                "skill_registry_mode": "filesystem"}
    raise ValueError(f"unknown arm: {arm}")


def _normalize_result(result: dict) -> dict:
    selected = result.get("selected_skill") or {}
    verification = result.get("evidence_verification") or {}
    data = result.get("node_result", {}).get("data", {})
    for action in result.get("action_results", []):
        action_data = action.get("result", {}).get("data", {})
        if action_data.get("decision"):
            data = action_data
    decision = data.get("decision") or {}
    placeholder = "待执行前确认"
    structured_experiment_pass = (
        data.get("generation") == "llm"
        and all(
            str(decision.get(key, "")).strip()
            and not str(decision.get(key, "")).startswith(placeholder)
            for key in ("experiment_metric", "observation_window", "success_threshold")
        )
    )
    return {
        "selected_skill_id": selected.get("id"),
        "skill_version": selected.get("version"),
        "action_sequence": result.get("action_sequence", []),
        "evidence_contract_pass": verification.get("skill_contract", {}).get("sufficient", False),
        "evidence_sufficient": bool(verification.get("sufficient", False)),
        "structured_experiment_pass": structured_experiment_pass,
        "generation": data.get("generation"),
        "decision": decision,
        "replan": bool(verification.get("replan_count", 0)),
        "policy_violations": 0,
    }


def _deterministic_result(case: dict, arm: str) -> dict:
    base_actions = {
        "anomaly-root-cause": ["attribution"],
        "cross-period-comparison": ["metric"],
        "outcome-driven-experiment": ["strategy"],
    }[case["oracle"]["selected_skill"]]
    if arm in {"bare", "memory_only"}:
        return {"selected_skill_id": None, "action_sequence": base_actions,
                "evidence_contract_pass": False, "evidence_sufficient": True,
                "structured_experiment_pass": case["oracle"]["selected_skill"] == "outcome-driven-experiment",
                "replan": False, "policy_violations": 0}
    registry = runtime_registry("runtime") if arm == "canonical_memory_evolved_skill" else SkillRegistry()
    selected = select_skill(case["query"], case["task_type"], registry.discover())
    if not selected:
        return {"selected_skill_id": None, "action_sequence": [], "evidence_contract_pass": False,
                "evidence_sufficient": False,
                "structured_experiment_pass": False,
                "replan": False, "policy_violations": 0}
    loaded = registry.load(selected["id"])
    recalled = case.get("memory_seed", []) if arm in {
        "canonical_memory_static_skill", "canonical_memory_evolved_skill", "raw_history_static_skill",
    } else []
    dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", case["query"])
    try:
        plan = compile_skill(loaded.contract, {
            "user_query": case["query"],
            "time_window": {"start": dates[0], "end": dates[-1]} if dates else {},
            "recalled_memories": recalled,
        })
    except ValueError:
        return {"selected_skill_id": None, "action_sequence": base_actions,
                "evidence_contract_pass": False, "evidence_sufficient": True,
                "structured_experiment_pass": False,
                "replan": False, "policy_violations": 0}
    return {"selected_skill_id": selected["id"], "skill_version": loaded.contract.version,
            "action_sequence": [action.name for action in plan.actions],
            "evidence_contract_pass": True, "evidence_sufficient": True,
            "structured_experiment_pass": case["oracle"]["selected_skill"] == "outcome-driven-experiment",
            "replan": False, "policy_violations": 0}


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(*, partition: str, out: Path, budget_checkpoint: Path, mode: str,
        confirm_frozen_test: bool = False, run_id: str = "engineering") -> dict:
    hashes = validate_frozen_datasets()
    if partition == "test" and not confirm_frozen_test:
        raise ValueError("frozen test requires --confirm-frozen-test")
    dataset = json.loads((DATA_ROOT / "skill_eval_140.json").read_text(encoding="utf-8"))
    cases = [row for row in dataset["cases"] if row["split"] == partition]
    if partition != "test":
        assert_no_test_contamination({row["case_id"] for row in cases}, purpose="selection")
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
        "kind": "engineering_dry_run" if mode == "deterministic" else "formal_api",
        "partition": partition, "run_id": run_id,
        "dataset_hash": hashes["skill_eval_140.json"], "arms": list(ARMS), "rows": [],
    }
    expected_header = {
        "partition": partition, "dataset_hash": hashes["skill_eval_140.json"],
        "arms": list(ARMS), "run_id": run_id,
    }
    if any(existing.get(key) != value for key, value in expected_header.items()):
        raise ValueError("checkpoint header/config mismatch")
    completed = {(row["case_id"], row["arm"]) for row in existing["rows"]}
    if len(completed) != len(existing["rows"]):
        raise ValueError("duplicate case/arm in checkpoint")
    guard = BudgetGuard(SNAPSHOT, budget_checkpoint)
    for case in cases:
        for arm in ARMS:
            key = (case["case_id"], arm)
            if key in completed:
                continue
            call_key = f"{run_id}::{case['case_id']}::{arm}"
            started = time.perf_counter()
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            try:
                if mode == "deterministic":
                    normalized = _deterministic_result(case, arm)
                else:
                    if not guard.reserve(call_key, model="deepseek-v4-flash",
                                         worst_prompt_tokens=20_000, worst_completion_tokens=10_000):
                        raise RuntimeError("budget checkpoint completed call but matrix row is missing")
                    context = RunContext(
                        thread_id=f"eval-{case['case_id']}", merchant_id=case["merchant_id"],
                        dataset_partition=partition, evaluation_arm=arm,
                        budget_context={"hard_stop_cny": 100},
                    )
                    with capture_usage() as usage_rows, capture_llm_trace() as model_traces:
                        try:
                            result = run_query(case["query"], run_context=context,
                                               state_overrides=_arm_state(arm, case))
                        finally:
                            usage = _usage_total(usage_rows)
                            failed_traces = [row for row in model_traces if row.get("status") != "completed"]
                            if failed_traces:
                                guard.complete_unknown(
                                    call_key, reason="one or more provider calls lack reliable usage",
                                )
                            elif usage["prompt_tokens"] or usage["completion_tokens"]:
                                guard.complete(call_key, usage)
                            else:
                                guard.complete_unknown(call_key, reason="Agent run returned no provider usage")
                    normalized = _normalize_result(result)
                status, error = "completed", None
            except Exception as exc:
                normalized = {"selected_skill_id": None, "action_sequence": [],
                              "evidence_contract_pass": False, "evidence_sufficient": False,
                              "structured_experiment_pass": False,
                              "policy_violations": 0}
                status, error = "nil", f"{type(exc).__name__}: {exc}"
            scores = score_skill_case(case, normalized)
            existing["rows"].append({"case_id": case["case_id"], "arm": arm, "status": status,
                                     "error": error, "result": normalized, "scores": scores,
                                     "usage": usage, "latency_ms": (time.perf_counter() - started) * 1000})
            completed.add(key)
            _save(out, existing)
    expected = len(cases) * len(ARMS)
    if len(existing["rows"]) != expected:
        raise ValueError(f"incomplete matrix: expected {expected}, got {len(existing['rows'])}")
    return existing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", choices=("dev", "regression", "test"), default="dev")
    parser.add_argument("--mode", choices=("deterministic", "api"), default="deterministic")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-checkpoint", type=Path, required=True)
    parser.add_argument("--confirm-frozen-test", action="store_true")
    parser.add_argument("--run-id", default="engineering")
    args = parser.parse_args()
    if args.mode == "api" and args.run_id == "engineering":
        raise SystemExit("formal API runs require an explicit --run-id")
    result = run(partition=args.partition, out=args.out, budget_checkpoint=args.budget_checkpoint,
                 mode=args.mode, confirm_frozen_test=args.confirm_frozen_test,
                 run_id=args.run_id)
    print(json.dumps({"rows": len(result["rows"]), "kind": result["kind"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
