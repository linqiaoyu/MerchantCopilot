"""Analyze the Qwen recalibration artifact without hiding unresolved samples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.calibration_metrics import calibration_gate


def analyze(payload: dict) -> dict:
    binary = [(int(row["human"]), int(row["judge"])) for row in payload["pairs"]["binary"]]
    strategy = [(float(row["human"]), float(row["judge"])) for row in payload["pairs"]["strategy"]]
    result = calibration_gate(binary, strategy)
    unresolved = payload.get("unresolved_ids", [])
    result.update({
        "binary_pairs": len(binary),
        "strategy_pairs_resolved": len(strategy),
        "strategy_pairs_expected": 12,
        "unresolved_ids": unresolved,
    })
    if unresolved:
        result["strategy_mode"] = "reference-only"
        result["strategy_gate_reason"] = "unresolved Qwen samples prevent complete 12-pair calibration"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
