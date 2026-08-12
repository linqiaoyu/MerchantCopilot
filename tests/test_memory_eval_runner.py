from evals.run_memory_v2 import CONFIGURATIONS, fact_id, memory_kind, visible_events


def test_runner_applies_temporal_and_feedback_semantics_without_labels():
    temporal = {"category": "temporal_conflict", "events": [
        {"event_id": "evt-old", "occurred_at": "2026-01-01", "kind": "verified_fact", "status": "active"},
        {"event_id": "evt-new", "occurred_at": "2026-02-01", "kind": "verified_fact", "status": "active"},
    ]}
    rows = visible_events(temporal)
    assert rows[0]["status"] == "superseded" and rows[1]["status"] == "active"
    assert fact_id("evt-d-01-proposed") == "fact-d-01-decision"
    assert memory_kind({"category": "stable_profile"}, {"kind": "verified_fact"}) == "core"


def test_preregistered_ablation_inputs_are_distinct_and_do_not_read_expected_labels():
    case = {"category": "temporal_conflict", "events": [
        {"event_id": "old", "occurred_at": "2026-01-01", "kind": "verified_fact", "status": "active"},
        {"event_id": "new", "occurred_at": "2026-02-01", "kind": "verified_fact", "status": "active"},
    ], "expected_recall_ids": ["not-used"], "forbidden_memory_ids": ["not-used"]}
    assert set(CONFIGURATIONS) == {"full", "minus_memory", "minus_rag", "bare", "raw_history", "no_temporal_policy"}
    assert visible_events(case, "minus_memory") == []
    assert visible_events(case, "bare") == []
    assert [event["status"] for event in visible_events(case, "full")] == ["superseded", "active"]
    assert [event["status"] for event in visible_events(case, "raw_history")] == ["active", "active"]
    assert visible_events(case, "minus_rag") == visible_events(case, "full")
