"""T03 regression: structured Metric output is rendered losslessly, not by an LLM."""
from __future__ import annotations

from app.agent.graph import build_graph


def _run_metric(monkeypatch, query: str) -> dict:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("QWEN_API_KEY", "")
    return build_graph().invoke({"user_query": query})


def test_q025_group_values_are_all_surface(monkeypatch):
    state = _run_metric(monkeypatch, "2026-05-15 当天按 traffic_source 分组的访客数和订单数分别是多少?")
    data = state["node_result"]["data"]
    answer = state["final_answer"]

    assert state["steps"][-1]["method"] == "deterministic"
    assert len(data["groups"]) == 4
    for group in data["groups"]:
        for value in group.values():
            assert str(value) in answer


def test_q068_declares_partial_month_and_preserves_period_values(monkeypatch):
    state = _run_metric(
        monkeypatch, "2026-02 月(从 02-17 开始,共 12 天)和 2026-04 月(30 天)的 GMV 对比,跨度 2 个月的变化趋势是什么?"
    )
    data = state["node_result"]["data"]
    answer = state["final_answer"]

    assert "有效数据 12 天" in answer
    for period in data["periods"]:
        for value in period.values():
            if isinstance(value, dict):
                for nested in value.values():
                    assert str(nested) in answer
            else:
                assert str(value) in answer


def test_q069_surfaces_complete_three_by_three_metric_matrix(monkeypatch):
    state = _run_metric(
        monkeypatch, "把 2026-03、2026-04、2026-05 三个月份的 GMV、UV、转化率三个指标分别列出,各月趋势如何?"
    )
    periods = state["node_result"]["data"]["periods"]
    answer = state["final_answer"]

    assert len(periods) == 3
    for period in periods:
        for key in ("label", "gmv", "uv", "conversion_pct"):
            assert str(period[key]) in answer
    assert "有效数据 17 天" in answer
