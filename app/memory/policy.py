"""Deterministic Memory policy primitives; persistence is added by the repository layer."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

FactStatus = Literal["active", "pending", "proposed_decision", "superseded"]


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    subject: str
    predicate: str
    value: str
    source_type: str
    kind: str = "episodic"
    causal_inference: bool = False


@dataclass(frozen=True)
class CanonicalFact:
    memory_id: str
    subject: str
    predicate: str
    value: str
    status: FactStatus
    source_event_id: str
    valid_to: str | None = None
    index_status: str = "pending"


def gate_candidate(candidate: MemoryCandidate, positive_feedback: bool = False) -> FactStatus:
    """Policy gate: only verified tool facts can activate without human feedback."""
    if candidate.kind == "strategy":
        return "active" if positive_feedback else "proposed_decision"
    if candidate.causal_inference or candidate.source_type == "llm":
        return "pending"
    if candidate.source_type in {"mcp", "sql", "user_approved", "seed"}:
        return "active"
    return "pending"


def resolve_temporal(existing: list[CanonicalFact], incoming: CanonicalFact, closed_at: str) -> list[CanonicalFact]:
    """Append incoming fact and close only active facts with same subject/predicate."""
    resolved = [
        replace(item, status="superseded", valid_to=closed_at)
        if item.status == "active" and item.valid_to is None
        and item.subject == incoming.subject and item.predicate == incoming.predicate
        else item
        for item in existing
    ]
    return [*resolved, incoming]


def eligible_for_reuse(fact: CanonicalFact) -> bool:
    return fact.status == "active" and fact.valid_to is None


def mark_index_result(fact: CanonicalFact, succeeded: bool) -> CanonicalFact:
    """Canonical fact is retained when vector indexing fails and retried later."""
    return replace(fact, index_status="indexed" if succeeded else "pending")


def pending_index_facts(facts: list[CanonicalFact]) -> list[CanonicalFact]:
    return [fact for fact in facts if fact.index_status == "pending" and fact.status == "active"]
