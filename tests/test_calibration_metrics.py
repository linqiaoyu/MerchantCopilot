import pytest

from evals.calibration_metrics import calibration_gate, krippendorff_alpha_binary, spearman_rank_correlation
from evals.analyze_v2_calibration import analyze


def test_binary_alpha_and_strategy_gate_are_explicit():
    assert krippendorff_alpha_binary([(1, 1)] * 10 + [(0, 0)] * 10) == 1.0
    result = calibration_gate([(1, 1)] * 8 + [(0, 0)] * 2, [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
    assert result == {"binary_alpha": 1.0, "binary_mode": "eligible", "strategy_spearman": 1.0, "strategy_mode": "eligible"}


def test_failed_dimensions_are_reference_only():
    result = calibration_gate([(1, 0)] * 5 + [(0, 1)] * 5, [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)])
    assert result["binary_mode"] == "reference-only"
    assert result["strategy_mode"] == "reference-only"


def test_calibration_requires_real_paired_ratings():
    with pytest.raises(ValueError):
        krippendorff_alpha_binary([])
    with pytest.raises(ValueError):
        spearman_rank_correlation([(1.0, 1.0)])


def test_calibration_analysis_consumes_explicit_human_and_judge_pairs():
    result = analyze({
        "binary": [{"human": 1, "judge": 1}, {"human": 0, "judge": 0}],
        "strategy": [{"human": 0.0, "judge": 0.0}, {"human": 1.0, "judge": 1.0}],
    })
    assert result["binary_alpha"] == 1.0
