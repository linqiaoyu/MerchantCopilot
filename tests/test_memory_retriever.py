from datetime import datetime, timedelta, timezone

from app.memory.retriever import MIN_TOPIC_RELEVANCE, RetrievedMemory, assemble_context, select


NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _memory(i, kind="core", **kwargs):
    return RetrievedMemory(f"m{i}", f"e{i}", kind, kwargs.pop("content", f"memory-{i}"),
                           kwargs.pop("semantic", .8), kwargs.pop("importance", .5),
                           kwargs.pop("confidence", .9), kwargs.pop("valid_from", NOW - timedelta(days=i)), **kwargs)


def test_filters_stale_and_enforces_core_budget_with_provenance():
    memories = [_memory(i, content="x" * 150) for i in range(10)]
    memories.append(_memory(99, valid_to=NOW))
    context = assemble_context(memories, NOW)
    assert len(context) <= 6  # 800 chars admits five 150-char items
    assert sum(len(row["content"]) for row in context) <= 800
    assert all({"memory_id", "source_event_id"} <= row.keys() for row in context)


def test_fixed_budgets_for_episodic_and_decision():
    memories = [_memory(i, "episodic") for i in range(20)] + [_memory(100 + i, "decision") for i in range(8)]
    assert len(select(memories, "episodic", NOW)) == 5
    assert len(select(memories, "decision", NOW)) == 3


def test_topic_relevance_gate_blocks_low_semantic_memory_before_recency_sorting():
    unrelated = _memory(1, "episodic", semantic=MIN_TOPIC_RELEVANCE - .01,
                        importance=1.0, confidence=1.0, valid_from=NOW)
    relevant = _memory(2, "episodic", semantic=MIN_TOPIC_RELEVANCE,
                       importance=.1, confidence=.1)
    assert [memory.memory_id for memory in select([unrelated, relevant], "episodic", NOW)] == ["m2"]
