import pytest

from evals.analyze_v2_component_binary_judge import _mcnemar_exact, analyze
from evals.run_v2_component_ablation import CONFIGURATIONS


def _payload():
    results = {}
    for cfg in CONFIGURATIONS:
        rows = {}
        for i in range(30):
            qid = f"q_{i:03d}"
            rows[qid] = {"query_type": ("data_query", "cross_period", "attribution")[i % 3], "mode_score": i % 2}
        results[cfg] = rows
    return {"runtime": {"configurations": list(CONFIGURATIONS)}, "results": results}


def test_binary_judge_analysis_requires_complete_four_arms():
    report = analyze(_payload())
    assert report["configurations"]["full"]["n"] == 30
    assert report["paired_against_full"]["bare"]["mcnemar_exact_two_sided_p"] == 1.0


def test_binary_judge_analysis_rejects_error():
    payload = _payload()
    payload["results"]["bare"]["q_000"] = {"error": "timeout"}
    with pytest.raises(ValueError, match="incomplete"):
        analyze(payload)


def test_mcnemar_exact_is_two_sided():
    assert _mcnemar_exact(3, 0) == 0.25
