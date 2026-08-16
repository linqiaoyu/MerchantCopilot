from evals.render_v2_memory_bad_cases import render


def test_bad_case_report_keeps_all_differential_failures(monkeypatch):
    monkeypatch.setattr("evals.analyze_v2_ablation._case_ids", lambda: {"c1"})
    matrix = {"dataset_version": "eval-dataset-v2.0-rc1", "runs": {}}
    result = {"category": "temporal_conflict", "expected_ids": ["new"], "recalled_ids": ["old", "new"],
              "forbidden_recalled": ["old"], "provenance_ok": True}
    names = ("full", "minus_memory", "minus_rag", "bare", "raw_history", "no_temporal_policy")
    for name in names:
        matrix["runs"][name] = [{"case_id": "c1", "passed": name in {"full", "minus_rag"},
                                  "latency_ms": 1.0, "cost_usd": 0.0, "result": result}]
    report = render(matrix)
    assert "## raw_history" in report
    assert "| c1 | temporal_conflict | new | old, new | old | ok |" in report
    assert "## minus_rag" in report and "无差异失败" in report
