"""Memory retrieval scoring and context assembly, independent of a vector-store backend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    subject: str = ""
    predicate: str = ""
    fact_type: str = "observation"
    scope_type: str = "merchant"
    scope_id: str = ""
    truth_confidence: float = 1.0
    utility_score: float = 0.0
    observed_at: datetime | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


def build_query_plan(query: str, intent: str = "") -> dict:
    """Create deterministic hard filters before vector retrieval."""
    lower = query.lower()
    requested_types: list[str] = []
    if any(term in lower for term in ("效果", "结果", "复盘", "outcome")):
        requested_types.extend(["decision", "outcome"])
    if any(term in lower for term in ("偏好", "客群", "类目", "画像")):
        requested_types.extend(["user_fact", "observation"])
    if intent == "strategy" or any(term in lower for term in ("建议", "策略", "怎么", "实验")):
        requested_types.extend(["user_fact", "observation", "decision", "outcome"])
    raw_dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", query)
    parsed_dates = sorted(datetime.fromisoformat(item).replace(tzinfo=timezone.utc) for item in raw_dates)
    effective_window = None
    if parsed_dates:
        effective_window = {
            "start": parsed_dates[0].isoformat(),
            "end": (parsed_dates[-1] + timedelta(days=1)).isoformat(),
        }
    return {
        "fact_types": list(dict.fromkeys(requested_types)),
        "scope_types": ["merchant", "thread"],
        "requires_temporal_validity": True,
        "effective_window": effective_window,
    }


def score_variant(memory: RetrievedMemory, now: datetime, variant: str = "type_aware",
                  requested_types: set[str] | None = None) -> float:
    age_days = max((now - memory.valid_from).total_seconds() / 86400, 0)
    recency = max(0.0, 1.0 - age_days / 90)
    confidence = memory.truth_confidence if memory.truth_confidence is not None else memory.confidence
    if variant == "semantic_only":
        return memory.semantic
    if variant == "temporal":
        return .70 * memory.semantic + .30 * recency
    if variant == "fixed_weight":
        return .55 * memory.semantic + .20 * recency + .15 * memory.importance + .10 * confidence
    if variant == "type_aware":
        type_match = 1.0 if requested_types and memory.fact_type in requested_types else 0.0
        return (.47 * memory.semantic + .18 * recency + .12 * memory.importance
                + .10 * confidence + .08 * memory.utility_score + .05 * type_match)
    raise ValueError(f"unknown retrieval variant: {variant}")


def score(memory: RetrievedMemory, now: datetime) -> float:
    return score_variant(memory, now)


def rank_ablation(memories: list[RetrievedMemory], now: datetime, *, variant: str,
                  requested_types: set[str] | None = None) -> list[RetrievedMemory]:
    eligible = [item for item in memories if item.status == "active" and item.valid_to is None]
    return sorted(eligible, key=lambda item: score_variant(item, now, variant, requested_types), reverse=True)


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
                     "kind": memory.kind, "subject": memory.subject,
                     "predicate": memory.predicate, "fact_type": memory.fact_type,
                     "scope_type": memory.scope_type, "scope_id": memory.scope_id,
                     "effective_from": memory.effective_from.isoformat() if memory.effective_from else None,
                     "effective_to": memory.effective_to.isoformat() if memory.effective_to else None,
                     "content": content})
    return rows
