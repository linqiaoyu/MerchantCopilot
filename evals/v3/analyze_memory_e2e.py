"""Aggregate the complete three-arm Memory-E2E-80 artifact."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evals.v3.run_memory_e2e import ARMS
from evals.v3.statistics import binary_paired_comparison, paired_bootstrap_delta

METRICS = (
    "extraction_precision", "extraction_recall", "extraction_f1",
    "temporal_fact_accuracy", "stale_memory", "irrelevant_injection",
    "cross_thread_leaks", "answer_provenance", "decision_outcome_link_accuracy",
    "task_success",
)


def analyze(payload: dict) -> dict:
    rows = payload["rows"]
    keys = [(row["case_id"], row["arm"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate Memory case/arm rows")
    case_ids = sorted({row["case_id"] for row in rows})
    if len(case_ids) != 80 or set(row["arm"] for row in rows) != set(ARMS):
        raise ValueError("wrong or incomplete Memory-E2E arm set")
    if len(rows) != len(case_ids) * len(ARMS):
        raise ValueError("incomplete Memory-E2E matrix")
    by_arm = defaultdict(list)
    by_key = {}
    for row in rows:
        by_arm[row["arm"]].append(row)
        by_key[(row["case_id"], row["arm"])] = row
    aggregates = {
        arm: {
            metric: sum(float(row["scores"][metric]) for row in arm_rows) / len(arm_rows)
            for metric in METRICS
        }
        for arm, arm_rows in by_arm.items()
    }
    comparisons = {}
    for baseline in ("raw_history", "no_memory"):
        left = [bool(by_key[(case_id, baseline)]["scores"]["task_success"]) for case_id in case_ids]
        right = [bool(by_key[(case_id, "canonical_memory")]["scores"]["task_success"]) for case_id in case_ids]
        comparisons[f"canonical_vs_{baseline}"] = {
            **binary_paired_comparison(left, right),
            "temporal_accuracy_delta": paired_bootstrap_delta(
                [float(by_key[(case_id, baseline)]["scores"]["temporal_fact_accuracy"]) for case_id in case_ids],
                [float(by_key[(case_id, "canonical_memory")]["scores"]["temporal_fact_accuracy"]) for case_id in case_ids],
            ),
        }
    return {
        "kind": payload["kind"], "dataset_hash": payload["dataset_hash"],
        "aggregates": aggregates, "comparisons": comparisons,
        "claim_eligible": payload["kind"] == "formal_deterministic_postgres",
        "bad_cases": [
            {"case_id": row["case_id"], "arm": row["arm"], "scores": row["scores"]}
            for row in rows if row["arm"] == "canonical_memory" and not row["scores"]["task_success"]
        ],
    }


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
