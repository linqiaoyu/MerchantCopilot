from evals.run_memory_v2 import fact_id, memory_kind, visible_events


def test_runner_applies_temporal_and_feedback_semantics_without_labels():
    temporal = {"category": "temporal_conflict", "events": [
        {"event_id": "evt-old", "occurred_at": "2026-01-01", "kind": "verified_fact", "status": "active"},
        {"event_id": "evt-new", "occurred_at": "2026-02-01", "kind": "verified_fact", "status": "active"},
    ]}
    rows = visible_events(temporal)
    assert rows[0]["status"] == "superseded" and rows[1]["status"] == "active"
    assert fact_id("evt-d-01-proposed") == "fact-d-01-decision"
    assert memory_kind({"category": "stable_profile"}, {"kind": "verified_fact"}) == "core"
