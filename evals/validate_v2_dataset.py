"""Validate the frozen v2.0 Memory evaluation dataset without external dependencies."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "datasets" / "v2.0" / "memory_sequences.json"
EXPECTED = {
    "stable_profile": 20,
    "temporal_conflict": 15,
    "cross_thread_recall": 10,
    "irrelevant_memory": 10,
    "strategy_feedback_outcome": 5,
}


def validate(dataset: dict) -> list[str]:
    errors: list[str] = []
    cases = dataset.get("cases")
    if dataset.get("version") != "eval-dataset-v2.0-rc1":
        errors.append("version must be eval-dataset-v2.0-rc1")
    if not isinstance(cases, list) or len(cases) != 60:
        return errors + ["cases must contain exactly 60 records"]

    ids = [case.get("id") for case in cases]
    if len(set(ids)) != len(ids) or any(not item for item in ids):
        errors.append("case IDs must be present and unique")
    counts = Counter(case.get("category") for case in cases)
    if counts != EXPECTED:
        errors.append(f"category counts mismatch: {dict(counts)}")

    required = {
        "id", "category", "merchant_id", "query_thread_id", "query", "events",
        "current_truth", "expected_recall_ids", "forbidden_memory_ids", "expected_provenance",
    }
    for case in cases:
        missing = required - set(case)
        if missing:
            errors.append(f"{case.get('id')}: missing {sorted(missing)}")
            continue
        events = case["events"]
        if not events or any(not event.get("event_id") or not event.get("occurred_at") for event in events):
            errors.append(f"{case['id']}: every event requires id and occurred_at")
        event_ids = {event["event_id"] for event in events}
        facts = {truth["fact_id"] for truth in case["current_truth"]}
        expected = set(case["expected_recall_ids"])
        forbidden = set(case["forbidden_memory_ids"])
        if not expected <= facts:
            errors.append(f"{case['id']}: expected recall must be current truth")
        if expected & forbidden:
            errors.append(f"{case['id']}: expected and forbidden IDs overlap")
        for provenance in case["expected_provenance"]:
            if provenance.get("memory_id") not in expected or provenance.get("source_event_id") not in event_ids:
                errors.append(f"{case['id']}: invalid expected provenance")
        if case["category"] == "temporal_conflict":
            if len(events) != 2 or not case["forbidden_memory_ids"]:
                errors.append(f"{case['id']}: temporal case requires replacement and stale fact")
        if case["category"] == "cross_thread_recall":
            source_threads = {event.get("thread_id") for event in events}
            if case["query_thread_id"] in source_threads:
                errors.append(f"{case['id']}: cross-thread query must use a new thread")
        if case["category"] == "strategy_feedback_outcome":
            kinds = {event.get("kind") for event in events}
            if not {"proposed_decision", "feedback", "verified_outcome"} <= kinds:
                errors.append(f"{case['id']}: decision sequence is incomplete")
    return errors


def main() -> int:
    errors = validate(json.loads(DATASET.read_text(encoding="utf-8")))
    if errors:
        print("\n".join(errors))
        return 1
    print("OK: 60 frozen v2.0 Memory sequences; category distribution validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
