"""Render every non-LLM strategy outcome in component-ablation raw outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.run_v2_component_ablation import CONFIGURATIONS


def render(payload: dict) -> str:
    lines = ["# v2 组件消融：Strategy 降级样本", "",
             "此清单来自原始运行工件，不以 Judge 分数替代失败记录。每行均为实际非 `llm` 的 Strategy 结果。", ""]
    for configuration in CONFIGURATIONS:
        rows = payload["runs"][configuration]
        failed = []
        for qid, row in sorted(rows.items()):
            data = row.get("node_result", {}).get("data", {})
            if row.get("node_result", {}).get("task") == "strategy" and data.get("generation") != "llm":
                failed.append((qid, data.get("generation"), data.get("rag_status"), row.get("latency_ms"),
                               (row.get("final_answer") or "").replace("\n", " ")[:100]))
        lines.extend([f"## {configuration}", "", f"降级：{len(failed)} / 80。", "",
                      "| qid | generation | rag_status | latency_ms | final_answer 前 100 字 |",
                      "|---|---|---|---:|---|"])
        lines.extend(f"| {qid} | {generation} | {rag_status} | {latency} | {answer} |"
                     for qid, generation, rag_status, latency, answer in failed)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(render(json.loads(args.input.read_text(encoding="utf-8"))), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
