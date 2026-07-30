"""Internal consistency re-derivation; not independent human review."""
from __future__ import annotations
import json
from pathlib import Path

DATA = Path(__file__).parent / "datasets/v2.0/memory_sequences.json"

def main() -> int:
    cases = json.loads(DATA.read_text())["cases"]
    errors = []
    for case in cases:
        events = {e["event_id"] for e in case["events"]}
        if any(t["valid_from_event_id"] not in events for t in case["current_truth"]):
            errors.append(case["id"] + ": unknown source event")
        if case["category"] == "temporal_conflict" and (not case["forbidden_memory_ids"] or not any("supersedes" in t for t in case["current_truth"])):
            errors.append(case["id"] + ": temporal supersession missing")
    print("OK" if not errors else "\n".join(errors))
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
