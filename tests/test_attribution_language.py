"""Natural-language direction must dispatch the supported deterministic tool."""
from __future__ import annotations

from importlib import import_module

import pytest

attribution_module = import_module("app.agent.nodes.attribution")


@pytest.mark.parametrize("query", [
    "这一天GMV异常下滑，分析原因",
    "2026-04-02销售下滑是什么原因",
    "这一天成交额下滑，请归因",
    "营业额下滑怎么回事",
])
def test_explicit_gmv_decline_dispatches_attribution_tool(query, monkeypatch):
    calls = []
    tool_result = {"task": "attribution", "headline": "SQL attribution",
                   "data": {"anomaly_type": "gmv", "sql_verified": True}, "evidence": ["sql:controlled"]}
    def call_tool(name, **arguments):
        calls.append((name, arguments))
        return tool_result
    monkeypatch.setattr(attribution_module, "call_tool", call_tool)
    result = attribution_module.attribution({"user_query": query,
        "time_window": {"start": "2026-04-02", "end": "2026-04-02"}})
    assert calls == [("attribute_anomaly", {"anomaly_type": "gmv_drop", "anomaly_date": "2026-04-02"})]
    assert result["node_result"] == tool_result


@pytest.mark.parametrize("query", ["这一天GMV异常，分析原因", "UV下滑，分析原因", "客单价下滑，分析原因"])
def test_unsupported_or_unspecified_direction_keeps_honest_fallback(query, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unknown anomaly must not call an unrelated tool")
    monkeypatch.setattr(attribution_module, "call_tool", forbidden)
    result = attribution_module.attribution({"user_query": query,
        "time_window": {"start": "2026-04-02", "end": "2026-04-02"}})
    assert result["node_result"]["data"]["anomaly_type"] == "unknown"
    assert "未识别" in result["node_result"]["headline"]
