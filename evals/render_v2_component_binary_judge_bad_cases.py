"""Render every calibrated binary-Judge failure from a complete T13 matrix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.run_v2_component_binary_judge import CONFIGURATIONS


def render(payload: dict) -> str:
    results = payload.get("results", {})
    if set(results) != set(CONFIGURATIONS):
        raise ValueError("artifact must contain exactly four component arms")
    lines = ["# v2 组件消融：calibrated binary Judge 失败样本", "",
             "Strategy 未进入本报告：其 Qwen 校准未达门槛，仍为 reference-only。", ""]
    for configuration in CONFIGURATIONS:
        rows = results[configuration]
        if len(rows) != 30 or any("error" in row for row in rows.values()):
            raise ValueError(f"{configuration}: binary Judge matrix is incomplete")
        failures = [(qid, row) for qid, row in sorted(rows.items()) if row["mode_score"] == 0]
        lines += [f"## {configuration}", "", f"失败：{len(failures)} / 30。", ""]
        for qid, row in failures:
            reasons = []
            for dimension, detail in row["samples"][0]["dimensions"].items():
                if int(detail["score"]) == 0:
                    reasons.append(f"{dimension}: {detail.get('reason', '')}")
            lines += [f"### {qid} ({row['query_type']})", "",
                      f"- 三次分数：`{row['scores']}`", f"- 首次失败维度：{'；'.join(reasons) or '聚合失败'}", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(render(json.loads(args.input.read_text(encoding="utf-8"))), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
