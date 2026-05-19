"""MetricQuery 节点:自然语言 → 指标。

阶段 2 直连 DuckDB(工具化/MCP 留阶段 3)。不做 LLM 翻 SQL:
按关键词识别用户问的指标 + 时间窗,跑模板 SQL,统一算一个指标包。
headline/data 全部确定性产出,可被 test_graph 直接断言。
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from app.agent.state import AgentState

_DB_PATH = str(Path(__file__).resolve().parents[3] / "data" / "merchant.duckdb")
# README 口径:基线日均剔除两个植入异常日
_ANOMALY_DAYS = ("2026-04-02", "2026-04-17")

# 关键词 → 用户主要关心的指标(用于 headline 措辞;data 始终给全量包)
_METRIC_KW = [
    ("net_gmv", ["净gmv", "净 gmv", "净销售"]),
    ("gmv", ["gmv", "销售额", "成交额", "营业额"]),
    ("refund_rate", ["退款率", "退货率", "退款"]),
    ("conversion", ["转化率", "转化"]),
    ("uv", ["uv", "访客", "流量"]),
    ("orders", ["订单", "单量", "成交笔数"]),
]


def _focus_metric(query: str) -> str:
    q = query.lower()
    for metric, kws in _METRIC_KW:
        if any(kw in q for kw in kws):
            return metric
    return "overview"


def _resolve_window(state: AgentState, con) -> tuple[str, str]:
    """优先 Router 解析的 time_window;否则按「最近N天」或默认最新一天。"""
    tw = state.get("time_window") or {}
    if tw.get("start") and tw.get("end"):
        return tw["start"], tw["end"]

    max_day = con.execute("SELECT MAX(date) FROM fact_order").fetchone()[0]
    max_day = max_day.isoformat()
    m = re.search(r"(?:最近|近|过去)\s*(\d+)\s*天", state["user_query"])
    if m:
        n = int(m.group(1))
        start = con.execute(
            "SELECT (?::DATE - INTERVAL (?) DAY)::DATE", [max_day, n - 1]
        ).fetchone()[0].isoformat()
        return start, max_day
    return max_day, max_day  # 默认:最新一天


def metric_query(state: AgentState) -> dict:
    con = duckdb.connect(_DB_PATH, read_only=True)
    try:
        start, end = _resolve_window(state, con)
        row = con.execute(
            """
            WITH o AS (
              SELECT COUNT(*) AS orders,
                     SUM(gmv) AS gmv,
                     SUM(CASE WHEN NOT is_refund THEN gmv ELSE 0 END) AS net_gmv,
                     AVG(is_refund::INT) AS refund_rate
              FROM fact_order WHERE date BETWEEN ? AND ?
            ),
            v AS (
              SELECT SUM(visitors) AS uv
              FROM fact_traffic WHERE date BETWEEN ? AND ?
            )
            SELECT o.orders, o.gmv, o.net_gmv, o.refund_rate, v.uv
            FROM o, v
            """,
            [start, end, start, end],
        ).fetchone()
        orders, gmv, net_gmv, refund_rate, uv = row
        gmv = float(gmv or 0)
        net_gmv = float(net_gmv or 0)
        uv = int(uv or 0)
        conv = (orders / uv * 100) if uv else 0.0
        refund_pct = float(refund_rate or 0) * 100

        # 基线日均毛 GMV(剔除两个异常日),给单日查询一个对比锚
        base = con.execute(
            """
            SELECT AVG(g) FROM (
              SELECT date, SUM(gmv) AS g FROM fact_order
              WHERE date NOT IN (?, ?)
              GROUP BY date
            )
            """,
            list(_ANOMALY_DAYS),
        ).fetchone()[0]
        baseline_daily_gmv = float(base or 0)
    finally:
        con.close()

    data = {
        "window": {"start": start, "end": end},
        "orders": orders,
        "gmv": round(gmv, 2),
        "net_gmv": round(net_gmv, 2),
        "uv": uv,
        "conversion_pct": round(conv, 2),
        "refund_rate_pct": round(refund_pct, 1),
        "baseline_daily_gmv": round(baseline_daily_gmv, 2),
    }

    focus = _focus_metric(state["user_query"])
    span = start if start == end else f"{start} ~ {end}"
    if focus == "overview":
        headline = (
            f"{span}:毛GMV ¥{gmv:,.0f}、订单 {orders} 笔、UV {uv:,}、"
            f"转化率 {conv:.2f}%、退款率 {refund_pct:.1f}%"
        )
    else:
        label = {
            "gmv": f"毛GMV ¥{gmv:,.0f}",
            "net_gmv": f"净GMV ¥{net_gmv:,.0f}",
            "orders": f"订单 {orders} 笔",
            "uv": f"UV {uv:,}",
            "conversion": f"转化率 {conv:.2f}%",
            "refund_rate": f"退款率 {refund_pct:.1f}%",
        }[focus]
        headline = f"{span}:{label}"

    evidence = [
        f"窗口 {span} 共 {orders} 笔订单,毛GMV ¥{gmv:,.2f},净GMV ¥{net_gmv:,.2f}",
        f"UV {uv:,},转化率 {conv:.2f}%,退款率 {refund_pct:.1f}%",
        f"对比:基线日均毛GMV ¥{baseline_daily_gmv:,.0f}(剔除已知异常日)",
    ]

    result = {"task": "metric", "headline": headline, "data": data, "evidence": evidence}
    step = {"node": "MetricQuery", "summary": headline, "data": data}
    return {"node_result": result, "steps": [step]}
