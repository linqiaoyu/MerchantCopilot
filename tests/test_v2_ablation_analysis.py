import copy

import pytest

from evals.analyze_v2_ablation import CONFIGURATIONS, analyze, validate_matrix


def _payload():
    rows = [
        {"case_id": f"mem-{index:02d}", "passed": index % 2 == 0,
         "latency_ms": float(index), "cost_usd": .001}
        for index in range(60)
    ]
    # Unit-test the matrix shape independently of the frozen content identifiers.
    return {"dataset_version": "eval-dataset-v2.0-rc1", "runs": {name: copy.deepcopy(rows) for name in CONFIGURATIONS}}


def test_complete_matrix_reports_pairing_and_cost(monkeypatch):
    payload = _payload()
    monkeypatch.setattr("evals.analyze_v2_ablation._case_ids", lambda: {f"mem-{index:02d}" for index in range(60)})
    payload["runs"]["minus_memory"][0]["passed"] = False
    report = analyze(payload)
    assert report["configurations"]["full"]["n"] == 60
    assert report["configurations"]["full"]["cost_usd"] == pytest.approx(.06)
    assert report["paired_against_full"]["minus_memory"]["full_only_pass"] == 1


def test_rejects_missing_or_duplicate_frozen_cases(monkeypatch):
    payload = _payload()
    monkeypatch.setattr("evals.analyze_v2_ablation._case_ids", lambda: {f"mem-{index:02d}" for index in range(60)})
    payload["runs"]["bare"][-1]["case_id"] = "mem-00"
    with pytest.raises(ValueError, match="exactly once"):
        validate_matrix(payload)
