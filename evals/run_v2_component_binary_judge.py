"""Checkpointed Qwen binary evaluation for the frozen v2 component matrix.

Strategy is deliberately excluded: the fixed Qwen snapshot did not meet the
strategy calibration gate.  The historical binary calibration did pass, so
these outputs are a calibrated *reference metric*, not a replacement for
deterministic Memory metrics or human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.client import capture_usage  # noqa: E402
from evals.judge import judge_client, judge_one  # noqa: E402
from evals.run_v2_component_ablation import CONFIGURATIONS  # noqa: E402
from evals.run_v2_deepseek_baseline import load_records  # noqa: E402

BINARY_TYPES = {"data_query", "cross_period", "attribution"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _usage_total(rows: list[dict]) -> dict[str, int]:
    return {key: sum(int(row.get("usage", {}).get(key, 0)) for row in rows)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _agent_output(row: dict) -> dict:
    result = row.get("node_result", {})
    return {
        "final_answer": row.get("final_answer", ""),
        "evidence": result.get("evidence", []),
        "node_data": result.get("data", {}),
        "retrieved_chunks": result.get("data", {}).get("retrieved_chunks", []),
    }


def _contract(source: Path, client, samples: int) -> dict:
    return {
        "source": str(source.relative_to(ROOT)),
        "source_sha256": _sha256(source),
        "configurations": list(CONFIGURATIONS),
        "query_scope": "30 frozen historical binary queries only; strategy excluded (reference-only)",
        "judge_provider": client.provider,
        "judge_model": client.model,
        "samples_per_output": samples,
        "calibration": "binary alpha=1.0 on 18 independent historical labels; strategy is not scored",
    }


def run(source: Path, checkpoint: Path, *, samples: int = 3) -> dict:
    if samples < 1:
        raise ValueError("samples must be positive")
    source = source.resolve()
    checkpoint = checkpoint.resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if tuple(payload.get("runtime", {}).get("configurations", [])) != CONFIGURATIONS:
        raise ValueError("source must be the fixed four-arm component artifact")
    records = {row["id"]: row for row in load_records() if row["query_type"] in BINARY_TYPES}
    if len(records) != 30:
        raise ValueError(f"expected 30 binary frozen records, got {len(records)}")
    client = judge_client()
    contract = _contract(source, client, samples)
    result = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
        "runtime": contract, "results": {configuration: {} for configuration in CONFIGURATIONS},
    }
    if result.get("runtime") != contract:
        raise ValueError("checkpoint has a different source, Judge, or sampling contract")
    for configuration in CONFIGURATIONS:
        rows = result["results"].setdefault(configuration, {})
        for index, qid in enumerate(sorted(records), 1):
            if qid in rows:
                print(f"[{configuration} {index}/30] {qid} checkpointed", flush=True)
                continue
            raw = payload["runs"][configuration].get(qid)
            if raw is None or raw.get("error"):
                rows[qid] = {"error": raw.get("error", "missing Agent output") if raw else "missing Agent output"}
            else:
                judged, usage = [], []
                try:
                    for _ in range(samples):
                        with capture_usage() as usage_rows:
                            judged.append(judge_one(records[qid], _agent_output(raw), client=client, timeout=90.0))
                        usage.extend(usage_rows)
                    scores = [item["score"] for item in judged]
                    rows[qid] = {"query_type": records[qid]["query_type"], "scores": scores,
                                 "mode_score": Counter(scores).most_common(1)[0][0],
                                 "samples": judged, "usage": _usage_total(usage)}
                except Exception as exc:
                    rows[qid] = {"query_type": records[qid]["query_type"],
                                 "error": f"{type(exc).__name__}: {exc}"}
            checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[{configuration} {index}/30] {qid} score={rows[qid].get('scores')} "
                  f"error={rows[qid].get('error')}", flush=True)
    result["usage_total"] = _usage_total([
        row for configuration in CONFIGURATIONS for row in result["results"][configuration].values()
    ])
    checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    result = run(args.source, args.out, samples=args.samples)
    print(json.dumps({"out": str(args.out), "usage_total": result["usage_total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
