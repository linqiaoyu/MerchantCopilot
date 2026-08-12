import pytest

from evals.analyze_v2_deepseek_baseline import analyze


def test_baseline_analysis_rejects_partial_or_failed_runs(monkeypatch):
    monkeypatch.setattr("evals.analyze_v2_deepseek_baseline.load_records", lambda: [{"id": "q1"}, {"id": "q2"}])
    base = {"dataset": "historical-v1.0-v1.1-80", "runtime": {"model": "deepseek-v4-flash", "memory": "disabled", "memory_candidate_extraction": "disabled"}, "runs": {}}
    with pytest.raises(ValueError, match="every historical"):
        analyze(base)
    base["runs"] = {"q1": {"query_type": "metric", "error": "bad"}, "q2": {"query_type": "strategy", "error": "bad"}}
    with pytest.raises(ValueError, match="failed"):
        analyze(base)


def test_baseline_analysis_reports_usage_and_latency(monkeypatch):
    monkeypatch.setattr("evals.analyze_v2_deepseek_baseline.load_records", lambda: [{"id": "q1"}, {"id": "q2"}])
    row = lambda kind, latency: {"query_type": kind, "latency_ms": latency,
                                 "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
    report = analyze({"dataset": "historical-v1.0-v1.1-80", "runtime": {"model": "deepseek-v4-flash", "memory": "disabled", "memory_candidate_extraction": "disabled"}, "runs": {"q1": row("metric", 1), "q2": row("strategy", 9)}})
    assert report["n"] == 2
    assert report["usage"]["total_tokens"] == 6
    assert report["latency_ms"]["p95"] == 9
