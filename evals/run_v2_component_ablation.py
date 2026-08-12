"""Checkpointed v2 component-ablation runner for the frozen historical corpus.

It records raw Agent outputs only. Strategy Judge is reference-only, and an
LLM Judge cannot replace canonical Memory metrics or independent human labels.
A caller supplies an isolated evaluation DSN with a declared canonical seed;
candidate extraction is disabled so this runner never mutates that database.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run_v2_deepseek_baseline import _usage_total, load_records

CONFIGURATIONS = ("full", "minus_memory", "minus_rag", "bare")


def evaluation_state(record: dict, configuration: str, merchant_id: str) -> dict:
    if configuration not in CONFIGURATIONS:
        raise ValueError(f"unknown component configuration: {configuration}")
    return {
        "user_query": record["query"], "merchant_id": merchant_id, "steps": [],
        "disable_memory_candidates": True,
        "disable_memory_recall": configuration in {"minus_memory", "bare"},
        "disable_rag": configuration in {"minus_rag", "bare"},
    }


def _contract(dsn: str, merchant_id: str) -> dict:
    return {
        "dataset": "historical-v1.0-v1.1-80", "model": "deepseek-v4-flash",
        "configurations": list(CONFIGURATIONS), "merchant_id": merchant_id,
        "database": "provided evaluation DSN" if dsn else "missing",
        "memory_candidate_extraction": "disabled",
        "judge": "not-called; raw Agent outputs only",
    }


def run(output: Path, *, dsn: str, merchant_id: str, limit: int | None = None) -> dict:
    if not dsn:
        raise ValueError("DATABASE_URL is required: full Memory needs a declared isolated evaluation seed")
    from app.agent.graph_v2 import build_graph_v2
    from app.llm.client import capture_usage

    records = load_records()
    if limit is not None:
        records = records[:limit]
    contract = _contract(dsn, merchant_id)
    payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {
        "runtime": contract, "runs": {name: {} for name in CONFIGURATIONS},
    }
    if payload.get("runtime") != contract:
        raise ValueError("existing artifact has a different runtime contract")
    graph = build_graph_v2()
    for configuration in CONFIGURATIONS:
        for index, record in enumerate(records, 1):
            existing = payload["runs"][configuration].get(record["id"])
            if existing and "error" not in existing:
                continue
            started = time.perf_counter()
            try:
                with capture_usage() as usage_rows:
                    state = graph.invoke(evaluation_state(record, configuration, merchant_id))
                payload["runs"][configuration][record["id"]] = {
                    "query_type": record["query_type"], "final_answer": state.get("final_answer", ""),
                    "node_result": state.get("node_result", {}), "recalled_memories": state.get("recalled_memories", []),
                    "steps": state.get("steps", []), "usage": _usage_total(usage_rows), "usage_calls": usage_rows,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            except Exception as exc:
                payload["runs"][configuration][record["id"]] = {
                    "query_type": record["query_type"], "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[{configuration} {index}/{len(records)}] {record['id']} done", flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merchant-id", default="eval-component-ablation")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    payload = run(args.output, dsn=os.environ.get("DATABASE_URL", "").strip(),
                  merchant_id=args.merchant_id, limit=args.limit)
    print(json.dumps({name: len(rows) for name, rows in payload["runs"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
