"""Validate and summarize raw v2 component-ablation outputs without judging quality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

from evals.run_v2_component_ablation import CONFIGURATIONS
from evals.run_v2_deepseek_baseline import load_records

# ``attribution_comparison`` is the bounded executor's valid two-date form of
# the Router's ``attribution`` intent.  Keep it distinct from a real routing
# mismatch in the report.
_EXPECTED_TASKS = {
    "data_query": {"metric"},
    "cross_period": {"metric"},
    "attribution": {"attribution", "attribution_comparison"},
    "strategy": {"strategy"},
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * percentile) - 1)]


def analyze(payload: dict) -> dict:
    expected_ids = {row["id"] for row in load_records()}
    runtime = payload.get("runtime", {})
    if tuple(runtime.get("configurations", [])) != CONFIGURATIONS:
        raise ValueError("artifact configurations do not match the fixed component matrix")
    runs = payload.get("runs", {})
    if set(runs) != set(CONFIGURATIONS):
        raise ValueError("artifact must contain exactly four component arms")
    report = {"runtime": runtime, "configurations": {}, "quality_metric": "not computed; raw output only"}
    for configuration in CONFIGURATIONS:
        rows = runs[configuration]
        if set(rows) != expected_ids:
            missing, extra = sorted(expected_ids - set(rows)), sorted(set(rows) - expected_ids)
            raise ValueError(f"{configuration}: expected 80 unique rows; missing={missing} extra={extra}")
        values = list(rows.values())
        hard_errors = sorted(qid for qid, row in rows.items() if "error" in row)
        latency = [float(row["latency_ms"]) for row in values]
        usage = {key: sum(int(row.get("usage", {}).get(key, 0)) for row in values)
                 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        strategy_degraded = []
        for qid, row in rows.items():
            data = row.get("node_result", {}).get("data", {})
            if row.get("node_result", {}).get("task") == "strategy" and data.get("generation") != "llm":
                strategy_degraded.append({"id": qid, "generation": data.get("generation"),
                                          "rag_status": data.get("rag_status")})
        recalled_total = sum(len(row.get("recalled_memories", [])) for row in values)
        if configuration in {"full", "minus_rag"} and recalled_total == 0:
            raise ValueError(f"{configuration}: expected canonical recall, got none")
        if configuration in {"minus_memory", "bare"} and recalled_total != 0:
            raise ValueError(f"{configuration}: Memory disabled but recall was non-empty")
        expected_rag = "disabled_for_component_ablation" if configuration in {"minus_rag", "bare"} else None
        strategy_steps = [step for row in values for step in row.get("steps", []) if step.get("node") == "Strategy"]
        if expected_rag and any(step.get("data", {}).get("rag_status") != expected_rag for step in strategy_steps):
            raise ValueError(f"{configuration}: executed Strategy step has inconsistent RAG flag")
        routing_drift = sorted(qid for qid, row in rows.items()
                               if row.get("node_result", {}).get("task")
                               not in _EXPECTED_TASKS[row["query_type"]])
        report["configurations"][configuration] = {
            "n": len(values), "hard_errors": hard_errors, "strategy_degraded": strategy_degraded,
            "recalled_total": recalled_total, "usage_total": usage,
            "latency_ms": {"p50": round(median(latency), 3), "p95": round(_percentile(latency, .95), 3)},
            "routing_drift": routing_drift,
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
