"""Mechanism-only four-way retrieval ablation on preregistered synthetic profiles."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.memory.retriever import RetrievedMemory, rank_ablation

VARIANTS = ("semantic_only", "temporal", "fixed_weight", "type_aware")


def _memory(identifier: str, now: datetime, *, semantic: float, age: int,
            importance: float, confidence: float, utility: float, fact_type: str) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=identifier, source_event_id=f"event-{identifier}", kind="episodic",
        content=identifier, semantic=semantic, importance=importance, confidence=confidence,
        valid_from=now - timedelta(days=age), fact_type=fact_type,
        truth_confidence=confidence, utility_score=utility,
    )


def run() -> dict:
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    rows = []
    for index in range(40):
        expected_type = "outcome" if index % 2 else "user_fact"
        memories = [
            _memory(f"case-{index}-current", now, semantic=.72, age=5, importance=.8,
                    confidence=.95, utility=.8, fact_type=expected_type),
            _memory(f"case-{index}-stale", now, semantic=.93, age=120, importance=.5,
                    confidence=.7, utility=.1, fact_type=expected_type),
            _memory(f"case-{index}-wrong-type", now, semantic=.85, age=1, importance=.5,
                    confidence=.6, utility=.1, fact_type="inference"),
        ]
        for variant in VARIANTS:
            ranked = rank_ablation(memories, now, variant=variant, requested_types={expected_type})
            rows.append({"case_id": f"retrieval-{index:02d}", "variant": variant,
                         "top1": ranked[0].memory_id, "correct": ranked[0].memory_id.endswith("-current")})
    metrics = {variant: sum(row["correct"] for row in rows if row["variant"] == variant) / 40
               for variant in VARIANTS}
    return {"kind": "mechanism_only_synthetic_ablation", "claim_eligible": False,
            "case_count": 40, "variants": list(VARIANTS), "top1_accuracy": metrics, "rows": rows}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = run()
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["top1_accuracy"], ensure_ascii=False))


if __name__ == "__main__":
    main()
