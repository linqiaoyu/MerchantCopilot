"""Validate and summarize a complete 80-case DeepSeek v4 Flash baseline run."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run_v2_deepseek_baseline import load_records


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * ratio)]


def analyze(payload: dict) -> dict:
    expected = {record["id"] for record in load_records()}
    runs = payload.get("runs", {})
    if payload.get("runtime") != {"model": "deepseek-v4-flash", "memory": "disabled", "memory_candidate_extraction": "disabled"}:
        raise ValueError("input is not the fixed no-Memory DeepSeek baseline")
    if set(runs) != expected:
        raise ValueError("input must contain every historical query exactly once")
    errors = {query_id: row["error"] for query_id, row in runs.items() if "error" in row}
    completed = [row for row in runs.values() if "error" not in row]
    if errors:
        raise ValueError(f"input contains {len(errors)} failed runs")
    usage = {key: sum(row["usage"][key] for row in completed) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    by_type = Counter(row["query_type"] for row in completed)
    return {
        "dataset": payload["dataset"], "model": payload["runtime"]["model"], "n": len(completed),
        "errors": errors, "by_query_type": dict(sorted(by_type.items())), "usage": usage,
        "latency_ms": {"p50": _percentile([row["latency_ms"] for row in completed], .5),
                       "p95": _percentile([row["latency_ms"] for row in completed], .95)},
        "cost_usd": "not derivable from API responses; reconcile recorded tokens against provider billing",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": report["n"], "errors": len(report["errors"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
