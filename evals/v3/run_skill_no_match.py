"""Frozen no-Skill safety regression for generic requests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.agent.nodes.router import _rule_intent
from app.skills.registry import PostgresSkillRegistry, SkillRegistry
from app.skills.selector import select_skill


def build_cases() -> list[dict]:
    rows = []
    for index in range(10):
        day = index + 1
        rows.extend([
            {"case_id": f"plain-gmv-{index:02d}", "query": f"2026-04-{day:02d} GMV 怎么样"},
            {"case_id": f"plain-uv-{index:02d}", "query": f"查一下 2026-04-{day:02d} UV 数据"},
            {"case_id": f"generic-{index:02d}", "query": f"第{day}场直播数据给我看一下"},
        ])
    return rows


def canonical_hash(cases: list[dict]) -> str:
    raw = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def run(*, dsn: str, out: Path) -> dict:
    cases = build_cases()
    registries = {"static": SkillRegistry(), "evolved": PostgresSkillRegistry(dsn)}
    rows = []
    for name, registry in registries.items():
        metadata = registry.discover()
        for case in cases:
            selected = select_skill(case["query"], _rule_intent(case["query"]), metadata)
            rows.append({"case_id": case["case_id"], "registry": name,
                         "selected_skill_id": selected["id"] if selected else None,
                         "wrong_skill_injection": selected is not None})
    payload = {
        "kind": "formal_deterministic_no_match_regression", "case_count": len(cases),
        "dataset_hash": canonical_hash(cases), "rows": rows,
        "wrong_skill_injection_rate": sum(row["wrong_skill_injection"] for row in rows) / len(rows),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(dsn=args.dsn, out=args.out)
    print(json.dumps({"rows": len(result["rows"]),
                      "wrong_skill_injection_rate": result["wrong_skill_injection_rate"]}))


if __name__ == "__main__":
    main()
