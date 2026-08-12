"""Validate and summarize the preregistered v2 Memory/RAG ablation matrix.

This module never calls a model and never fills missing rows.  It makes the
60-case-per-configuration requirement executable before a human reads results.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from math import comb, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evals" / "datasets" / "v2.0" / "memory_sequences.json"
CONFIGURATIONS = (
    "full", "minus_memory", "minus_rag", "bare", "raw_history", "no_temporal_policy",
)


def _case_ids() -> set[str]:
    dataset = json.loads(DATA.read_text(encoding="utf-8"))
    return {case["id"] for case in dataset["cases"]}


def validate_matrix(payload: dict) -> None:
    expected = _case_ids()
    if payload.get("dataset_version") != "eval-dataset-v2.0-rc1":
        raise ValueError("input must declare the frozen eval-dataset-v2.0-rc1")
    runs = payload.get("runs")
    if not isinstance(runs, dict) or set(runs) != set(CONFIGURATIONS):
        raise ValueError(f"runs must contain exactly {CONFIGURATIONS}")
    for configuration in CONFIGURATIONS:
        rows = runs[configuration]
        if not isinstance(rows, list):
            raise ValueError(f"{configuration} must be a list")
        ids = [row.get("case_id") for row in rows if isinstance(row, dict)]
        if len(ids) != len(expected) or set(ids) != expected or len(set(ids)) != len(expected):
            raise ValueError(f"{configuration} must contain each frozen case exactly once")
        for row in rows:
            if not isinstance(row.get("passed"), bool):
                raise ValueError(f"{configuration}/{row.get('case_id')} needs boolean passed")
            if float(row.get("latency_ms", -1)) < 0 or float(row.get("cost_usd", -1)) < 0:
                raise ValueError(f"{configuration}/{row.get('case_id')} has invalid cost or latency")


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * ratio)
    return ordered[index]


def _exact_sign_pvalue(positive: int, negative: int) -> float:
    """Two-sided exact binomial sign-test p value for discordant paired rows."""
    n = positive + negative
    if not n:
        return 1.0
    tail = sum(comb(n, count) for count in range(0, min(positive, negative) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _summary(rows: list[dict]) -> dict:
    latency = [float(row["latency_ms"]) for row in rows]
    failures = [row["case_id"] for row in rows if not row["passed"]]
    return {
        "n": len(rows),
        "pass_rate": sum(row["passed"] for row in rows) / len(rows),
        "latency_ms": {"p50": _percentile(latency, .50), "p95": _percentile(latency, .95)},
        "cost_usd": sum(float(row["cost_usd"]) for row in rows),
        "failed_case_ids": failures,
    }


def _paired(full: list[dict], ablation: list[dict]) -> dict:
    by_id = {row["case_id"]: row for row in ablation}
    deltas = [int(row["passed"]) - int(by_id[row["case_id"]]["passed"]) for row in full]
    positive, negative = deltas.count(1), deltas.count(-1)
    mean = sum(deltas) / len(deltas)
    spread = sqrt(sum((delta - mean) ** 2 for delta in deltas) / len(deltas))
    return {
        "n": len(deltas),
        "full_only_pass": positive,
        "ablation_only_pass": negative,
        "paired_pass_rate_delta": mean,
        "standardized_paired_effect": 0.0 if not spread else mean / spread,
        "exact_sign_test_pvalue": _exact_sign_pvalue(positive, negative),
    }


def analyze(payload: dict) -> dict:
    validate_matrix(payload)
    runs = payload["runs"]
    return {
        "dataset_version": payload["dataset_version"],
        "configurations": {configuration: _summary(runs[configuration]) for configuration in CONFIGURATIONS},
        "paired_against_full": {
            configuration: _paired(runs["full"], runs[configuration])
            for configuration in CONFIGURATIONS if configuration != "full"
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="complete raw 60×6 ablation JSON")
    parser.add_argument("--out", type=Path, required=True, help="explicit report output JSON")
    args = parser.parse_args()
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"configurations": len(report["configurations"]), "cases_per_configuration": 60}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
