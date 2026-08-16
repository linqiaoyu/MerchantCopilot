"""Re-derive frozen v2 RC1 labels from its event sequence.

This is only an internal-consistency check: it shares the annotation policy and
does not constitute independent human review or two-person sign-off.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "datasets/v2.0/memory_sequences.json"


def _fact_id(event_id: str) -> str:
    if event_id.endswith("-scratch"):
        return "scratch-" + event_id.removeprefix("evt-").removesuffix("-scratch")
    fact_id = event_id.replace("evt-", "fact-", 1)
    return fact_id.removesuffix("-proposed") + "-decision" if event_id.endswith("-proposed") else fact_id


def _truth(event: dict[str, Any], **extra: str) -> dict[str, str]:
    return {"fact_id": _fact_id(event["event_id"]), "subject": event["subject"],
            "predicate": event["predicate"], "value": event["value"],
            "valid_from_event_id": event["event_id"], **extra}


def derive_case(case: dict[str, Any]) -> dict[str, list[dict[str, str]] | list[str]]:
    """Apply the five frozen annotation rules without reading label fields."""
    events = sorted(case["events"], key=lambda event: event["occurred_at"])
    category = case["category"]
    forbidden: list[str] = []
    truths: list[dict[str, str]] = []
    if category == "temporal_conflict":
        active = [event for event in events if event["kind"] == "verified_fact" and event["status"] == "active"]
        latest = active[-1]
        forbidden = [_fact_id(event["event_id"]) for event in active[:-1]]
        truths = [_truth(latest, supersedes=_fact_id(active[-2]["event_id"]))]
    elif category == "cross_thread_recall":
        for event in events:
            if event["kind"] == "working_note" and event["thread_id"] != case["query_thread_id"]:
                forbidden.append(_fact_id(event["event_id"]))
            elif event["kind"] == "verified_fact" and event["status"] == "active":
                truths.append(_truth(event))
    elif category == "irrelevant_memory":
        for event in events:
            if event["event_id"].endswith("-noise"):
                forbidden.append(_fact_id(event["event_id"]))
            elif event["kind"] == "verified_fact" and event["status"] == "active":
                truths.append(_truth(event))
    elif category == "strategy_feedback_outcome":
        feedback = next(event for event in events if event["kind"] == "feedback" and event["value"] == "positive")
        decision = next(event for event in events if event["kind"] == "proposed_decision")
        outcome = next(event for event in events if event["kind"] == "verified_outcome")
        truths = [_truth(decision, requires_feedback_event_id=feedback["event_id"]),
                  _truth(outcome, links_to=_fact_id(decision["event_id"]))]
    else:
        truths = [_truth(event) for event in events if event["kind"] == "verified_fact" and event["status"] == "active"]
    return {"current_truth": truths, "expected_recall_ids": [truth["fact_id"] for truth in truths],
            "forbidden_memory_ids": forbidden,
            "expected_provenance": [{"memory_id": truth["fact_id"], "source_event_id": truth["valid_from_event_id"]}
                                    for truth in truths]}


def validate(cases: list[dict[str, Any]]) -> list[str]:
    fields = ("current_truth", "expected_recall_ids", "forbidden_memory_ids", "expected_provenance")
    return [f"{case['id']}: {field} differs from deterministic re-derivation"
            for case in cases for field in fields if derive_case(case)[field] != case[field]]


def main() -> int:
    errors = validate(json.loads(DATA.read_text(encoding="utf-8"))["cases"])
    print("OK" if not errors else "\n".join(errors))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
