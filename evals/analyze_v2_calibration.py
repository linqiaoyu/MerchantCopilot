"""Analyze frozen human-vs-Qwen calibration labels without calling either model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.calibration_metrics import calibration_gate


def analyze(payload: dict) -> dict[str, float | str]:
    binary = [(int(row["human"]), int(row["judge"])) for row in payload["binary"]]
    strategy = [(float(row["human"]), float(row["judge"])) for row in payload["strategy"]]
    return calibration_gate(binary, strategy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSON with binary/strategy paired human and judge ratings")
    parser.add_argument("--out", type=Path, help="optional report JSON path")
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
