"""Structured Memory-candidate extraction using DeepSeek non-thinking mode."""
from __future__ import annotations

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
                "causal_inference": {"type": "boolean"},
            },
            "required": ["subject", "predicate", "value", "kind", "causal_inference"],
            "additionalProperties": False,
        }},
    },
    "required": ["candidates"], "additionalProperties": False,
}


def extract_candidates(run_id: str, text: str, source_type: str = "llm") -> list[MemoryCandidate]:
    """Extract bounded candidates; extraction failure cannot invalidate an answer.

    Candidate extraction follows evidence verification.  A malformed model JSON
    must result in no candidate for the policy gate, not an Agent-run failure.
    """
    llm = get_llm()
    if llm.is_stub:
        return []
    try:
        payload, _ = llm.complete_json(
            "Extract durable merchant-memory candidates. Return JSON only; do not invent facts.",
            text, _SCHEMA, thinking=False,
        )
    except Exception:
        return []
    return [
        MemoryCandidate(
            candidate_id=f"{run_id}:{index}", subject=item["subject"], predicate=item["predicate"],
            value=item["value"], source_type=source_type, kind=item["kind"],
            causal_inference=item["causal_inference"],
        )
        for index, item in enumerate(payload["candidates"])
    ]
