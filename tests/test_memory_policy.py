from __future__ import annotations

import pytest

from app.memory.policy import (
    CanonicalFact, MemoryCandidate, eligible_for_reuse, gate_candidate,
    mark_index_result, pending_index_facts, resolve_temporal,
)


@pytest.mark.parametrize("source,status", [
    ("mcp", "active"), ("sql", "active"), ("user_approved", "active"), ("seed", "active"),
] * 10)
def test_policy_gate_verified_facts_activate(source, status):
    candidate = MemoryCandidate("c", "merchant", "category", "女装", source)
    assert gate_candidate(candidate) == status


@pytest.mark.parametrize("source", ["llm", "agent", "unknown", "llm", "agent"] * 2)
def test_policy_gate_inferences_stay_pending(source):
    candidate = MemoryCandidate("c", "merchant", "cause", "投流导致下滑", source, causal_inference=True)
    assert gate_candidate(candidate) == "pending"


def test_strategy_requires_positive_feedback_before_reuse():
    candidate = MemoryCandidate("c", "strategy", "recommendation", "缩窄定向", "llm", kind="strategy")
    assert gate_candidate(candidate) == "proposed_decision"
    assert gate_candidate(candidate, positive_feedback=True) == "active"


def test_temporal_update_supersedes_old_fact_and_preserves_event():
    old = CanonicalFact("old", "merchant", "audience", "学生", "active", "event-old", index_status="indexed")
    new = CanonicalFact("new", "merchant", "audience", "职场新人", "active", "event-new")
    facts = resolve_temporal([old], new, "2026-05-01T00:00:00Z")
    assert facts[0].status == "superseded"
    assert facts[0].valid_to is not None
    assert facts[0].source_event_id == "event-old"
    assert eligible_for_reuse(facts[1])


def test_index_failure_is_recoverable_and_compensated():
    fact = CanonicalFact("m", "merchant", "style", "实穿", "active", "event")
    failed = mark_index_result(fact, False)
    assert pending_index_facts([failed]) == [failed]
    assert mark_index_result(failed, True).index_status == "indexed"
