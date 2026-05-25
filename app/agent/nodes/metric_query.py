"""MetricQuery 节点:自然语言 → 指标。

阶段 3 起,SQL 全部下沉 MCP Server,本节点退化为「薄壳」:
识别用户聚焦哪个指标(关键词,非 SQL)→ 调 query_metric tool → 把
返回的统一契约直接放进 node_result。节点不再认识 DuckDB / SQL。
时间窗只读 Router 写入的 state["time_window"](纯正则,无 DB);
缺省时不传日期,由 Server 用 MAX(date) 兜底并在 evidence 声明。
"""
from __future__ import annotations

from langsmith import traceable

from app.agent.state import AgentState
from app.tools.client import call_tool

# 关键词 → query_metric 的 metric 枚举(只决定 headline 聚焦,不裁剪 data)。
# 枚举无 net_gmv/orders/overview → 归并到 gmv;识别不到也默认 gmv(商家最常问)。
_METRIC_KW = [
    ("aov", ["客单价", "aov", "单价"]),
    ("refund_rate", ["退款率", "退货率", "退款"]),
    ("conversion", ["转化率", "转化"]),
    ("uv", ["uv", "访客", "流量"]),
    ("gmv", ["净gmv", "净 gmv", "净销售", "gmv", "销售额", "成交额",
             "营业额", "订单", "单量", "成交笔数"]),
]


def _focus_metric(query: str) -> str:
    q = query.lower()
    for metric, kws in _METRIC_KW:
        if any(kw in q for kw in kws):
            return metric
    return "gmv"


@traceable(name="node_metric_query", tags=["agent_node"])
def metric_query(state: AgentState) -> dict:
    tw = state.get("time_window") or {}
    result = call_tool(
        "query_metric",
        metric=_focus_metric(state["user_query"]),
        start_date=tw.get("start"),
        end_date=tw.get("end"),
    )
    step = {"node": "MetricQuery", "summary": result["headline"],
            "data": result["data"]}
    return {"node_result": result, "steps": [step]}
