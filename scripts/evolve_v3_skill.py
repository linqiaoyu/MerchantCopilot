"""Run one budgeted offline evolution batch for anomaly-root-cause."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import psycopg

from app.llm.client import capture_llm_trace, capture_usage
from app.skills.candidate_generator import generate_patch
from app.skills.compiler import compile_skill
from app.skills.evolution import PairedMetrics
from app.skills.evolution_engine import EvolutionEngine
from app.skills.registry import LoadedSkill, PostgresSkillRegistry, SkillRegistry
from app.skills.selector import select_skill
from app.storage.skill_repository import record_skill_eval_run
from evals.v3.budget import BudgetGuard
from evals.v3.datasets import DATA_ROOT, assert_no_test_contamination, validate_frozen_datasets

SKILL_ID = "anomaly-root-cause"
SNAPSHOT = Path(__file__).resolve().parents[1] / "evals" / "v3" / "price_snapshot_2026-08-17.json"


def _usage(rows: list[dict]) -> dict[str, int]:
    return {
        key: sum(int(row.get("usage", {}).get(key, 0)) for row in rows)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _success(contract, all_metadata: list[dict], case: dict) -> tuple[bool, float, float]:
    metadata = [row for row in all_metadata if row["id"] != contract.id]
    metadata.append({**contract.metadata(), "status": "ready"})
    selected = select_skill(case["query"], case["task_type"], metadata)
    if not selected or selected["id"] != case["oracle"]["selected_skill"]:
        return False, 0.0, 0.0
    chosen = contract if selected["id"] == contract.id else SkillRegistry().load(selected["id"]).contract
    dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", case["query"])
    state = {
        "user_query": case["query"],
        "time_window": {"start": dates[0], "end": dates[-1]} if dates else {},
        "recalled_memories": case.get("memory_seed", []),
    }
    try:
        plan = compile_skill(chosen, state)
    except ValueError:
        return False, 0.0, 0.0
    actions = [action.name for action in plan.actions]
    success = actions == case["oracle"]["action_sequence"] and bool(chosen.evidence_contract)
    return success, float(len(actions)), float(bool(chosen.evidence_contract))


def _paired(active: LoadedSkill, candidate: LoadedSkill, partition: str, dataset: dict) -> PairedMetrics:
    cases = [row for row in dataset["cases"] if row["split"] == partition]
    assert_no_test_contamination({row["case_id"] for row in cases}, purpose="promotion")
    metadata = SkillRegistry().discover()
    active_rows = [_success(active.contract, metadata, case) for case in cases]
    candidate_rows = [_success(candidate.contract, metadata, case) for case in cases]
    return PairedMetrics(
        active_success=tuple(row[0] for row in active_rows),
        candidate_success=tuple(row[0] for row in candidate_rows),
        active_tool_calls=tuple(row[1] for row in active_rows),
        candidate_tool_calls=tuple(row[1] for row in candidate_rows),
        active_tokens=(0.0,) * len(cases), candidate_tokens=(0.0,) * len(cases),
        active_replans=(0.0,) * len(cases), candidate_replans=(0.0,) * len(cases),
        active_evidence_fidelity=sum(row[2] for row in active_rows) / len(cases),
        candidate_evidence_fidelity=sum(row[2] for row in candidate_rows) / len(cases),
        active_stale_rate=0.0, candidate_stale_rate=0.0,
        policy_violations=0, cross_thread_leaks=0,
    )


def run(*, dsn: str, out: Path, budget_checkpoint: Path, batch_id: str) -> dict:
    hashes = validate_frozen_datasets()
    dataset = json.loads((DATA_ROOT / "skill_eval_140.json").read_text(encoding="utf-8"))
    train = [row for row in dataset["cases"] if row["split"] == "train"]
    assert_no_test_contamination({row["case_id"] for row in train}, purpose="generation")
    registry = PostgresSkillRegistry(dsn)
    active = registry.load(SKILL_ID)
    metadata = SkillRegistry().discover()
    failures = []
    for case in train:
        ok, _calls, _evidence = _success(active.contract, metadata, case)
        if case["oracle"]["selected_skill"] == SKILL_ID and not ok:
            observed = select_skill(case["query"], case["task_type"], metadata)
            failures.append({
                "trace_id": case["case_id"], "partition": "train",
                "failure_type": "metadata_no_match", "query": case["query"],
                "expected_skill": SKILL_ID,
                "observed_skill": observed["id"] if observed else None,
            })
    if not failures:
        raise ValueError("no train failures available for evolution")
    guard = BudgetGuard(SNAPSHOT, budget_checkpoint)
    generation_round = {"value": 0}

    def generator(contract: dict, traces: list[dict]):
        generation_round["value"] += 1
        key = f"evolve:{SKILL_ID}:{batch_id}:round:{generation_round['value']}"
        if not guard.reserve(key, model="deepseek-v4-flash",
                             worst_prompt_tokens=12_000, worst_completion_tokens=3_000):
            raise RuntimeError(f"completed generation call has no candidate artifact: {key}")
        with capture_usage() as usage_rows, capture_llm_trace() as model_traces:
            try:
                operations, generation = generate_patch(contract, traces)
            finally:
                usage = _usage(usage_rows)
                if any(row.get("status") != "completed" for row in model_traces):
                    guard.complete_unknown(key, reason="candidate generation provider call failed")
                elif usage["prompt_tokens"] or usage["completion_tokens"]:
                    guard.complete(key, usage)
                else:
                    guard.complete_unknown(key, reason="candidate generation returned no provider usage")
        return operations, generation

    with psycopg.connect(dsn) as conn:
        engine = EvolutionEngine(
            conn, generator,
            lambda candidate, partition: _paired(active, candidate, partition, dataset),
        )
        result = engine.run(active, failures, max_rounds=3)
        for attempt in result["attempts"]:
            metrics = attempt.get("metrics") or {}
            record_skill_eval_run(
                conn, skill_id=SKILL_ID, version=attempt["version"],
                dataset_partition="dev", dataset_hash=hashes["skill_eval_140.json"],
                metrics=metrics, report_path=str(out),
            )
            if attempt.get("regression"):
                record_skill_eval_run(
                    conn, skill_id=SKILL_ID, version=attempt["version"],
                    dataset_partition="regression", dataset_hash=hashes["skill_eval_140.json"],
                    metrics=attempt["regression"], report_path=str(out),
                )
        conn.commit()
    payload = {
        "kind": "formal_offline_skill_evolution", "dataset_hash": hashes["skill_eval_140.json"],
        "skill_id": SKILL_ID, "batch_id": batch_id,
        "source_trace_ids": [row["trace_id"] for row in failures],
        "result": result, "spent_cny": guard.spent_cny,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-checkpoint", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    result = run(dsn=args.dsn, out=args.out, budget_checkpoint=args.budget_checkpoint,
                 batch_id=args.batch_id)
    print(json.dumps({"status": result["result"]["status"],
                      "active_version": result["result"]["active_version"],
                      "spent_cny": result["spent_cny"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
