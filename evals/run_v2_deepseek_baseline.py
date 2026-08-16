"""Re-run the frozen historical 80-query corpus with the v2 DeepSeek graph.

This is a no-Memory baseline: DATABASE_URL must be empty, so no canonical
facts are recalled.  Every record, including errors, is checkpointed to JSON
after execution; it never reuses v1 scores or calls Qwen.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_records() -> list[dict]:
    files = [ROOT / "evals/datasets/v1.0/queries.jsonl"] + sorted(
        (ROOT / "evals/datasets/v1.1").glob("queries_v1.1_round*.jsonl")
    )
    records = [json.loads(line) for path in files for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 80 or len({record["id"] for record in records}) != 80:
        raise ValueError("historical baseline must contain exactly 80 unique records")
    return sorted(records, key=lambda record: record["id"])


def _usage_total(rows: list[dict]) -> dict[str, int]:
    return {key: sum(int(row["usage"].get(key, 0)) for row in rows) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def run(output: Path, *, limit: int | None = None) -> dict:
    from app.agent.graph_v2 import build_graph_v2
    from app.llm.client import capture_usage

    records = load_records()
    if limit is not None:
        records = records[:limit]
    contract = {"model": "deepseek-v4-flash", "memory": "disabled", "memory_candidate_extraction": "disabled"}
    payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {
        "dataset": "historical-v1.0-v1.1-80", "runtime": contract, "runs": {},
    }
    if payload.get("runtime") != contract:
        # Earlier runner checkpoints extracted candidates and are not a valid
        # no-Memory baseline.  Replace only this runner's own output artifact.
        payload = {"dataset": "historical-v1.0-v1.1-80", "runtime": contract, "runs": {}}
    graph = build_graph_v2()
    for index, record in enumerate(records, 1):
        if record["id"] in payload["runs"] and "error" not in payload["runs"][record["id"]]:
            continue
        started = time.perf_counter()
        try:
            with capture_usage() as usage_rows:
                state = graph.invoke({"user_query": record["query"], "merchant_id": "eval-no-memory",
                                      "disable_memory_candidates": True, "steps": []})
            node_result = state.get("node_result", {})
            payload["runs"][record["id"]] = {
                "query_type": record["query_type"], "final_answer": state.get("final_answer", ""),
                "node_result": node_result, "steps": state.get("steps", []),
                "usage": _usage_total(usage_rows), "usage_calls": usage_rows,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        except Exception as exc:
            payload["runs"][record["id"]] = {"query_type": record["query_type"], "error": f"{type(exc).__name__}: {exc}",
                                                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{index}/{len(records)}] {record['id']} done", flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    payload = run(args.output, limit=args.limit)
    print(json.dumps({"runs": len(payload["runs"]), "errors": sum("error" in value for value in payload["runs"].values())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
