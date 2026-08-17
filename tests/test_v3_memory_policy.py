from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.memory.policy import MemoryCandidate, candidate_from_dict, candidate_to_dict, gate_candidate


@pytest.mark.parametrize("case", range(100))
def test_v3_inference_never_activates_across_100_policy_scenarios(case):
    candidate = MemoryCandidate(
        candidate_id=f"c-{case}", subject="merchant", predicate=f"inference-{case}",
        value="plausible but unverified", source_type="llm", fact_type="inference",
        truth_confidence=(case % 11) / 10, schema_version=3,
    )
    assert gate_candidate(candidate) == "pending"


def test_tool_observation_without_evidence_is_rejected():
    candidate = MemoryCandidate(
        "c", "merchant", "gmv", "100", "sql", fact_type="observation", schema_version=3,
    )
    with pytest.raises(ValueError, match="requires evidence"):
        gate_candidate(candidate)


def test_invalid_fact_type_and_partial_effective_range_are_rejected():
    with pytest.raises(ValueError, match="unsupported fact_type"):
        gate_candidate(MemoryCandidate("c", "m", "p", "v", "user", fact_type="belief"))
    with pytest.raises(ValueError, match="supplied together"):
        gate_candidate(MemoryCandidate(
            "c", "m", "p", "v", "user", fact_type="user_fact",
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))


def test_v3_candidate_round_trip_preserves_temporal_and_evidence_fields():
    candidate = MemoryCandidate(
        "c", "m", "gmv", "100", "sql", fact_type="observation",
        evidence_refs=("sql:q1",), schema_version=3,
        utility_score=0.7, contradiction_group_id="00000000-0000-0000-0000-000000000001",
        approval_reason="verified SQL evidence",
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert candidate_from_dict(candidate_to_dict(candidate)) == candidate
