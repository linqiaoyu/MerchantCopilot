"""Typed candidate extraction: model structures provenance, policy decides reuse."""
from __future__ import annotations

from copy import deepcopy

from app.llm.client import get_llm
from app.memory.policy import MemoryCandidate

_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"}, "predicate": {"type": "string"},
                "value": {"type": "string"}, "kind": {"type": "string"},
                "fact_type": {"type": "string", "enum": ["observation", "user_fact", "inference", "decision", "outcome"]},
                "causal_inference": {"type": "boolean"},
                "truth_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["subject", "predicate", "value", "kind", "fact_type", "causal_inference", "truth_confidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["candidates"], "additionalProperties": False,
}


def extract_candidates(
    run_id: str, text: str, source_type: str = "llm",
    thread_id: str | None = None, merchant_id: str | None = None,
    evidence_refs: list[str] | tuple[str, ...] = (),
    allowed_fact_types: tuple[str, ...] | None = None,
) -> list[MemoryCandidate]:
    """Extract bounded candidates; extraction failure cannot invalidate an answer.

    Candidate extraction follows evidence verification.  A malformed model JSON
    must result in no candidate for the policy gate, not an Agent-run failure.
    """
    llm = get_llm()
    if llm.is_stub:
        return []
    try:
        schema = deepcopy(_SCHEMA)
        if allowed_fact_types:
            schema["properties"]["candidates"]["items"]["properties"]["fact_type"]["enum"] = list(allowed_fact_types)
        payload, _ = llm.complete_json(
            "Extract durable merchant-memory candidates. Return JSON only; do not invent facts.",
            text, schema, thinking=False,
        )
    except Exception:
        return []
    candidates = [
        MemoryCandidate(
            candidate_id=f"{run_id}:{index}", subject=item["subject"], predicate=item["predicate"],
            value=item["value"], source_type=source_type, kind=item["kind"],
            causal_inference=item["causal_inference"],
            fact_type=item["fact_type"], thread_id=thread_id,
            scope_type="merchant", scope_id=merchant_id,
            evidence_refs=tuple(evidence_refs),
            truth_confidence=float(item["truth_confidence"]), schema_version=3,
        )
        for index, item in enumerate(payload["candidates"])
        if source_type != "user" or str(item["value"]).strip() in text
    ]
    return candidates
