from evals.run_v2_deepseek_baseline import _usage_total, load_records


def test_historical_baseline_source_is_exactly_80_unique_records():
    records = load_records()
    assert len(records) == 80
    assert records[0]["id"] == "q_001"
    assert records[-1]["id"] == "q_080"


def test_usage_totals_keep_provider_usage_auditable():
    assert _usage_total([
        {"usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}},
        {"usage": {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18}},
    ]) == {"prompt_tokens": 9, "completion_tokens": 14, "total_tokens": 23}
