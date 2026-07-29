"""Memory retrieval scoring and context assembly, independent of a vector-store backend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RetrievedMemory:
    memory_id: str
    source_event_id: str
    kind: str
    content: str
    semantic: float
    importance: float
    confidence: float
    valid_from: datetime
    valid_to: datetime | None = None
    status: str = "active"


def score(memory: RetrievedMemory, now: datetime) -> float:
    age_days = max((now - memory.valid_from).total_seconds() / 86400, 0)
    recency = max(0.0, 1.0 - age_days / 90)
    return .55 * memory.semantic + .20 * recency + .15 * memory.importance + .10 * memory.confidence


def select(memories: list[RetrievedMemory], kind: str, now: datetime) -> list[RetrievedMemory]:
    active = [m for m in memories if m.kind == kind and m.status == "active" and m.valid_to is None]
    limit = {"core": 8, "episodic": 5, "decision": 3, "outcome": 3}[kind]
    return sorted(active, key=lambda m: score(m, now), reverse=True)[:limit]


def assemble_context(memories: list[RetrievedMemory], now: datetime) -> list[dict]:
    selected = [*select(memories, "core", now), *select(memories, "episodic", now),
                *select(memories, "decision", now), *select(memories, "outcome", now)]
    core_chars = 0
    rows = []
    for memory in selected:
        if memory.kind == "core":
            remaining = 800 - core_chars
            if remaining <= 0:
                continue
            content = memory.content[:remaining]
            core_chars += len(content)
        else:
            content = memory.content
        rows.append({"memory_id": memory.memory_id, "source_event_id": memory.source_event_id,
                     "kind": memory.kind, "content": content})
    return rows
