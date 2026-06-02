"""MerchantCopilot MCP Server(stdio,单 Server 暴露 2 个 tool)。

阶段 3 灵魂:metric_query / attribution 两个节点原本直连 DuckDB 的 SQL
**全部搬到这里**,节点退化为「调 tool 的薄壳」。SQL 与编排解耦 ——
这是 MCP 协议在本演示项目里的核心价值。

独立启动(stdio 会阻塞等 stdin,属正常,Ctrl+C 退出):
    python -m app.tools.server

无 stub 模式:Server 是本地子进程、零外部依赖,起来即可跑;
若 DuckDB 文件缺失等,直接抛错,由 Client 上抛(fail-fast,绝不编数字)。
"""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import duckdb
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from app.tools import schemas

_DB_PATH = str(Path(__file__).resolve().parents[2] / "data" / "merchant.duckdb")
_ANOMALY_DAYS = ("2026-04-02", "2026-04-17")  # README 口径:基线剔除这两天
_BASELINE_CONV = 4.2  # README 基线转化率涌现值


# ───────────────────────── 公共:默认窗口 ─────────────────────────

def _max_day(con) -> str:
    return con.execute("SELECT MAX(date) FROM fact_order").fetchone()[0].isoformat()


def _shift(con, day: str, days: int) -> str:
    """day 向前回溯 days 天(用 DuckDB 算,Server 内部不手撸日期)。"""
    return con.execute(
        "SELECT (?::DATE - INTERVAL (?) DAY)::DATE", [day, days]
    ).fetchone()[0].isoformat()


# ───────────────────────── tool 1: query_metric ─────────────────────────

# group_by 维度 → SQL 表达式(task #26 additive 扩展;不传 group_by 时此路径不触发)
_GROUP_EXPR = {
    "streamer": "o.streamer",
    "traffic_source": "o.traffic_source",
    "sub_category": "p.sub_category",
    "price_band": "p.price_band",
    "hour_bucket": (
        "CASE WHEN EXTRACT(hour FROM o.order_time) >= 6 AND EXTRACT(hour FROM o.order_time) < 12 THEN '早(6-12)' "
        "WHEN EXTRACT(hour FROM o.order_time) >= 12 AND EXTRACT(hour FROM o.order_time) < 18 THEN '中(12-18)' "
        "WHEN EXTRACT(hour FROM o.order_time) >= 18 THEN '晚(18-24)' ELSE '凌晨(0-6)' END"
    ),
}
_GROUP_NEEDS_JOIN = {"sub_category", "price_band"}


def _query_metric_grouped(con, start: str, end: str, group_by: list[str]) -> list[dict]:
    """按用户维度分组返回每组指标包(orders/gmv/aov/refund_rate_pct;
    traffic_source 单维额外补 uv/转化率)。additive:仅 group_by 传入时调用。"""
    dims = [d for d in group_by if d in _GROUP_EXPR]
    if not dims:
        return []
    sel = ", ".join(f"{_GROUP_EXPR[d]} AS g{i}" for i, d in enumerate(dims))
    pos = ", ".join(str(i + 1) for i in range(len(dims)))
    join = ("JOIN dim_product p ON o.product_id = p.product_id"
            if any(d in _GROUP_NEEDS_JOIN for d in dims) else "")
    rows = con.execute(
        f"""SELECT {sel}, COUNT(*) AS orders, SUM(o.gmv) AS gmv,
                   AVG(o.is_refund::INT) AS refund_rate
            FROM fact_order o {join}
            WHERE o.date BETWEEN ? AND ?
            GROUP BY {pos} ORDER BY {pos}""",
        [start, end],
    ).fetchall()
    n = len(dims)
    groups = []
    for r in rows:
        g = {dims[i]: r[i] for i in range(n)}
        orders = r[n]
        gmv = float(r[n + 1] or 0)
        rr = float(r[n + 2] or 0)
        g.update(orders=orders, gmv=round(gmv, 2),
                 aov=round(gmv / orders, 2) if orders else 0.0,
                 refund_rate_pct=round(rr * 100, 1))
        groups.append(g)
    if dims == ["traffic_source"]:  # 访客数/转化率只对流量来源维有意义,补 fact_traffic
        vis = dict(con.execute(
            "SELECT traffic_source, SUM(visitors) FROM fact_traffic "
            "WHERE date BETWEEN ? AND ? GROUP BY 1", [start, end]).fetchall())
        for g in groups:
            g["uv"] = int(vis.get(g["traffic_source"], 0) or 0)
            g["conversion_pct"] = round(g["orders"] / g["uv"] * 100, 2) if g["uv"] else 0.0
    if dims == ["hour_bucket"]:  # 补空桶:mock 数据无 morning 订单 → 早场=0 是正确结果非漏数据
        order = {"早(6-12)": 0, "中(12-18)": 1, "晚(18-24)": 2}
        present = {g["hour_bucket"] for g in groups}
        for b in order:
            if b not in present:
                groups.append({"hour_bucket": b, "orders": 0, "gmv": 0.0,
                               "aov": 0.0, "refund_rate_pct": 0.0})
        groups.sort(key=lambda g: order.get(g["hour_bucket"], 99))
    return groups


def _query_metric(metric: str, start: str | None, end: str | None,
                  group_by: list[str] | None = None) -> dict:
    con = duckdb.connect(_DB_PATH, read_only=True)
    try:
        defaulted = not (start and end)
        if defaulted:
            start = end = _max_day(con)

        row = con.execute(
            """
            WITH o AS (
              SELECT COUNT(*) AS orders,
                     SUM(gmv) AS gmv,
                     SUM(CASE WHEN NOT is_refund THEN gmv ELSE 0 END) AS net_gmv,
                     AVG(is_refund::INT) AS refund_rate,
                     COUNT(DISTINCT date) AS days
              FROM fact_order WHERE date BETWEEN ? AND ?
            ),
            v AS (
              SELECT SUM(visitors) AS uv
              FROM fact_traffic WHERE date BETWEEN ? AND ?
            )
            SELECT o.orders, o.gmv, o.net_gmv, o.refund_rate, o.days, v.uv
            FROM o, v
            """,
            [start, end, start, end],
        ).fetchone()
        orders, gmv, net_gmv, refund_rate, days, uv = row
        gmv = float(gmv or 0)
        net_gmv = float(net_gmv or 0)
        uv = int(uv or 0)
        days = int(days or 0)
        conv = (orders / uv * 100) if uv else 0.0
        refund_pct = float(refund_rate or 0) * 100
        aov = (gmv / orders) if orders else 0.0

        # 基线日均毛 GMV(剔除两个植入异常日),给单日查询一个对比锚
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

        # group_by 传入时分组(con 关闭前算好);默认 None → groups 不进 data
        groups = _query_metric_grouped(con, start, end, group_by) if group_by else None
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
        "aov": round(aov, 2),
        "days": days,
        "baseline_daily_gmv": round(baseline_daily_gmv, 2),
    }

    span = start if start == end else f"{start} ~ {end}"
    label = {
        "gmv": f"毛GMV ¥{gmv:,.0f}",
        "uv": f"UV {uv:,}",
        "conversion": f"转化率 {conv:.2f}%",
        "refund_rate": f"退款率 {refund_pct:.1f}%",
        "aov": f"客单价 ¥{aov:,.2f}",
    }[metric]
    headline = f"{span}:{label}"

    evidence = [
        f"窗口 {span} 共 {orders} 笔订单,毛GMV ¥{gmv:,.2f},净GMV ¥{net_gmv:,.2f}",
        f"UV {uv:,},转化率 {conv:.2f}%,退款率 {refund_pct:.1f}%,客单价 ¥{aov:,.2f}",
        f"对比:基线日均毛GMV ¥{baseline_daily_gmv:,.0f}(剔除已知异常日)",
    ]
    if defaulted:
        evidence.insert(0, f"未指定日期,默认使用数据集最新日 {start}")

    # group_by:追加 groups 到 data + enrich headline/evidence(additive,不改 flat 字段)
    if groups is not None:
        data["groups"] = groups
        dim_label = "×".join(group_by)
        headline = f"{span}:按 {dim_label} 分组({len(groups)} 组)"
        evidence.append(
            f"按 {dim_label} 分组:" + "；".join(
                f"{'/'.join(str(g[d]) for d in group_by)} "
                f"orders={g['orders']} gmv={g['gmv']} aov={g['aov']} 退款率={g['refund_rate_pct']}%"
                + (f" uv={g['uv']} 转化率={g['conversion_pct']}%" if 'uv' in g else "")
                for g in groups))

    return {"task": "metric", "headline": headline, "data": data, "evidence": evidence}


# ──────────────── tool 2: attribute_anomaly(SQL 自 attribution.py 逐字搬入)────────────────

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
    """Case 3 路径:退款率连续异常 → 毛/净GMV缺口 → 退款订单按 product 分组。

    单日 anomaly_date 无法体现「连续」,故调用方对本类型派生 14 天回溯窗
    (anomaly_date-13d .. anomaly_date),start/end 在此即为该窗口。
    """
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


# enum(对外清晰)→ 内部分支 + stage2 短码(短码须保持,test_graph 断言 d["anomaly_type"]=="gmv")
_BRANCHES = {
    "gmv_drop": ("gmv", _attr_gmv_drop),
    "uv_surge": ("traffic", _attr_traffic_surge),
    "refund_surge": ("refund", _attr_refund_surge),
}


def _attribute_anomaly(anomaly_type: str, anomaly_date: str | None) -> dict:
    short, branch = _BRANCHES[anomaly_type]
    con = duckdb.connect(_DB_PATH, read_only=True)
    try:
        defaulted = not anomaly_date
        if defaulted:
            anomaly_date = _max_day(con)
        # refund 是「连续异常」,单日画不出爬升 → 内部派生 14 天回溯窗
        if anomaly_type == "refund_surge":
            start, end = _shift(con, anomaly_date, 13), anomaly_date
        else:
            start = end = anomaly_date
        headline, data, evidence = branch(con, start, end)
    finally:
        con.close()

    data["window"] = {"start": start, "end": end}
    data["anomaly_type"] = short
    if defaulted:
        evidence = [f"未指定日期,默认使用数据集最新日 {anomaly_date}", *evidence]
    return {"task": "attribution", "headline": headline,
            "data": data, "evidence": evidence}


# ───────────────────────── MCP 注册 + stdio 启动 ─────────────────────────

server = Server("merchant-copilot-tools")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=schemas.QUERY_METRIC_NAME,
            description=schemas.QUERY_METRIC_DESC,
            inputSchema=schemas.QUERY_METRIC_SCHEMA,
        ),
        types.Tool(
            name=schemas.ATTRIBUTE_ANOMALY_NAME,
            description=schemas.ATTRIBUTE_ANOMALY_DESC,
            inputSchema=schemas.ATTRIBUTE_ANOMALY_SCHEMA,
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """tool 同步执行(纯 DuckDB 本地查询,无 IO 等待,不必异步化)。"""
    if name == schemas.QUERY_METRIC_NAME:
        result = _query_metric(
            arguments["metric"],
            arguments.get("start_date"),
            arguments.get("end_date"),
            arguments.get("group_by"),
        )
    elif name == schemas.ATTRIBUTE_ANOMALY_NAME:
        result = _attribute_anomaly(
            arguments["anomaly_type"],
            arguments.get("anomaly_date"),
        )
    else:
        raise ValueError(f"未知 tool: {name}")
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, default=str),
    )]


async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(_main)
