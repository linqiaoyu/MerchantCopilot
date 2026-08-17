"""Rebuild aggregate metrics, paired statistics and bad cases from raw matrix JSON."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evals.v3.run_skill_matrix import ARMS
from evals.v3.statistics import binary_paired_comparison, holm_adjust, paired_bootstrap_delta

METRICS = (
    "task_success", "skill_top1", "wrong_skill_injection", "evidence_contract_pass",
    "tool_call_accuracy", "tool_calls", "replan", "policy_violations",
    "structured_contract_pass",
)


def analyze(payload: dict) -> dict:
    rows = payload["rows"]
    keys = [(row["case_id"], row["arm"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate case/arm rows")
    case_ids = sorted({row["case_id"] for row in rows})
    if {row["arm"] for row in rows} != set(ARMS):
        raise ValueError("wrong arm set")
    if len(rows) != len(case_ids) * len(ARMS):
        raise ValueError("incomplete six-arm matrix")
    by_arm = defaultdict(list)
    by_key = {}
    for row in rows:
        by_arm[row["arm"]].append(row)
        by_key[(row["case_id"], row["arm"])] = row
    aggregates = {}
    for arm, arm_rows in by_arm.items():
        aggregates[arm] = {
            metric: sum(float(row["scores"][metric]) for row in arm_rows) / len(arm_rows)
            for metric in METRICS
        }
        aggregates[arm]["nil_rate"] = sum(row["status"] != "completed" for row in arm_rows) / len(arm_rows)
        aggregates[arm]["mean_latency_ms"] = sum(row["latency_ms"] for row in arm_rows) / len(arm_rows)
        aggregates[arm]["prompt_tokens"] = sum(row["usage"]["prompt_tokens"] for row in arm_rows)
        aggregates[arm]["completion_tokens"] = sum(row["usage"]["completion_tokens"] for row in arm_rows)

    comparisons = {}
    raw_p = {}
    for baseline, candidate, label in (
        ("bare", "canonical_memory_evolved_skill", "full_evolved_vs_bare"),
        ("static_skill_only", "canonical_memory_static_skill", "memory_plus_static_vs_static"),
        ("canonical_memory_static_skill", "canonical_memory_evolved_skill", "evolved_vs_static"),
        ("raw_history_static_skill", "canonical_memory_static_skill", "canonical_vs_raw_history"),
    ):
        active = [bool(by_key[(case_id, baseline)]["scores"]["task_success"]) for case_id in case_ids]
        evolved = [bool(by_key[(case_id, candidate)]["scores"]["task_success"]) for case_id in case_ids]
        comparison = binary_paired_comparison(active, evolved)
        tool_effect = paired_bootstrap_delta(
            [float(by_key[(case_id, baseline)]["scores"]["tool_calls"]) for case_id in case_ids],
            [float(by_key[(case_id, candidate)]["scores"]["tool_calls"]) for case_id in case_ids],
        )
        comparison["tool_calls"] = tool_effect
        comparisons[label] = comparison
        raw_p[label] = comparison["p_exact_mcnemar"]
    adjusted = holm_adjust(raw_p)
    for label, value in adjusted.items():
        comparisons[label]["p_holm"] = value
    bad_cases = [
        {"case_id": row["case_id"], "arm": row["arm"], "status": row["status"],
         "error": row["error"], "scores": row["scores"]}
        for row in rows if row["status"] != "completed" or not row["scores"]["task_success"]
    ]
    return {"kind": payload["kind"], "partition": payload["partition"],
            "dataset_hash": payload["dataset_hash"], "aggregates": aggregates,
            "comparisons": comparisons, "bad_cases": bad_cases,
            "claim_eligible": payload["kind"] == "formal_api" and payload["partition"] == "test"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bad_cases": len(report["bad_cases"]), "claim_eligible": report["claim_eligible"]}))


if __name__ == "__main__":
    main()
