import pytest

from evals.render_v2_component_binary_judge_bad_cases import render
from evals.run_v2_component_ablation import CONFIGURATIONS


def _payload():
    sample = {"dimensions": {"factual_accuracy": {"score": 0, "reason": "wrong"}}}
    rows = {f"q_{i:03d}": {"query_type": "data_query", "mode_score": int(i != 0),
                            "scores": [int(i != 0)] * 3, "samples": [sample]}
            for i in range(30)}
    return {"results": {cfg: dict(rows) for cfg in CONFIGURATIONS}}


def test_renderer_keeps_each_configuration_failure():
    text = render(_payload())
    assert text.count("### q_000") == 4
    assert "Strategy 未进入本报告" in text


def test_renderer_rejects_incomplete_matrix():
    payload = _payload()
    payload["results"]["bare"].pop("q_001")
    with pytest.raises(ValueError, match="incomplete"):
        render(payload)
