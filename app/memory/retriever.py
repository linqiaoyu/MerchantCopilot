"""Memory retrieval scoring and context assembly, independent of a vector-store backend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

MIN_TOPIC_RELEVANCE = 0.30


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


def _topic_tokens(text: str) -> set[str]:
    """Conservative bilingual topic terms without a second model instance."""
    tokens: set[str] = set()
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    tokens.update(term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}", text))
    return tokens


def topic_related(query: str, memory: RetrievedMemory) -> bool:
    """Block explicit cross-topic injections while preserving stable Core context."""
    if memory.kind == "core":
        return True
    query_terms = _topic_tokens(query)
    return not query_terms or bool(query_terms.intersection(_topic_tokens(memory.content)))


def select(memories: list[RetrievedMemory], kind: str, now: datetime, query: str = "") -> list[RetrievedMemory]:
    # pgvector 的候选数量允许多主题历史混入；固定相关性门槛先阻断
    # 低语义相关记忆，之后才应用 recency/importance/confidence 的排序。
    # 此值是实现契约，不从冻结 RC1 的结果反调。
    active = [
        memory for memory in memories
        if memory.kind == kind
        and memory.status == "active"
        and memory.valid_to is None
        and memory.semantic >= MIN_TOPIC_RELEVANCE
        and topic_related(query, memory)
    ]
    limit = {"core": 8, "episodic": 5, "decision": 3, "outcome": 3}[kind]
    return sorted(active, key=lambda m: score(m, now), reverse=True)[:limit]


def assemble_context(memories: list[RetrievedMemory], now: datetime, query: str = "") -> list[dict]:
    selected = [*select(memories, "core", now, query), *select(memories, "episodic", now, query),
                *select(memories, "decision", now, query), *select(memories, "outcome", now, query)]
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
