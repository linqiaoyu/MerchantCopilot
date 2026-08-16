from evals.analyze_ablation import anchoring_pairs, mcnemar


def test_anchoring_pairs_uses_explicit_frozen_criterion_and_skips_metadata():
    payload = {
        "_metadata": {"version": "legacy"},
        "q_001": {"mem0_exclusive_85": {"full": 1, "minus_mem0": 0}},
        "q_002": {"broad": {"full": 1, "minus_mem0": 1}},
    }
    assert anchoring_pairs(payload) == [(1, 0)]
    assert mcnemar(anchoring_pairs(payload))["b"] == 1
