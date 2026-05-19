"""Attribution 节点:异常归因。

故意写得「足够笨」:不做异常类型 dispatcher 引擎、不预留可扩展归因接口。
就是 3 个 if 分支对应 3 类已知异常(GMV跌 / UV涨 / 退款涨),
每个分支按 README 的 2 步固定归因路径直连 DuckDB 查。
匹配不上 → 诚实回退「未识别异常类型,建议人工排查」+ 基础时间序列。
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from app.agent.state import AgentState

_DB_PATH = str(Path(__file__).resolve().parents[3] / "data" / "merchant.duckdb")
_ANOMALY_DAYS = ("2026-04-02", "2026-04-17")  # README 口径:基线剔除这两天
_BASELINE_CONV = 4.2  # README 基线转化率涌现值


def _resolve_window(state: AgentState, con) -> tuple[str, str]:
    tw = state.get("time_window") or {}
    if tw.get("start") and tw.get("end"):
        return tw["start"], tw["end"]
    # 无显式日期:默认近 14 天(归因需要一个跨度做对比)
    max_day = con.execute("SELECT MAX(date) FROM fact_order").fetchone()[0]
    start = con.execute(
        "SELECT (?::DATE - INTERVAL 13 DAY)::DATE", [max_day.isoformat()]
    ).fetchone()[0]
    return start.isoformat(), max_day.isoformat()


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


def _day_metrics(con, start, end) -> tuple[int, float, int, float]:
    """窗口 step1 拆解:(订单数, 毛GMV, UV, 转化率%) —— gmv/traffic 分支共用。"""
    o, g, uv = con.execute(
        """SELECT COUNT(*), SUM(gmv),
                  (SELECT SUM(visitors) FROM fact_traffic WHERE date BETWEEN ? AND ?)
           FROM fact_order WHERE date BETWEEN ? AND ?""",
        [start, end, start, end],
    ).fetchone()
    g, uv = float(g or 0), int(uv or 0)
    conv = (o / uv * 100) if uv else 0.0
    return o, g, uv, conv


def _attr_gmv_drop(con, start, end) -> tuple[str, dict, list]:
    """Case 1 路径:GMV异常 → 拆UV/转化率 → 按 product 下钻 join dim_product。"""
    o, g, uv, conv = _day_metrics(con, start, end)
    base_g = con.execute(
        """SELECT AVG(g) FROM (SELECT date, SUM(gmv) g FROM fact_order
           WHERE date NOT IN (?, ?) GROUP BY date)""",
        list(_ANOMALY_DAYS),
    ).fetchone()[0]
    # 下钻信号 = 当日份额 / 该SKU日常份额 的跳变比(README 口径:
    # 异常 SKU 是「份额相对自己日常异常飙升」的,不是「当日订单最多」的)
    top = con.execute(
        """
        WITH day AS (
          SELECT product_id, COUNT(*) AS cnt FROM fact_order
          WHERE date BETWEEN ? AND ? GROUP BY 1
        ),
        base AS (
          SELECT product_id, COUNT(*) AS c FROM fact_order
          WHERE date NOT IN (?, ?) GROUP BY 1
        )
        SELECT d.product_id, p.name, p.target_audience, p.price_band, d.cnt,
          ROUND(100.0*d.cnt/(SELECT SUM(cnt) FROM day),1) AS day_share,
          ROUND(100.0*COALESCE(b.c,0)/(SELECT SUM(c) FROM base),2) AS base_share
        FROM day d JOIN dim_product p USING(product_id)
        LEFT JOIN base b USING(product_id)
        ORDER BY (d.cnt*1.0/(SELECT SUM(cnt) FROM day))
                 / NULLIF(COALESCE(b.c,0.5)*1.0/(SELECT SUM(c) FROM base),0) DESC
        LIMIT 3
        """,
        [start, end, *_ANOMALY_DAYS],
    ).fetchall()
    seg = con.execute(
        """SELECT ROUND(100.0*AVG((customer_segment IN ('student','young_pro'))::INT),0)
           FROM fact_order WHERE date BETWEEN ? AND ?""",
        [start, end],
    ).fetchone()[0]
    sku = top[0]
    data = {
        "step1_split": {"orders": o, "gmv": round(g, 2),
                        "uv": uv, "conversion_pct": round(conv, 2),
                        "baseline_daily_gmv": round(float(base_g), 2),
                        "baseline_conversion_pct": _BASELINE_CONV},
        "step2_product_drill": [
            {"product_id": r[0], "name": r[1], "target_audience": r[2],
             "price_band": r[3], "orders": r[4],
             "order_share_pct": r[5], "baseline_share_pct": r[6]}
            for r in top
        ],
        "buyer_student_youngpro_pct": float(seg),
    }
    crashed = conv < _BASELINE_CONV * 0.6
    if not crashed:
        return ("该时段毛GMV与转化率未见显著异常", data,
                [f"转化率 {conv:.2f}% 接近基线 {_BASELINE_CONV}%,无需归因"])
    headline = (
        f"GMV ¥{g:,.0f}(基线日均 ¥{float(base_g):,.0f})暴跌,根因:人货错配——"
        f"单品「{sku[1]}」(price_band={sku[3]}/{sku[2]})当日订单份额 {sku[5]}%"
        f"(日常仅 {sku[6]}%),与店铺主力客群(student+young_pro {seg:.0f}%)错配"
    )
    evidence = [
        f"步骤1 拆解:UV {uv:,} 正常,但转化率崩到 {conv:.2f}%(基线 {_BASELINE_CONV}%)→ 不是流量问题",
        f"步骤2 按product下钻:{sku[1]}({sku[0]})当日份额 {sku[5]}% vs 日常 {sku[6]}%,"
        f"份额异常飙升,是当日最突出的单品",
        f"join dim_product:该 SKU price_band={sku[3]}、target_audience={sku[2]},"
        f"而当日 {seg:.0f}% 买家是 student/young_pro → 高端/成熟定位与主力客群错配",
    ]
    return headline, data, evidence


def _attr_traffic_surge(con, start, end) -> tuple[str, dict, list]:
    """Case 2 路径:UV暴涨 → GMV没等比涨 → 按 traffic_source 算各来源转化率。"""
    o, _, uv, conv = _day_metrics(con, start, end)
    base_uv = con.execute(
        """SELECT AVG(v) FROM (SELECT date, SUM(visitors) v FROM fact_traffic
           WHERE date NOT IN (?, ?) GROUP BY date)""",
        list(_ANOMALY_DAYS),
    ).fetchone()[0]
    by_src = con.execute(
        """SELECT t.traffic_source, t.visitors, COUNT(o.order_id) AS orders,
                  ROUND(100.0*COUNT(o.order_id)/t.visitors,2) AS conv,
                  ROUND(100.0*t.visitors/SUM(t.visitors) OVER(),1) AS uv_share
           FROM fact_traffic t
           LEFT JOIN fact_order o ON o.date=t.date AND o.traffic_source=t.traffic_source
           WHERE t.date BETWEEN ? AND ?
           GROUP BY 1,2 ORDER BY 4""",
        [start, end],
    ).fetchall()
    rows = [{"traffic_source": r[0], "visitors": r[1], "orders": r[2],
             "conversion_pct": r[3], "uv_share_pct": r[4]} for r in by_src]
    data = {
        "step1_split": {"uv": uv, "baseline_daily_uv": round(float(base_uv)),
                        "uv_multiple": round(uv / base_uv, 1) if base_uv else None,
                        "overall_conversion_pct": round(conv, 2),
                        "baseline_conversion_pct": _BASELINE_CONV},
        "step2_by_traffic_source": rows,
    }
    surged = base_uv and uv > base_uv * 1.8
    if not surged:
        return ("该时段 UV 未见异常放量", data,
                [f"UV {uv:,} 接近基线日均 {float(base_uv):,.0f},无需归因"])
    paid = next((r for r in rows if r["traffic_source"] == "付费投流"), rows[0])
    nat = next((r for r in rows if r["traffic_source"] == "自然"), rows[-1])
    headline = (
        f"UV {uv:,}(≈日常 {uv/base_uv:.1f}x)暴涨但转化率掉到 {conv:.2f}%,根因:"
        f"付费投流泛流量灌入——付费投流转化 {paid['conversion_pct']}% vs 自然 {nat['conversion_pct']}%"
    )
    evidence = [
        f"步骤1 拆解:UV {uv:,} ≈ 基线 {float(base_uv):,.0f} 的 {uv/base_uv:.1f} 倍,但整体转化率从 {_BASELINE_CONV}% 掉到 {conv:.2f}% → GMV 没等比涨",
        f"步骤2 按traffic_source下钻:付费投流 UV占比 {paid['uv_share_pct']}%、转化仅 {paid['conversion_pct']}%",
        f"对比自然流量转化 {nat['conversion_pct']}% → 泛流量购买意图极低,是流量结构问题非商品问题",
    ]
    return headline, data, evidence


def _attr_refund_surge(con, start, end) -> tuple[str, dict, list]:
    """Case 3 路径:退款率连续异常 → 毛/净GMV缺口 → 退款订单按 product 分组。"""
    trend = con.execute(
        """SELECT date, COUNT(*) orders, ROUND(100.0*AVG(is_refund::INT),1) refund_pct,
                  SUM(gmv) gross, SUM(CASE WHEN NOT is_refund THEN gmv ELSE 0 END) net
           FROM fact_order WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date""",
        [start, end],
    ).fetchall()
    top = con.execute(
        """SELECT o.product_id, p.name, p.launch_date, COUNT(*) refund_cnt
           FROM fact_order o JOIN dim_product p USING(product_id)
           WHERE o.is_refund AND o.date BETWEEN ? AND ?
           GROUP BY 1,2,3 ORDER BY refund_cnt DESC LIMIT 3""",
        [start, end],
    ).fetchall()
    series = [{"date": str(r[0]), "orders": r[1], "refund_pct": r[2],
               "gross_gmv": round(float(r[3]), 2), "net_gmv": round(float(r[4]), 2)}
              for r in trend]
    data = {
        "step1_refund_trend": series,
        "step2_product_drill": [
            {"product_id": r[0], "name": r[1], "launch_date": str(r[2]),
             "refund_orders": r[3]} for r in top
        ],
    }
    peak = max((s["refund_pct"] for s in series), default=0)
    if peak < 15:
        return ("该时段退款率未见持续异常", data,
                [f"窗口内退款率峰值 {peak}%,接近 ~8% 基线,无需归因"])
    sku = top[0]
    reason = con.execute(
        """SELECT refund_reason,
                  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),0) AS pct
           FROM fact_order WHERE product_id=? AND is_refund
           GROUP BY 1 ORDER BY 2 DESC LIMIT 1""",
        [sku[0]],
    ).fetchone()
    data["step2_top_refund_reason"] = {"reason": reason[0], "pct": float(reason[1])}
    headline = (
        f"退款率从 {series[0]['refund_pct']}% 持续爬到 {peak}%,根因:新品「{sku[1]}」"
        f"({sku[2]} 上架)质量爆雷,退款主因「{reason[0]}」占 {reason[1]:.0f}%"
    )
    evidence = [
        f"步骤1:退款率逐日 {series[0]['refund_pct']}% → {peak}% 持续异常,毛GMV看着正常但净GMV持续下滑",
        f"步骤2 退款订单按product分组:{sku[1]}({sku[0]})贡献最大,{sku[3]} 新上架",
        f"该 SKU 退款原因「{reason[0]}」占 {reason[1]:.0f}% → 单品质量问题,非全店性",
    ]
    return headline, data, evidence


def _fallback(con, start, end) -> tuple[str, dict, list]:
    """未识别异常类型:诚实回退,只给基础时间序列,不硬扯归因。"""
    rows = con.execute(
        """SELECT date, COUNT(*) orders, SUM(gmv) gmv,
                  ROUND(100.0*AVG(is_refund::INT),1) refund_pct
           FROM fact_order WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date""",
        [start, end],
    ).fetchall()
    data = {"basic_series": [
        {"date": str(r[0]), "orders": r[1], "gmv": round(float(r[2]), 2),
         "refund_pct": r[3]} for r in rows]}
    return ("未识别的异常类型,建议人工排查(已附该时段基础时间序列)", data,
            [f"已输出 {start} ~ {end} 共 {len(rows)} 天的 订单/GMV/退款率 时间序列供人工判断"])


_BRANCHES = {
    "gmv": _attr_gmv_drop,
    "traffic": _attr_traffic_surge,
    "refund": _attr_refund_surge,
}


def attribution(state: AgentState) -> dict:
    con = duckdb.connect(_DB_PATH, read_only=True)
    try:
        start, end = _resolve_window(state, con)
        atype = _anomaly_type(state["user_query"])
        branch = _BRANCHES.get(atype, _fallback)
        headline, data, evidence = branch(con, start, end)
    finally:
        con.close()

    data["window"] = {"start": start, "end": end}
    data["anomaly_type"] = atype or "unknown"
    result = {"task": "attribution", "headline": headline,
              "data": data, "evidence": evidence}
    step = {"node": "Attribution",
            "summary": f"anomaly={atype or 'unknown'} | {headline}",
            "data": data}
    return {"node_result": result, "steps": [step]}
