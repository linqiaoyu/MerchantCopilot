"""MetricQuery 节点:自然语言 → 指标。

阶段 3 起,SQL 全部下沉 MCP Server,本节点退化为「薄壳」:
识别用户聚焦哪个指标(关键词,非 SQL)→ 调 query_metric tool → 把
返回的统一契约直接放进 node_result。节点不再认识 DuckDB / SQL。
时间窗只读 Router 写入的 state["time_window"](纯正则,无 DB);
缺省时不传日期,由 Server 用 MAX(date) 兜底并在 evidence 声明。

task #26 additive 扩展(6.4):识别 group-by 维度 → 传 query_metric 的可选 group_by;
识别多段时间窗(月度对比/上下半月/多月)→ 节点内 per-segment 多次调 query_metric 组装 periods。
两者都识别不到 → 完全走原单次调用路径(向后兼容,simple query 行为字节级不变)。
多段解析放节点(不动 Router _parse_time_window,后者是所有 intent 公共入口,blast radius 大)。
"""
from __future__ import annotations

import calendar
import re

from langsmith import traceable

from app.agent.state import AgentState
from app.tools.client import call_tool

# 关键词 → 聚焦指标(决定 headline 措辞,不裁剪 data)。orders 单列(task #26:
# "订单数" 此前误并入 gmv,导致跨期"总订单数"query headline 讲成 GMV)。
_METRIC_KW = [
    ("aov", ["客单价", "aov", "单价"]),
    ("refund_rate", ["退款率", "退货率", "退款"]),
    ("conversion", ["转化率", "转化"]),
    ("uv", ["uv", "访客", "流量"]),
    ("orders", ["订单数", "订单量", "单量", "成交笔数", "多少单", "几单", "订单"]),
    ("gmv", ["净gmv", "净 gmv", "净销售", "gmv", "销售额", "成交额", "营业额"]),
]

# 聚焦指标 → data 字段 / 中文名(headline lead 用)
_FOCUS_FIELD = {"orders": "orders", "gmv": "gmv", "uv": "uv",
                "conversion": "conversion_pct", "refund_rate": "refund_rate_pct", "aov": "aov"}
_FOCUS_NAME = {"orders": "订单数", "gmv": "毛GMV", "uv": "UV",
               "conversion": "转化率", "refund_rate": "退款率", "aov": "客单价"}
_ENUM_METRICS = {"gmv", "uv", "conversion", "refund_rate", "aov"}


def _focus_metric(query: str) -> str:
    q = query.lower()
    for metric, kws in _METRIC_KW:
        if any(kw in q for kw in kws):
            return metric
    return "gmv"


def _enum_metric(focus: str) -> str:
    """query_metric 工具的 metric 枚举无 orders;orders 映射到 gmv 调用(data 始终含
    orders,focus 仅决定 headline)。其余 focus 即合法枚举。"""
    return focus if focus in _ENUM_METRICS else "gmv"


# ---- task #26:group-by 维度识别(规则,shadow 验证零误触发 simple query)----
def _parse_group_by(query: str) -> list[str]:
    dims: list[str] = []
    if re.search(r"主播|小张和小李|小张.*小李|各自", query):
        dims.append("streamer")
    if re.search(r"子品类|品类", query):
        dims.append("sub_category")
    if re.search(r"traffic_source|流量来源|渠道|来源", query):
        dims.append("traffic_source")
    if re.search(r"价位段|价位|价格段", query):
        dims.append("price_band")
    if re.search(r"时段|早中晚|早\s*6|早.{0,3}中.{0,3}晚", query):
        dims.append("hour_bucket")
    return dims


# ---- task #26:多段时间窗识别(月级 token 排除完整日期,避免误触发单窗 query)----
# 2026-MM 后跟 月/、/和/非(-数字),排除 2026-MM-DD 完整日期(simple data_query 不误触发)
_MONTH_TOK = re.compile(r"2026-(\d{2})(?=\s*月|、|和|[^-\d]|$)")


def _month_range(month: int) -> tuple[str, str]:
    last = calendar.monthrange(2026, month)[1]
    return f"2026-{month:02d}-01", f"2026-{month:02d}-{last:02d}"


def _parse_periods(query: str) -> list[dict]:
    """返回 [{label,start,end}, ...];非多段返回 []。SQL WHERE 自然 clamp 到数据覆盖
    (02 月只 17~28、05 月只 01~17 → 日历范围输入,工具自动只算有数据的天)。"""
    months = [int(m) for m in _MONTH_TOK.findall(query)]
    if re.search(r"上半月.*下半月", query) and months:
        m = months[0]
        _, end = _month_range(m)
        return [
            {"label": f"2026-{m:02d} 上半月", "start": f"2026-{m:02d}-01", "end": f"2026-{m:02d}-15"},
            {"label": f"2026-{m:02d} 下半月", "start": f"2026-{m:02d}-16", "end": end},
        ]
    if len(months) >= 2:
        segs = []
        for m in months:
            s, e = _month_range(m)
            segs.append({"label": f"2026-{m:02d}", "start": s, "end": e})
        return segs
    return []


@traceable(name="node_metric_query", tags=["agent_node"])
def metric_query(state: AgentState) -> dict:
    query = state["user_query"]
    periods = _parse_periods(query)

    # --- 多段时间窗:节点内 per-segment 多次调 query_metric,组装 periods(additive)---
    if periods:
        focus = _focus_metric(query)
        field = _FOCUS_FIELD[focus]
        seg_results = []
        for seg in periods:
            d = call_tool("query_metric", metric=_enum_metric(focus),
                          start_date=seg["start"], end_date=seg["end"])["data"]
            seg_results.append({
                "label": seg["label"], "window": {"start": seg["start"], "end": seg["end"]},
                "orders": d["orders"], "gmv": d["gmv"], "uv": d["uv"],
                "conversion_pct": d["conversion_pct"], "refund_rate_pct": d["refund_rate_pct"],
                "aov": d["aov"], "days": d["days"],
                "gmv_per_day": round(d["gmv"] / d["days"], 2) if d["days"] else 0.0,
            })
        # headline 显式 lead 焦点指标值(否则 Insight 易编辑成叙事丢掉 query 问的指标)。
        # gmv 是体量指标:不等长周期比原始 GMV 会误导(2月12天 vs 4月30天)→ 用日均归一;
        # label 带天数,让 Insight 正确表达时间窗(grounding)。
        if focus == "gmv":
            lead_field, lead_name = "gmv_per_day", "日均GMV"
        else:
            lead_field, lead_name = field, _FOCUS_NAME[focus]
        headline = (f"跨期对比·{lead_name}:" + " vs ".join(
            f"{s['label']}({s['days']}天) {s[lead_field]}" for s in seg_results))
        if len(seg_results) == 2:
            headline += f"(差异 {round(seg_results[1][lead_field] - seg_results[0][lead_field], 2)})"
        data = {"periods": seg_results, "focus": focus,
                "window": {"start": periods[0]["start"], "end": periods[-1]["end"]}}
        evidence = [
            f"{s['label']}({s['days']}天):订单 {s['orders']},毛GMV ¥{s['gmv']:,.0f},"
            f"日均GMV ¥{s['gmv_per_day']:,.0f},UV {s['uv']:,},转化率 {s['conversion_pct']}%,"
            f"退款率 {s['refund_rate_pct']}%"
            for s in seg_results
        ]
        result = {"task": "metric", "headline": headline, "data": data, "evidence": evidence}
        step = {"node": "MetricQuery", "summary": headline, "data": {"periods": len(seg_results)}}
        return {"node_result": result, "steps": [step]}

    # --- group-by / 单窗:识别不到 group_by 则 None → call_tool 滤掉 → 原行为不变 ---
    tw = state.get("time_window") or {}
    group_by = _parse_group_by(query)
    result = call_tool(
        "query_metric",
        metric=_enum_metric(_focus_metric(query)),
        start_date=tw.get("start"),
        end_date=tw.get("end"),
        group_by=group_by or None,
    )
    step = {"node": "MetricQuery", "summary": result["headline"],
            "data": result["data"]}
    return {"node_result": result, "steps": [step]}
