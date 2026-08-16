"""Produce the preregistered 60×6 deterministic Memory retrieval matrix.

This is intentionally separate from model/Judge evaluation: every row is a
canonical pgvector recall result, costs are exactly zero, and no missing or
failed run is filled in.  The output is accepted by analyze_v2_ablation.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.analyze_v2_ablation import CONFIGURATIONS
from evals.run_memory_v2 import DATA, run_case


def run_matrix(dsn: str, dataset: dict, embedder) -> dict:
    runs: dict[str, list[dict]] = {configuration: [] for configuration in CONFIGURATIONS}
    with psycopg.connect(dsn) as conn:
        for configuration in CONFIGURATIONS:
            for case in dataset["cases"]:
                started = time.perf_counter()
                try:
                    result = run_case(conn, case, embedder, configuration)
                    runs[configuration].append({
                        "case_id": case["id"], "passed": result["passed"],
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "cost_usd": 0.0, "result": result,
                    })
                finally:
                    # Every case is isolated and leaves the demo ledger untouched.
                    conn.rollback()
    return {"dataset_version": dataset["version"], "metric": "canonical_retrieval", "runs": runs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required for pgvector evaluation")
    from app.rag.indexer import get_embedder

    dataset = json.loads(DATA.read_text(encoding="utf-8"))
    matrix = run_matrix(dsn, dataset, get_embedder())
    args.output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"configurations": len(matrix["runs"]), "cases_per_configuration": len(dataset["cases"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
