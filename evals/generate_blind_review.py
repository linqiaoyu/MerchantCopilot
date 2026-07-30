"""Print the 60-case blind-review payload without ground-truth labels."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "datasets/v2.0/memory_sequences.json"


def blind_cases() -> list[dict]:
    cases = json.loads(DATA.read_text(encoding="utf-8"))["cases"]
    return [{"id": case["id"], "category": case["category"], "query": case["query"], "events": case["events"],
             "must_independently_judge": case["category"] in {"irrelevant_memory", "strategy_feedback_outcome"}}
            for case in cases]


if __name__ == "__main__":
    print(json.dumps(blind_cases(), ensure_ascii=False, indent=2))
