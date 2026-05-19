"""Attribution 节点:异常归因。

阶段 3 起,3 类异常的多步下钻 SQL 全部下沉 MCP Server,本节点退化为
「薄壳」:关键词识别异常类型(非 SQL,属编排职责)→ 调 attribute_anomaly
tool → 把统一契约直接放进 node_result。识别不到 → 诚实回退(不调工具、
不碰 DB,因为节点已无 DuckDB 依赖)。
"""
from __future__ import annotations

from app.agent.state import AgentState
from app.tools.client import call_tool

# 内部短码 → tool 对外枚举(短码须保持:test_graph 断言 d["anomaly_type"]=="gmv")
_TYPE_TO_ENUM = {
    "gmv": "gmv_drop",
    "traffic": "uv_surge",
    "refund": "refund_surge",
}


def _anomaly_type(query: str) -> str | None:
    q = query.lower()
    if any(k in q for k in ["退款", "退货", "色差"]):
        return "refund"
    if any(k in q for k in ["uv", "流量", "访客"]) and any(
        k in q for k in ["涨", "暴涨", "猛涨", "灌", "多"]
    ):
        return "traffic"
    if any(k in q for k in ["gmv", "销售", "成交", "营业额"]) and any(
        k in q for k in ["跌", "暴跌", "掉", "降", "少", "崩"]
    ):
        return "gmv"
    return None


def attribution(state: AgentState) -> dict:
    tw = state.get("time_window") or {}
    atype = _anomaly_type(state["user_query"])

    if atype is None:
        # 诚实回退:不硬扯归因,也不碰 DB(SQL 已全在 Server)
        result = {
            "task": "attribution",
            "headline": "未识别的异常类型,建议人工排查",
            "data": {"anomaly_type": "unknown", "window": tw},
            "evidence": ["未匹配到 GMV跌 / UV涨 / 退款涨 任一已知异常模式,"
                         "已交人工排查(节点不臆造归因结论)"],
        }
    else:
        # 单个 anomaly_date;refund 的 14 天回溯窗由 Server 内部派生
        result = call_tool(
            "attribute_anomaly",
            anomaly_type=_TYPE_TO_ENUM[atype],
            anomaly_date=tw.get("end") or tw.get("start"),
        )

    short = result["data"].get("anomaly_type", "unknown")
    step = {"node": "Attribution",
            "summary": f"anomaly={short} | {result['headline']}",
            "data": result["data"]}
    return {"node_result": result, "steps": [step]}
