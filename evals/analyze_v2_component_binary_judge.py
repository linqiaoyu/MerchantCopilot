"""Summarize checkpointed calibrated binary Judge scores for v2 ablation."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from evals.run_v2_component_ablation import CONFIGURATIONS


def _mcnemar_exact(discordant_full_only: int, discordant_other_only: int) -> float:
    n = discordant_full_only + discordant_other_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(discordant_full_only, discordant_other_only) + 1))
    return min(1.0, 2 * tail / (2 ** n))


def analyze(payload: dict) -> dict:
    runtime = payload.get("runtime", {})
    if tuple(runtime.get("configurations", [])) != CONFIGURATIONS:
        raise ValueError("artifact configurations do not match the fixed component matrix")
    results = payload.get("results", {})
    if set(results) != set(CONFIGURATIONS):
        raise ValueError("artifact must contain exactly four component arms")
    output = {"runtime": runtime, "configurations": {}, "paired_against_full": {}}
    scores_by_config: dict[str, dict[str, int]] = {}
    for configuration in CONFIGURATIONS:
        rows = results[configuration]
        errors = sorted(qid for qid, row in rows.items() if row.get("error"))
        scores = {qid: int(row["mode_score"]) for qid, row in rows.items() if "mode_score" in row}
        if len(rows) != 30 or errors or len(scores) != 30:
            raise ValueError(f"{configuration}: incomplete binary Judge artifact rows={len(rows)} errors={errors}")
        scores_by_config[configuration] = scores
        by_type = {}
        for query_type in ("data_query", "cross_period", "attribution"):
            typed = [int(row["mode_score"]) for row in rows.values() if row["query_type"] == query_type]
            by_type[query_type] = {"n": len(typed), "passed": sum(typed), "pass_rate": sum(typed) / len(typed)}
        output["configurations"][configuration] = {
            "n": len(scores), "passed": sum(scores.values()), "pass_rate": sum(scores.values()) / len(scores),
            "by_query_type": by_type,
        }
    for configuration in CONFIGURATIONS[1:]:
        full, other = scores_by_config["full"], scores_by_config[configuration]
        full_only = sum(full[qid] == 1 and other[qid] == 0 for qid in full)
        other_only = sum(full[qid] == 0 and other[qid] == 1 for qid in full)
        output["paired_against_full"][configuration] = {
            "full_only_pass": full_only, "other_only_pass": other_only,
            "mcnemar_exact_two_sided_p": _mcnemar_exact(full_only, other_only),
        }
    return output


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
