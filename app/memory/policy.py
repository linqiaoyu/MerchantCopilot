"""Deterministic Memory policy primitives; persistence is added by the repository layer."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

FactStatus = Literal["active", "pending", "proposed_decision", "superseded", "rejected"]
FactType = Literal["observation", "user_fact", "inference", "decision", "outcome"]
FACT_TYPES = frozenset({"observation", "user_fact", "inference", "decision", "outcome"})


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    subject: str
    predicate: str
    value: Any
    source_type: str
    kind: str = "episodic"
    causal_inference: bool = False
    fact_type: str = ""
    thread_id: str | None = None
    scope_type: str = "merchant"
    scope_id: str | None = None
    observed_at: datetime | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    evidence_refs: tuple[str, ...] = ()
    truth_confidence: float = 1.0
    utility_score: float = 0.0
    contradiction_group_id: str | None = None
    approval_reason: str | None = None
    schema_version: int = 2


def resolved_fact_type(candidate: MemoryCandidate) -> FactType:
    explicit = candidate.fact_type.strip()
    if explicit:
        if explicit not in FACT_TYPES:
            raise ValueError(f"unsupported fact_type: {explicit}")
        return explicit  # type: ignore[return-value]
    if candidate.kind in {"strategy", "decision"}:
        return "decision"
    if candidate.kind == "outcome":
        return "outcome"
    if candidate.causal_inference or candidate.source_type in {"llm", "agent"}:
        return "inference"
    if candidate.source_type in {"user", "user_approved"}:
        return "user_fact"
    return "observation"


def validate_candidate(candidate: MemoryCandidate) -> None:
    fact_type = resolved_fact_type(candidate)
    if not candidate.subject.strip() or not candidate.predicate.strip():
        raise ValueError("memory subject and predicate are required")
    if candidate.scope_type not in {"merchant", "thread"}:
        raise ValueError("scope_type must be merchant or thread")
    if not 0.0 <= candidate.truth_confidence <= 1.0:
        raise ValueError("truth_confidence must be between 0 and 1")
    if not 0.0 <= candidate.utility_score <= 1.0:
        raise ValueError("utility_score must be between 0 and 1")
    if (candidate.effective_from is None) != (candidate.effective_to is None):
        raise ValueError("effective_from and effective_to must be supplied together")
    if candidate.effective_from and candidate.effective_to and candidate.effective_from >= candidate.effective_to:
        raise ValueError("effective memory range must be increasing")
    if candidate.schema_version >= 3 and fact_type in {"observation", "outcome"}:
        if candidate.source_type in {"mcp", "sql"} and not candidate.evidence_refs:
            raise ValueError("tool-derived observation/outcome requires evidence_refs")
    if fact_type == "outcome" and candidate.source_type not in {"mcp", "sql", "user_approved"}:
        raise ValueError("outcome requires tool evidence or explicit user approval")


def candidate_to_dict(candidate: MemoryCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "subject": candidate.subject,
        "predicate": candidate.predicate,
        "value": candidate.value,
        "source_type": candidate.source_type,
        "kind": candidate.kind,
        "causal_inference": candidate.causal_inference,
        "fact_type": resolved_fact_type(candidate),
        "thread_id": candidate.thread_id,
        "scope_type": candidate.scope_type,
        "scope_id": candidate.scope_id,
        "observed_at": candidate.observed_at.isoformat() if candidate.observed_at else None,
        "effective_from": candidate.effective_from.isoformat() if candidate.effective_from else None,
        "effective_to": candidate.effective_to.isoformat() if candidate.effective_to else None,
        "evidence_refs": list(candidate.evidence_refs),
        "truth_confidence": candidate.truth_confidence,
        "utility_score": candidate.utility_score,
        "contradiction_group_id": candidate.contradiction_group_id,
        "approval_reason": candidate.approval_reason,
        "schema_version": candidate.schema_version,
    }


def candidate_from_dict(payload: dict[str, Any]) -> MemoryCandidate:
    observed_at = payload.get("observed_at")
    effective_from = payload.get("effective_from")
    effective_to = payload.get("effective_to")
    return MemoryCandidate(
        candidate_id=str(payload["candidate_id"]), subject=str(payload["subject"]),
        predicate=str(payload["predicate"]), value=payload.get("value"),
        source_type=str(payload.get("source_type", "llm")), kind=str(payload.get("kind", "episodic")),
        causal_inference=bool(payload.get("causal_inference", False)),
        fact_type=str(payload.get("fact_type", "")), thread_id=payload.get("thread_id"),
        scope_type=str(payload.get("scope_type", "merchant")), scope_id=payload.get("scope_id"),
        observed_at=datetime.fromisoformat(observed_at) if observed_at else None,
        effective_from=datetime.fromisoformat(effective_from) if effective_from else None,
        effective_to=datetime.fromisoformat(effective_to) if effective_to else None,
        evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
        truth_confidence=float(payload.get("truth_confidence", 1.0)),
        utility_score=float(payload.get("utility_score", 0.0)),
        contradiction_group_id=payload.get("contradiction_group_id"),
        approval_reason=payload.get("approval_reason"),
        schema_version=int(payload.get("schema_version", 2)),
    )


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
    validate_candidate(candidate)
    fact_type = resolved_fact_type(candidate)
    if fact_type == "decision":
        return "active" if positive_feedback or candidate.source_type == "user_approved" else "proposed_decision"
    if fact_type == "inference":
        return "pending"
    if fact_type == "outcome":
        return "active"
    if fact_type == "user_fact" and candidate.source_type not in {"user", "user_approved"}:
        return "pending"
    if candidate.source_type in {"mcp", "sql", "user", "user_approved", "seed"}:
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
