from datetime import datetime, timedelta, timezone

import pytest

from app.memory.retriever import RetrievedMemory, rank_ablation, score_variant
from evals.v3.run_memory_retrieval_ablation import run


def test_four_retrieval_variants_are_explicit_and_unknown_variant_fails():
    now = datetime.now(timezone.utc)
    memory = RetrievedMemory("m", "e", "episodic", "x", .8, .5, .9, now)
    assert {name: score_variant(memory, now, name) for name in (
        "semantic_only", "temporal", "fixed_weight", "type_aware",
    )}
    with pytest.raises(ValueError, match="unknown retrieval variant"):
        score_variant(memory, now, "learned_ranker")


def test_type_aware_ablation_uses_fact_type_without_learning_a_ranker():
    report = run()
    assert report["case_count"] == 40
    assert report["top1_accuracy"]["type_aware"] == 1.0
    assert report["top1_accuracy"]["semantic_only"] < 1.0
    assert report["claim_eligible"] is False
