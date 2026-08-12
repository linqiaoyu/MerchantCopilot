"""Render an auditable bad-case report from a complete v2 Memory matrix.

The renderer is deterministic: it never calls a model or redacts failed rows.
It compares each configuration with the full arm and exposes recall, forbidden
recall and provenance for every differential failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.analyze_v2_ablation import CONFIGURATIONS, validate_matrix


def render(matrix: dict) -> str:
    validate_matrix(matrix)
    rows = matrix["runs"]
    full = {row["case_id"]: row for row in rows["full"]}
    lines = [
        "# v2 Memory 60×6 bad-case report", "",
        f"数据集：`{matrix['dataset_version']}`。此报告仅评估 canonical retrieval；"
        "不把 RAG 或 Qwen Judge 的未运行结果写入其中。", "",
    ]
    for configuration in CONFIGURATIONS:
        if configuration == "full":
            continue
        failed = [row for row in rows[configuration] if full[row["case_id"]]["passed"] and not row["passed"]]
        categories = Counter(row["result"]["category"] for row in failed)
        lines.extend([
            f"## {configuration}", "",
            f"相对 full 的失败：{len(failed)}/60。类别："
            + ("、".join(f"{name} {count}" for name, count in sorted(categories.items())) if categories else "无"), "",
        ])
        if not failed:
            lines.append("无差异失败；该配置未改变 canonical retrieval 指标。")
            lines.append("")
            continue
        lines.extend(["| case | category | expected | recalled | forbidden recalled | provenance |", "|---|---|---|---|---|---|"])
        for row in failed:
            result = row["result"]
            lines.append(
                f"| {row['case_id']} | {result['category']} | {', '.join(result['expected_ids']) or '—'} | "
                f"{', '.join(result['recalled_ids']) or '—'} | {', '.join(result['forbidden_recalled']) or '—'} | "
                f"{'ok' if result['provenance_ok'] else 'missing'} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    matrix = json.loads(args.input.read_text(encoding="utf-8"))
    args.out.write_text(render(matrix), encoding="utf-8")
    print("bad-case report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
